# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""
Scores written in red onto graded answer sheets: the multiple-choice total, each sub-question and the total, at the
positions of one template per exam. Pure functions (no Tk, no API); see score_marks_service for when they run.

Each mark is a one-row table, question number then score (e.g. 26(1) | 4分), so a score still reads as its question's
when a scan is shifted from the template's sample. Every sheet is marked: a score the report lacks shows MISSING and
what does not add up is returned as warnings for the log.

A marked image carries a marker (JPEG comment / PNG text) with the SHA-256 of its decoded pixels, so a marked image
edited afterwards (editors keep the marker) is told apart from one this module wrote.
"""

import collections
import hashlib
import io
import json
import math
import os
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin

from translations import TRANSLATIONS

SCHEMA = 1
RENDERER = 2  # Bump when the drawing changes, so that sheets drawn before are redrawn (2: tables)
MARKER_KEY = 'AIExamGrader-marks'
JPEG_PREFIX = b'AIExamGrader-marks '
JPEG_QUALITY = 93

TOTAL, OBJECTIVE = 'total', 'objective'  # Mark ids besides the sub-question ids
OBJ_ADJ = 'Obj_Adj'  # Correction the review adds when an objective total is typed without objective details

ENABLED, DISABLED, DRAFT, PENDING = 'enabled', 'disabled', 'draft', 'pending_check'
STATUSES = (ENABLED, DISABLED, DRAFT, PENDING)
ANCHORS = ('rm', 'lm', 'mm', 'mb', 'mt')

SIZE_QUESTION = 0.019  # Font size as a share of sqrt(width x height): about 67 px on a 4233 x 2970 A3 scan
SIZE_TOTAL = 0.030
SIZE_RANGE = (0.006, 0.08)
COLOR = (220, 0, 0)
MISSING = '—'  # A score the report lacks or cannot be read
CELL_PADDING = (0.30, 0.14)  # Around the text of a table cell, as shares of the font size (across, down)
BACKGROUND_ALPHA = 215  # White behind a table (of 255): legible over printed lines and writing, which still show

FONT_CANDIDATES = (
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/Hiragino Sans GB.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/Supplemental/Songti.ttc',
    '/Library/Fonts/Arial Unicode.ttf',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'msyhbd.ttc'),
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'msyh.ttc'),
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'simhei.ttf'),
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'simsun.ttc'),
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
)


# --- Question ids ---

def normalize_qid(qid):
    """17（1） and ' 17(1)' are 17(1): full-width forms and spaces are dropped, nothing else is merged (17-1 stays)."""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(qid)))


def qid_sort_key(qid):
    return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.findall(r'\d+|\D+', str(qid))]


def is_objective(item):
    """Same split as the reports and the summary: a type naming 客观 or 选择 (also 客观题修正, i.e. Obj_Adj)."""
    q_type = str(item.get('type', ''))
    return '客观' in q_type or '选择' in q_type


def items_from_answer_key(answer_key):
    """
    A first guess at the question list before any sheet is graded: a numbered question answered with letters
    (A, BD) is multiple choice, everything else a sub-question to mark. Only a candidate list (see the dialog).
    """
    objective, subjective, labels = [], [], {}
    for qid, answer in (answer_key or {}).items():
        key = normalize_qid(qid)
        if not key or key in labels:
            continue
        labels[key] = str(qid)
        letters = re.sub(r'[\s,，、]', '', str(answer))
        if re.fullmatch(r'\d+', key) and re.fullmatch(r'[A-Ha-h]{1,8}', letters):
            objective.append(key)
        else:
            subjective.append(key)
    return {'objective': sorted(objective, key=qid_sort_key), 'subjective': sorted(subjective, key=qid_sort_key),
            'labels': labels, 'source': 'answer_key'}


def items_from_reports(reports):
    """Question list from graded reports: the ids found in at least half of them, split as the reports split them."""
    counts, kinds, labels = {}, {}, {}
    for data in reports:
        seen = set()
        for item in (data.get('details') or []) if isinstance(data, dict) else []:
            if not isinstance(item, dict) or item.get('question_id') in (None, OBJ_ADJ):
                continue
            key = normalize_qid(item['question_id'])
            if key in seen:
                continue
            seen.add(key)
            counts[key] = counts.get(key, 0) + 1
            kinds.setdefault(key, 'objective' if is_objective(item) else 'subjective')
            labels.setdefault(key, str(item['question_id']))
    needed = max(1, (len(reports) + 1) // 2)
    keep = [k for k, n in counts.items() if n >= needed]
    return {'objective': sorted((k for k in keep if kinds[k] == 'objective'), key=qid_sort_key),
            'subjective': sorted((k for k in keep if kinds[k] == 'subjective'), key=qid_sort_key),
            'labels': {k: labels[k] for k in keep}, 'source': 'reports'}


# --- Scores of one sheet ---

def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def format_score(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip('0').rstrip('.')


def mark_texts(lang):
    """(score format, multiple-choice label, total label) in the template's language."""
    texts = TRANSLATIONS.get(lang) or TRANSLATIONS['CN']
    return texts['mark_cell_score'], texts['mark_cell_objective'], texts['mark_cell_total']


