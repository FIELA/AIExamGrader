# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

"""
Scores written in red onto graded answer sheets: the multiple-choice total, each sub-question and the total, at the
positions of one template per exam. Pure functions (no Tk, no API); see score_marks_service for when they run.

A marked image carries a marker (JPEG comment / PNG text) with the SHA-256 of its decoded pixels, so a marked image
edited afterwards (editors keep the marker) is told apart from one this module wrote.
"""

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
RENDERER = 1  # Bump when the drawing changes, so that sheets drawn before are redrawn
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
ASPECT_TOLERANCE = 0.04  # A sheet whose width/height differs more from the template's sample is not marked

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
    texts = TRANSLATIONS.get(lang) or TRANSLATIONS['CN']
    return texts['mark_text_question'], texts['mark_text_objective'], texts['mark_text_total']


class SheetMarks:
    """What one sheet's marks say: texts by mark id, or the problems that keep the sheet from being marked."""

    def __init__(self, texts, problems):
        self.texts = texts
        self.problems = problems

    @property
    def ok(self):
        return not self.problems

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
    The marks for a saved report, checked against the template's question list rather than the report's own items:
    a sub-question the model skipped is reported missing even when the total left it out too. The total must equal
    the multiple-choice total plus the sub-questions. Any problem means the sheet is not marked at all.
    """
    fmt_question, fmt_objective, fmt_total = mark_texts(template.get('lang', 'CN'))
    items = template.get('items') or {}
    expected_objective, expected_subjective = items.get('objective') or [], items.get('subjective') or []
    problems = []
    details = data.get('details') if isinstance(data, dict) else None
    if not isinstance(details, list) or not details:
        return SheetMarks({}, [('mark_problem_no_details', {})])

    objective_ids, objective_scores, subjective_ids, subjective = [], [], [], {}
    for item in details:
        if not isinstance(item, dict) or item.get('question_id') in (None, ''):
            problems.append(('mark_problem_bad_item', {}))
            continue
        qid, score = normalize_qid(item['question_id']), item.get('score')
        if not is_number(score):
            problems.append(('mark_problem_bad_score', {'qid': item['question_id']}))
            continue
        if is_objective(item):
            objective_scores.append(score)
            if item['question_id'] != OBJ_ADJ:
                objective_ids.append(qid)
        else:
            subjective_ids.append(qid)
            subjective[qid] = score
            top = item.get('max_score')
            if score < 0 or (is_number(top) and score > top + 1e-9):
                problems.append(('mark_problem_range', {'qid': item['question_id'], 'score': format_score(score),
                                                        'max': format_score(top) if is_number(top) else '-'}))

    problems += _id_problems(subjective_ids, expected_subjective,
                             ('mark_problem_missing', 'mark_problem_extra', 'mark_problem_duplicate'))
    texts = {}
    if expected_objective:
        if objective_scores:
            problems += _id_problems(objective_ids, expected_objective,
                                     ('mark_problem_obj_missing', 'mark_problem_obj_extra', 'mark_problem_obj_duplicate'))
            objective_total = sum(objective_scores)
        elif is_number(data.get('legacy_obj_score')):
            objective_total = data['legacy_obj_score']  # Reports from before per-question details
        else:
            problems.append(('mark_problem_no_objective', {}))
            objective_total = 0
        if objective_total < 0:
            problems.append(('mark_problem_range', {'qid': OBJECTIVE, 'score': format_score(objective_total), 'max': '-'}))
        texts[OBJECTIVE] = fmt_objective.format(score=format_score(objective_total))
    else:
        if objective_scores:
            problems.append(('mark_problem_obj_extra', {'qids': '、'.join(sorted(set(objective_ids), key=qid_sort_key)) or OBJ_ADJ}))
        objective_total = 0

    total = data.get('total_score')
    if not is_number(total):
        problems.append(('mark_problem_bad_score', {'qid': 'total_score'}))
    elif abs(total - (objective_total + sum(subjective.values()))) > 1e-6:
        problems.append(('mark_problem_total', {'total': format_score(total),
                                                'sum': format_score(objective_total + sum(subjective.values()))}))
    if problems:
        return SheetMarks({}, problems)
    for qid in expected_subjective:
        texts[qid] = fmt_question.format(score=format_score(subjective[qid]))
    texts[TOTAL] = fmt_total.format(score=format_score(total))
    return SheetMarks(texts, [])


def preview_texts(template, max_scores=None):
    """The longest text each mark may show (its full score less half a point), for checking the layout."""
    fmt_question, fmt_objective, fmt_total = mark_texts(template.get('lang', 'CN'))
    items = template.get('items') or {}
    max_scores = max_scores or {}
    longest = lambda top: format_score(top - 0.5) if top >= 1 else format_score(top)
    texts = {}
    if items.get('objective'):
        top = sum(max_scores.get(q, 3) for q in items['objective'])
        texts[OBJECTIVE] = fmt_objective.format(score=longest(top))
    for qid in items.get('subjective') or []:
        texts[qid] = fmt_question.format(score=longest(max_scores.get(qid, 10)))
    top = sum(max_scores.get(q, 3) for q in items.get('objective') or []) + \
        sum(max_scores.get(q, 10) for q in items.get('subjective') or [])
    texts[TOTAL] = fmt_total.format(score=longest(max(top, 100)))
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


def layout_fits(template, size):
    """Same orientation and nearly the same width/height as the template's sample; it does not prove alignment."""
    ref = (template.get('reference') or {}).get('size') or [0, 0]
    if not (ref[0] and ref[1] and size[0] and size[1]):
        return False
    if (ref[0] >= ref[1]) != (size[0] >= size[1]):
        return False
    return abs((size[0] / size[1]) / (ref[0] / ref[1]) - 1) <= ASPECT_TOLERANCE


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


