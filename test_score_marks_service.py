"""
When the red scores are written (score_marks_service): an image never ends up showing older scores than its report,
work left when the app closed is picked up again, restoring the scans cannot be undone by work still running, and a
graded image that may carry scores never stands in for its scan.
"""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

import score_marks as sm
import score_marks_service
from AutoGrader import App
from score_marks_service import MarksSourceError, ScoreMarksService, write_json_atomic
from test_score_marks import report, scan, template


class MarksApp:
    """What the service uses of App: folders, translations, the main-thread queue and the rename lock."""
    t = App.t
    get_folder_path = App.get_folder_path
    current_lang = 'CN'

    def __init__(self, exam):
        self.exam_folder = str(exam)
        self.rename_lock = threading.Lock()
        self.logs = []
        self.score_marks = ScoreMarksService(self)

    def ui_after(self, delay, callback, *args):
        callback(*args)

    def log(self, message):
        self.logs.append(message)


def scores(a, b, objective=(3, 3)):
    """Report scores: two multiple-choice questions and sub-questions 17(1), 17(2) out of 40."""
    return dict(objective=[('1', objective[0]), ('2', objective[1])], subjective=[('17(1)', a, 40), ('17(2)', b, 40)])


def rescored(data, a, b):
    """The same sheet's report with new scores (as a review or regrade saves it)."""
    fresh = report(**scores(a, b))
    return dict(data, details=fresh['details'], total_score=fresh['total_score'])


class Exam:
    def __init__(self, root):
        self.root = root / 'exam'
        self.originals, self.success = self.root / '原始文件', self.root / '成功归档'
        self.reports, self.data = self.root / '阅卷报告', self.root / '阅卷数据'
        for folder in (self.originals, self.success, self.reports, self.data):
            folder.mkdir(parents=True)

    def sheet(self, name, a=2, b=2, archived_as=None, size=(1200, 850)):
        """A graded sheet: its scan in the original files, the same file in Success, and its report."""
        scan(self.originals / name, size=size, quality=90)
        shutil.copy2(self.originals / name, self.success / (archived_as or name))
        data = report(**scores(a, b), original_filename=name)
        if archived_as:
            data['renamed_filename'] = archived_as
        json_path = self.reports / (os.path.splitext(name)[0] + '.json')
        write_json_atomic(json_path, data)
        return str(json_path), data

    def template(self, status=sm.ENABLED, **changes):
        t = template()
        t.update(status=status, ever_enabled=status == sm.ENABLED, **changes)
        write_json_atomic(self.data / 'score_marks.json', t)
        return t

    def saved_template(self):
        return json.loads((self.data / 'score_marks.json').read_text(encoding='utf-8'))


def digest_of(data, t):
    return sm.sheet_marks(data, t).digest


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.exam = Exam(Path(self.tmp.name))
        self.app = MarksApp(self.exam.root)
        self.service = self.app.score_marks

    def tearDown(self):
        self.service.drain(10)
        self.tmp.cleanup()

    def marker(self, name='a.jpg'):
        return sm.read_marker(self.exam.success / name)