class SheetMarks:
    """
    What one sheet's marks say: cells [question number, score] by mark id, and warnings (translation key, values)
    about what does not add up in its report. Warnings do not keep the sheet from being marked.
    """

    def __init__(self, texts, warnings):
        self.texts = texts
        self.warnings = warnings

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.texts, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


def _id_problems(found, expected, keys):
    """Missing, extra and repeated ids (found is a list, so repeats show) as (translation key, values)."""
    problems = []
    names = lambda ids: '、'.join(sorted(ids, key=qid_sort_key))
    missing = set(expected) - set(found)
    extra = set(found) - set(expected)
    repeated = {q for q in found if found.count(q) > 1}
    if missing:
        problems.append((keys[0], {'qids': names(missing)}))
    if extra:
        problems.append((keys[1], {'qids': names(extra)}))
    if repeated:
        problems.append((keys[2], {'qids': names(repeated)}))
    return problems


def sheet_marks(data, template):
    """
    The cells for a saved report, one per mark of the template (the template's question list, not the report's own
    items): [question number, score]. Every mark gets a cell, MISSING when the report has no readable score for it.
    Warnings name what does not add up: questions the report misses, adds or repeats, scores out of range, a total
    that is not the multiple-choice total plus the sub-questions (the total shown is the one the report records).
    """
    fmt_score, objective_label, total_label = mark_texts(template.get('lang', 'CN'))
    score_text = lambda value: fmt_score.format(score=format_score(value))
    items = template.get('items') or {}
    expected_objective, expected_subjective = items.get('objective') or [], items.get('subjective') or []
    warnings = []
    details = data.get('details') if isinstance(data, dict) else None
    if not isinstance(details, list) or not details:
        details = []
        warnings.append(('mark_problem_no_details', {}))

    objective_ids, objective_scores, subjective_ids, subjective = [], [], [], {}
    for item in details:
        if not isinstance(item, dict) or item.get('question_id') in (None, ''):
            warnings.append(('mark_problem_bad_item', {}))
            continue
        qid, score = normalize_qid(item['question_id']), item.get('score')
        if not is_number(score):
            warnings.append(('mark_problem_bad_score', {'qid': item['question_id']}))
            continue
        if is_objective(item):
            objective_scores.append(score)
            if item['question_id'] != OBJ_ADJ:
                objective_ids.append(qid)
        else:
            subjective_ids.append(qid)
            subjective.setdefault(qid, score)  # A repeated question shows its first score, and a warning
            top = item.get('max_score')
            if score < 0 or (is_number(top) and score > top + 1e-9):
                warnings.append(('mark_problem_range', {'qid': item['question_id'], 'score': format_score(score),
                                                        'max': format_score(top) if is_number(top) else '-'}))
    warnings += _id_problems(subjective_ids, expected_subjective,
                             ('mark_problem_missing', 'mark_problem_extra', 'mark_problem_duplicate'))

    cells = {}
    if objective_scores:
        objective_total = sum(objective_scores)
    elif is_number((data or {}).get('legacy_obj_score')):
        objective_total = data['legacy_obj_score']  # Reports from before per-question details
    else:
        objective_total = None
    if expected_objective:
        if objective_scores:
            warnings += _id_problems(objective_ids, expected_objective,
                                     ('mark_problem_obj_missing', 'mark_problem_obj_extra', 'mark_problem_obj_duplicate'))
        if objective_total is None:
            warnings.append(('mark_problem_no_objective', {}))
        elif objective_total < 0:
            warnings.append(('mark_problem_range', {'qid': objective_label, 'score': format_score(objective_total), 'max': '-'}))
        cells[OBJECTIVE] = [objective_label, MISSING if objective_total is None else score_text(objective_total)]
    elif objective_scores:
        warnings.append(('mark_problem_obj_extra', {'qids': '、'.join(sorted(set(objective_ids), key=qid_sort_key)) or OBJ_ADJ}))
    for qid in expected_subjective:
        cells[qid] = [qid, score_text(subjective[qid]) if qid in subjective else MISSING]

    total = (data or {}).get('total_score')
    if is_number(total):
        parts = (objective_total or 0) + sum(s for q, s in subjective.items())
        if abs(total - parts) > 1e-6:
            warnings.append(('mark_problem_total', {'total': format_score(total), 'sum': format_score(parts)}))
        cells[TOTAL] = [total_label, score_text(total)]
    else:
        warnings.append(('mark_problem_bad_score', {'qid': 'total_score'}))
        cells[TOTAL] = [total_label, MISSING]
    return SheetMarks(cells, warnings)


