"""
Scores written in red on graded sheets (score_marks): the tables each sheet gets (question number, score), what is
flagged when a report does not add up (the sheet is marked all the same), and that drawing never touches the scan and
can always be told apart from an image edited afterwards.
"""
import io
import math
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin

import score_marks as sm


def report(objective=(), subjective=(), total=None, **extra):
    """A saved report: objective [(qid, score)], subjective [(qid, score, max)]."""
    details = [{'question_id': q, 'type': '客观题', 'score': s, 'max_score': 3} for q, s in objective]
    details += [{'question_id': q, 'type': '主观题', 'score': s, 'max_score': m} for q, s, m in subjective]
    if total is None:
        total = sum(s for _, s in objective) + sum(s for _, s, _ in subjective)
    return dict({'details': details, 'total_score': total, 'original_filename': 'scan.jpg'}, **extra)


def template(objective=('1', '2'), subjective=('17(1)', '17(2)'), lang='CN', size=(1200, 850)):
    t = sm.new_template({'objective': list(objective), 'subjective': list(subjective)}, lang, list(size))
    marks = {sm.TOTAL: {'x': 0.6, 'y': 0.06, 'anchor': 'lm'}}
    if objective:
        marks[sm.OBJECTIVE] = {'x': 0.25, 'y': 0.25, 'anchor': 'rm'}
    for i, qid in enumerate(subjective):
        marks[qid] = {'x': 0.2, 'y': 0.45 + 0.12 * i, 'anchor': 'rm'}
    t['marks'] = marks
    t['status'] = sm.ENABLED
    return t


def scan(path, size=(1200, 850), mode='RGB', fmt='JPEG', **save):
    """A synthetic scan: printed frames and lines in black on white."""
    image = Image.new('RGB', size, 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, size[0] - 40, size[1] - 40), outline='black', width=4)
    for y in range(int(size[1] * 0.45), size[1] - 60, 50):
        draw.line((300, y, size[0] - 80, y), fill='black', width=2)
    image.convert(mode).save(path, fmt, **save)
    return path


def is_red(pixel):
    return pixel[0] > 150 and pixel[1] < 90 and pixel[2] < 90


def render(original, out, t, texts):
    picture, info, _ = sm.open_normalized(original)
    drawn = sm.draw_marks(picture, t, texts, sm.font_problem(t['lang'])[0])
    payload, digest = sm.encode_marked(drawn, info, sm.image_format(out), {
        'v': sm.SCHEMA, 'tpl': sm.template_hash(t), 'scores': 'x', 'renderer': sm.RENDERER,
        'orig': os.path.basename(original), 'orig_sha256': sm.file_sha256(original)})
    Path(out).write_bytes(payload)
    return digest


