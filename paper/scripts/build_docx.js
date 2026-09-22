// Render the submission manuscript as .docx, for the revision round.
//
// Run:  npm install docx
//       node paper/scripts/build_docx.js . "paper/Eco Pulse Benchmark.docx"
//
// `paper/journal_submission_notes.md` records that a first submission wants a single PDF and
// that .docx is asked for only at revision, so `build_pdf.py` is the primary renderer and this
// is its counterpart. It exists for the same reason that one does: the manuscript is stitched
// from templates by `scripts/build_sdata.py`, and an artefact produced by hand would be the
// one submitted file in the project that no script can rebuild.
//
// This is deliberately NOT wired into `make reproduce`, and needs Node with docx-js, which is
// not in `requirements-lock.txt`. Neither pandoc nor python-docx is installed here, and adding
// either would widen the reproducibility surface that `make reproduce` has to satisfy on a
// clean machine for the sake of a convenience file wanted after peer review. That is the same
// trade `build_pdf.py` makes when it takes xhtml2pdf over WeasyPrint. The PDF remains the
// artefact the tests bind to.
//
// The manuscript is walked block by block rather than handed to a generic converter, because
// the parts an editor actually looks at -- the title block with its superscript affiliations,
// four tables, three numbered figures with captions, and scientific Unicode -- are the parts a
// generic converter mangles. Output is checked by rendering it and reading the pages, not by
// trusting it: `soffice --convert-to pdf`, then `pdftoppm`.

const fs = require("fs");
const path = require("path");

// docx-js is in no project manifest, on purpose, so say what to do instead of throwing a stack
// trace at someone who cloned the repo and expected the PDF pipeline's dependencies to cover it.
let docx;
try {
  docx = require("docx");
} catch {
  console.error("  build_docx.js needs docx-js, which is not a project dependency.");
  console.error("  Install it on the module path and re-run:");
  console.error("      npm install docx");
  console.error("  or set NODE_PATH to an existing install.");
  console.error("  build_pdf.py, which renders the submitted artefact, needs none of this.");
  process.exit(1);
}
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, LevelFormat,
  convertMillimetersToTwip,
} = docx;

const REPO = process.argv[2];
const OUT = process.argv[3];
const SRC = path.join(REPO, "paper", "sdata_descriptor.md");
// The manuscript is written with CRLF on Windows; normalise so the blank-line split matches.
const md = fs.readFileSync(SRC, "utf8").replace(/\r\n?/g, "\n");

// A4 with 19 mm side margins, matching the PDF. Text width in DXA drives the tables.
const PAGE_W = convertMillimetersToTwip(210);
const MARGIN = convertMillimetersToTwip(19);
const TEXT_W = PAGE_W - 2 * MARGIN;

const FONT = "Calibri";
const MONO = "Consolas";
// Half-points. The submitted PDF sets in 13 pages, and the .docx should not disagree with it
// about how long the paper is, so these were swept against the rendered page count rather
// than guessed: 11 pt ran to 15 pages, 10 pt fell to 12, and 10.5 pt with 12.6 pt leading
// lands on 13. Overridable by DOCX_PT / DOCX_LINE / DOCX_AFTER to re-sweep if the text grows.
const SIZE = Number(process.env.DOCX_PT || 21);
const LINE = Number(process.env.DOCX_LINE || 252);   // twentieths of a point
const AFTER = Number(process.env.DOCX_AFTER || 105); // paragraph spacing
const SMALL = 18;     // 9 pt, for affiliations and captions

// ---------------------------------------------------------------- inline runs
// Handles **bold**, *italic*, `code`, <sup>..</sup> and the \* escape, nested one level.
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*)|`[^`]+`|<sup>.*?<\/sup>)/g;
  let last = 0;
  let m;
  const plain = (s) => s.replace(/\\\*/g, "*").replace(/\\_/g, "_");
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: plain(text.slice(last, m.index)), font: FONT, size: SIZE, ...base }));
    const tok = m[0];
    if (tok.startsWith("**")) {
      out.push(new TextRun({ text: plain(tok.slice(2, -2)), bold: true, font: FONT, size: SIZE, ...base }));
    } else if (tok.startsWith("`")) {
      out.push(new TextRun({ text: tok.slice(1, -1), font: MONO, size: SIZE - 2, ...base }));
    } else if (tok.startsWith("<sup>")) {
      const inner = tok.replace(/<\/?sup>/g, "");
      out.push(...runs(inner, { ...base, superScript: true }));
    } else {
      out.push(new TextRun({ text: plain(tok.slice(1, -1)), italics: true, font: FONT, size: SIZE, ...base }));
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ text: plain(text.slice(last)), font: FONT, size: SIZE, ...base }));
  return out.length ? out : [new TextRun({ text: "", font: FONT, size: SIZE, ...base })];
}

const para = (text, opts = {}) =>
  new Paragraph({ children: runs(text), spacing: { after: AFTER, line: LINE }, alignment: AlignmentType.JUSTIFIED, ...opts });