def preview_texts(template, max_scores=None):
    """The widest cells each mark may show (its full score less half a point), for checking the layout."""
    fmt_score, objective_label, total_label = mark_texts(template.get('lang', 'CN'))
    items = template.get('items') or {}
    max_scores = max_scores or {}
    longest = lambda top: fmt_score.format(score=format_score(top - 0.5) if top >= 1 else format_score(top))
    texts = {}
    if items.get('objective'):
        texts[OBJECTIVE] = [objective_label, longest(sum(max_scores.get(q, 3) for q in items['objective']))]
    for qid in items.get('subjective') or []:
        texts[qid] = [qid, longest(max_scores.get(qid, 10))]
    top = sum(max_scores.get(q, 3) for q in items.get('objective') or []) + \
        sum(max_scores.get(q, 10) for q in items.get('subjective') or [])
    texts[TOTAL] = [total_label, longest(max(top, 100))]
    return texts


# --- Template ---

def required_marks(template):
    items = template.get('items') or {}
    return [TOTAL] + ([OBJECTIVE] if items.get('objective') else []) + list(items.get('subjective') or [])


def unplaced_marks(template):
    marks = template.get('marks') or {}
    return [m for m in required_marks(template) if m not in marks]


def template_hash(template):
    """Fingerprint of everything that changes what a sheet looks like (not its status or sample)."""
    fields = {k: template.get(k) for k in ('schema', 'lang', 'items', 'marks', 'size_question', 'size_total', 'color')}
    fields['items'] = {k: (fields['items'] or {}).get(k) for k in ('objective', 'subjective')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


def validate_template(template):
    """Problems that make a template file unusable (a damaged or foreign file), as messages for the log."""
    if not isinstance(template, dict):
        return ['not an object']
    problems = []
    if template.get('schema') != SCHEMA:
        problems.append(f"schema {template.get('schema')!r}")
    if template.get('status') not in STATUSES:
        problems.append(f"status {template.get('status')!r}")
    if template.get('lang') not in TRANSLATIONS:
        problems.append(f"lang {template.get('lang')!r}")
    items = template.get('items')
    if not isinstance(items, dict) or not all(isinstance(items.get(k), list) and all(isinstance(q, str) for q in items[k])
                                              for k in ('objective', 'subjective')):
        problems.append('items')
    marks = template.get('marks')
    if not isinstance(marks, dict):
        problems.append('marks')
    else:
        for mark_id, pos in marks.items():
            if not (isinstance(pos, dict) and is_number(pos.get('x')) and is_number(pos.get('y'))
                    and 0 <= pos['x'] <= 1 and 0 <= pos['y'] <= 1 and pos.get('anchor') in ANCHORS):
                problems.append(f"mark {mark_id}")
    for key in ('size_question', 'size_total'):
        if not (is_number(template.get(key)) and SIZE_RANGE[0] <= template[key] <= SIZE_RANGE[1]):
            problems.append(key)
    reference = template.get('reference') or {}
    size = reference.get('size')
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
        problems.append('reference size')
    return problems


def new_template(items, lang, reference_size, reference_image='', reference_sha256=''):
    return {'schema': SCHEMA, 'status': DRAFT, 'ever_enabled': False, 'lang': lang,
            'items': {'objective': list(items.get('objective') or []), 'subjective': list(items.get('subjective') or []),
                      'labels': dict(items.get('labels') or {}), 'source': items.get('source', '')},
            'marks': {}, 'size_question': SIZE_QUESTION, 'size_total': SIZE_TOTAL, 'color': list(COLOR),
            'reference': {'image': reference_image, 'sha256': reference_sha256, 'size': list(reference_size)}}


def same_orientation(template, size):
    """
    Whether a sheet is upright the way the template's sample is (both portrait or both landscape). Scans cropped
    differently are marked all the same, their marks a little off; a turned one gets a warning, as its marks may be
    far from their questions.
    """
    ref = (template.get('reference') or {}).get('size') or [0, 0]
    if not (ref[0] and ref[1] and size[0] and size[1]):
        return True
    return (ref[0] >= ref[1]) == (size[0] >= size[1])


def ids_match(template, data):
    """Whether a report has exactly the template's ids (used to confirm a list guessed from the answer key)."""
    found = items_from_reports([data])
    items = template.get('items') or {}
    return (sorted(found['objective'], key=qid_sort_key) == sorted(items.get('objective') or [], key=qid_sort_key) and
            sorted(found['subjective'], key=qid_sort_key) == sorted(items.get('subjective') or [], key=qid_sort_key))


def ids_difference(template, data):
    """(only in the template, only in the report) for the dialog's list of what to set."""
    found = items_from_reports([data])
    items = template.get('items') or {}
    mine = set(items.get('objective') or []) | set(items.get('subjective') or [])
    theirs = set(found['objective']) | set(found['subjective'])
    return sorted(mine - theirs, key=qid_sort_key), sorted(theirs - mine, key=qid_sort_key)


# --- Fonts ---

def font_size(template, mark_id, size):
    share = template.get('size_total' if mark_id == TOTAL else 'size_question') or SIZE_QUESTION
    return max(10, round(share * math.sqrt(size[0] * size[1])))


def load_font(path, px):
    if path:
        return ImageFont.truetype(path, px)
    try:
        return ImageFont.load_default(px)
    except TypeError:  # Pillow before 10.1 has one size only
        return ImageFont.load_default()


def _glyph(font, ch):
    left, top, right, bottom = font.getbbox(ch)
    image = Image.new('L', (max(1, right - left), max(1, bottom - top)), 0)
    ImageDraw.Draw(image).text((-left, -top), ch, font=font, fill=255)
    return image.size, image.tobytes()


def has_glyphs(font, text):
    """Every character of text has its own glyph (a missing one renders as the font's missing-glyph box)."""
    missing = _glyph(font, '\U0010FFFF')
    return all(_glyph(font, ch) != missing for ch in set(text) - {' '})


def find_font(text, candidates=FONT_CANDIDATES):
    """
    The first installed font that draws all of text; None when none does (Pillow's own font may still do, see
    font_problem).
    """
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            if has_glyphs(ImageFont.truetype(path, 32), text):
                return path
        except OSError:
            continue
    return None


def font_problem(lang, extra='', candidates=FONT_CANDIDATES):
    """
    (font path, missing) for the template's language and the question numbers in extra; missing is True when the
    cells cannot be drawn.
    """
    sample = ''.join(mark_texts(lang)).replace('{score}', '0123456789.') + extra  # MISSING: see _cell_text
    path = find_font(sample, candidates)
    if path:
        return path, False
    try:  # Pillow's own font, which draws Latin text
        if has_glyphs(load_font(None, 32), sample):
            return None, False
    except (OSError, ValueError):
        pass
    return None, True


# --- Images ---

def normalized_size(path):
    """Width and height as shown (EXIF orientation applied), read from the header only."""
    with Image.open(path) as im:
        w, h = im.size
        if im.getexif().get(0x0112) in (5, 6, 7, 8):
            w, h = h, w
    return w, h


def open_normalized(path):
    """The image as shown, loaded, with its orientation tag reset so that it is not turned a second time."""
    with Image.open(path) as im:
        im.load()
        info = dict(im.info)
        fmt = im.format
        image = ImageOps.exif_transpose(im)
        if image is None or image is im:
            image = im.copy()
    if 'exif' in image.info:
        info['exif'] = image.info['exif']
    return image, info, fmt


def pixel_digest(image):
    return hashlib.sha256(f"{image.mode}|{image.size[0]}x{image.size[1]}|".encode() + image.tobytes()).hexdigest()


def file_pixel_digest(path):
    with Image.open(path) as im:
        im.load()
        return pixel_digest(im)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def files_equal(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, 'rb') as fa, open(b, 'rb') as fb:
            while True:
                block = fa.read(1 << 20)
                if block != fb.read(1 << 20):
                    return False
                if not block:
                    return True
    except OSError:
        return False


def read_marker(path):
    """The marker a marked image carries, or None; it is only a claim until its content digest is checked."""
    try:
        with Image.open(path) as im:
            if im.format == 'JPEG':
                raw = im.info.get('comment') or b''
                if isinstance(raw, str):
                    raw = raw.encode('latin-1', 'ignore')
                if not raw.startswith(JPEG_PREFIX):
                    return None
                text = raw[len(JPEG_PREFIX):].decode('utf-8')
            elif im.format == 'PNG':
                text = im.info.get(MARKER_KEY)
                if not text:
                    return None
            else:
                return None
        marker = json.loads(text)
    except Exception:
        return None
    return marker if isinstance(marker, dict) and isinstance(marker.get('content'), str) else None


def classify_archive(archive, original, original_sha256=None):
    """
    'clean': the same bytes as the scan; 'ours': drawn here from that scan and not changed since (its pixels still
    match the marker's digest); 'foreign': anything else, e.g. edited by hand or with the marker kept by an editor.
    Only 'clean' and 'ours' may be overwritten or restored.
    """
    if files_equal(archive, original):
        return 'clean'
    marker = read_marker(archive)
    if not marker:
        return 'foreign'
    if original_sha256 is not None and marker.get('orig_sha256') != original_sha256:
        return 'foreign'
    try:
        return 'ours' if file_pixel_digest(archive) == marker['content'] else 'foreign'
    except OSError:
        return 'foreign'


class MarkBox(collections.namedtuple('MarkBox', 'mark_id cells xy anchor px box wanted')):
    """
    A placed mark: its cells, anchor point and anchor, font size, and the table's box (left, top, right, bottom) as
    drawn, kept inside the image; wanted is where the anchor alone would put it, which may stick out.
    """


def _font_height(font):
    try:
        ascent, descent = font.getmetrics()
        return ascent + descent
    except AttributeError:  # Pillow's old bitmap font
        return font.getbbox('0')[3]


def _cell_text(font, text):
    """A cell's text as drawn: MISSING becomes '-' in a font without it (Pillow's own font has no dash)."""
    return '-' if text == MISSING and not has_glyphs(font, MISSING) else text


def _table_layout(cells, px, font):
    """(width, height, line, padding across, padding down, first cell width) of a one-row table."""
    pad_x, pad_y = max(1, round(CELL_PADDING[0] * px)), max(1, round(CELL_PADDING[1] * px))
    line = max(1, round(px / 16))
    first = round(font.getlength(_cell_text(font, cells[0]))) + 2 * pad_x
    second = round(font.getlength(_cell_text(font, cells[1]))) + 2 * pad_x
    return first + second + 3 * line, _font_height(font) + 2 * pad_y + 2 * line, line, pad_x, pad_y, first


def table_image(cells, px, font, color=COLOR):
    """A one-row table, question number then score, in red on translucent white."""
    width, height, line, pad_x, pad_y, first = _table_layout(cells, px, font)
    image = Image.new('RGBA', (width, height), (255, 255, 255, BACKGROUND_ALPHA))
    draw = ImageDraw.Draw(image)
    red = tuple(color) + (255,)
    draw.rectangle((0, 0, width - 1, height - 1), outline=red, width=line)
    draw.rectangle((line + first, 0, 2 * line + first - 1, height - 1), fill=red)
    draw.text((line + pad_x, line + pad_y), _cell_text(font, cells[0]), font=font, fill=red)
    draw.text((2 * line + first + pad_x, line + pad_y), _cell_text(font, cells[1]), font=font, fill=red)
    return image


def _anchored(anchor, xy, width, height):
    across, down = anchor[0], anchor[1]
    left = xy[0] - width if across == 'r' else xy[0] - width / 2 if across == 'm' else xy[0]
    top = xy[1] - height if down == 'b' else xy[1] - height / 2 if down == 'm' else xy[1]
    return round(left), round(top)


def mark_boxes(template, texts, size, font_path, fonts=None):
    """A MarkBox for each placed mark of texts (mark id -> [question number, score]), in pixels of an image of size."""
    fonts = {} if fonts is None else fonts
    boxes = []
    for mark_id, cells in texts.items():
        pos = (template.get('marks') or {}).get(mark_id)
        if not pos:
            continue
        px = font_size(template, mark_id, size)
        font = fonts.get(px) or fonts.setdefault(px, load_font(font_path, px))
        width, height = _table_layout(cells, px, font)[:2]
        xy = (pos['x'] * size[0], pos['y'] * size[1])
        left, top = _anchored(pos['anchor'], xy, width, height)
        wanted = (left, top, left + width, top + height)
        left = min(max(0, left), max(0, size[0] - width))  # A shifted scan moves its marks; keep them whole
        top = min(max(0, top), max(0, size[1] - height))
        boxes.append(MarkBox(mark_id, cells, xy, pos['anchor'], px, (left, top, left + width, top + height), wanted))
    return boxes


def layout_problems(boxes, size):
    """Marks that would stick out of the image where they are placed (they are drawn moved inside it), and overlaps."""
    outside = [b.mark_id for b in boxes if b.wanted[0] < 0 or b.wanted[1] < 0 or b.wanted[2] > size[0] or b.wanted[3] > size[1]]
    overlaps = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a.box[0] < b.box[2] and b.box[0] < a.box[2] and a.box[1] < b.box[3] and b.box[1] < a.box[3]:
                overlaps.append((a.mark_id, b.mark_id))
    return outside, overlaps


def ink_ratio(gray, box, threshold=128):
    """Share of dark pixels (print or handwriting) under a box of a grayscale image."""
    left, top = max(0, int(box[0])), max(0, int(box[1]))
    right, bottom = min(gray.size[0], int(box[2])), min(gray.size[1], int(box[3]))
    if right <= left or bottom <= top:
        return 0.0
    histogram = gray.crop((left, top, right, bottom)).histogram()
    return sum(histogram[:threshold]) / max(1, sum(histogram))


def draw_marks(image, template, texts, font_path):
    """image with the marks drawn on a copy, as red tables, in a mode that can show red (with any transparency kept)."""
    keep_alpha = image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info)
    canvas = image.convert('RGBA')
    fonts = {}
    color = tuple(template.get('color') or COLOR)
    for box in mark_boxes(template, texts, canvas.size, font_path, fonts):
        canvas.alpha_composite(table_image(box.cells, box.px, fonts[box.px], color), (box.box[0], box.box[1]))
    return canvas if keep_alpha else canvas.convert('RGB')


