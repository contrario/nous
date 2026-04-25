"""test_grammar_sync.py — enforce grammar_data.py == nous.lark.

If anyone touches nous.lark and forgets to run scripts/sync_grammar.py,
this test fails. Closes the wheel-vs-source drift that produced the
v4.11.2 broken-template incident.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAMMAR = ROOT / "nous.lark"
TARGET = ROOT / "grammar_data.py"
SYNC_SCRIPT = ROOT / "scripts" / "sync_grammar.py"


class TestGrammarSync(unittest.TestCase):
    def test_grammar_lark_exists(self) -> None:
        self.assertTrue(GRAMMAR.exists(), f"missing {GRAMMAR}")

    def test_grammar_data_exists(self) -> None:
        self.assertTrue(TARGET.exists(), f"missing {TARGET}")

    def test_sync_script_exists(self) -> None:
        self.assertTrue(SYNC_SCRIPT.exists(), f"missing {SYNC_SCRIPT}")

    def test_grammar_data_in_sync(self) -> None:
        """grammar_data.py must embed the current nous.lark verbatim.

        Regenerate with: python3 scripts/sync_grammar.py
        """
        from grammar_data import get_grammar  # type: ignore

        embedded = get_grammar()
        on_disk = GRAMMAR.read_text(encoding="utf-8")
        self.assertEqual(
            embedded,
            on_disk,
            "grammar_data.py is out of sync with nous.lark. "
            "Run: python3 scripts/sync_grammar.py",
        )

    def test_sync_script_idempotent(self) -> None:
        """Running sync_grammar.py when in sync must produce no change."""
        before = TARGET.read_text(encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = TARGET.read_text(encoding="utf-8")
        self.assertEqual(before, after, "sync_grammar.py is not idempotent")


if __name__ == "__main__":
    unittest.main()
