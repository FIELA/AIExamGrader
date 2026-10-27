# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""
When the red scores are written and how the scans stay clean (score_marks draws them).

One worker thread draws every marked image from the sheet's scan in the original files folder. A report is saved,
and its image queued, under commit_lock; an image is published under rename_lock and commit_lock after its report,
the template and the image itself are read again, so an image is never published for scores older than the report
at that moment, nor onto a sheet renamed (two sheets may swap names) or taken out of the grades meanwhile. Work left
when the app closes is found again by scan(), which compares each image's marker with its report.

Once an exam has had marks, its graded images are never used as scans: grading, backups and recovery take the
original files only.
"""

import collections
import json
import os
import shutil
import threading
import time

import score_marks as sm
from report_files import record_image_name

TEMPLATE_FILE = 'score_marks.json'
TEMP_SUFFIX = '.aieg-marks.tmp'
RETRIES = 3
RETRY_DELAY = 0.5  # Seconds before the first retry; doubled each time


class MarksSourceError(Exception):
    """No scan can be trusted for this sheet, so it must not be sent to the model."""


def write_json_atomic(path, data):
    """A report or template is replaced whole or not at all, so that no reader ever sees half of it."""
    temp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


class _Task:
    __slots__ = ('exam', 'json_path', 'generation', 'attempts', 'not_before')

    def __init__(self, exam, json_path, generation):
        self.exam, self.json_path, self.generation = exam, json_path, generation
        self.attempts, self.not_before = 0, 0.0


class ScoreMarksService:
    def __init__(self, app):
        self.app = app
        # Inner lock (taken after write_lock or rename_lock, never before them): saving a report and queueing its
        # image, and publishing an image. Kept to file writes, which take milliseconds.
        self.commit_lock = threading.RLock()
        self._cond = threading.Condition()
        self._pending = collections.OrderedDict()  # Report path -> task; one per report
        self._jobs = collections.deque()  # Whole-exam work run in the worker: scans and restores
        self._generation = {}  # Exam folder -> counter; pausing, restoring and template changes void queued work
        self._status = {}  # Report path -> (status, message) of its last attempt
        self._logged = set()
        self._listeners = []
        self._fonts = {}
        self._busy = False
        self._thread = None

    # --- Paths and template ---

    def _exam(self, exam):
        return exam or self.app.exam_folder

    def folder(self, exam, key):
        return self.app.get_folder_path(key, exam_folder=self._exam(exam))

    def template_path(self, exam=None):
        return os.path.join(self.folder(exam, 'grading_data'), TEMPLATE_FILE)

    def load_template(self, exam=None):
        """(template, None), (None, None) without one, or (None, error) for a damaged file, which stops the marks."""
        path = self.template_path(exam)
        if not os.path.isfile(path):
            return None, None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                template = json.load(f)
        except (OSError, ValueError) as e:
            return None, str(e)
        problems = sm.validate_template(template)
        if problems:
            return None, ', '.join(problems)
        return template, None

    def save_template(self, template, exam=None):
        """Save the template; queued work drawn with the old one is voided, and the sheets are checked again."""
        exam = self._exam(exam)
        if template.get('status') == sm.ENABLED:
            template['ever_enabled'] = True
        os.makedirs(self.folder(exam, 'grading_data'), exist_ok=True)
        with self.commit_lock:
            write_json_atomic(self.template_path(exam), template)
            self._void(exam)
        if template.get('status') in (sm.ENABLED, sm.PENDING):
            self.scan_async(exam)

    def marks_ever_written(self, exam=None, image_path=None):
        """Whether graded images of this exam may carry marks: then they must never stand in for scans."""
        template, error = self.load_template(exam)
        if error or (template and template.get('ever_enabled')):
            return True
        return bool(image_path and os.path.isfile(image_path) and sm.read_marker(image_path))

    def original_path(self, exam, data):
        """The sheet's scan: only the name its report records it was scanned with, never a guess."""
        name = os.path.basename(str((data or {}).get('original_filename') or ''))
        if not name:
            return None
        path = os.path.join(self.folder(exam, 'original_files'), name)
        return path if os.path.isfile(path) else None

    def archive_path(self, exam, data):
        name = record_image_name(data or {})
        path = os.path.join(self.folder(exam, 'success'), name) if name else None
        return path if path and os.path.isfile(path) else None

    def font(self, lang, extra=''):
        """(font path, missing) for the cells in lang with the question numbers in extra."""
        key = (lang, ''.join(sorted(set(extra))))
        if key not in self._fonts:
            self._fonts[key] = sm.font_problem(lang, extra)
        return self._fonts[key]

    # --- Committing reports ---

    def commit_report(self, json_path, data, enqueue=True, exam=None):
        """Save a report whole; when its scores may have changed, queue its image in the same step."""
        with self.commit_lock:
            write_json_atomic(json_path, data)
            if enqueue:
                self.enqueue(json_path, exam)

    def enqueue(self, json_path, exam=None):
        exam = self._exam(exam)
        if not exam or not json_path:
            return
        template, _ = self.load_template(exam)
        if not template or template.get('status') not in (sm.ENABLED, sm.PENDING):
            return
        key = os.path.abspath(json_path)
        with self._cond:
            task = self._pending.get(key)
            if task:
                task.generation = self._generation.get(exam, 0)
            else:
                self._pending[key] = _Task(exam, key, self._generation.get(exam, 0))
            self._start()
            self._cond.notify_all()

    # --- Worker ---

    def _start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name='score-marks', daemon=True)
            self._thread.start()

    def _add_job(self, job):
        with self._cond:
            self._jobs.append(job)
            self._start()
            self._cond.notify_all()

    def _void(self, exam):
        """Queued and running work for exam will not publish (see _publish)."""
        with self._cond:
            self._generation[exam] = self._generation.get(exam, 0) + 1
            for key in [k for k, t in self._pending.items() if t.exam == exam]:
                del self._pending[key]

    def _run(self):
        while True:
            with self._cond:
                while True:
                    if self._jobs:
                        job, task = self._jobs.popleft(), None
                        break
                    now = time.monotonic()
                    task = next((t for t in self._pending.values() if t.not_before <= now), None)
                    if task:
                        del self._pending[task.json_path]
                        job = None
                        break
                    self._busy = False
                    self._cond.notify_all()
                    waits = [t.not_before - now for t in self._pending.values()]
                    self._cond.wait(max(0.05, min(waits)) if waits else None)
                self._busy = True
            try:
                if job:
                    job()
                else:
                    self._process(task)
            except Exception as e:  # The worker must outlive any one sheet
                self._log('log_marks_failed', image=os.path.basename(task.json_path) if task else '-', error=e)

    def drain(self, timeout=30):
        """Wait until nothing is queued or running (tests, and before reporting a whole-exam result)."""
        end = time.monotonic() + timeout
        with self._cond:
            while self._jobs or self._pending or self._busy:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(min(left, 0.1))
        return True

    # --- One sheet ---

    def _read_report(self, json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('not a report')
        return data

    def _process(self, task):
        exam, json_path = task.exam, task.json_path
        if task.generation != self._generation.get(exam, 0):
            return
        template, _ = self.load_template(exam)
        if not template or template.get('status') not in (sm.ENABLED, sm.PENDING):
            return
        try:
            data = self._read_report(json_path)
        except FileNotFoundError:
            self._set(json_path, 'removed')
            return
        except (OSError, ValueError) as e:  # Being written by code that does not use commit_report, or locked
            self._retry(task, e)
            return
        if template['status'] == sm.PENDING:
            template = self._confirm_list(exam, template, data)
            if not template:
                return
        image = record_image_name(data) or os.path.basename(json_path)
        marks = sm.sheet_marks(data, template)  # Written even when its report does not add up; the log says what
        warnings = list(marks.warnings)
        archive = self.archive_path(exam, data)
        if not archive:
            self._set(json_path, 'not_archived')  # Queued again once it is moved to the success folder
            return
        original = self.original_path(exam, data)
        if not original:
            self._problem(json_path, image, [('mark_problem_no_original', {'file': data.get('original_filename') or '-'})])
            return
        try:
            size = sm.normalized_size(original)
            if sm.normalized_size(archive) != size:
                self._problem(json_path, image, [('mark_problem_size', {'file': os.path.basename(original)})])
                return
            if not sm.same_orientation(template, size):
                warnings.append(('mark_problem_layout', {}))  # Marked all the same: each mark names its question
            self._warn(json_path, image, warnings)
            original_sha = sm.file_sha256(original)
            before = self._stat(archive)  # Taken before the check, so that any later change is seen at publishing
            state = sm.classify_archive(archive, original, original_sha)
            if state == 'foreign':
                self._problem(json_path, image, [('mark_problem_conflict', {})])
                return
            tpl_hash = sm.template_hash(template)
            marker = sm.read_marker(archive) if state == 'ours' else None
            if marker and marker.get('scores') == marks.digest and marker.get('tpl') == tpl_hash \
                    and marker.get('renderer') == sm.RENDERER:
                self._set(json_path, 'ok')
                return
            font_path, missing = self.font(template['lang'], ''.join((template.get('items') or {}).get('subjective') or []))
            if missing:
                self._problem(json_path, image, [('mark_problem_font', {})])
                return
            picture, info, _ = sm.open_normalized(original)
            drawn = sm.draw_marks(picture, template, marks.texts, font_path)
            payload, _ = sm.encode_marked(drawn, info, sm.image_format(archive), {
                'v': sm.SCHEMA, 'tpl': tpl_hash, 'scores': marks.digest, 'renderer': sm.RENDERER,
                'orig': os.path.basename(original), 'orig_sha256': original_sha})
            temp = self._temp_path(archive)
            try:
                with open(temp, 'wb') as f:
                    f.write(payload)
                self._publish(task, tpl_hash, marks.digest, before, original, original_sha, temp, image)
            finally:
                if os.path.exists(temp):
                    os.remove(temp)
        except OSError as e:
            self._retry(task, e)

    def _publish(self, task, tpl_hash, digest, before, original, original_sha, temp, image):
        exam, json_path = task.exam, task.json_path
        with self.app.rename_lock:
            with self.commit_lock:
                if task.generation != self._generation.get(exam, 0):
                    return
                template, _ = self.load_template(exam)
                if not template or template.get('status') != sm.ENABLED or sm.template_hash(template) != tpl_hash:
                    return  # A new template queues every sheet again
                try:
                    data = self._read_report(json_path)
                except FileNotFoundError:
                    self._set(json_path, 'removed')
                    return
                now = sm.sheet_marks(data, template)
                if now.digest != digest:
                    self.enqueue(json_path, exam)  # Scores changed while drawing: draw the new ones
                    return
                path = self.archive_path(exam, data)  # Its name now, after any renaming
                if not path:
                    self._set(json_path, 'not_archived')
                    return
                if self._stat(path) != before and sm.classify_archive(path, original, original_sha) == 'foreign':
                    self._problem(json_path, image, [('mark_problem_conflict', {})])
                    return
                os.replace(temp, path)
        self._set(json_path, 'ok')
        for callback in list(self._listeners):
            self.app.ui_after(0, callback, json_path)

    def _confirm_list(self, exam, template, data):
        """
        A question list guessed from the answer key is confirmed by the first graded report: the same ids start the
        marks; others keep them off and are shown, once, for the teacher to settle in the dialog.
        """
        if sm.ids_match(template, data):
            template = dict(template, status=sm.ENABLED, ever_enabled=True)
            template.pop('pending_diff', None)
            with self.commit_lock:
                write_json_atomic(self.template_path(exam), template)
            self._log('log_marks_list_confirmed')
            self.scan_async(exam)  # Sheets graded before this report
            return template
        only_template, only_report = sm.ids_difference(template, data)
        difference = {'only_template': only_template, 'only_report': only_report}
        if template.get('pending_diff') != difference:
            with self.commit_lock:
                write_json_atomic(self.template_path(exam), dict(template, pending_diff=difference))
            self._log('log_marks_list_differs', only_template='、'.join(only_template) or '-',
                      only_report='、'.join(only_report) or '-')
        return None

    def _retry(self, task, error):
        task.attempts += 1
        if task.attempts >= RETRIES:
            self._set(task.json_path, 'failed', str(error))
            self._log('log_marks_failed', image=os.path.basename(task.json_path), error=error)
            return
        task.not_before = time.monotonic() + RETRY_DELAY * 2 ** task.attempts
        with self._cond:
            self._pending.setdefault(task.json_path, task)
            self._cond.notify_all()

    @staticmethod
    def _stat(path):
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns

    @staticmethod
    def _temp_path(path):
        folder, name = os.path.split(path)
        return os.path.join(folder, f".{name}.{os.getpid()}{TEMP_SUFFIX}")

    def _set(self, json_path, status, message=''):
        self._status[os.path.abspath(json_path)] = (status, message)

    def _problem(self, json_path, image, problems):
        """Something that keeps the sheet from being marked (no scan to draw on, an image changed elsewhere ...)."""
        message = '；'.join(self.app.t(key, **values) for key, values in problems)
        self._set(json_path, 'problem', message)
        if (json_path, message) not in self._logged:
            self._logged.add((json_path, message))
            self._log('log_marks_problem', image=image, reason=message)

    def _warn(self, json_path, image, warnings):
        """What does not add up on a sheet that is marked all the same, logged once per report and message."""
        if not warnings:
            return
        message = '；'.join(self.app.t(key, **values) for key, values in warnings)
        if (json_path, message) not in self._logged:
            self._logged.add((json_path, message))
            self._log('log_marks_warning', image=image, reason=message)

    def _log(self, key, **values):
        self.app.ui_after(0, self.app.log, self.app.t(key, **values))

    def status(self, json_path):
        return self._status.get(os.path.abspath(json_path))

    def add_listener(self, callback):
        self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    # --- Whole exam ---

    def reports(self, exam=None):
        reports_dir = self.folder(exam, 'reports')
        if not reports_dir or not os.path.isdir(reports_dir):
            return []
        found = []
        for name in sorted(os.listdir(reports_dir)):
            if name.endswith('.json'):
                path = os.path.join(reports_dir, name)
                try:
                    found.append((path, self._read_report(path)))
                except (OSError, ValueError):
                    continue
        return found

    def scan(self, exam=None, queue=True):
        """
        Compare each graded image's marker (its header only) with its report and the template, queue those out of
        date, and return the counts: 'ok', 'stale', 'not_archived', and 'warned' (sheets whose report does not add
        up; they are marked all the same).
        """
        exam = self._exam(exam)
        counts = {'ok': 0, 'stale': 0, 'warned': 0, 'not_archived': 0}
        template, _ = self.load_template(exam)
        if not template or template.get('status') not in (sm.ENABLED, sm.PENDING):
            return counts
        tpl_hash = sm.template_hash(template)
        for json_path, data in self.reports(exam):
            archive = self.archive_path(exam, data)
            if not archive:
                counts['not_archived'] += 1
                continue
            marks = sm.sheet_marks(data, template) if template['status'] == sm.ENABLED else None
            if marks is not None and marks.warnings:
                counts['warned'] += 1
            marker = sm.read_marker(archive)
            if marks is not None and marker and marker.get('scores') == marks.digest and \
                    marker.get('tpl') == tpl_hash and marker.get('renderer') == sm.RENDERER:
                counts['ok'] += 1
                continue
            counts['stale'] += 1
            if queue:
                self.enqueue(json_path, exam)
        return counts

    def scan_async(self, exam=None, report=False):
        """Scan in the worker; with report, log the outcome once the queued sheets are done."""
        exam = self._exam(exam)
        if not exam:
            return

        def job():
            self.cleanup_temp(exam)
            counts = self.scan(exam)
            if report and any(counts.values()):
                self._log('log_marks_scan', ok=counts['ok'], stale=counts['stale'], warned=counts['warned'])
        self._add_job(job)

    def cleanup_temp(self, exam=None):
        """Remove images this feature left half-written (only its own temporary names)."""
        success = self.folder(exam, 'success')
        if not success or not os.path.isdir(success):
            return
        for name in os.listdir(success):
            if name.startswith('.') and name.endswith(TEMP_SUFFIX):
                try:
                    os.remove(os.path.join(success, name))
                except OSError:
                    pass

    def pause(self, exam=None):
        """Stop writing marks for exam (marks already written stay); queued and running work is voided."""
        exam = self._exam(exam)
        template, _ = self.load_template(exam)
        with self.commit_lock:
            if template and template.get('status') != sm.DISABLED:
                write_json_atomic(self.template_path(exam), dict(template, status=sm.DISABLED))
            self._void(exam)

    def marked_sheets(self, exam=None):
        """(report path, image name) of the graded images that carry this feature's marker."""
        exam = self._exam(exam)
        found = []
        for json_path, data in self.reports(exam):
            archive = self.archive_path(exam, data)
            if archive and sm.read_marker(archive):
                found.append((json_path, os.path.basename(archive)))
        return found

    def restore(self, json_paths, done, exam=None):
        """
        Put the scans back in place of the listed marked images, keeping their names, scores and review history;
        marks are paused first, so that no queued or running work draws them again, and stay paused.
        done(restored, skipped) runs on the main thread; skipped holds (image, reason).
        """
        exam = self._exam(exam)
        self.pause(exam)
        self._add_job(lambda: self._restore(exam, json_paths, done))

    def _restore(self, exam, json_paths, done):
        restored, skipped = [], []
        for json_path in json_paths:
            try:
                data = self._read_report(json_path)
            except (OSError, ValueError):
                skipped.append((os.path.basename(json_path), self.app.t('mark_problem_no_report')))
                continue
            image = record_image_name(data) or os.path.basename(json_path)
            original = self.original_path(exam, data)
            if not original:
                skipped.append((image, self.app.t('mark_problem_no_original', file=data.get('original_filename') or '-')))
                continue
            try:
                original_sha = sm.file_sha256(original)
                with self.app.rename_lock:
                    with self.commit_lock:
                        archive = self.archive_path(exam, self._read_report(json_path))
                        state = sm.classify_archive(archive, original, original_sha) if archive else None
                        if state != 'ours':
                            reason = 'mark_problem_already_clean' if state == 'clean' else \
                                'mark_problem_conflict' if state else 'mark_problem_not_archived'
                            skipped.append((image, self.app.t(reason)))
                            continue
                        temp = self._temp_path(archive)
                        try:
                            shutil.copyfile(original, temp)
                            os.replace(temp, archive)
                        finally:
                            if os.path.exists(temp):
                                os.remove(temp)
                restored.append(image)
            except (OSError, ValueError) as e:
                skipped.append((image, str(e)))
        self._log('log_marks_restored', count=len(restored), skipped=len(skipped))
        self.app.ui_after(0, done, restored, skipped)

    # --- Keeping marked images away from the model and the backups ---

    def model_source(self, image_path, data, exam=None):
        """
        The image to grade a sheet from. Before any marks, the graded image itself (as always); after, only its
        scan, as the graded image may carry scores (or have lost its marker to an editor).
        """
        exam = self._exam(exam)
        if not self.marks_ever_written(exam, image_path):
            return image_path
        original = self.original_path(exam, data)
        if original and os.path.isfile(image_path) and sm.normalized_size(original) == sm.normalized_size(image_path):
            return original
        raise MarksSourceError(self.app.t('msg_marks_no_clean_source', image=os.path.basename(image_path),
                                          file=(data or {}).get('original_filename') or '-'))

    def may_back_up(self, image_path, exam=None):
        """Whether a graded image may be copied to the original files as its scan (never once marks were written)."""
        return not self.marks_ever_written(exam, image_path)

    def recover_for_regrading(self, success_path, exam=None):
        """
        A graded sheet to grade again (its report is missing) goes back to the exam folder as its scan:
        ('move', name) moves it as before, ('copied', name) put its verified scan there instead, (None, None) means
        nothing can be trusted and the teacher must put the scan back by hand.
        """
        exam = self._exam(exam)
        name = os.path.basename(success_path)
        if not self.marks_ever_written(exam, success_path):
            return 'move', name
        originals = self.folder(exam, 'original_files')
        marker = sm.read_marker(success_path)
        if marker:
            original = os.path.join(originals, os.path.basename(str(marker.get('orig') or '')))
            target = os.path.join(exam, os.path.basename(original))
            try:
                if (os.path.isfile(original) and not os.path.exists(target)
                        and sm.file_pixel_digest(success_path) == marker['content']
                        and sm.file_sha256(original) == marker.get('orig_sha256')):
                    shutil.copy2(original, target)
                    if sm.files_equal(original, target):
                        os.remove(success_path)  # Only a drawing of the scan, which stays in the original files
                        return 'copied', os.path.basename(target)
                    os.remove(target)
            except OSError:
                pass
            return None, None
        same = os.path.join(originals, name)
        if os.path.isfile(same) and sm.files_equal(success_path, same):
            return 'move', name
        return None, None
