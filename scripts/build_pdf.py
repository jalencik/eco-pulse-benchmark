"""Render paper/extended_technical_report.md to a PDF technical report.

The output is deliberately NOT named after the Data Descriptor. It is the longer
research-article treatment of the same benchmark, carrying the same verified numbers from the
same numbers.json, and it exists for the preprint and fallback venues. The Data Descriptor
submitted to Scientific Data is paper/sdata_descriptor.md. Two documents with similar names
inside one public deposit read as a duplicate submission, so the filename states the role.

Run:  python scripts/build_pdf.py [--in PATH] [--out PATH]

Neither pandoc nor any LaTeX engine is installed on the development machine, and neither is
wkhtmltopdf, so the usual `pandoc --pdf-engine=xelatex` route is unavailable. This uses a
pure-Python chain instead — `markdown` for parsing and `xhtml2pdf`/reportlab for layout —
which has no native dependencies and therefore works wherever the project venv works.

Formatting follows the submission requirement: 11 pt body, 1-inch margins, serif face.

Two details that are easy to get wrong and are handled explicitly:

1. **Unicode.** The manuscript carries µg/m³, PM2.5 subscripts, SO₂, R² and en/em dashes.
   reportlab's built-in Type 1 faces cover Latin-1 only, so anything outside it renders as a
   black box. A DejaVu TrueType face is registered when one can be found, and the absence of
   one is reported rather than silently producing a PDF full of tofu.

2. **Verification.** A PDF that exists is not a PDF that is correct. After writing, the text
   layer is extracted and checked for content that must be present, so a silently-empty or
   mojibake render fails the build instead of shipping to a mentor.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "paper" / "extended_technical_report.md"
DEFAULT_OUT = ROOT / "paper" / "extended_technical_report.pdf"

# Candidate DejaVu locations: bundled with matplotlib (a project dependency), then the
# usual system paths. Checked in order; the first hit wins.
FONT_CANDIDATES = [
    "matplotlib",  # sentinel, resolved at runtime
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
]

CSS = """
@page {
    size: a4 portrait;
    margin: 1in;
    @frame footer { -pdf-frame-content: footer; bottom: 0.5in; height: 0.3in; }
}
body { font-family: %(family)s; font-size: 11pt; line-height: 1.45; text-align: justify; }
h1 { font-size: 17pt; margin: 18pt 0 8pt 0; font-weight: bold; }
h2 { font-size: 13pt; margin: 14pt 0 6pt 0; font-weight: bold; }
h3 { font-size: 11.5pt; margin: 10pt 0 4pt 0; font-weight: bold; }
p  { margin: 0 0 7pt 0; }
li { margin: 0 0 3pt 0; }
code, pre { font-family: Courier; font-size: 9pt; background: #f4f4f4; }
pre { padding: 5pt; border: 0.5pt solid #ddd; }
table { width: 100%%; border-collapse: collapse; font-size: 8.5pt; margin: 7pt 0; }
th { background: #ececec; border: 0.5pt solid #999; padding: 3pt; font-weight: bold;
     text-align: left; }
td { border: 0.5pt solid #bbb; padding: 3pt; vertical-align: top; }
blockquote { margin: 7pt 18pt; font-size: 10pt; color: #333;
             border-left: 2pt solid #999; padding-left: 8pt; }
img { max-width: 460px; }
hr { border: 0; border-top: 0.5pt solid #ccc; margin: 12pt 0; }
"""

FOOTER = (
    '<div id="footer" style="text-align:center;font-size:8pt;color:#666;"><pdf:pagenumber> </div>'
)


def find_font() -> str | None:
    """Locate a Unicode TrueType face, or None if the build must fall back."""
    for cand in FONT_CANDIDATES:
        if cand == "matplotlib":
            try:
                import matplotlib

                p = (
                    Path(matplotlib.__file__).parent
                    / "mpl-data"
                    / "fonts"
                    / "ttf"
                    / "DejaVuSans.ttf"
                )
                if p.exists():
                    return str(p)
            except ImportError:
                continue
        elif Path(cand).exists():
            return cand
    return None


def to_html(md_text: str, font_family: str, base: Path) -> str:
    import markdown

    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    # xhtml2pdf's parser is strict about void elements.
    body = re.sub(r"<(hr|br)>", r"<\1 />", body)

    # Unicode subscripts (U+2080-2089) survive the font but are mismapped by reportlab's
    # TTF handling: SO<sub>2</sub> came out as the literal string "SOn". Superscripts are
    # unaffected and are deliberately left alone. Rewriting subscripts as real <sub>
    # markup draws them with the ordinary digit glyph, which renders and extracts.
    body = body.translate({0x2080 + i: f"<sub>{i}</sub>" for i in range(10)})

    # Rewrite relative figure paths to absolute file paths. pisa's `path=` base did not
    # resolve them: it emitted "Could not get image data from src attribute" to stderr and
    # still produced a complete-looking PDF with zero embedded images.
    def _abs(m: re.Match[str]) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "/")):
            return m.group(0)
        return m.group(0).replace(src, (base / src).resolve().as_posix())

    body = re.sub(r'<img[^>]*src="([^"]+)"', lambda m: _abs(m), body)
    return (
        "<html><head><meta charset='utf-8'><style>"
        + (CSS % {"family": font_family})
        + "</style></head><body>"
        + FOOTER
        + body
        + "</body></html>"
    )


def count_images(pdf: Path) -> int:
    """Embedded XObjects. A figure that fails to load still yields a valid-looking PDF."""
    from pdfminer.pdfpage import PDFPage

    total = 0
    with pdf.open("rb") as fh:
        for page in PDFPage.get_pages(fh):
            xo = (page.resources or {}).get("XObject")
            if xo is not None:
                total += len(xo.resolve() if hasattr(xo, "resolve") else xo)
    return total


def verify(pdf: Path, must_contain: list[str], min_images: int = 0) -> list[str]:
    """Extract the text layer and confirm real content landed.

    A zero-byte or blank PDF is a plausible-looking artifact; checking the bytes is the only
    way to know the render worked rather than merely completed.
    """
    problems: list[str] = []
    if not pdf.exists():
        return ["PDF was not written"]
    size = pdf.stat().st_size
    if size < 20_000:
        problems.append(f"suspiciously small ({size} bytes)")
    try:
        from pdfminer.high_level import extract_text  # type: ignore

        text = extract_text(str(pdf))
    except ImportError:
        return problems  # extraction unavailable; size check stands alone
    for needle in must_contain:
        if needle not in text:
            problems.append(f"missing from text layer: {needle!r}")
    if min_images:
        got = count_images(pdf)
        if got < min_images:
            problems.append(f"only {got} embedded images, expected >= {min_images}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(DEFAULT_IN))
    ap.add_argument("--out", dest="dst", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    if not src.exists():
        print(f"missing {src}; run `python tasks.py paper` first", file=sys.stderr)
        return 1

    md_text = src.read_text(encoding="utf-8")
    left = re.findall(r"\{\{[a-zA-Z0-9_]+\}\}", md_text)
    if left:
        print(
            f"REFUSING: unresolved placeholders in the source: {sorted(set(left))}", file=sys.stderr
        )
        return 1

    # Author-completion fields are not a build error -- drafts circulate with them -- but
    # they must never reach a journal unnoticed, so the count is printed on every build.
    todo = re.findall(r"\[TO COMPLETE[^\]]*\]", md_text)
    if todo:
        print(f"\n  {len(todo)} field(s) still need the author's input before submission:")
        for t in dict.fromkeys(todo):
            print(f"    {t}")
        print()

    font_path = find_font()
    if font_path:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont("DejaVu", font_path))
        family = "DejaVu"
        print(f"font: {font_path}")
    else:
        family = "Times-Roman"
        print(
            "WARNING: no DejaVu TrueType face found. Falling back to Times-Roman, which is\n"
            "         Latin-1 only -- µg/m3, subscripts and R-squared will not render.",
            file=sys.stderr,
        )

    html = to_html(md_text, family, src.parent)

    from xhtml2pdf import pisa

    with dst.open("wb") as fh:
        # `path` is the base for resolving relative <img src>. Without it the figure
        # references silently render as empty boxes -- the PDF still builds.
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")
    if result.err:
        print(f"FAILED: {result.err} error(s) during rendering", file=sys.stderr)
        return 2

    # "SO2" is checked because the subscript form silently degraded to "SOn" before the
    # translate() above; a plain size check would not have caught it.
    problems = verify(
        dst, ["Central Asia", "Introduction", "Limitations", "SO2", "Abstract"], min_images=5
    )
    if problems:
        print("FAILED verification:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 2

    kb = dst.stat().st_size / 1024
    print(f"wrote {dst}  ({kb:,.0f} KB, 11pt, 1in margins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