def stroke_width(px):
    return max(1, round(px / 22))


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
    The first installed font that draws all of text; None when none does. For text in ASCII only, None also means
    Pillow's own font will do (see font_problem).
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


def font_problem(lang, candidates=FONT_CANDIDATES):
    """(font path, missing) for the template's language; missing is True when the texts cannot be drawn."""
    sample = ''.join(mark_texts(lang)).replace('{score}', '0123456789.')
    path = find_font(sample, candidates)
    if path or sample.isascii():
        return path, False
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


def mark_boxes(template, texts, size, font_path, fonts=None):
    """(mark id, text, (x, y), anchor, px, box) for each placed mark; box is (left, top, right, bottom) in pixels."""
    fonts = {} if fonts is None else fonts
    boxes = []
    for mark_id, text in texts.items():
        pos = (template.get('marks') or {}).get(mark_id)
        if not pos:
            continue
        px = font_size(template, mark_id, size)
        font = fonts.get(px) or fonts.setdefault(px, load_font(font_path, px))
        xy = (pos['x'] * size[0], pos['y'] * size[1])
        left, top, right, bottom = font.getbbox(text, anchor=pos['anchor'], stroke_width=stroke_width(px))
        boxes.append((mark_id, text, xy, pos['anchor'], px, (xy[0] + left, xy[1] + top, xy[0] + right, xy[1] + bottom)))
    return boxes


def layout_problems(boxes, size):
    """Marks partly outside the image, and pairs of marks that overlap."""
    outside = [b[0] for b in boxes if b[5][0] < 0 or b[5][1] < 0 or b[5][2] > size[0] or b[5][3] > size[1]]
    overlaps = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a[5][0] < b[5][2] and b[5][0] < a[5][2] and a[5][1] < b[5][3] and b[5][1] < a[5][3]:
                overlaps.append((a[0], b[0]))
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
    """image with the marks drawn on a copy, in red with a thin white outline, in a mode that can show red."""
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        canvas, fill = image.convert('RGBA'), tuple(template.get('color') or COLOR) + (255,)
    else:
        canvas, fill = image.convert('RGB'), tuple(template.get('color') or COLOR)
    draw = ImageDraw.Draw(canvas)
    fonts = {}
    for mark_id, text, xy, anchor, px, _ in mark_boxes(template, texts, canvas.size, font_path, fonts):
        draw.text(xy, text, font=fonts[px], fill=fill, anchor=anchor,
                  stroke_width=stroke_width(px), stroke_fill=(255, 255, 255) + ((255,) if canvas.mode == 'RGBA' else ()))
    return canvas


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
        text = preview_texts(template)[TOTAL]
        font = load_font(font_path, total_px)
        width = font.getbbox(text, stroke_width=stroke_width(total_px))[2] / w
        gap_t = 0.5 * total_px / w
        y = (title[0] + title[2]) / 2000
        if title[3] / 1000 + gap_t + width <= 1:
            marks[TOTAL] = {'x': title[3] / 1000 + gap_t, 'y': y, 'anchor': 'lm'}
        elif title[1] / 1000 - gap_t - width >= 0:
            marks[TOTAL] = {'x': title[1] / 1000 - gap_t, 'y': y, 'anchor': 'rm'}
        else:
            marks[TOTAL] = {'x': (title[1] + title[3]) / 2000, 'y': max(0.0, title[0] / 1000 - 0.2 * total_px / h), 'anchor': 'mb'}
    return marks
