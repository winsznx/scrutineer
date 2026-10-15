"""Export technical_report.md to Scrutineer_Report.pdf with pandoc and typst.

Needs `pandoc` (3.x, typst writer) and `typst` on PATH. Not part of `make run`: the PDF is a
committed artefact, rebuilt by the author with `scrutineer report --pdf`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent


def export_pdf(report_md: Path, out_pdf: Path) -> Path:
    for tool in ("pandoc", "typst"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} is required for --pdf")
    root = report_md.parent
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        work = Path(tmp)
        subprocess.run(["pandoc", str(report_md), "-t", "typst", "--wrap=preserve", "-o", str(work / "body.typ")],
                       check=True)
        body = (work / "body.typ").read_text(encoding="utf-8")
        # Images are referenced relative to the report; the body now lives one level deeper.
        (work / "body.typ").write_text(body.replace('image("docs/', 'image("../docs/'), encoding="utf-8")
        shutil.copy(HERE / "report.typ", work / "main.typ")
        subprocess.run(["typst", "compile", "--root", str(root), "--font-path", str(HERE / "fonts"),
                        str(work / "main.typ"), str(out_pdf)], check=True)
    return out_pdf