class TestSheetMarks(unittest.TestCase):
    def test_marks_follow_the_saved_scores(self):
        marks = sm.sheet_marks(report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2.5, 4)]), template())
        self.assertEqual(marks.warnings, [])
        self.assertEqual(marks.texts, {sm.OBJECTIVE: ['选择题', '6分'], '17(1)': ['17(1)', '2分'], '17(2)': ['17(2)', '2.5分'],
                                       sm.TOTAL: ['总分', '10.5分']})
        changed = sm.sheet_marks(report([('1', 3), ('2', 0)], [('17(1)', 2, 4), ('17(2)', 2.5, 4)]), template())
        self.assertNotEqual(marks.digest, changed.digest)
        english = sm.sheet_marks(report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 0, 4)]), template(lang='EN'))
        self.assertEqual(english.texts[sm.OBJECTIVE], ['MC', '6 pts'])
        self.assertEqual(english.texts['17(2)'], ['17(2)', '0 pts'])
        self.assertEqual(english.texts[sm.TOTAL], ['Total', '8 pts'])

    def test_the_review_objective_correction_counts_in_the_multiple_choice_total(self):
        data = report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4)], total=8)
        data['details'].append({'question_id': sm.OBJ_ADJ, 'type': '客观题修正', 'score': -2})
        marks = sm.sheet_marks(data, template())
        self.assertEqual(marks.warnings, [])
        self.assertEqual(marks.texts[sm.OBJECTIVE], ['选择题', '4分'])
        self.assertNotIn(sm.OBJ_ADJ, marks.texts)  # Not a sub-question of its own

    def test_a_sub_question_the_model_skipped_is_written_as_missing_even_when_the_total_agrees(self):
        # The total left 17(2) out too, so only the template's question list shows it is missing
        marks = sm.sheet_marks(report([('1', 3), ('2', 3)], [('17(1)', 2, 4)]), template())
        self.assertIn(('mark_problem_missing', {'qids': '17(2)'}), marks.warnings)
        self.assertEqual(marks.texts['17(2)'], ['17(2)', sm.MISSING])  # Written, and plainly without a score
        self.assertEqual(marks.texts[sm.TOTAL], ['总分', '8分'])

    def test_extra_repeated_and_full_width_ids(self):
        data = report([('1', 3), ('2', 3)], [('17（1）', 2, 4), ('17(1)', 1, 4), ('17(2)', 2, 4), ('20', 1, 5)])
        marks = sm.sheet_marks(data, template())
        keys = [key for key, _ in marks.warnings]
        self.assertIn('mark_problem_duplicate', keys)  # 17（1） is 17(1)
        self.assertIn('mark_problem_extra', keys)
        self.assertEqual(marks.texts['17(1)'], ['17(1)', '2分'])  # The first of the repeated scores
        self.assertNotIn('20', marks.texts)  # No position for it: in the warning only
        data = report([('1', 3), ('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4)])
        self.assertIn('mark_problem_obj_duplicate', [key for key, _ in sm.sheet_marks(data, template()).warnings])
        data = report([('1', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4)])
        self.assertIn(('mark_problem_obj_missing', {'qids': '2'}), sm.sheet_marks(data, template()).warnings)

    def test_the_total_must_equal_the_questions(self):
        marks = sm.sheet_marks(report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4)], total=11), template())
        self.assertEqual(marks.warnings, [('mark_problem_total', {'total': '11', 'sum': '10'})])
        self.assertEqual(marks.texts[sm.TOTAL], ['总分', '11分'])  # The total the report and the summary record

    def test_invalid_and_out_of_range_scores(self):
        for bad in (True, None, '2', math.nan, math.inf):
            data = report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4)])
            data['details'][2]['score'] = bad
            marks = sm.sheet_marks(data, template())
            self.assertIn('mark_problem_bad_score', [key for key, _ in marks.warnings], bad)
            self.assertEqual(marks.texts['17(1)'], ['17(1)', sm.MISSING])
        too_high = report([('1', 3), ('2', 3)], [('17(1)', 5, 4), ('17(2)', 2, 4)])
        self.assertIn('mark_problem_range', [k for k, _ in sm.sheet_marks(too_high, template()).warnings])
        negative = report([('1', 3), ('2', 3)], [('17(1)', -1, 4), ('17(2)', 2, 4)])
        self.assertIn('mark_problem_range', [k for k, _ in sm.sheet_marks(negative, template()).warnings])
        empty = sm.sheet_marks({'details': [], 'total_score': 0}, template())
        self.assertIn(('mark_problem_no_details', {}), empty.warnings)
        self.assertEqual(empty.texts[sm.TOTAL], ['总分', '0分'])
        self.assertEqual(empty.texts[sm.OBJECTIVE], ['选择题', sm.MISSING])

    def test_legacy_objective_total_and_absent_sheets(self):
        data = report((), [('17(1)', 2, 4), ('17(2)', 2, 4)], total=10, legacy_obj_score=6)
        marks = sm.sheet_marks(data, template())
        self.assertEqual(marks.warnings, [])
        self.assertEqual(marks.texts[sm.OBJECTIVE], ['选择题', '6分'])
        zeroed = sm.sheet_marks(report([('1', 0), ('2', 0)], [('17(1)', 0, 4), ('17(2)', 0, 4)]), template())
        self.assertEqual(zeroed.texts[sm.TOTAL], ['总分', '0分'])  # A sheet confirmed absent shows its zeros
        no_mc = sm.sheet_marks(report((), [('17(1)', 2, 4), ('17(2)', 2, 4)]), template(objective=()))
        self.assertEqual(no_mc.warnings, [])
        self.assertNotIn(sm.OBJECTIVE, no_mc.texts)

    def test_scores_are_written_plainly(self):
        self.assertEqual([sm.format_score(v) for v in (2, 2.0, 2.5, 2.25, 0, -0.0)], ['2', '2', '2.5', '2.25', '0', '0'])


