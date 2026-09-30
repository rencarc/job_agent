import shutil
import tempfile
import unittest
from pathlib import Path

from job_agent.latex_build import build_resume


@unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "LaTeX tools unavailable")
class LatexBuildTests(unittest.TestCase):
    def test_compiles_readable_pdf_and_checks_important_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src"
            source.mkdir()
            (source / "main.tex").write_text(r"\documentclass{article}\begin{document}"
                                             "Verified professional experience in Power Pages and Dataverse. "
                                             "This is a readable resume document with source-backed work examples."
                                             r"\end{document}")
            result = build_resume(source, "main.tex", root / "out" / "cv.pdf", ("Dataverse",))
            self.assertTrue(result.pdf_path.is_file())
            self.assertEqual(len(result.pdf_sha256), 64)
            with self.assertRaisesRegex(ValueError, "missing required phrase"):
                build_resume(source, "main.tex", root / "out" / "bad.pdf", ("Kubernetes",))

    def test_rejects_tex_outside_project(self):
        with self.assertRaises(ValueError):
            build_resume(Path("."), "../secret.tex", Path("out.pdf"))