def encode_marked(image, info, fmt, marker):
    """
    Bytes of the marked image with marker (plus the digest of the pixels the bytes decode to) embedded. A JPEG
    comment does not change the decoded pixels, so the digest is taken from an encoding without it and checked again.
    """
    options = {k: info[k] for k in ('dpi', 'icc_profile') if info.get(k)}
    if fmt == 'JPEG':
        image = image.convert('RGB') if image.mode != 'RGB' else image
        if info.get('exif'):
            options['exif'] = info['exif']
        plain = io.BytesIO()
        image.save(plain, 'JPEG', quality=JPEG_QUALITY, comment=b'', **options)
        digest = _decoded_digest(plain.getvalue())
        payload = json.dumps(dict(marker, content=digest), ensure_ascii=True, sort_keys=True).encode('ascii')
        out = io.BytesIO()
        image.save(out, 'JPEG', quality=JPEG_QUALITY, comment=JPEG_PREFIX + payload, **options)
    elif fmt == 'PNG':
        digest = pixel_digest(image)
        text = PngImagePlugin.PngInfo()
        text.add_text(MARKER_KEY, json.dumps(dict(marker, content=digest), ensure_ascii=True, sort_keys=True))
        out = io.BytesIO()
        image.save(out, 'PNG', pnginfo=text, **options)
    else:
        raise ValueError(f"unsupported image format {fmt}")
    data = out.getvalue()
    if _decoded_digest(data) != digest:
        raise RuntimeError("the marked image does not decode to the pixels it was checked with")
    return data, digest