// ---------------------------------------------------------------- tables
function table(lines) {
  const rows = lines
    .filter((l) => !/^\|[\s:|-]+\|?$/.test(l))
    .map((l) => l.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  const ncol = Math.max(...rows.map((r) => r.length));
  // Backticks and bold markers are markup, not glyphs, so strip them before measuring.
  const bare = (s) => (s || "").replace(/[`*]/g, "");
  const CHAR = 130;   // DXA per character, generous enough for a bold 11 pt header
  const PAD = 180;    // the 90 + 90 DXA cell margins

  // A column's share of the width comes from how much text it holds, but its minimum comes
  // from its longest unbreakable word. Word has no overflow: a column narrower than its own
  // header breaks that header one letter per line, which is how "Format" first came out.
  // The floor is capped at 14 characters so a 33-character filename may still wrap.
  const weights = [];
  const floors = [];
  for (let c = 0; c < ncol; c++) {
    let longest = 0;
    let longestWord = 0;
    for (const r of rows) {
      const t = bare(r[c]);
      longest = Math.max(longest, t.length);
      for (const w of t.split(/\s+/)) longestWord = Math.max(longestWord, w.length);
    }
    weights.push(Math.max(longest, 4));
    floors.push(Math.min(longestWord, 14) * CHAR + PAD);
  }
  const total = weights.reduce((a, b) => a + b, 0);
  let widths = weights.map((w) => Math.floor((w / total) * TEXT_W));

  // Lift every starved column to its floor and bill the difference to the columns with slack.
  for (let pass = 0; pass < 12; pass++) {
    const deficit = widths.reduce((s, w, i) => s + Math.max(0, floors[i] - w), 0);
    if (!deficit) break;
    const slack = widths.map((w, i) => Math.max(0, w - floors[i]));
    const slackTotal = slack.reduce((a, b) => a + b, 0);
    if (!slackTotal) break;                     // floors exceed the page; normalised below
    const bill = Math.min(deficit, slackTotal);
    widths = widths.map((w, i) =>
      w < floors[i] ? floors[i] : w - Math.round((slack[i] / slackTotal) * bill));
  }

  let sum = widths.reduce((a, b) => a + b, 0);
  if (sum > TEXT_W) widths = widths.map((w) => Math.floor((w / sum) * TEXT_W));
  sum = widths.reduce((a, b) => a + b, 0);
  widths[widths.length - 1] += TEXT_W - sum;   // absorb rounding in the widest column

  const cell = (txt, isHeader, colIdx) =>
    new TableCell({
      width: { size: widths[colIdx], type: WidthType.DXA },
      shading: isHeader ? { type: ShadingType.CLEAR, fill: "EFEFEF" } : undefined,
      margins: { top: 60, bottom: 60, left: 90, right: 90 },
      children: [
        new Paragraph({
          children: runs(txt).map((r) => r),
          spacing: { after: 0, line: 240 },
          alignment: /^[-\d.,\s±()]+$/.test(txt) && txt.trim() ? AlignmentType.RIGHT : AlignmentType.LEFT,
        }),
      ],
    });

  return new Table({
    columnWidths: widths,
    width: { size: TEXT_W, type: WidthType.DXA },
    rows: rows.map((r, i) =>
      new TableRow({
        tableHeader: i === 0,
        children: Array.from({ length: ncol }, (_, c) => cell(r[c] || "", i === 0, c)),
      })
    ),
  });
}

// ---------------------------------------------------------------- figures
const PNG_SIZE = (buf) => ({ w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) });
function figure(rel) {
  const p = path.join(REPO, "paper", rel);
  const buf = fs.readFileSync(p);
  const { w, h } = PNG_SIZE(buf);
  // Journal widths, as in the PDF: the study-area map at 85 mm, the two wide panels at 130 mm.
  const mm = rel.includes("fig1_study_area") ? 85 : 130;
  const px = Math.round((mm / 25.4) * 96);
  return new Paragraph({
    children: [new ImageRun({ type: "png", data: buf, transformation: { width: px, height: Math.round((px * h) / w) } })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 80 },
  });
}

// ---------------------------------------------------------------- walk blocks
const children = [];
const blocks = md.split(/\n{2,}/);
let seenH1 = false;

for (const raw of blocks) {
  const block = raw.replace(/\s+$/, "");
  if (!block.trim()) continue;
  const lines = block.split("\n");

  // horizontal rule
  if (/^-{3,}$/.test(block.trim())) {
    children.push(new Paragraph({
      text: "",
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "AAAAAA", space: 1 } },
      spacing: { before: 120, after: 200 },
    }));
    continue;
  }

  // title
  if (lines[0].startsWith("# ")) {
    children.push(new Paragraph({
      children: runs(lines[0].slice(2)).map((r) => r),
      heading: HeadingLevel.TITLE,
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
    }));
    seenH1 = true;
    continue;
  }

  // section / subsection headings
  if (lines[0].startsWith("## ")) {
    children.push(new Paragraph({
      children: runs(lines[0].slice(3)).map((r) => r),
      heading: HeadingLevel.HEADING_1,
      spacing: { before: 280, after: 120 },
    }));
    continue;
  }
  if (lines[0].startsWith("### ")) {
    children.push(new Paragraph({
      children: runs(lines[0].slice(4)).map((r) => r),
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 220, after: 100 },
    }));
    continue;
  }

  // table
  if (lines[0].startsWith("|")) { children.push(table(lines)); continue; }

  // figure
  const img = block.match(/^!\[[^\]]*\]\(([^)]+)\)$/);
  if (img) { children.push(figure(img[1])); continue; }

  // fenced code
  if (lines[0].startsWith("```")) {
    for (const l of lines.slice(1).filter((l) => !l.startsWith("```"))) {
      children.push(new Paragraph({
        children: [new TextRun({ text: l, font: MONO, size: SIZE - 3 })],
        shading: { type: ShadingType.CLEAR, fill: "F4F4F4" },
        spacing: { after: 0, line: 240 },
      }));
    }
    children.push(new Paragraph({ text: "", spacing: { after: 100 } }));
    continue;
  }

  // bullet list
  if (lines[0].startsWith("- ")) {
    let cur = null;
    for (const l of lines) {
      if (l.startsWith("- ")) { if (cur) children.push(bullet(cur)); cur = l.slice(2); }
      else cur += " " + l.trim();
    }
    if (cur) children.push(bullet(cur));
    continue;
  }

  // numbered list
  if (/^\d+\.\s/.test(lines[0])) {
    let cur = null;
    for (const l of lines) {
      if (/^\d+\.\s/.test(l)) { if (cur) children.push(numbered(cur)); cur = l.replace(/^\d+\.\s/, ""); }
      else cur += " " + l.trim();
    }
    if (cur) children.push(numbered(cur));
    continue;
  }

  // affiliation / corresponding-author lines: one paragraph each, small type
  if (lines.every((l) => l.trim().startsWith("<sup>"))) {
    for (const l of lines) {
      children.push(new Paragraph({
        children: runs(l.trim()).map((r) => r),
        spacing: { after: 20, line: 240 },
        alignment: AlignmentType.CENTER,
      }));
    }
    continue;
  }

  // author line, immediately after the title
  const joined = lines.join(" ");
  if (!children.some((c) => c.constructor === Table) && /^\*\*[A-Z]/.test(block) && /<sup>/.test(block) && seenH1) {
    children.push(new Paragraph({
      children: runs(joined).map((r) => r),
      alignment: AlignmentType.CENTER,
      spacing: { after: 140 },
    }));
    continue;
  }
  // ORCID line, centred like the rest of the front matter
  if (/^ORCID iDs:/.test(block)) {
    children.push(new Paragraph({
      children: runs(joined).map((r) => r),
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
    }));
    continue;
  }

  // figure caption and ordinary prose
  children.push(/^\*\*(Figure|Table) \d/.test(block)
    ? new Paragraph({
        children: runs(joined).map((r) => r),
        spacing: { after: 200, line: 240 },
        alignment: AlignmentType.LEFT,
      })
    : para(joined));
}

function bullet(text) {
  return new Paragraph({
    children: runs(text).map((r) => r),
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: Math.round(AFTER * 0.66), line: LINE },
    alignment: AlignmentType.JUSTIFIED,
  });
}
function numbered(text) {
  return new Paragraph({
    children: runs(text).map((r) => r),
    numbering: { reference: "numbers", level: 0 },
    spacing: { after: Math.round(AFTER * 0.66), line: LINE },
    alignment: AlignmentType.JUSTIFIED,
  });
}

// Two builds of this file are identical in 25 of their 26 archive entries, word/document.xml
// and all three images included. The exception is docProps/core.xml, which carries
// dcterms:created and dcterms:modified: docx-js 9.7.1 stamps both from new Date() and exposes
// no option to pin them, so a SOURCE_DATE_EPOCH knob was tried and removed rather than left in
// place claiming a guarantee it cannot keep. The .docx is therefore reproducible in content but
// not in digest, unlike everything the tests check. `lastModifiedBy` is set because the library
// otherwise writes "Un-named" into the properties an editor can see.
const doc = new Document({
  creator: "Jaloliddin Musayev",
  lastModifiedBy: "Jaloliddin Musayev",
  title: "Eco Pulse Benchmark",
  description: "A quality-controlled PM2.5 dataset with frozen cross-city evaluation splits for six Central Asian cities",
  styles: {
    default: {
      document: { run: { font: FONT, size: SIZE }, paragraph: { spacing: { line: LINE } } },
      title: { run: { font: FONT, size: 34, bold: true, color: "000000" }, paragraph: { spacing: { after: 240 } } },
      heading1: { run: { font: FONT, size: 26, bold: true, color: "000000" } },
      heading2: { run: { font: FONT, size: 23, bold: true, italics: true, color: "000000" } },
    },
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 440, hanging: 220 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 440, hanging: 220 } } } }] },
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: PAGE_W, height: convertMillimetersToTwip(297) },
              margin: { top: convertMillimetersToTwip(20), bottom: convertMillimetersToTwip(20), left: MARGIN, right: MARGIN } },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`  wrote ${OUT}  (${(buf.length / 1024).toFixed(0)} KB, ${children.length} blocks)`);
});