class TestQuestionLists(unittest.TestCase):
    def test_answer_key_guess(self):
        items = sm.items_from_answer_key({'1': 'A', '2': 'BD', '5': '√', '17(1)': 'P', '17（2）': '北', '20': '论述'})
        self.assertEqual(items['objective'], ['1', '2'])
        self.assertEqual(items['subjective'], ['5', '17(1)', '17(2)', '20'])
        self.assertEqual(items['source'], 'answer_key')

    def test_reports_give_the_ids_most_of_them_have(self):
        full = report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4)])
        skipped = report([('1', 3), ('2', 3)], [('17(1)', 2, 4)])  # The model left out 17(2)
        odd = report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2, 4), ('99', 1, 1)])
        items = sm.items_from_reports([full, skipped, odd])
        self.assertEqual(items['objective'], ['1', '2'])
        self.assertEqual(items['subjective'], ['17(1)', '17(2)'])
        t = template()
        self.assertTrue(sm.ids_match(t, full))
        self.assertFalse(sm.ids_match(t, skipped))
        self.assertEqual(sm.ids_difference(t, odd), ([], ['99']))


class TestTemplate(unittest.TestCase):
    def test_validation_and_fingerprint(self):
        t = template()
        self.assertEqual(sm.validate_template(t), [])
        self.assertEqual(sm.unplaced_marks(t), [])
        fingerprint = sm.template_hash(t)
        self.assertEqual(sm.template_hash(dict(t, status=sm.DISABLED, reference={'size': [9, 9]})), fingerprint)
        moved = template()
        moved['marks']['17(1)']['x'] = 0.21
        self.assertNotEqual(sm.template_hash(moved), fingerprint)
        broken = dict(t, marks={'17(1)': {'x': 2, 'y': 0.5, 'anchor': 'rm'}}, lang='FR')
        self.assertTrue(sm.validate_template(broken))
        del t['marks']['17(2)']
        self.assertEqual(sm.unplaced_marks(t), ['17(2)'])

    def test_scans_cropped_differently_are_all_marked(self):
        t = template(size=(2290, 3072))
        for size in ((2022, 3072), (2520, 3072), (2290, 3072)):  # Widths of one exam's scans, 11% either way
            self.assertTrue(sm.same_orientation(t, size))
        self.assertFalse(sm.same_orientation(t, (3072, 2290)))  # Turned: marked, with a warning

    def test_layout_problems(self):
        t = template()
        texts = {m: v for m, v in sm.preview_texts(t).items()}
        font = sm.font_problem('CN')[0]
        self.assertEqual(sm.layout_problems(sm.mark_boxes(t, texts, (1200, 850), font), (1200, 850)), ([], []))
        t['marks']['17(1)'] = {'x': 0.01, 'y': 0.45, 'anchor': 'rm'}  # Right-aligned at the left edge: would stick out
        t['marks']['17(2)'] = {'x': 0.6, 'y': 0.06, 'anchor': 'lm'}  # On top of the total
        boxes = sm.mark_boxes(t, texts, (1200, 850), font)
        outside, overlaps = sm.layout_problems(boxes, (1200, 850))
        self.assertEqual(outside, ['17(1)'])
        self.assertEqual(overlaps, [('17(2)', sm.TOTAL)])
        moved = next(b for b in boxes if b.mark_id == '17(1)')
        self.assertLess(moved.wanted[0], 0)
        self.assertEqual(moved.box[0], 0)  # Drawn whole, moved just inside the image

    def test_boxes_from_a_model(self):
        raw = {'title': [40, 300, 80, 700], 'objective': {'box_2d': [200, 250, 300, 500]},
               'questions': {'17（1）': [450, 210, 480, 240], '17(2)': [600, 500, 580, 520],  # ymin > ymax
                             '18(1)': [1, 2, 3, 4], '17(3)': [10, 20, math.nan, 40]}}
        boxes = sm.parse_boxes(raw, ['17(1)', '17(2)', '17(3)'])
        self.assertEqual(set(boxes), {'title', 'objective', '17(1)'})  # 18(1) was not asked for
        t = template(subjective=('17(1)',))
        anchors = sm.anchors_from_boxes(t, boxes, (1200, 850), sm.font_problem('CN')[0])
        self.assertEqual(anchors['17(1)']['anchor'], 'rm')
        self.assertLess(anchors['17(1)']['x'], 0.21)  # Ends just left of the question number
        self.assertAlmostEqual(anchors['17(1)']['y'], 0.465)
        self.assertEqual(anchors[sm.TOTAL]['anchor'], 'lm')  # Right of the title
        wide_title = sm.anchors_from_boxes(t, {'title': [40, 50, 80, 990]}, (1200, 850), sm.font_problem('CN')[0])
        self.assertEqual(wide_title[sm.TOTAL]['anchor'], 'mb')  # No room beside it: above it

    def test_fonts(self):
        self.assertEqual(sm.font_problem('CN', candidates=()), (None, True))  # Chinese texts need a font
        self.assertEqual(sm.font_problem('EN', candidates=()), (None, False))  # Pillow's own font draws ASCII
        path, missing = sm.font_problem('CN')
        self.assertFalse(missing)
        self.assertTrue(sm.has_glyphs(sm.load_font(path, 30), '选择题总分'))
        self.assertFalse(sm.has_glyphs(sm.load_font(None, 30), '总分'))


