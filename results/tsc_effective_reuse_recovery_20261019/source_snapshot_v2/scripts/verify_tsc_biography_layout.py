"""Internal biography space audit; never supplies personal biographical facts.

Uses the frozen Story V3 source and its inspected LaTeX compile wrapper.
The two specimen paragraphs contain 50 and 69 whitespace-delimited words.
Generated specimens are layout tests, not a submission manuscript.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

import fitz

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Paper/revision_story_v3_20261017"
OUT = ROOT / "submission/biography_layout_audit_20261017"
WORK = ROOT / ".artifacts/bio_layout_20261017/reproducible_append_test"
TEXT = (
    "This paragraph is a layout specimen for one brief author biography. "
    "It fixes only the expected length and includes no claims about degrees, "
    "dates, appointments, research areas, honors, or memberships. The final "
    "text must come from the named author and be checked before submission. "
    "This is an internal typesetting test."
)
EXTRA = (
    "The reserved space also includes the standard portrait area. No invented "
    "personal information should appear in a submission manuscript."
)


def compile_tex(path):
    env = os.environ.copy()
    if os.name == "nt":
        env["PATH"] = str(Path(env["LOCALAPPDATA"]) /
            "Programs/MiKTeX/miktex/bin/x64") + os.pathsep + env["PATH"]
    for run in range(2):
        result = subprocess.run(
            [sys.executable, "-B", str(SOURCE / "scripts/compile.py"),
             str(path), "--recipe", "pdflatex"],
            env=env, capture_output=True,
        )
        (path.parent / (path.stem + f"_compile{run + 1}.txt")).write_bytes(
            result.stdout + result.stderr)
        if result.returncode:
            sys.stdout.buffer.write(result.stdout + result.stderr)
            raise SystemExit(result.returncode)
    return fitz.open(path.with_suffix(".pdf"))


def biographies(environment):
    return (
        f"\\begin{{{environment}}}{{Layout specimen A}}\n{TEXT}\n"
        f"\\end{{{environment}}}\n"
        f"\\begin{{{environment}}}{{Layout specimen B}}\n{TEXT} {EXTRA}\n"
        f"\\end{{{environment}}}\n"
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    source_pdf = SOURCE / "contractkv_tsc_story_v3.pdf"
    original = fitz.open(source_pdf)
    text_blocks = [b for b in original[-1].get_text("blocks")
                   if b[6] == 0 and b[1] > 45]
    bottom = max(b[3] for b in text_blocks)
    top = min(b[1] for b in text_blocks)
    right_bottom = max(b[3] for b in text_blocks if b[0] > 305)
    body_height = bottom - top
    report = {
        "purpose": "Internal typesetting only; no author biography supplied",
        "source_pdf_sha256": hashlib.sha256(source_pdf.read_bytes()).hexdigest(),
        "source_main_pages": len(original),
        "specimen_word_counts": [len(TEXT.split()), len((TEXT + " " + EXTRA).split())],
        "fonts_and_margins": "Unchanged IEEEtran journal defaults",
        "photo_dimensions_inches": [1.0, 1.25],
        "approximate_existing_last_column_free_pt": bottom - right_bottom,
        "approximate_body_height_pt": body_height,
        "specimens": {},
    }
    for name, environment in [("photo_specimen", "IEEEbiography"),
                              ("text_specimen", "IEEEbiographynophoto")]:
        tex = (
            "\\documentclass[journal]{IEEEtran}\n\\usepackage{graphicx}\n"
            "\\begin{document}\n"
            "{\\raggedright\\noindent\\textbf{INTERNAL LAYOUT TEST.}\\par\n"
            "These are generic specimens, not author biographies.\\par}\n"
            "\\noindent\\begin{minipage}{\\columnwidth}\n"
            + biographies(environment)
            + "\\end{minipage}\n\\end{document}\n"
        )
        target = OUT / (name + ".tex")
        target.write_text(tex, encoding="utf-8")
        doc = compile_tex(target)
        page = doc[0]
        blocks = [b for b in page.get_text("blocks") if b[6] == 0
                  and ("Layout specimen" in b[4] or "PHOTO" in b[4])]
        drawing_rects = [v["rect"] for v in page.get_drawings()]
        first = min(b[1] for b in blocks)
        last = max([b[3] for b in blocks] + [r.y1 for r in drawing_rects])
        # The first IEEEbiography skip is outside the visible text/photo envelope.
        # Four standard footnote baselines are about 36 pt in this template.
        budget = last - first + 36
        report["specimens"][name] = {
            "pages": len(doc),
            "visible_envelope_pt": last - first,
            "budget_including_approx_first_skip_pt": budget,
            "approximate_fraction_of_two_column_body_area": budget / (2 * body_height),
        }
        page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35)).save(
            str(OUT / (name + ".png")))

    for folder in ("sections", "figures"):
        shutil.copytree(SOURCE / folder, WORK / folder, dirs_exist_ok=True)
    shutil.copy2(SOURCE / "references.tex", WORK / "references.tex")
    tex = (SOURCE / "contractkv_tsc_story_v3.tex").read_text(encoding="utf-8")
    tex = tex.replace("\\input{references}", "\\input{references}\n" +
                      biographies("IEEEbiography"))
    tex = tex.replace("\\markboth{ContractKV:",
                      "\\markboth{INTERNAL LAYOUT TEST; ContractKV:")
    target = WORK / "append_test.tex"
    target.write_text(tex, encoding="utf-8")
    appended = compile_tex(target)
    report["unchanged_manuscript_with_specimens_appended_pages"] = len(appended)
    report["conclusion"] = (
        "A quarter of a two-column body page is a sufficient planning allowance "
        "for two brief biographies. The present last column alone is too short. "
        "Final page count still requires real author text and final compilation."
    )
    (OUT / "layout_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
