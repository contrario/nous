"""
test_phrase_detector.py - Session 56

Runs standalone: python3 tests/test_phrase_detector.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Allow running from tests/ subdir or repo root
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from phrase_detector import (
    PhraseDetector,
    detect_sycophancy,
    get_default_detector,
    load_phrases_from_yaml,
    reset_default_detector,
)


class TestPhraseDetector(unittest.TestCase):
    def test_empty_text_returns_false(self) -> None:
        det = PhraseDetector(["great question"])
        self.assertFalse(det.detect(""))

    def test_empty_phrase_list_returns_false(self) -> None:
        det = PhraseDetector([])
        self.assertFalse(det.detect("You're absolutely right!"))

    def test_exact_match(self) -> None:
        det = PhraseDetector(["great question"])
        self.assertTrue(det.detect("That is a great question, thanks."))

    def test_case_insensitive(self) -> None:
        det = PhraseDetector(["great question"])
        self.assertTrue(det.detect("GREAT QUESTION!"))
        self.assertTrue(det.detect("Great Question"))

    def test_no_match(self) -> None:
        det = PhraseDetector(["great question"])
        self.assertFalse(det.detect("The answer is 42."))

    def test_substring_match(self) -> None:
        det = PhraseDetector(["absolutely right"])
        self.assertTrue(det.detect("You're absolutely right about this."))

    def test_multiple_phrases_any_match(self) -> None:
        det = PhraseDetector(["foo", "bar", "baz"])
        self.assertTrue(det.detect("qux bar qux"))
        self.assertFalse(det.detect("qux qux qux"))

    def test_whitespace_only_phrases_ignored(self) -> None:
        det = PhraseDetector(["   ", "real phrase"])
        self.assertFalse(det.detect("   lots of spaces   "))
        self.assertTrue(det.detect("contains real phrase here"))

    def test_non_string_phrases_ignored(self) -> None:
        det = PhraseDetector(["valid"])  # type: ignore[list-item]
        self.assertTrue(det.detect("valid text"))


class TestYamlLoader(unittest.TestCase):
    def _write_tmp(self, content: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(content)
            return Path(f.name)

    def test_valid_yaml(self) -> None:
        path = self._write_tmp('phrases:\n  - "foo"\n  - "bar"\n')
        try:
            self.assertEqual(load_phrases_from_yaml(path), ["foo", "bar"])
        finally:
            path.unlink()

    def test_invalid_schema_not_dict(self) -> None:
        path = self._write_tmp("- foo\n- bar\n")
        try:
            with self.assertRaises(ValueError):
                load_phrases_from_yaml(path)
        finally:
            path.unlink()

    def test_invalid_schema_missing_phrases(self) -> None:
        path = self._write_tmp("other_key: value\n")
        try:
            with self.assertRaises(ValueError):
                load_phrases_from_yaml(path)
        finally:
            path.unlink()

    def test_invalid_schema_non_string_phrase(self) -> None:
        path = self._write_tmp("phrases:\n  - 42\n")
        try:
            with self.assertRaises(ValueError):
                load_phrases_from_yaml(path)
        finally:
            path.unlink()

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_phrases_from_yaml(
                Path("/tmp/definitely_does_not_exist_12345.yaml")
            )


class TestDefaultDetector(unittest.TestCase):
    def setUp(self) -> None:
        reset_default_detector()
        self._orig_env = os.environ.pop("NOUS_SYCOPHANCY_PHRASES", None)

    def tearDown(self) -> None:
        reset_default_detector()
        if self._orig_env is not None:
            os.environ["NOUS_SYCOPHANCY_PHRASES"] = self._orig_env

    def test_fallback_default_phrases(self) -> None:
        det = get_default_detector()
        self.assertTrue(det.detect("You're absolutely right!"))
        self.assertTrue(det.detect("Great question, by the way."))
        self.assertFalse(det.detect("The square root of 144 is 12."))

    def test_env_var_override(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write('phrases:\n  - "custom zebra phrase"\n')
            path = Path(f.name)
        try:
            os.environ["NOUS_SYCOPHANCY_PHRASES"] = str(path)
            reset_default_detector()
            det = get_default_detector()
            self.assertTrue(det.detect("This is a custom zebra phrase test."))
            self.assertFalse(det.detect("You're absolutely right!"))
        finally:
            path.unlink()

    def test_convenience_wrapper(self) -> None:
        self.assertTrue(detect_sycophancy("You're absolutely right!"))
        self.assertFalse(detect_sycophancy("42 is the answer."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
