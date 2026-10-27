"""The redacted export listings validate as the product they came from.

The listings under ``tests/ddp/listings/`` are member paths only, redacted
(see ``INDEX.md`` there); each test rebuilds an in-memory zip of empty files
from one listing. The corpus is local and git-ignored, like every real DDP
fixture (ADR-0014): it is never committed, and on a machine whose listings
directory holds no listings every test here skips with a reason. The three
participant skeletons listed in ``INDEX.md`` as held out of marker derivation
are acceptance evidence only: never add a marker because one of them holds it.
"""

import re
from pathlib import Path

import pytest

import port.platforms.facebook as facebook
import port.platforms.instagram as instagram

from port.helpers.meta_recognition import (
    OTHER_PRODUCT,
    STRONG_LEAVES,
    STRONG_ROOTS,
    kept,
    score_members,
    validate_meta,
)
from test_meta_recognition import make_zip

LISTINGS_DIR = Path(__file__).parent / "ddp" / "listings"
CATEGORIES = {"facebook": facebook.DDP_CATEGORIES, "instagram": instagram.DDP_CATEGORIES}

_WRAPPER = "<wrapper>/"
_COUNT = re.compile(r"^(.*?)\s+x(\d+)$")


def load_listing(path: Path) -> list[str]:
    """The member paths of one listing: the ``#`` header skipped, leading
    ``<wrapper>/`` segments stripped, and a trailing ``   xN`` count expanded
    into N copies of the path. Other redacted tokens stay literal segments."""
    members: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    for line in lines:
        if not line.strip():
            continue
        count = 1
        match = _COUNT.match(line)
        if match:
            line, count = match.group(1), int(match.group(2))
        while line.startswith(_WRAPPER):
            line = line[len(_WRAPPER):]
        members.extend([line] * count)
    return members


def listings() -> list[tuple[str, str, list[str]]]:
    """``(file name, expected product, members)`` for every listing, sorted by
    name; empty when the listings are not on this machine (ADR-0014)."""
    return [
        (path.name, path.name.split("-")[0], load_listing(path))
        for path in sorted(LISTINGS_DIR.glob("*.txt"))
    ]


# Danielle's Facebook export holding only data_logs/ and a readme: no marker
# of either product, so neither step can claim it.
DATA_LOGS_ONLY = "facebook-json-en-7ac9b7fe0dc8.txt"
# The researcher's three-member Instagram skeleton: weak Instagram markers only.
RESEARCHER_SKELETON = "instagram-json-nl-d6daaab72300.txt"
# Held out of marker derivation: the participant skeleton from
# "instagram-skeleton (7).zip", whose messages/photos folder once read as Facebook.
HELD_OUT_MESSAGES_PHOTOS = "instagram-json-nl-8db7763e6c90.txt"


def expected_category(name: str) -> str:
    """The format category a listing's own step picks, from its file name."""
    return {"json": "json_en", "html": "html_en"}[name.split("-")[1]]


@pytest.mark.filterwarnings("ignore:Duplicate name")
@pytest.mark.parametrize(
    "name,product,members", listings(), ids=[name for name, _, _ in listings()]
)
def test_every_listing_validates_as_its_product(name, product, members):
    other = OTHER_PRODUCT[product]
    own = validate_meta(make_zip(members), product, CATEGORIES[product])
    wrong = validate_meta(make_zip(members), other, CATEGORIES[other])

    if name == DATA_LOGS_ONLY:
        for validation in (own, wrong):
            assert validation.reason == "unknown"
            assert validation.current_ddp_category.id == "unknown"
            assert validation.get_status_code_id() == 1
        return

    assert own.reason == product
    assert own.current_ddp_category.id == expected_category(name)
    assert own.get_status_code_id() == 0
    if name == RESEARCHER_SKELETON:
        assert own.basis == "weak"
        assert wrong.reason == "unknown"
        assert wrong.current_ddp_category.id == "unknown"
    else:
        assert own.basis == "strong"
        assert wrong.reason == product
        assert wrong.current_ddp_category.id == f"{product}_detected"
    assert wrong.get_status_code_id() == 1


def folders(member: str) -> list[str]:
    segments = [s for s in member.split("/") if s]
    return segments if member.endswith("/") else segments[:-1]


@pytest.mark.parametrize("product", ["instagram", "facebook"])
def test_strong_evidence_is_absent_from_the_other_product(product):
    other_listings = [(n, m) for n, p, m in listings() if p == OTHER_PRODUCT[product]]
    if not other_listings:
        pytest.skip("no listings of the other product (ADR-0014: kept locally)")
    found = []
    for name, members in other_listings:
        # The members recognition scores: a ``__MACOSX`` mirror or dotfile is not evidence.
        for member in kept(members):
            fs = folders(member)
            pairs = {f"{a}/{b}" for a, b in zip(fs, fs[1:])}
            hits = (STRONG_ROOTS[product] & set(fs)) | (STRONG_LEAVES[product] & pairs)
            found.extend((name, hit) for hit in hits)
    assert found == []


def test_held_out_skeleton_with_messages_photos_is_instagram():
    path = LISTINGS_DIR / HELD_OUT_MESSAGES_PHOTOS
    if not path.exists():
        pytest.skip("held-out listing absent (ADR-0014: kept locally)")
    score = score_members(load_listing(path))
    assert score.facebook_strong == 0
    assert score.facebook_weak == 0
    assert score.instagram_strong >= 1
