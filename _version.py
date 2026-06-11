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

__version__: str = "5.35.0"  # __s127_release_v5_35_0__  # __s126_release_v5_34_0__  # __s125_release_v5_33_0__  # __s124_release_v5_32_0__  # __s122_release_v5_31_0__  # __s121_release_v5_30_0__  # __s120_release_v5_29_0__  # __s118_release_v5_28_0_version__  # __s116_release_v5_27_0_version__  # __s112_release_v5_26_1_version__  # __s112_release_v5_26_0_version__  # __session107_release_v5_25_0_version__  # __session106_release_v5_24_0_version__  # __session105_release_v5_23_0_version__  # __session105_release_v5_22_0_version__  # __session105_release_v5_21_0_version__  # __session104_release_v5_20_1_version__  # __session104_release_v5_20_0_version__  # __session104_release_v5_19_0_version__  # __session103_release_v5_18_0_version__  # __session102_release_v5_17_0_version__  # __session101_release_v5_16_0_version__  # __session101_release_v5_15_1_version__  # __session100_release_v5_15_0_version__  # __session98_release_v5_14_0_version__  # __session98_release_v5_13_1_version__  # __session97_release_v5_13_0_version__  # __session95_release_v5_12_0_version__  # __session93_release_v5_11_0_version__  # __session86_release_v5_8_1_version__  # __session86_release_v5_8_0_version__  # __session86_release_v5_7_1_version__  # __session85_release_v5_7_0_version__  # __session80_release_v5_3_0_version__  # __nous_aetherproof_release_530_prep_v1__  # __session81_release_v5_4_0_version__  # __session82_release_v5_5_0_version__  # __session88_release_v5_9_0_version__
__version_tuple__: tuple[int, int, int] = (5, 35, 0)  # __s127_release_v5_35_0__  # __s126_release_v5_34_0__  # __s125_release_v5_33_0__  # __s124_release_v5_32_0__  # __s122_release_v5_31_0__  # __s121_release_v5_30_0__  # __s120_release_v5_29_0__  # __s118_release_v5_28_0_tuple__  # __s116_release_v5_27_0_tuple__  # __s112_release_v5_26_1_tuple__  # __s112_release_v5_26_0_tuple__  # __session107_release_v5_25_0_tuple__  # __session106_release_v5_24_0_tuple__  # __session105_release_v5_23_0_tuple__  # __session105_release_v5_22_0_tuple__  # __session105_release_v5_21_0_tuple__  # __session104_release_v5_20_1_tuple__  # __session104_release_v5_20_0_tuple__  # __session104_release_v5_19_0_tuple__  # __session103_release_v5_18_0_version__  # __session102_release_v5_17_0_version__  # __session101_release_v5_16_0_version__  # __session101_release_v5_15_1_version__  # __session100_release_v5_15_0_version__

__all__ = ["__version__", "__version_tuple__"]

# __session70_phase5b_step10_release_prep_v1__
# __session84_release_v5_6_0_version__
