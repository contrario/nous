"""
test_templates.py - Session 57

Unit + integration tests for the `templates` package.

Runs standalone: python3 tests/test_templates.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import templates as tpl
from templates import (
    TemplateExtractError,
    TemplateNotFoundError,
    extract_template,
    get_template_path,
    get_template_source,
    list_templates,
    template_exists,
)


class TestListTemplates(unittest.TestCase):
    def test_returns_sorted_list_of_strings(self) -> None:
        names = list_templates()
        self.assertIsInstance(names, list)
        self.assertTrue(all(isinstance(n, str) for n in names))
        self.assertEqual(names, sorted(names))

    def test_includes_shipped_sycophancy_guard(self) -> None:
        self.assertIn("sycophancy_guard", list_templates())

    def test_includes_shipped_governance_demo(self) -> None:
        self.assertIn("governance_demo", list_templates())

    def test_names_have_no_suffix(self) -> None:
        for n in list_templates():
            self.assertFalse(n.endswith(".nous"), f"{n!r} still has suffix")


class TestTemplateExists(unittest.TestCase):
    def test_existing_name_without_suffix(self) -> None:
        self.assertTrue(template_exists("sycophancy_guard"))

    def test_existing_name_with_suffix(self) -> None:
        self.assertTrue(template_exists("sycophancy_guard.nous"))

    def test_nonexistent_name(self) -> None:
        self.assertFalse(template_exists("does_not_exist_12345"))

    def test_empty_name(self) -> None:
        self.assertFalse(template_exists(""))

    def test_path_traversal_rejected(self) -> None:
        self.assertFalse(template_exists("../secrets"))
        self.assertFalse(template_exists("foo/bar"))


class TestGetTemplateSource(unittest.TestCase):
    def test_returns_non_empty_string(self) -> None:
        src = get_template_source("sycophancy_guard")
        self.assertIsInstance(src, str)
        self.assertGreater(len(src), 0)

    def test_sycophancy_guard_contains_expected_policy(self) -> None:
        src = get_template_source("sycophancy_guard")
        self.assertIn("SycophancyPhraseGuard", src)
        self.assertIn("sycophancy_phrase_detected", src)
        self.assertIn("inject_message", src)

    def test_raises_template_not_found_for_missing(self) -> None:
        with self.assertRaises(TemplateNotFoundError):
            get_template_source("nonexistent_template_xyz")

    def test_rejects_path_traversal(self) -> None:
        with self.assertRaises(TemplateNotFoundError):
            get_template_source("../../etc/passwd")

    def test_accepts_both_with_and_without_suffix(self) -> None:
        a = get_template_source("sycophancy_guard")
        b = get_template_source("sycophancy_guard.nous")
        self.assertEqual(a, b)


class TestExtractTemplate(unittest.TestCase):
    def test_extract_to_tempdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = extract_template("sycophancy_guard", dest_dir=td)
            self.assertTrue(out.is_file())
            self.assertEqual(out.name, "sycophancy_guard.nous")
            self.assertEqual(out.parent.resolve(), Path(td).resolve())
            text = out.read_text(encoding="utf-8")
            self.assertIn("SycophancyPhraseGuard", text)

    def test_extract_creates_missing_dest_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            nested = Path(td) / "a" / "b" / "c"
            self.assertFalse(nested.exists())
            out = extract_template("sycophancy_guard", dest_dir=nested)
            self.assertTrue(out.is_file())
            self.assertEqual(out.parent.resolve(), nested.resolve())

    def test_extract_refuses_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            extract_template("sycophancy_guard", dest_dir=td)
            with self.assertRaises(TemplateExtractError):
                extract_template("sycophancy_guard", dest_dir=td)

    def test_extract_overwrite_true_replaces_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = extract_template("sycophancy_guard", dest_dir=td)
            out.write_text("STOMPED", encoding="utf-8")
            extract_template("sycophancy_guard", dest_dir=td, overwrite=True)
            self.assertIn("SycophancyPhraseGuard", out.read_text(encoding="utf-8"))

    def test_extract_unknown_template(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(TemplateNotFoundError):
                extract_template("nonexistent_xyz", dest_dir=td)


class TestGetTemplatePath(unittest.TestCase):
    def test_returns_path_object(self) -> None:
        p = get_template_path("sycophancy_guard")
        self.assertIsInstance(p, Path)
        self.assertEqual(p.name, "sycophancy_guard.nous")

    def test_raises_for_unknown(self) -> None:
        with self.assertRaises(TemplateNotFoundError):
            get_template_path("nonexistent_xyz")


class TestCLIIntegration(unittest.TestCase):
    """Invoke `python cli.py templates ...` and assert behavior."""

    def _run_cli(self, *args: str, cwd: str | None = None) -> tuple[int, str, str]:
        cli_path = _ROOT / "cli.py"
        proc = subprocess.run(
            [sys.executable, str(cli_path), "templates", *args],
            capture_output=True,
            text=True,
            cwd=cwd or str(_ROOT),
            timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_cli_list_prints_known_template(self) -> None:
        rc, stdout, stderr = self._run_cli("list")
        self.assertEqual(rc, 0, f"stderr={stderr}")
        self.assertIn("sycophancy_guard", stdout)

    def test_cli_show_prints_source(self) -> None:
        rc, stdout, stderr = self._run_cli("show", "sycophancy_guard")
        self.assertEqual(rc, 0, f"stderr={stderr}")
        self.assertIn("SycophancyPhraseGuard", stdout)

    def test_cli_show_unknown_fails(self) -> None:
        rc, stdout, stderr = self._run_cli("show", "nonexistent_xyz")
        self.assertNotEqual(rc, 0)
        self.assertIn("not found", stderr.lower())

    def test_cli_extract_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rc, stdout, stderr = self._run_cli(
                "extract", "sycophancy_guard", "--dest", td
            )
            self.assertEqual(rc, 0, f"stderr={stderr}")
            out_file = Path(td) / "sycophancy_guard.nous"
            self.assertTrue(out_file.is_file())
            self.assertIn("SycophancyPhraseGuard", out_file.read_text())

    def test_cli_extract_without_overwrite_fails_second_time(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rc1, _, _ = self._run_cli("extract", "sycophancy_guard", "--dest", td)
            self.assertEqual(rc1, 0)
            rc2, _, stderr2 = self._run_cli(
                "extract", "sycophancy_guard", "--dest", td
            )
            self.assertNotEqual(rc2, 0)
            self.assertIn("already exists", stderr2.lower())

    def test_cli_extract_overwrite_flag_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self._run_cli("extract", "sycophancy_guard", "--dest", td)
            rc, _, stderr = self._run_cli(
                "extract", "sycophancy_guard", "--dest", td, "--overwrite"
            )
            self.assertEqual(rc, 0, f"stderr={stderr}")


class TestEndToEnd(unittest.TestCase):
    """Round-trip: extract template, then nous compile succeeds on it."""

    def test_extract_then_compile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_file = extract_template("sycophancy_guard", dest_dir=td)
            self.assertTrue(out_file.is_file())

            cli_path = _ROOT / "cli.py"
            proc = subprocess.run(
                [sys.executable, str(cli_path), "compile",
                 str(out_file), "-o", str(Path(td) / "generated.py")],
                capture_output=True,
                text=True,
                cwd=str(_ROOT),
                timeout=60,
            )
            self.assertEqual(
                proc.returncode, 0,
                f"compile failed: stdout={proc.stdout} stderr={proc.stderr}",
            )
            self.assertTrue((Path(td) / "generated.py").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
