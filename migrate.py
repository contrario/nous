"""Shim for the YAML/TOML agent migrator, which moved to
nous_migrate_config (PKG001, seat S475). This file is not declared in
pyproject py-modules: no wheel ships the import name migrate, which the
distribution sqlalchemy-migrate also uses. It keeps
"python3 migrate.py <path>" working in a checkout.
"""
import sys

from nous_migrate_config import *  # noqa: F401,F403
from nous_migrate_config import (  # noqa: F401
    config_to_soul, main, migrate_directory, migrate_file)

if __name__ == "__main__":
    sys.exit(main())