class TestWriting(ServiceTest):
    def test_a_saved_report_gets_its_scores_drawn_from_the_scan(self):
        json_path, data = self.exam.sheet('a.jpg')
        t = self.exam.template()
        before = sm.file_sha256(self.exam.originals / 'a.jpg')
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        self.assertEqual(self.marker()['scores'], digest_of(data, t))
        self.assertEqual(sm.file_sha256(self.exam.originals / 'a.jpg'), before)
        self.assertEqual(self.service.status(json_path)[0], 'ok')
        # Nothing to do the second time
        self.service.enqueue(json_path)
        self.assertTrue(self.service.drain())
        self.assertEqual(self.marker()['scores'], digest_of(data, t))

    def test_the_image_follows_the_last_save(self):
        json_path, data = self.exam.sheet('a.jpg')
        t = self.exam.template()
        self.service.commit_report(json_path, rescored(data, 20, 21))
        last = rescored(data, 24, 21)
        self.service.commit_report(json_path, last)
        self.assertTrue(self.service.drain())
        self.assertEqual(self.marker()['scores'], digest_of(last, t))

    def test_a_save_made_while_an_image_is_published_waits_for_it(self):
        json_path, data = self.exam.sheet('a.jpg')
        t = self.exam.template()
        newer = rescored(data, 24, 21)
        real_replace, seen = os.replace, {}

        def replace(src, dst):
            if str(dst).endswith('a.jpg') and 'blocked' not in seen:
                saver = threading.Thread(target=self.service.commit_report, args=(json_path, newer))
                saver.start()
                saver.join(0.3)
                seen['blocked'] = saver.is_alive()  # The save could not slip in between the check and this step
                seen['saver'] = saver
            return real_replace(src, dst)

        with patch.object(score_marks_service.os, 'replace', side_effect=replace):
            self.service.commit_report(json_path, data)
            self.assertTrue(self.service.drain())
            seen['saver'].join(5)
            self.assertTrue(self.service.drain())
        self.assertTrue(seen['blocked'])
        self.assertEqual(self.marker()['scores'], digest_of(newer, t))

    def test_scores_saved_while_drawing_are_never_published_as_the_old_ones(self):
        # Report 51 while 47 is being drawn: the drawing of 47 must not reach the image
        json_path, data = self.exam.sheet('a.jpg')
        t = self.exam.template()
        old, new = rescored(data, 20, 21), rescored(data, 24, 21)
        self.assertEqual((old['total_score'], new['total_score']), (47, 51))
        published = []
        self.service.add_listener(lambda path: published.append(self.marker()['scores']))
        real_draw, calls = sm.draw_marks, []

        def draw(*args):
            calls.append(1)
            if len(calls) == 1:
                self.service.commit_report(json_path, new)  # The teacher saves meanwhile
            return real_draw(*args)

        with patch.object(score_marks_service.sm, 'draw_marks', side_effect=draw):
            self.service.commit_report(json_path, old)
            self.assertTrue(self.service.drain())
        self.assertEqual(published, [digest_of(new, t)])
        self.assertEqual(len(calls), 2)

    def test_work_left_when_the_app_closed_is_found_again(self):
        json_path, data = self.exam.sheet('a.jpg')
        t = self.exam.template()
        self.service.commit_report(json_path, rescored(data, 20, 21))
        self.assertTrue(self.service.drain())
        newer = rescored(data, 24, 21)
        write_json_atomic(json_path, newer)  # Saved, then the app closed before the image was redrawn
        reopened = MarksApp(self.exam.root).score_marks
        counts = reopened.scan()
        self.assertEqual(counts['stale'], 1)
        self.assertTrue(reopened.drain())
        self.assertEqual(self.marker()['scores'], digest_of(newer, t))
        self.assertEqual(reopened.scan()['ok'], 1)

    def test_an_image_edited_by_hand_is_left_alone(self):
        json_path, data = self.exam.sheet('a.jpg')
        self.exam.template()
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        archive = self.exam.success / 'a.jpg'
        with Image.open(archive) as im:
            edited = im.convert('RGB')
            ImageDraw.Draw(edited).line((500, 500, 700, 520), fill='blue', width=6)
            edited.save(archive, 'JPEG', quality=93)  # The marker survives the edit
        edited_bytes = archive.read_bytes()
        self.service.commit_report(json_path, rescored(data, 24, 21))
        self.assertTrue(self.service.drain())
        self.assertEqual(archive.read_bytes(), edited_bytes)
        self.assertEqual(self.service.status(json_path)[0], 'problem')
        self.assertTrue(any('外部修改' in line for line in self.app.logs), self.app.logs)

    def test_a_sheet_whose_report_does_not_add_up_is_marked_and_flagged(self):
        json_path, data = self.exam.sheet('a.jpg')
        t = self.exam.template()
        incomplete = dict(data)
        incomplete['details'] = [d for d in data['details'] if d['question_id'] != '17(2)']
        incomplete['total_score'] = data['total_score'] - 2
        self.service.commit_report(json_path, incomplete)
        self.assertTrue(self.service.drain())
        marks = sm.sheet_marks(incomplete, t)
        self.assertEqual(marks.texts['17(2)'], ['17(2)', sm.MISSING])
        self.assertEqual(self.marker()['scores'], marks.digest)  # Written, with the missing score plainly missing
        self.assertTrue(any('已回写分值' in line and '缺少小问 17(2)' in line for line in self.app.logs), self.app.logs)
        self.assertEqual(self.service.scan(queue=False), {'ok': 1, 'stale': 0, 'warned': 1, 'not_archived': 0})

    def test_scans_cropped_or_turned_differently_are_marked(self):
        narrow, data_narrow = self.exam.sheet('narrow.jpg', size=(1080, 850))  # 10% narrower than the sample
        turned, data_turned = self.exam.sheet('turned.jpg', size=(850, 1200))  # Portrait; the sample is landscape
        self.exam.template()
        self.service.commit_report(narrow, data_narrow)
        self.service.commit_report(turned, data_turned)
        self.assertTrue(self.service.drain())
        self.assertIsNotNone(self.marker('narrow.jpg'))
        self.assertIsNotNone(self.marker('turned.jpg'))
        warnings = [line for line in self.app.logs if '方向' in line]
        self.assertEqual(len(warnings), 1, self.app.logs)  # Only the turned one, flagged
        self.assertIn('turned.jpg', warnings[0])


