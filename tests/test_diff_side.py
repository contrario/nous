"""Regression tests for DiffSide / render_diff_side / DiffRequest provenance.

Locks the contract for diff source labels (Session 67, v4.18.0).
If the rendered string for a given (kind, identifier) pair changes, audit
logs and dossier evidence emitted before the change become inconsistent
with new evidence. These tests catch silent renames.
"""
from __future__ import annotations

import pytest

from nous_api import DiffRequest, DiffSide, render_diff_side


def test_render_none_returns_unknown() -> None:
    assert render_diff_side(None) == "(unknown source)"


def test_render_unknown_kind_returns_unknown() -> None:
    assert render_diff_side(DiffSide(kind="unknown")) == "(unknown source)"


def test_render_template_with_id() -> None:
    assert (
        render_diff_side(DiffSide(kind="template", identifier="sycophancy_guard"))
        == "Template: sycophancy_guard"
    )


def test_render_template_without_id() -> None:
    assert render_diff_side(DiffSide(kind="template")) == "Template (unnamed)"


def test_render_editor_default() -> None:
    assert render_diff_side(DiffSide(kind="editor")) == "Editor (current)"


def test_render_editor_with_session() -> None:
    assert (
        render_diff_side(DiffSide(kind="editor", identifier="session_abc123"))
        == "Editor: session_abc123"
    )


def test_render_paste_anonymous() -> None:
    assert render_diff_side(DiffSide(kind="paste")) == "Paste"


def test_render_paste_with_marker() -> None:
    assert render_diff_side(DiffSide(kind="paste", identifier="A")) == "Paste A"


def test_render_replay_truncates_long_uuid() -> None:
    long_uuid = "550e8400-e29b-41d4-a716-446655440000"
    out = render_diff_side(DiffSide(kind="replay", identifier=long_uuid))
    assert out == "Replay 550e8400\u2026"
    assert "\u2026" in out  # ellipsis present


def test_render_replay_short_id_no_truncate() -> None:
    out = render_diff_side(DiffSide(kind="replay", identifier="abc"))
    assert out == "Replay abc\u2026"


def test_render_replay_without_id() -> None:
    assert render_diff_side(DiffSide(kind="replay")) == "Replay (unknown)"


def test_render_file_uses_basename_only() -> None:
    assert (
        render_diff_side(
            DiffSide(kind="file", identifier="/var/lib/nous/replays/sample_a.jsonl")
        )
        == "File: sample_a.jsonl"
    )


def test_render_file_without_id() -> None:
    assert render_diff_side(DiffSide(kind="file")) == "File (unnamed)"


def test_label_override_wins_over_kind() -> None:
    side = DiffSide(
        kind="template", identifier="anything", label="Custom: My Override"
    )
    assert render_diff_side(side) == "Custom: My Override"


def test_diff_request_default_sides_are_none() -> None:
    """Backward-compat: existing 4.16.x clients send only original/modified."""
    req = DiffRequest(original="x", modified="y")
    assert req.original_side is None
    assert req.modified_side is None
    assert render_diff_side(req.original_side) == "(unknown source)"
    assert render_diff_side(req.modified_side) == "(unknown source)"


def test_diff_request_with_both_sides() -> None:
    req = DiffRequest(
        original="x",
        modified="y",
        original_side=DiffSide(kind="template", identifier="sycophancy_guard"),
        modified_side=DiffSide(kind="editor"),
    )
    assert render_diff_side(req.original_side) == "Template: sycophancy_guard"
    assert render_diff_side(req.modified_side) == "Editor (current)"


def test_kind_enum_rejects_invalid_value() -> None:
    """Pydantic v2 enforces Literal at construction. Future kinds must be
    added to the enum, not silently accepted."""
    with pytest.raises(Exception):  # ValidationError; kept loose for v2/v3
        DiffSide(kind="branch")  # type: ignore[arg-type]
