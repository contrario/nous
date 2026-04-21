"""
NOUS Templates Package — resource API for shipped .nous templates.

Templates are packaged as non-code resources via setuptools' package-data
mechanism and accessed through importlib.resources (Python 3.9+ stdlib).

Public API:
    list_templates()            -> list[str]
    template_exists(name)       -> bool
    get_template_source(name)   -> str
    get_template_path(name)     -> Path   (may be a Traversable, not a real FS path)
    extract_template(name, dest_dir, overwrite=False) -> Path
"""
from __future__ import annotations

import shutil
from importlib.resources import files as _pkg_files
from pathlib import Path
from typing import Iterable

__all__ = [
    "list_templates",
    "template_exists",
    "get_template_source",
    "get_template_path",
    "extract_template",
    "TemplateNotFoundError",
    "TemplateExtractError",
]

_TEMPLATE_SUFFIX: str = ".nous"


class TemplateNotFoundError(FileNotFoundError):
    """Raised when a named template cannot be resolved within the package."""


class TemplateExtractError(OSError):
    """Raised when template extraction to a destination directory fails."""


def _iter_template_resources() -> Iterable[str]:
    """Iterate names of .nous resource files shipped inside this package."""
    root = _pkg_files(__name__)
    for entry in root.iterdir():
        name = entry.name
        if name.endswith(_TEMPLATE_SUFFIX) and entry.is_file():
            yield name


def list_templates() -> list[str]:
    """Return sorted list of template names (without .nous suffix)."""
    return sorted(
        name.removesuffix(_TEMPLATE_SUFFIX)
        for name in _iter_template_resources()
    )


def _resolve(name: str) -> str:
    """Normalize a template identifier to its resource filename."""
    if not name:
        raise TemplateNotFoundError("template name must be non-empty")
    if "/" in name or "\\" in name or ".." in name:
        raise TemplateNotFoundError(
            f"invalid template name: {name!r} (no path separators allowed)"
        )
    fname = name if name.endswith(_TEMPLATE_SUFFIX) else f"{name}{_TEMPLATE_SUFFIX}"
    if fname not in set(_iter_template_resources()):
        available = ", ".join(list_templates()) or "(none)"
        raise TemplateNotFoundError(
            f"template not found: {name!r}. Available: {available}"
        )
    return fname


def template_exists(name: str) -> bool:
    """Return True if the named template ships with the installed package."""
    try:
        _resolve(name)
    except TemplateNotFoundError:
        return False
    return True


def get_template_source(name: str) -> str:
    """Return the raw .nous source of a shipped template as a string."""
    fname = _resolve(name)
    return _pkg_files(__name__).joinpath(fname).read_text(encoding="utf-8")


def get_template_path(name: str) -> Path:
    """
    Return a filesystem Path to the template resource.

    Note: when installed from a wheel this usually resolves to a concrete
    site-packages path, but importlib.resources may return a Traversable
    that is not a real on-disk file (e.g. when imported from a zip). For
    cross-environment reliability, prefer `extract_template` for anything
    that needs a stable file path.
    """
    fname = _resolve(name)
    traversable = _pkg_files(__name__).joinpath(fname)
    return Path(str(traversable))


def extract_template(
    name: str,
    dest_dir: Path | str = ".",
    overwrite: bool = False,
) -> Path:
    """
    Copy a shipped template to dest_dir. Returns the written Path.

    Raises:
        TemplateNotFoundError: if the template name does not exist.
        TemplateExtractError:  if dest_dir is not writable, or file exists
                               and overwrite is False.
    """
    fname = _resolve(name)
    dest_root = Path(dest_dir).expanduser().resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    target = dest_root / fname

    if target.exists() and not overwrite:
        raise TemplateExtractError(
            f"{target} already exists (pass overwrite=True to replace)"
        )

    source_text = get_template_source(name)
    try:
        target.write_text(source_text, encoding="utf-8")
    except OSError as exc:
        raise TemplateExtractError(f"cannot write {target}: {exc}") from exc

    return target


# Convenience: expose SUFFIX constant for downstream tools
TEMPLATE_SUFFIX: str = _TEMPLATE_SUFFIX