class TestStopping(ServiceTest):
    def test_restoring_waits_for_running_work_and_stays_paused(self):
        json_path, data = self.exam.sheet('a.jpg')
        self.exam.template()
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        drawing, release = threading.Event(), threading.Event()
        real_draw = sm.draw_marks

        def slow_draw(*args):
            drawing.set()
            release.wait(5)
            return real_draw(*args)

        results = []
        with patch.object(score_marks_service.sm, 'draw_marks', side_effect=slow_draw):
            self.service.commit_report(json_path, rescored(data, 24, 21))
            self.assertTrue(drawing.wait(5))  # A redraw is under way...
            self.service.restore([json_path], lambda restored, skipped: results.append((restored, skipped)))
            release.set()  # ...and finishes after the restore was asked for
            self.assertTrue(self.service.drain())
        self.assertTrue(sm.files_equal(self.exam.success / 'a.jpg', self.exam.originals / 'a.jpg'))
        self.assertEqual(results, [(['a.jpg'], [])])
        self.assertEqual(self.exam.saved_template()['status'], sm.DISABLED)
        self.service.commit_report(json_path, rescored(data, 30, 21))
        self.assertTrue(self.service.drain())
        self.assertTrue(sm.files_equal(self.exam.success / 'a.jpg', self.exam.originals / 'a.jpg'))

    def test_restoring_skips_images_it_did_not_draw(self):
        json_path, data = self.exam.sheet('a.jpg')
        self.exam.template()
        results = []
        self.service.restore([json_path], lambda restored, skipped: results.append((restored, skipped)))
        self.assertTrue(self.service.drain())
        self.assertEqual(results[0][0], [])
        self.assertEqual(results[0][1][0][0], 'a.jpg')  # Already the scan

    def test_work_that_cannot_publish_ends(self):
        json_path, data = self.exam.sheet('a.jpg')
        self.exam.template()
        self.service.enqueue(str(self.exam.reports / 'gone.json'))  # Report taken out of the grades
        self.assertTrue(self.service.drain(5))
        self.assertEqual(self.service.status(str(self.exam.reports / 'gone.json'))[0], 'removed')
        self.service.pause()
        self.service.commit_report(json_path, data)  # Paused: not queued at all
        self.assertTrue(self.service.drain(5))
        self.assertIsNone(self.marker())

    def test_errors_are_retried_a_few_times_then_reported(self):
        json_path, data = self.exam.sheet('a.jpg')
        self.exam.template()
        with patch.object(score_marks_service.sm, 'open_normalized', side_effect=OSError('disk unplugged')), \
                patch.object(score_marks_service, 'RETRY_DELAY', 0.01):
            self.service.commit_report(json_path, data)
            self.assertTrue(self.service.drain(10))
        self.assertEqual(self.service.status(json_path), ('failed', 'disk unplugged'))
        self.assertTrue(any('disk unplugged' in line for line in self.app.logs))