class TestDrawing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def texts(self, t):
        return sm.sheet_marks(report([('1', 3), ('2', 3)], [('17(1)', 2, 4), ('17(2)', 2.5, 4)]), t).texts

    def test_drawing_is_repeatable_and_leaves_the_scan_alone(self):
        original = scan(self.dir / 'scan.jpg', quality=90)
        before = sm.file_sha256(original)
        t = template()
        out = self.dir / 'graded.jpg'
        digest = render(original, out, t, self.texts(t))
        self.assertEqual(sm.file_sha256(original), before)
        marker = sm.read_marker(out)
        self.assertEqual(marker['content'], digest)
        self.assertEqual(marker['orig_sha256'], before)
        self.assertEqual(sm.classify_archive(out, original, before), 'ours')
        self.assertEqual(sm.classify_archive(original, original), 'clean')
        # Drawn again from the scan: the same image, so marks never pile up
        self.assertEqual(render(original, self.dir / 'again.jpg', t, self.texts(t)), digest)
        with Image.open(out) as im:
            x, y = int(0.2 * im.size[0]) - 12, int(0.45 * im.size[1])  # Just left of where 17(1)'s score ends
            self.assertTrue(any(is_red(im.getpixel((x - dx, y + dy))) for dx in range(0, 40, 2) for dy in range(-6, 7, 2)))
            self.assertFalse(is_red(im.getpixel((int(0.9 * im.size[0]), int(0.9 * im.size[1])))))

    def test_an_edited_marked_image_is_not_ours_even_with_the_marker(self):
        original = scan(self.dir / 'scan.jpg', quality=90)
        t = template()
        out = self.dir / 'graded.jpg'
        render(original, out, t, self.texts(t))
        with Image.open(out) as im:
            edited = im.convert('RGB')
            ImageDraw.Draw(edited).line((500, 500, 700, 520), fill='blue', width=6)  # Written on by hand
            edited.save(out, 'JPEG', quality=93)  # Pillow keeps the comment, so the marker stays
        self.assertIsNotNone(sm.read_marker(out))
        self.assertEqual(sm.classify_archive(out, original, sm.file_sha256(original)), 'foreign')
        # A marker that names another scan does not count either
        render(original, out, t, self.texts(t))
        self.assertEqual(sm.classify_archive(out, original, 'another scan'), 'foreign')

    def test_png_keeps_transparency_and_marker(self):
        original = self.dir / 'scan.png'
        image = Image.new('RGBA', (1200, 850), (255, 255, 255, 0))
        ImageDraw.Draw(image).rectangle((40, 40, 1160, 810), outline=(0, 0, 0, 255), width=4)
        image.save(original)
        t = template()
        out = self.dir / 'graded.png'
        render(original, out, t, self.texts(t))
        with Image.open(out) as im:
            self.assertEqual((im.format, im.mode), ('PNG', 'RGBA'))
            self.assertEqual(im.getpixel((600, 800))[3], 0)  # Still see-through where nothing is drawn
        self.assertEqual(sm.classify_archive(out, original, sm.file_sha256(original)), 'ours')
        with Image.open(out) as im:
            info = PngImagePlugin.PngInfo()
            for key, value in im.info.items():
                if isinstance(value, str):
                    info.add_text(key, value)
            edited = im.copy()
            ImageDraw.Draw(edited).line((500, 500, 700, 520), fill=(0, 0, 255, 255), width=6)
        edited.save(out, pnginfo=info)
        self.assertIsNotNone(sm.read_marker(out))
        self.assertEqual(sm.classify_archive(out, original, sm.file_sha256(original)), 'foreign')

    def test_grayscale_scans_show_red(self):
        original = scan(self.dir / 'gray.jpg', mode='L', quality=90)
        t = template()
        out = self.dir / 'graded.jpg'
        render(original, out, t, self.texts(t))
        with Image.open(out) as im:
            self.assertEqual(im.mode, 'RGB')
            pixels = im.crop((0, 0, 600, 425)).tobytes()
            self.assertTrue(any(is_red(pixels[i:i + 3]) for i in range(0, len(pixels), 3)))

    def test_a_turned_scan_is_drawn_as_shown_and_not_turned_again(self):
        original = self.dir / 'turned.jpg'
        stored = Image.new('RGB', (850, 1200), 'white')  # Stored upright-portrait, shown landscape (orientation 6)
        exif = stored.getexif()
        exif[0x0112] = 6
        stored.save(original, 'JPEG', quality=90, exif=exif.tobytes(), dpi=(300, 300))
        self.assertEqual(sm.normalized_size(original), (1200, 850))
        t = template()
        out = self.dir / 'graded.jpg'
        render(original, out, t, self.texts(t))
        with Image.open(out) as im:
            self.assertEqual(im.size, (1200, 850))
            self.assertIn(im.getexif().get(0x0112), (None, 1))
            self.assertEqual(tuple(round(v) for v in im.info.get('dpi')), (300, 300))

    def test_each_mark_is_a_table_of_question_number_and_score(self):
        font = sm.load_font(sm.font_problem('CN')[0], 40)
        table = sm.table_image(['26(1)', '4分'], 40, font)
        w, h = table.size
        red = lambda p: p[0] > 200 and p[1] < 40 and p[2] < 40 and p[3] == 255
        self.assertTrue(all(red(table.getpixel(p)) for p in ((0, 0), (w - 1, h - 1), (w // 2, 0), (0, h // 2))))  # Frame
        dividers = [x for x in range(3, w - 3) if all(red(table.getpixel((x, y))) for y in range(h))]
        self.assertTrue(dividers, 'a line between the two cells')
        self.assertLess(dividers[0], w * 0.75)  # The question number's cell comes first
        self.assertEqual(table.getpixel((dividers[0] - 3, 3))[:3], (255, 255, 255))  # Translucent white inside
        self.assertEqual(table.getpixel((dividers[0] - 3, 3))[3], sm.BACKGROUND_ALPHA)
        wider = sm.table_image(['26(1)', '10.5分'], 40, font)
        self.assertGreater(wider.size[0], w)
        self.assertEqual(wider.size[1], h)  # Same height whatever the score

    def test_writing_under_a_table_still_shows(self):
        image = Image.new('RGB', (1200, 850), 'white')
        ImageDraw.Draw(image).rectangle((0, 300, 1200, 600), fill='black')  # An answer under every mark
        t = template()
        drawn = sm.draw_marks(image, t, self.texts(t), sm.font_problem('CN')[0])
        box = next(b for b in sm.mark_boxes(t, self.texts(t), image.size, sm.font_problem('CN')[0]) if b.mark_id == '17(1)')
        inside = drawn.getpixel((box.box[0] + 3, box.box[1] + 3))
        self.assertTrue(all(150 < v < 250 for v in inside), inside)  # Lightened, not hidden
        self.assertEqual(drawn.getpixel((1100, 450)), (0, 0, 0))  # Away from the marks: untouched

    def test_ink_under_a_mark(self):
        gray = Image.new('L', (100, 100), 255)
        ImageDraw.Draw(gray).rectangle((0, 0, 49, 99), fill=0)
        self.assertAlmostEqual(sm.ink_ratio(gray, (0, 0, 100, 100)), 0.5, places=2)
        self.assertEqual(sm.ink_ratio(gray, (60, 0, 100, 100)), 0.0)


if __name__ == '__main__':
    unittest.main()
