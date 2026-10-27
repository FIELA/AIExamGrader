"""The score-position dialog: placing and dragging marks, correcting the question list, and what keeps it from enabling."""
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image, ImageDraw

import score_marks as sm
import score_marks_dialog
from score_marks_dialog import CHAIN, MANAGE, ScoreMarksDialog
from test_score_marks import scan, template
from translations import TRANSLATIONS


def t(key, **values):
    text = TRANSLATIONS['CN'][key]
    return text.format(**values) if values else text


def event(x, y):
    return types.SimpleNamespace(x=x, y=y)


class DialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        for job in cls.root.tk.call('after', 'info'):  # customtkinter's own timers, not to fire on a destroyed root
            cls.root.after_cancel(job)
        cls.root.destroy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sample = str(scan(Path(self.tmp.name) / 'sample.jpg', quality=90))
        self.done = []

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, tpl, mode=CHAIN, **options):
        dialog = ScoreMarksDialog(self.root, t, tpl, [self.sample], mode,
                                  lambda action, result: self.done.append((action, result)), **options)
        dialog.scale = 0.5  # 1200 x 850 sample shown at 600 x 425
        dialog.redraw()
        dialog.update()
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        return dialog

    def blank(self):
        tpl = template()
        tpl['marks'] = {}
        tpl['status'] = sm.DRAFT
        return tpl

    def place_all(self, dialog):
        spots = {sm.TOTAL: (400, 30), sm.OBJECTIVE: (150, 110), '17(1)': (120, 190), '17(2)': (120, 240)}
        for mark_id, (x, y) in spots.items():
            dialog.select(mark_id)
            dialog.on_press(event(x, y))
            dialog.on_release(event(x, y))


class TestPlacing(DialogTest):
    def test_a_click_places_the_selected_score_and_moves_on(self):
        dialog = self.open(self.blank())
        self.assertEqual(dialog.selected, sm.TOTAL)  # The first score still to place
        dialog.on_press(event(300, 30))
        dialog.on_release(event(300, 30))
        self.assertEqual(dialog.template['marks'][sm.TOTAL], {'anchor': 'mm', 'x': 0.5, 'y': round(30 / 425, 5)})
        self.assertEqual(dialog.selected, sm.OBJECTIVE)

    def test_dragging_a_score_moves_it(self):
        dialog = self.open(self.blank())
        self.place_all(dialog)
        before = dict(dialog.template['marks']['17(1)'])
        x, y = before['x'] * 600, before['y'] * 425
        self.assertEqual(before['anchor'], 'rm')  # The score ends where it was placed
        dialog.on_press(event(x - 6, y))  # On the drawn score, left of that point
        self.assertEqual(dialog.selected, '17(1)')
        dialog.on_motion(event(x + 14, y + 10))
        dialog.on_release(event(x + 14, y + 10))
        after = dialog.template['marks']['17(1)']
        self.assertAlmostEqual(after['x'], before['x'] + 20 / 600, places=4)
        self.assertAlmostEqual(after['y'], before['y'] + 10 / 425, places=4)

    def test_enabling_waits_until_every_score_is_placed(self):
        dialog = self.open(self.blank())
        with patch.object(score_marks_dialog.messagebox, 'showwarning') as warning:
            dialog.finish('enable')
        warning.assert_called_once()
        self.assertIn('还没放置', warning.call_args[0][1])
        self.assertEqual(self.done, [])
        self.place_all(dialog)
        dialog.finish('enable')
        action, result = self.done[0]
        self.assertEqual(action, 'enable')
        self.assertEqual(sm.unplaced_marks(result), [])
        self.assertEqual(result['reference']['size'], [1200, 850])
        self.assertEqual(result['reference']['sha256'], sm.file_sha256(self.sample))

    def test_each_preview_is_the_table_the_sheets_get(self):
        dialog = self.open(self.blank())
        self.place_all(dialog)
        cells = {box.mark_id: box.cells for box in dialog.boxes()}
        self.assertEqual(cells[sm.TOTAL][0], '总分')
        self.assertEqual(cells[sm.OBJECTIVE][0], '选择题')
        self.assertEqual(cells['17(1)'], ['17(1)', '9.5分'])  # Its number, and the widest score it may show
        canvas = dialog.canvas
        kinds = [canvas.type(i) for i in canvas.find_all() if 'bg' not in canvas.gettags(i)]
        self.assertEqual(kinds.count('image'), 4)  # One table per placed score...
        self.assertEqual(kinds.count('text'), 0)  # ...and no separate numbers beside them

    def test_closing_the_window_before_grading_skips_for_now(self):
        dialog = self.open(self.blank())
        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.done[0][0], 'skip')
        dialog = self.open(template(), mode=MANAGE)
        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.done[1][0], 'close')

    def test_overlaps_and_writing_under_a_score_are_pointed_out(self):
        with Image.open(self.sample) as im:
            written = im.convert('RGB')
        ImageDraw.Draw(written).rectangle((640, 560, 880, 620), fill='black')  # An answer written there
        written.save(self.sample, 'JPEG', quality=90)
        dialog = self.open(self.blank())
        self.place_all(dialog)
        self.assertEqual(dialog.lbl_warn.cget('text'), '')
        pos = dialog.template['marks']['17(1)']
        dialog.template['marks']['17(2)'] = dict(pos)  # Right on top of 17(1)
        dialog.draw_marks()
        self.assertIn('相互重叠', dialog.lbl_warn.cget('text'))
        dialog.template['marks']['17(2)'] = {'x': 0.63, 'y': 0.69, 'anchor': 'mm'}  # On the answer
        dialog.draw_marks()
        self.assertIn('可能压住笔迹：17(2)', dialog.lbl_warn.cget('text'))
        # Printed lines under a score are not writing
        dialog.template['marks']['17(2)'] = {'x': 0.3, 'y': 0.47, 'anchor': 'mm'}
        dialog.draw_marks()
        self.assertEqual(dialog.lbl_warn.cget('text'), '')


