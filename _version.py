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

__version__: str = "5.5.0"  # __session80_release_v5_3_0_version__  # __nous_aetherproof_release_530_prep_v1__  # __session81_release_v5_4_0_version__  # __session82_release_v5_5_0_version__
__version_tuple__: tuple[int, int, int] = (5, 5, 0)

__all__ = ["__version__", "__version_tuple__"]

# __session70_phase5b_step10_release_prep_v1__