class TestScans(ServiceTest):
    def test_grading_never_takes_a_marked_image(self):
        json_path, data = self.exam.sheet('a.jpg', archived_as='701-张三.jpg')
        archive = str(self.exam.success / '701-张三.jpg')
        self.assertEqual(self.service.model_source(archive, data), archive)  # No marks yet: as before
        self.assertTrue(self.service.may_back_up(archive))
        self.exam.template()
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        self.assertIsNotNone(sm.read_marker(archive))
        self.assertEqual(self.service.model_source(archive, data), str(self.exam.originals / 'a.jpg'))
        self.assertFalse(self.service.may_back_up(archive))
        os.remove(self.exam.originals / 'a.jpg')
        with self.assertRaises(MarksSourceError):
            self.service.model_source(archive, data)

    def test_a_marked_sheet_without_its_report_goes_back_as_its_scan(self):
        json_path, data = self.exam.sheet('IMG_1.jpg', archived_as='701-张三.jpg')
        self.exam.template()
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        os.remove(json_path)
        archive = self.exam.success / '701-张三.jpg'
        self.assertEqual(self.service.recover_for_regrading(str(archive)), ('copied', 'IMG_1.jpg'))
        self.assertTrue(sm.files_equal(self.exam.root / 'IMG_1.jpg', self.exam.originals / 'IMG_1.jpg'))
        self.assertFalse(archive.exists())

    def test_an_unverifiable_sheet_is_left_for_the_teacher(self):
        json_path, data = self.exam.sheet('IMG_1.jpg', archived_as='701-张三.jpg')
        self.exam.template()
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        archive = self.exam.success / '701-张三.jpg'
        with Image.open(archive) as im:
            im.convert('RGB').save(archive, 'JPEG', quality=93, comment=b'')  # Marker lost, scores still drawn
        self.assertEqual(self.service.recover_for_regrading(str(archive)), (None, None))
        self.assertTrue(archive.exists())
        self.assertFalse((self.exam.root / 'IMG_1.jpg').exists())

    def test_before_any_marks_sheets_go_back_as_before(self):
        self.exam.sheet('IMG_1.jpg')
        self.assertEqual(self.service.recover_for_regrading(str(self.exam.success / 'IMG_1.jpg')), ('move', 'IMG_1.jpg'))
        self.exam.template()
        # Marks on, but this image is byte for byte its scan
        self.assertEqual(self.service.recover_for_regrading(str(self.exam.success / 'IMG_1.jpg')), ('move', 'IMG_1.jpg'))

    def test_a_guessed_question_list_waits_for_the_first_report(self):
        json_path, data = self.exam.sheet('a.jpg')
        self.exam.template(status=sm.PENDING)
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        self.assertEqual(self.exam.saved_template()['status'], sm.ENABLED)
        self.assertIsNotNone(self.marker())

    def test_a_list_that_differs_from_the_first_report_keeps_the_marks_off(self):
        json_path, data = self.exam.sheet('a.jpg')
        t = template(subjective=('17(1)', '17(2)', '17(3)'))
        t.update(status=sm.PENDING)
        write_json_atomic(self.exam.data / 'score_marks.json', t)
        for _ in range(2):
            self.service.commit_report(json_path, data)
            self.assertTrue(self.service.drain())
        saved = self.exam.saved_template()
        self.assertEqual(saved['status'], sm.PENDING)
        self.assertEqual(saved['pending_diff'], {'only_template': ['17(3)'], 'only_report': []})
        self.assertIsNone(self.marker())
        self.assertEqual(sum('不一致' in line for line in self.app.logs), 1)  # Said once

    def test_a_damaged_template_stops_the_marks(self):
        json_path, data = self.exam.sheet('a.jpg')
        (self.exam.data / 'score_marks.json').write_text('{"schema": 1, "status": ', encoding='utf-8')
        template_, error = self.service.load_template()
        self.assertIsNone(template_)
        self.assertTrue(error)
        self.service.commit_report(json_path, data)
        self.assertTrue(self.service.drain())
        self.assertIsNone(self.marker())
        self.assertTrue(self.service.marks_ever_written())  # Unknown, so graded images are not trusted as scans

    def test_only_its_own_temporary_files_are_removed(self):
        own, other = self.exam.success / '.a.jpg.123.aieg-marks.tmp', self.exam.success / 'notes.tmp'
        own.write_bytes(b'x')
        other.write_bytes(b'x')
        self.service.cleanup_temp()
        self.assertFalse(own.exists())
        self.assertTrue(other.exists())


if __name__ == '__main__':
    unittest.main()
