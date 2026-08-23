"""
CareerCompass — Guarded PDF access

One place that opens a PDF, so that every caller inherits the same two
protections. Both parsers used to call `pdfplumber.open()` directly and both
were wrong in the same two ways.

**A size limit on the upload is not a size limit on the work.** The API caps
uploads at 20 MB, which bounds the *compressed* bytes. PDF content streams are
Flate-compressed, and repeated drawing operators compress extraordinarily well:
a 354 KB file whose content stream expands to 106 MB (295:1) is trivial to
build, and pdfminer then materialises one Python object per glyph. Measured on
this project, that file drove a server from 2.5 GB to 12.4 GB of RSS and the
kernel OOM killer took out the process — and a second, unrelated instance with
it. The guard therefore bounds the **decompressed content stream**, which is
the number that actually predicts the work, and it does so before any layout
object is built. Reading the stream lengths of the bomb takes 0.11 s.

For calibration, every real document in this repository — 20 syllabi and 5
academic plans — is at most 8 pages, 0.81 MB of content stream and 13,815
glyphs. The defaults below leave a margin of 20x or more on all three.

**A corrupt PDF is a client error, not a server error.** `pdfplumber` raises
`PdfminerException`, which is not a `ValueError`, so it escaped the
`except ValueError` in both API upload handlers and surfaced as HTTP 500 — and
as a raw traceback from both CLIs. Everything downstream already turns a
`ValueError` into the right 422 or the right `❌ Error:` line, so this module
raises `ValueError` for every "this document cannot be parsed" case and the
correct behaviour follows without any caller changing.

Usage:
    from careercompass.parsing.pdf import open_pdf, page_texts

    with open_pdf(path) as pdf:
        texts = page_texts(pdf)
"""

import logging
import os
from contextlib import contextmanager
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

logger = logging.getLogger("careercompass.parsing")

# Real documents top out at 8 pages, 0.81 MB of content stream and ~14k glyphs.
# Each default is a wide multiple of that, so a legitimate document is never
# refused, while the 106 MB bomb is rejected with room to spare.
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_STREAM_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_CHARS = 2_000_000


def _budget(name: str, default: int) -> int:
    """An integer budget from the environment, ignoring unusable values.

    A malformed override must not be able to disable a guard, so anything that
    does not parse as a positive integer falls back to the default.
    """
    try:
        value = int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def max_pages() -> int:
    return _budget("CC_PDF_MAX_PAGES", DEFAULT_MAX_PAGES)


def max_stream_bytes() -> int:
    return _budget("CC_PDF_MAX_STREAM_BYTES", DEFAULT_MAX_STREAM_BYTES)


def max_chars() -> int:
    return _budget("CC_PDF_MAX_CHARS", DEFAULT_MAX_CHARS)


def _content_stream_bytes(page) -> int:
    """Decompressed size of one page's content streams, in bytes.

    Deliberately measured before anything touches ``page.chars``. Decompressing
    the stream costs its own length; building the layout objects from it costs
    two orders of magnitude more, and that is the step worth refusing to start.

    A page whose streams cannot be read at all contributes 0 rather than
    raising: an unreadable stream yields no glyphs either, so it is the text
    layer check downstream that should report it, not this one.
    """
    page_obj = getattr(page, "page_obj", None)
    contents = getattr(page_obj, "contents", None)
    if contents is None:
        return 0
    if not isinstance(contents, (list, tuple)):
        contents = [contents]

    total = 0
    for stream in contents:
        getter = getattr(stream, "get_data", None)
        if getter is None:
            continue
        try:
            total += len(getter())
        except Exception:  # noqa: BLE001 - an unreadable stream is not a budget failure
            continue
    return total


@contextmanager
def open_pdf(pdf_path, *, pages_limit: int = 0, stream_limit: int = 0):
    """
    Open a PDF for parsing, refusing corrupt and unboundedly expanding files.

    Args:
        pdf_path: Path to the PDF.
        pages_limit: Override the page-count budget. 0 uses the configured one.
        stream_limit: Override the decompressed content-stream budget, in
            bytes. 0 uses the configured one.

    Yields:
        The open ``pdfplumber.PDF``.

    Raises:
        FileNotFoundError: The file does not exist.
        ValueError: The file is not a readable PDF, or exceeds a budget. Callers
            already map ``ValueError`` onto a 4xx, which is what makes this the
            right type: a document the parser refuses is the client's problem,
            not a server fault.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    pages_limit = pages_limit or max_pages()
    stream_limit = stream_limit or max_stream_bytes()

    try:
        pdf = pdfplumber.open(str(path))
    except PdfminerException as exc:
        raise ValueError(
            f"{path.name} could not be read as a PDF ({exc}). The file is "
            "corrupt, truncated, or not a PDF at all."
        ) from exc

    try:
        page_count = len(pdf.pages)
        if page_count > pages_limit:
            raise ValueError(
                f"{path.name} has {page_count} pages, over the {pages_limit}-page "
                "limit for a course document."
            )

        total = 0
        for number, page in enumerate(pdf.pages, start=1):
            total += _content_stream_bytes(page)
            if total > stream_limit:
                raise ValueError(
                    f"{path.name} expands to more than "
                    f"{stream_limit // (1024 * 1024)} MB of page content by page "
                    f"{number}. A compressed PDF can expand to hundreds of times "
                    "its stored size, so it is refused before it is rendered."
                )
        yield pdf
    except PdfminerException as exc:
        # Structural damage often only surfaces once a page is walked.
        raise ValueError(
            f"{path.name} could not be read as a PDF ({exc}). The file is "
            "corrupt, truncated, or not a PDF at all."
        ) from exc
    finally:
        try:
            pdf.close()
        except Exception:  # noqa: BLE001 - closing must not mask the real error
            pass


def page_texts(pdf, *, chars_limit: int = 0) -> list:
    """
    Extract each page's text, stopping if the document exceeds the glyph budget.

    A second net behind the content-stream budget in `open_pdf`, for a document
    that is compact on disk but still enormous once laid out.

    Args:
        pdf: An open ``pdfplumber.PDF``, normally from `open_pdf`.
        chars_limit: Override the character budget. 0 uses the configured one.

    Returns:
        One string per page, in order. Pages with no text layer yield "".

    Raises:
        ValueError: The document is corrupt, or exceeds the character budget.
    """
    chars_limit = chars_limit or max_chars()

    texts = []
    total = 0
    try:
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            total += len(text)
            if total > chars_limit:
                raise ValueError(
                    f"Text extraction exceeded {chars_limit} characters by page "
                    f"{number}; the document is too large to parse as a course "
                    "document."
                )
            texts.append(text)
    except PdfminerException as exc:
        raise ValueError(f"Text could not be extracted from the PDF ({exc}).") from exc
    return texts
