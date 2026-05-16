"""
cli_skill_export.py

CLI wrapper for `nous skill-export`. Reads a .nous file, parses it,
projects onto the agentskills.io subset via skill_export.export_skill,
and writes SKILL.md + nous.yaml to a target directory.

Usage:
  nous skill-export <input.nous>
      --description "<one-line description>"
      [--output <dir>]
      [--name <skill-name>]
      [--license <license>]
      [--compatibility <constraint>]

Output:
  <output>/SKILL.md
  <output>/nous.yaml

Defaults:
  - output: <input-basename>.skill/
  - name:   derived from world name (kebab-case)
  - license, compatibility: omitted

# __session77_cli_skill_export_v1__
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from parser import parse_nous
from skill_export import (
    ExportRequest,
    SkillExportError,
    export_skill,
)


def build_skill_export_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Register the `skill-export` subcommand on a cli.py-style parser.

    The cli.py entrypoint owns the dispatch table and command name; this
    function only declares the argparse subparser.
    """
    p = subparsers.add_parser(
        "skill-export",
        help=(
            "Export a .nous program as an agentskills.io-compliant skill "
            "(SKILL.md + nous.yaml)"
        ),
        description=(
            "Translate a .nous program into the agentskills.io subset: "
            "SKILL.md frontmatter + nous.yaml cost envelope. The "
            "translation is lossy and one-way."
        ),
    )
    p.add_argument(
        "input",
        type=str,
        metavar="INPUT.nous",
        help="Path to the .nous source file",
    )
    p.add_argument(
        "--description",
        type=str,
        required=True,
        help="Human-readable skill description (required, 1-1024 chars)",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="DIR",
        help=(
            "Output directory; defaults to <input-basename>.skill/. "
            "Created if missing. Existing files are atomically "
            "overwritten."
        ),
    )
    p.add_argument(
        "--name",
        type=str,
        default=None,
        metavar="SKILL_NAME",
        help=(
            "agentskills.io skill name (kebab-case). Defaults to a "
            "kebab-case projection of the world name."
        ),
    )
    p.add_argument(
        "--license",
        type=str,
        default=None,
        help="Optional license identifier (e.g. 'MIT', 'Apache-2.0')",
    )
    p.add_argument(
        "--compatibility",
        type=str,
        default=None,
        help=(
            "Optional compatibility constraint string (free-form, "
            "1-500 chars)"
        ),
    )


def _atomic_write_text(target: Path, text: str) -> None:
    """Atomic-write with mode 0o644 (mkstemp default 0o600 wrong)."""
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def cmd_skill_export(args: argparse.Namespace) -> int:
    """Entrypoint dispatched from cli.py.

    Returns 0 on success, non-zero on user-visible error. All error
    paths print to stderr; success prints one line per written file.
    """
    input_path = Path(args.input)
    if not input_path.is_file():
        print(
            f"ERROR: input file not found: {input_path}",
            file=sys.stderr,
        )
        return 1
    try:
        source = input_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot read {input_path}: {e}", file=sys.stderr)
        return 1
    try:
        program = parse_nous(source)
    except Exception as e:
        print(
            f"ERROR: parse failed for {input_path}: {e}",
            file=sys.stderr,
        )
        return 1
    try:
        request = ExportRequest(
            description=args.description,
            skill_name=args.name,
            license=args.license,
            compatibility=args.compatibility,
        )
    except Exception as e:
        print(
            f"ERROR: invalid export request arguments: {e}",
            file=sys.stderr,
        )
        return 1
    try:
        result = export_skill(program, request)
    except SkillExportError as e:
        print(f"ERROR: skill export refused: {e}", file=sys.stderr)
        return 1
    if args.output is not None:
        out_dir = Path(args.output)
    else:
        out_dir = input_path.parent / (input_path.stem + ".skill")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(
            f"ERROR: cannot create output dir {out_dir}: {e}",
            file=sys.stderr,
        )
        return 1
    skill_md_path = out_dir / "SKILL.md"
    nous_yaml_path = out_dir / "nous.yaml"
    try:
        _atomic_write_text(skill_md_path, result.skill_md)
        _atomic_write_text(nous_yaml_path, result.nous_yaml)
    except Exception as e:
        print(f"ERROR: write failed: {e}", file=sys.stderr)
        return 1
    print(f"WROTE: {skill_md_path}")
    print(f"WROTE: {nous_yaml_path}")
    print(f"SKILL_NAME: {result.skill_name}")
    return 0


__all__ = ["build_skill_export_parser", "cmd_skill_export"]
