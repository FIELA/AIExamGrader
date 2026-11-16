"""An exam's rubric, answer sheet folder and student list usually sit in one folder: the dialogs open there and
picking one selects the others. An open button can only be clicked when there is something to open."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from AutoGrader import App
from config_manager import ConfigManager
from exam_resources import find_exam_resources, is_answer_sheet_folder
from theme import Theme
from translations import TRANSLATIONS

CN = TRANSLATIONS['CN']


def scan(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (8, 8), 'white').save(path)


def exam_directory(root, name='期中考', rubric='评分标准.txt', roster='名单.csv', folder='答题卡'):
    """An exam as teachers keep it: the scans in a folder, the rubric and the student list beside it."""
    directory = Path(root) / name
    scan(directory / folder / '01-01.png')
    if rubric:
        (directory / rubric).write_text('1. A (2 points)', encoding='utf-8')
    if roster:
        (directory / roster).write_text('姓名,班级\n张三,高二1班\n李四,高二1班\n', encoding='utf-8')
    return directory


class FindExamResources(unittest.TestCase):
    def test_an_exam_directory_holds_one_of_each(self):
        with tempfile.TemporaryDirectory() as root:
            directory = exam_directory(root)
            (directory / '.DS_Store').write_text('')
            (directory / '~$名单.xlsx').write_text('')  # Excel's lock file while the list is open
            (directory / '空文件夹').mkdir()
            self.assertEqual(find_exam_resources(directory), {'exam_folder': [str(directory / '答题卡')],
                                                              'rubric': [str(directory / '评分标准.txt')],
                                                              'student_list': [str(directory / '名单.csv')]})

    def test_a_graded_folder_is_still_an_answer_sheet_folder(self):
        with tempfile.TemporaryDirectory() as root:
            graded = Path(root) / '答题卡'
            scan(graded / '成功归档' / '01-01.png')  # Graded scans move out of the top of the folder
            self.assertTrue(is_answer_sheet_folder(graded))
            (Path(root) / 'empty').mkdir()
            self.assertFalse(is_answer_sheet_folder(Path(root) / 'empty'))
            self.assertFalse(is_answer_sheet_folder(Path(root) / 'missing'))

    def test_what_grading_made_is_no_resource(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            scan(folder / '成功归档' / '01-01.png')
            scan(folder / 'original_files' / '01-01.png')
            (folder / '成绩汇总表.csv').write_text('姓名,总分\n张三,90\n', encoding='utf-8')
            self.assertEqual(find_exam_resources(folder), {'exam_folder': [], 'rubric': [], 'student_list': []})


class ResourceSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_path = str(self.root / 'config.json')
        self.config = ConfigManager(self.config_path)
        with patch('AutoGrader.ConfigManager', return_value=self.config):
            self.app = App()
        self.app.withdraw()
        checking = patch.object(self.app, 'check_completion_status')  # Checks the exam's grading in a worker
        self.check = checking.start()
        self.addCleanup(checking.stop)

    def tearDown(self):
        self.app.score_marks.drain(10)
        self.app.destroy()
        self.tmp.cleanup()

    def pick(self, method, path):
        """Pick path in the dialog that method opens; returns the folder the dialog opened in."""
        dialog = 'askdirectory' if method == 'select_folder' else 'askopenfilename'
        with patch(f'AutoGrader.filedialog.{dialog}', return_value=str(path)) as ask:
            getattr(self.app, method)()
        return ask.call_args.kwargs['initialdir']

    def log(self):
        return self.app.log_box.get('1.0', 'end')

    def open_buttons(self):
        return [self.app.btn_rubric_open, self.app.btn_folder_open, self.app.btn_list_open]

    def selected(self):
        """The selected rubric, answer sheet folder and student list; None for one not selected."""
        return [path or None for path in (self.app.rubric_path, self.app.exam_folder, self.app.student_manager.student_path)]

    def test_a_profile_whose_files_are_gone_selects_nothing_and_says_so(self):
        gone = self.root / '已删除'
        self.config.save_profile('上次', {'rubric_path': str(gone / '评分标准.txt'), 'exam_folder': str(gone / '答题卡'),
                                         'student_list': str(gone / '名单.xlsx')})
        self.app.apply_profile(self.config.load_profile('上次'))

        self.assertEqual(self.selected(), [None, None, None])
        self.assertEqual([self.app.lbl_rubric_status.cget('text'), self.app.lbl_folder_status.cget('text'),
                          self.app.lbl_list_status.cget('text')],
                         [CN['status_not_selected'], CN['status_not_selected'], CN['status_not_uploaded']])
        for button in self.open_buttons():
            self.assertEqual(button.cget('state'), 'disabled')
            self.assertNotEqual(button.cget('fg_color'), Theme.INFO, 'a button that opens nothing looks it')
        with patch('AutoGrader.subprocess.call') as call:
            for button in self.open_buttons():
                button.invoke()
        call.assert_not_called()
        for name in ('评分标准.txt', '答题卡', '名单.xlsx'):
            self.assertIn(str(gone / name), self.log())

    def test_open_buttons_open_what_is_selected(self):
        directory = exam_directory(self.root)
        for button in self.open_buttons():
            self.assertEqual(button.cget('state'), 'disabled', 'nothing is selected yet')
        self.app.set_rubric(str(directory / '评分标准.txt'))
        self.app.set_exam_folder(str(directory / '答题卡'))
        self.app.set_student_list(str(directory / '名单.csv'))
        for button in self.open_buttons():
            self.assertEqual(button.cget('state'), 'normal')
            self.assertEqual(button.cget('fg_color'), Theme.INFO)
        with patch('AutoGrader.sys.platform', 'darwin'), patch('AutoGrader.subprocess.call') as call:
            for button in self.open_buttons():
                button.invoke()
        self.assertEqual([c.args[0] for c in call.call_args_list],
                         [['open', str(directory / name)] for name in ('评分标准.txt', '答题卡', '名单.csv')])

        (directory / '评分标准.txt').unlink()  # Moved away after it was selected
        with patch('AutoGrader.subprocess.call') as call:
            self.app.btn_rubric_open.invoke()
        call.assert_not_called()
        self.assertIn(str(directory / '评分标准.txt'), self.log())
        self.assertEqual(self.app.btn_rubric_open.cget('state'), 'disabled')

        self.app.clear_list()
        self.assertEqual(self.app.btn_list_open.cget('state'), 'disabled')
        self.assertEqual(self.app.student_manager.students, [])

    def test_picking_the_answer_sheet_folder_selects_the_rubric_and_list_beside_it(self):
        directory = exam_directory(self.root)
        self.pick('select_folder', directory / '答题卡')

        self.assertEqual(self.selected(), [str(directory / '评分标准.txt'), str(directory / '答题卡'), str(directory / '名单.csv')])
        self.assertEqual(len(self.app.student_manager.students), 2)
        self.assertEqual(self.app.lbl_rubric_status.cget('text'), '评分标准.txt')
        self.assertEqual(self.app.lbl_list_status.cget('text'), CN['status_students'].format(count=2))
        self.assertIn('评分标准.txt', self.log())
        self.assertIn('名单.csv', self.log())
        self.check.assert_called_once()  # All three are there: the exam is checked as when each is picked
        # The dialogs open in the exam's directory from now on, also after a restart
        self.assertEqual(self.pick('load_rubric', ''), str(directory))
        self.assertEqual(self.pick('load_student_list', ''), str(directory))
        self.assertEqual(self.pick('select_folder', ''), str(directory))
        self.assertEqual(ConfigManager(self.config_path).get('resource_dir'), str(directory))

    def test_picking_any_one_of_them_selects_the_others(self):
        directory = exam_directory(self.root)
        self.pick('load_student_list', directory / '名单.csv')
        self.assertEqual(self.selected(), [str(directory / '评分标准.txt'), str(directory / '答题卡'), str(directory / '名单.csv')])

    def test_the_next_exam_replaces_the_last_ones_resources(self):
        last = exam_directory(self.root, '周测')
        self.pick('select_folder', last / '答题卡')
        following = exam_directory(self.root, '期中考', rubric='期中-参考答案.pdf', roster='期中名单.csv')
        self.pick('select_folder', following / '答题卡')
        self.assertEqual(self.selected(), [str(following / '期中-参考答案.pdf'), str(following / '答题卡'),
                                           str(following / '期中名单.csv')])

    def test_a_file_that_is_no_student_list_does_not_replace_the_list(self):
        last = exam_directory(self.root, '周测')
        self.pick('select_folder', last / '答题卡')
        following = exam_directory(self.root, '期中考', roster='成绩.csv')
        (following / '成绩.csv').write_text('总分,排名\n90,1\n', encoding='utf-8')  # Neither names nor exam numbers
        self.pick('select_folder', following / '答题卡')
        self.assertEqual(self.app.student_manager.student_path, str(last / '名单.csv'))
        self.assertEqual(len(self.app.student_manager.students), 2)
        self.assertIn('成绩.csv', self.log())

    def test_nothing_is_guessed_where_it_is_unclear(self):
        directory = exam_directory(self.root)
        (directory / '试卷.pdf').write_text('the exam paper')  # Two candidates for the rubric
        self.pick('select_folder', directory / '答题卡')
        self.assertEqual(self.selected(), [None, str(directory / '答题卡'), str(directory / '名单.csv')])

        for clear in (self.app.clear_rubric, self.app.clear_folder, self.app.clear_list):
            clear()
        downloads = exam_directory(self.root, 'Downloads', folder='photo')  # A folder of everything: scans of two exams
        scan(downloads / 'scans' / 'a.jpg')
        self.pick('load_rubric', downloads / '评分标准.txt')
        self.assertEqual(self.selected(), [str(downloads / '评分标准.txt'), None, None])

    def test_work_under_way_keeps_its_exam(self):
        last = exam_directory(self.root, '周测')
        self.pick('select_folder', last / '答题卡')
        following = exam_directory(self.root, '期中考')
        self.app.processing = True
        try:
            self.pick('load_rubric', following / '评分标准.txt')
        finally:
            self.app.processing = False
        self.assertEqual(self.selected(), [str(following / '评分标准.txt'), str(last / '答题卡'), str(last / '名单.csv')])


if __name__ == '__main__':
    unittest.main()
