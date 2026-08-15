"""Render a built manuscript to the single PDF Scientific Data wants at first submission.

Run:  python paper/scripts/build_pdf.py            # the Data Descriptor
      python paper/scripts/build_pdf.py <in.md>    # any built markdown

Scientific Data's submission guidelines (checked 2026-08-15) ask for "a single pdf file for
the main article" in the first review round, and only require .docx/.tex at revision. The
Data Descriptor is written as templates and stitched by `scripts/build_sdata.py`, so until
now there was no PDF of it at all -- only of the longer technical report, which is not the
submitted document. Producing it by hand would mean the submitted artefact was the one thing
in the project that no script could reproduce, so this exists to keep that from being true.

xhtml2pdf is used because it is already the producer of `extended_technical_report.pdf` and
is a pure-Python dependency; WeasyPrint would render better but needs system libraries that
would break `make reproduce` on a clean machine.

Figures are resolved relative to the markdown file's directory and inlined as data URIs, so
the PDF does not depend on the working directory it was built from.
"""

from __future__ import annotations

import base64
import mimetypes
import pathlib
import re
import sys

import markdown
from xhtml2pdf import pisa

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_IN = ROOT / "paper" / "sdata_descriptor.md"

CSS = """
@page { size: A4; margin: 2.0cm 1.9cm 2.0cm 1.9cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.4pt; line-height: 1.42;
       color: #111; }
h1 { font-size: 16pt; line-height: 1.25; margin: 0 0 0.5em 0; }
h2 { font-size: 11.5pt; margin: 1.5em 0 0.45em 0; border-bottom: 0.6pt solid #999;
     padding-bottom: 2pt; }
h3 { font-size: 10pt; margin: 1.1em 0 0.35em 0; }
p  { margin: 0 0 0.55em 0; text-align: justify; }
ul, ol { margin: 0 0 0.6em 1.1em; }
li { margin-bottom: 0.22em; }
code { font-family: Courier, monospace; font-size: 8.3pt; }
pre { font-family: Courier, monospace; font-size: 8pt; background: #f5f5f5;
      padding: 5pt; margin: 0.5em 0; }
table { width: 100%; border-collapse: collapse; margin: 0.6em 0; font-size: 7.9pt; }
th { background: #eee; border: 0.5pt solid #999; padding: 3pt; text-align: left;
     font-weight: bold; }
td { border: 0.5pt solid #999; padding: 3pt; vertical-align: top; }
img { max-width: 100%; }
sup { font-size: 6.6pt; }
"""


def _inline_images(html: str, base: pathlib.Path) -> str:
    """Replace <img src="rel/path"> with a data URI so the PDF is self-contained."""

    def repl(m: re.Match[str]) -> str:
        src = m.group(1)
        if src.startswith(("data:", "http://", "https://")):
            return m.group(0)
        path = (base / src).resolve()
        if not path.is_file():
            print(f"  WARNING: figure not found, dropped from PDF: {src}")
            return ""
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return m.group(0).replace(src, f"data:{mime};base64,{b64}")

    return re.sub(r'<img[^>]+src="([^"]+)"', repl, html)


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_IN
    if not src.is_file():
        print(f"FAILED: {src} does not exist -- build the markdown first")
        return 1

    out = src.with_suffix(".pdf")
    text = src.read_text(encoding="utf-8")

    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = _inline_images(body, src.parent)
    html = f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"

    with out.open("wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")

    if result.err:
        print(f"FAILED: {result.err} error(s) rendering {out.name}")
        return 1

    kb = out.stat().st_size / 1024
    print(f"wrote {out}")
    print(f"  {len(text.split()):,} words -> {kb:,.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