def _decoded_digest(data):
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        return pixel_digest(im)


def image_format(path):
    ext = os.path.splitext(path)[1].lower()
    return 'PNG' if ext == '.png' else 'JPEG' if ext in ('.jpg', '.jpeg') else None


# --- Positions found by a model (box_2d: [ymin, xmin, ymax, xmax], 0-1000) ---

def parse_boxes(raw, allowed_ids):
    """
    Boxes a model returned, kept only when four finite numbers within 0-1000 in order; ids outside allowed_ids
    (and anything else unexpected) are dropped. Returns {'title': box, 'objective': box, qid: box}.
    """
    found = {}

    def box(value):
        if isinstance(value, dict):
            value = value.get('box_2d')
        if not (isinstance(value, (list, tuple)) and len(value) == 4 and all(is_number(v) for v in value)):
            return None
        ymin, xmin, ymax, xmax = (float(v) for v in value)
        if not (0 <= ymin < ymax <= 1000 and 0 <= xmin < xmax <= 1000):
            return None
        return [ymin, xmin, ymax, xmax]

    if not isinstance(raw, dict):
        return found
    for key in ('title', 'objective'):
        b = box(raw.get(key))
        if b:
            found[key] = b
    allowed = {normalize_qid(q) for q in allowed_ids}
    questions = raw.get('questions')
    if isinstance(questions, dict):
        for qid, value in questions.items():
            key = normalize_qid(qid)
            b = box(value)
            if key in allowed and b:
                found[key] = b
    return found


