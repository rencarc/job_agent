"""Compile a copied LaTeX résumé and verify readable PDF text."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResumeBuild:
    pdf_path: Path
    pdf_sha256: str
    extracted_text: str


def build_resume(source_dir: Path, main_tex: str, output_pdf: Path,
                 required_phrases: tuple[str, ...] = ()) -> ResumeBuild:
    """Build in isolation with shell escape disabled; reject unreadable output."""
    if Path(main_tex).name != main_tex or not main_tex.endswith(".tex"):
        raise ValueError("main_tex must be a filename inside the supplied project")
    if not (source_dir / main_tex).is_file():
        raise FileNotFoundError(source_dir / main_tex)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory) / "source"
        shutil.copytree(source_dir, work, ignore=shutil.ignore_patterns(".git", "*.aux", "*.log", "*.out"))
        for _ in range(2):
            result = subprocess.run(["pdflatex", "-no-shell-escape", "-halt-on-error",
                                     "-interaction=nonstopmode", main_tex], cwd=work,
                                    capture_output=True, text=True, timeout=90, check=False)
            if result.returncode:
                raise ValueError(f"LaTeX compilation failed: {result.stdout[-1200:]}")
        pdf = work / f"{Path(main_tex).stem}.pdf"
        if not pdf.is_file():
            raise ValueError("LaTeX did not create a PDF")
        extracted = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                   capture_output=True, text=True, timeout=20, check=True).stdout
        if len(extracted.strip()) < 40:
            raise ValueError("generated PDF has too little extractable text")
        for phrase in required_phrases:
            if phrase.casefold() not in extracted.casefold():
                raise ValueError(f"generated PDF is missing required phrase: {phrase}")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, output_pdf)
        return ResumeBuild(output_pdf, hashlib.sha256(output_pdf.read_bytes()).hexdigest(), extracted)
