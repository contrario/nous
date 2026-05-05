"""
NOUS — Single source of truth for version.

Zero dependencies (stdlib types only). All downstream consumers
(cli.py, nous_api.py, __init__.py, pyproject.toml) import from
this module.

Updating the version means editing exactly two literals here.
A test (tests/test_version_consistency.py) enforces that
__version__ and __version_tuple__ stay in sync, and that pip's
installed metadata matches.

# __nous_version_single_source_v1__
"""
from __future__ import annotations

__version__: str = "5.0.1"  # __hx_pyc_leak_fix_v1__
__version_tuple__: tuple[int, int, int] = (5, 0, 1)

__all__ = ["__version__", "__version_tuple__"]

# __session70_phase5b_step10_release_prep_v1__
