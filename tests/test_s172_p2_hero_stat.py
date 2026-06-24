from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INDEX = _REPO / "website" / "index.html"
_RELEASE = _REPO / "scripts" / "release.py"


def _pytest_floor() -> int:
    text = _RELEASE.read_text(encoding="utf-8")
    m = re.search(r"PYTEST_FLOOR\s*:\s*int\s*=\s*(\d+)", text)
    assert m is not None, "PYTEST_FLOOR literal not found in scripts/release.py"
    return int(m.group(1))


def _hero_target() -> int:
    text = _INDEX.read_text(encoding="utf-8")
    m = re.search(r'class="stat-num"\s+data-target="(\d+)">0</div>(?:<!--[^>]*-->)?\s*<div class="stat-label">Tests Passing</div>', text)  # __s172_p2_herotest_regex__
    assert m is not None, "hero 'Tests Passing' stat-num not found in website/index.html"
    return int(m.group(1))


def test_hero_tests_passing_matches_pytest_floor() -> None:
    assert _hero_target() == _pytest_floor(), (
        "hero 'Tests Passing' (" + str(_hero_target()) + ") != PYTEST_FLOOR ("
        + str(_pytest_floor()) + "); bump the hero stat in website/index.html "
        "and /var/www mirror in the same release window"
    )


def test_frontpage_story_removed() -> None:
    text = _INDEX.read_text(encoding="utf-8")
    assert "const STORY" not in text, "dead front-page STORY array still present"
    assert "function buildStory" not in text, "dead buildStory() still present"
    assert ".timeline{" not in text, "dead .timeline CSS still present"
    assert "__s172_p2_hero_story__" in text, "S172 P2 marker absent"