class TestList(DialogTest):
    def test_the_question_list_can_be_corrected(self):
        dialog = self.open(self.blank())
        dialog.entry_qid.insert(0, '20')
        dialog.add_item('subjective')
        self.assertIn('20', dialog.template['items']['subjective'])
        self.assertEqual(dialog.selected, '20')  # Ready to be placed
        dialog.entry_qid.insert(0, '2')
        dialog.add_item('subjective')  # Not multiple choice after all
        self.assertNotIn('2', dialog.template['items']['objective'])
        self.assertIn('2', dialog.template['items']['subjective'])
        dialog.entry_qid.insert(0, '２０')  # Full-width digits are the same question
        dialog.remove_item()
        self.assertNotIn('20', dialog.template['items']['subjective'])

    def test_a_missing_chinese_font_blocks_enabling(self):
        with patch.object(score_marks_dialog.sm, 'font_problem', return_value=(None, True)):
            dialog = self.open(template())
        self.assertIn('找不到能显示中文的字体', dialog.lbl_warn.cget('text'))
        with patch.object(score_marks_dialog.messagebox, 'showwarning') as warning:
            dialog.finish('enable')
        self.assertIn('找不到能显示中文的字体', warning.call_args[0][1])
        dialog.set_lang('English')  # English texts need no Chinese font
        self.assertEqual(dialog.template['lang'], 'EN')

    def test_located_positions_fill_only_the_scores_not_placed_yet(self):
        dialog = self.open(self.blank(), locate=lambda path, tpl: {})
        dialog.on_press(event(300, 30))  # Total placed by hand
        dialog.on_release(event(300, 30))
        by_hand = dict(dialog.template['marks'][sm.TOTAL])
        found = {sm.TOTAL: {'x': 0.9, 'y': 0.05, 'anchor': 'lm'}, '17(1)': {'x': 0.2, 'y': 0.45, 'anchor': 'rm'},
                 '99': {'x': 0.5, 'y': 0.5, 'anchor': 'rm'}}
        with patch.object(score_marks_dialog.messagebox, 'showinfo') as info:
            dialog.located(found, None)
        self.assertIn('2/4', info.call_args[0][1])  # 99 is not on the list
        self.assertEqual(dialog.template['marks'][sm.TOTAL], by_hand)
        self.assertEqual(dialog.template['marks']['17(1)'], found['17(1)'])
        self.assertNotIn('99', dialog.template['marks'])
        dialog.reset_candidates()
        self.assertEqual(dialog.template['marks'][sm.TOTAL], found[sm.TOTAL])
        with patch.object(score_marks_dialog.messagebox, 'showwarning') as warning:
            dialog.located(None, 'API key required')
        self.assertIn('API key required', warning.call_args[0][1])


if __name__ == '__main__':
    unittest.main()
