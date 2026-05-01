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

__version__: str = "4.18.0"  # __diff_side_provenance_v1__
__version_tuple__: tuple[int, int, int] = (4, 18, 0)

__all__ = ["__version__", "__version_tuple__"]