def anchors_from_boxes(template, boxes, size, font_path):
    """
    Candidate positions from boxes: each sub-question and the multiple-choice total right-aligned just left of its
    box, the total just right of the title (else left of it, else above it).
    """
    marks = {}
    w, h = size
    px = font_size(template, 'question', size)
    gap = 0.35 * px / w
    for mark_id in [OBJECTIVE] + list((template.get('items') or {}).get('subjective') or []):
        b = boxes.get(mark_id)
        if b:
            marks[mark_id] = {'x': max(0.0, b[1] / 1000 - gap), 'y': (b[0] + b[2]) / 2000, 'anchor': 'rm'}
    title = boxes.get('title')
    if title:
        total_px = font_size(template, TOTAL, size)
        width = _table_layout(preview_texts(template)[TOTAL], total_px, load_font(font_path, total_px))[0] / w
        gap_t = 0.5 * total_px / w
        y = (title[0] + title[2]) / 2000
        if title[3] / 1000 + gap_t + width <= 1:
            marks[TOTAL] = {'x': title[3] / 1000 + gap_t, 'y': y, 'anchor': 'lm'}
        elif title[1] / 1000 - gap_t - width >= 0:
            marks[TOTAL] = {'x': title[1] / 1000 - gap_t, 'y': y, 'anchor': 'rm'}
        else:
            marks[TOTAL] = {'x': (title[1] + title[3]) / 2000, 'y': max(0.0, title[0] / 1000 - 0.2 * total_px / h), 'anchor': 'mb'}
    return marks
