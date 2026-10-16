import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PIL import Image

from grader_engine import AIGraderEngine
from rubric_loader import RubricLoader, iter_pdf_page_images


def make_pdf(path, pages=2):
    images = [Image.new("RGB", (160, 200), color) for color in ("white", "lightgray")[:pages]]
    try:
        images[0].save(path, "PDF", save_all=True, append_images=images[1:])
    finally:
        for image in images:
            image.close()


def reply(text, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)])


class TestPdfRubric(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pdf = self.root / "rubric.PDF"
        make_pdf(self.pdf)
        self.loader = RubricLoader()
        self.engine = AIGraderEngine.__new__(AIGraderEngine)
        self.engine.provider = "OpenAI"
        self.engine.model_name = "synthetic-model"
        self.engine.client = Mock()
        self.client = self.engine.client.with_options.return_value

    def load(self):
        return self.loader.load(self.pdf, self.root / "grading_data", self.engine.convert_rubric_pdf)

    def test_scanned_pdf_is_rendered_and_original_preserved(self):
        original = self.pdf.read_bytes()
        pages = list((number, total, image.size, image.mode) for number, total, image in iter_pdf_page_images(self.pdf))
        self.assertEqual(pages, [(1, 2, (400, 500), "RGB"), (2, 2, (400, 500), "RGB")])
        self.assertEqual(self.pdf.read_bytes(), original)

    def test_openai_converts_all_pages_in_order_and_sends_real_images(self):
        self.client.chat.completions.create.side_effect = [reply("```markdown\n1. A (2 points)\n```"), reply("17(1). Reference answer, 4 points.")]
        progress = Mock()
        result = self.loader.load(self.pdf, self.root / "data", lambda path: self.engine.convert_rubric_pdf(path, progress))
        self.assertLess(result.text.index("1. A"), result.text.index("17(1)"))
        self.assertNotIn("```markdown", result.text)
        self.assertEqual(progress.call_args_list[0].args, (1, 2))
        self.assertEqual(progress.call_args_list[1].args, (2, 2))
        for call in self.client.chat.completions.create.call_args_list:
            image_url = call.kwargs["messages"][0]["content"][1]["image_url"]["url"]
            with Image.open(BytesIO(base64.b64decode(image_url.split(",", 1)[1]))) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (400, 500))
        self.assertEqual(result.path.read_text().strip(), result.text)
        self.assertEqual(self.engine.client.with_options.call_args.kwargs, {"timeout": 120, "max_retries": 0})

    def test_native_gemini_receives_live_page_images(self):
        self.engine.provider = "Gemini"
        self.engine.gemini_model = Mock()
        def respond(parts, **kwargs):
            self.assertIsInstance(parts[1], Image.Image)
            parts[1].getpixel((0, 0))
            self.assertEqual(kwargs["request_options"], {"timeout": 120, "retry": None})
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason=1)], text="1. A, 2 points.")
        self.engine.gemini_model.generate_content.side_effect = respond
        self.assertIn("1. A", self.load().text)
        self.assertEqual(self.engine.gemini_model.generate_content.call_count, 2)

    def test_failed_second_page_leaves_no_partial_markdown(self):
        self.client.chat.completions.create.side_effect = [reply("1. A"), TimeoutError("synthetic timeout")]
        with self.assertRaisesRegex(RuntimeError, "page 2/2"):
            self.load()
        self.assertFalse(list(self.root.rglob("*.md")))
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_truncated_empty_and_unreadable_replies_stop_conversion(self):
        for response in [reply("partial", "length"), reply(" "), reply("1. 【无法辨认】")]:
            with self.subTest(response=response):
                self.client.chat.completions.create.side_effect = None
                self.client.chat.completions.create.return_value = response
                with self.assertRaises((RuntimeError, ValueError)):
                    self.load()
                self.assertFalse(list(self.root.rglob("*.md")))

    def test_corrupt_pdf_does_not_call_model(self):
        self.pdf.write_bytes(b"not a PDF")
        with self.assertRaises(Exception):
            self.load()
        self.client.chat.completions.create.assert_not_called()

    def test_same_pdf_reuses_markdown_and_changed_pdf_keeps_history(self):
        convert = Mock(return_value="1. A, 2 points.")
        first = self.loader.load(self.pdf, self.root / "data", convert)
        reused = self.loader.load(self.pdf, self.root / "data", convert)
        self.assertTrue(reused.from_cache)
        convert.assert_called_once()
        original_text = first.path.read_bytes()
        make_pdf(self.pdf, pages=1)
        changed = self.loader.load(self.pdf, self.root / "data", convert)
        self.assertNotEqual(first.path, changed.path)
        self.assertEqual(first.path.read_bytes(), original_text)
        self.assertEqual(convert.call_count, 2)

    def test_edited_markdown_is_used_and_signature_changes(self):
        original = self.loader.load(self.pdf, self.root / "data", Mock(return_value="1. A"))
        original.path.write_text("1. B", encoding="utf-8")
        edited = self.loader.load(self.pdf, self.root / "data")
        self.assertEqual(edited.text, "1. B")
        self.assertNotEqual(edited.signature, original.signature)

    def test_concurrent_readers_only_convert_once(self):
        convert = Mock(return_value="1. A")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.loader.load(self.pdf, self.root / "data", convert), range(2)))
        convert.assert_called_once()
        self.assertEqual(results[0].text, results[1].text)

    def test_text_rubric_does_not_call_pdf_model(self):
        path = self.root / "rubric.md"
        text = "  1. A, 2 points.\n\n"
        path.write_text("\ufeff" + text, encoding="utf-8")
        convert = Mock()
        self.assertEqual(self.loader.load(path, convert_pdf=convert).text, text)
        convert.assert_not_called()

    def test_source_modified_during_conversion_does_not_commit_output(self):
        def change_source(path):
            Path(path).write_bytes(b"changed")
            return "1. A"
        with self.assertRaisesRegex(ValueError, "changed during conversion"):
            self.loader.load(self.pdf, self.root / "data", change_source)
        self.assertFalse(list(self.root.rglob("*.md")))


if __name__ == "__main__":
    unittest.main()
