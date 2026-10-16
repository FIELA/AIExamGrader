"""Load text rubrics and retain complete, model-transcribed PDF conversions."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile
import threading


_PDF_RENDER_LOCK = threading.Lock()  # PDFium is not thread-safe.


def iter_pdf_page_images(path):
    import pypdfium2 as pdfium

    with _PDF_RENDER_LOCK, pdfium.PdfDocument(str(path)) as document:
        total = len(document)
        if not total:
            raise ValueError("The PDF contains no pages.")
        for index in range(total):
            page = document[index]
            try:
                width, height = page.get_size()
                if min(width, height) <= 0:
                    raise ValueError(f"Invalid PDF page size: {index + 1}")
                scale = min(2.5, 2400 / max(width, height))
                bitmap = page.render(scale=scale)
                try:
                    with bitmap.to_pil() as rendered:
                        image = rendered.convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
            try:
                yield index + 1, total, image
            finally:
                image.close()


@dataclass(frozen=True)
class RubricDocument:
    text: str
    path: Path
    source_digest: str
    from_cache: bool = False

    @property
    def signature(self):
        return {"source_sha256": self.source_digest,
                "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest()}


class RubricLoader:
    def __init__(self):
        self._lock = threading.Lock()

    def load(self, path, output_dir=None, convert_pdf=None):
        source = Path(path)
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if source.suffix.lower() in {".txt", ".md"}:
            text = data.decode("utf-8-sig")
            if not text.strip():
                raise ValueError("The rubric is empty.")
            return RubricDocument(text, source, digest)
        if source.suffix.lower() != ".pdf":
            raise ValueError("Supported rubric formats: TXT, Markdown, PDF.")
        if output_dir is None:
            raise ValueError("Select an answer sheet folder before converting a PDF rubric.")
        cache_key = hashlib.sha256(b"rubric-pdf-v1\0" + data).hexdigest()[:16]
        target = Path(output_dir) / "rubric" / f"{source.stem[:60]}-{cache_key}.md"
        with self._lock:
            if target.exists():
                text = target.read_text(encoding="utf-8-sig").strip()
                if not text:
                    raise ValueError(f"Converted rubric is empty: {target}")
                return RubricDocument(text, target, digest, from_cache=True)
            if convert_pdf is None:
                raise ValueError("The PDF rubric must be converted by the model first.")
            text = convert_pdf(str(source))
            if not isinstance(text, str) or not text.strip():
                raise ValueError("The model returned an empty PDF rubric.")
            text = text.strip()
            if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise ValueError("The PDF changed during conversion. Please retry.")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                                 prefix=".rubric-", suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(text + "\n")
                temporary.replace(target)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
            return RubricDocument(text, target, digest)
