"""Integration tests for the Facebook extractors.

Requires real Facebook DDP zips at::

    tests/ddp/facebook_<format>_<anything>.zip      e.g. facebook_json_self-2026-03.zip
                                                        facebook_html_self-2026-03.zip

``<format>`` is ``json`` or ``html`` — the account holder picks one when
requesting the export, and every extractor has a code path per format, so one
fixture of each is needed to exercise the module. Tests skip when no fixture is
found — CI runs clean without real data (ADR-0014).

Expectation map
---------------
Which files an export contains depends on the categories selected at request
time and on what the account has actually done (an account that never clicked
an ad has no ``advertisers_you've_interacted_with``), so a flat "every extractor
is non-empty" list would fail on legitimate variation. Instead
``EXPECT_NON_EMPTY`` pins, per fixture stem, the extractors that must return a
non-empty frame — ADR-0027's expectation-map shape, keyed by zip stem instead
of set directory. The pins are the canary: a pinned extractor gone empty means
the extractor, or Facebook's export format, changed. A non-pinned extractor is
run but only checked not to raise.

``UNPINNED_KNOWN_GAPS`` names the extractors no local fixture can exercise,
with the reason; ``test_every_extractor_is_pinned_somewhere`` fails in CI (no
fixtures needed) if a registry entry is neither pinned nor listed there.
"""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from extractor_integration_helpers import DiskPart, find_fixtures
import port.platforms.facebook as facebook
from port.helpers.extraction_helpers import ZipArchiveReader
from port.helpers.table_extractor import load_port_config
from port.helpers.validate import DDPFiletype, ValidateInput, validate_zip

FIXTURES: list[Path] = find_fixtures("facebook")
_NO_FIXTURES_REASON = "No facebook_*.zip fixture found in tests/ddp/"
_PARAMS: list[Path | None] = list(FIXTURES) or [None]
_IDS = [p.stem for p in FIXTURES] or ["no-fixture"]

# Present in every profile export we have seen, whichever categories were
# selected and whichever format was chosen.
_ADS_TABLES = {
    "ad_preferences_to_df",
    "other_categories_used_to_reach_you_to_df",
    "advertisers_using_your_activity_to_df",
}
# The account holder's own activity — present when the export includes
# "Your Facebook activity" and the account has some.
_ACTIVITY_TABLES = {
    "your_events_to_df",
    "your_group_membership_activity_to_df",
    "likes_and_reactions_to_df",
    "your_posts_check_ins_to_df",
    "your_contributions_to_df",
    "your_comments_in_groups_to_df",
}

EXPECT_NON_EMPTY: dict[str, set[str]] = {
    # Real account, JSON, March 2026 — all categories except pages/followers.
    "facebook_json_self-2026-03": _ADS_TABLES | _ACTIVITY_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
    },
    # Same account and day, HTML. No logged_information/search in this export:
    # its only your_search_history.html is the Marketplace one, which the HTML
    # extractor currently picks up by bare basename — deliberately not pinned.
    "facebook_html_self-2026-03": _ADS_TABLES | _ACTIVITY_TABLES,
    # Real account, JSON, all time, delivered via Google Drive, March 2026 —
    # 2,209 files, the format participants are instructed to request. Drive
    # delivery spells the follow / like files `who_you_ve_followed` (apostrophe
    # replaced); the reader resolves that spelling, so both are pinned. The
    # grouped interaction layout (recently_viewed / recently_visited) is still
    # unread. The qualified JSON search path does not collide, so search is
    # pinned here. Reels usage is absent from this export although present
    # eight days earlier — file presence varies between exports of one account.
    "facebook_json_self-alltime-2026-03": _ADS_TABLES | _ACTIVITY_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "comments_to_df",
        "pages_and_profiles_you_follow_to_df",
        "who_youve_followed_to_df",
        "pages_youve_liked_to_df",
    },
    # Real account, HTML, all time (registered 2005), delivered via Google
    # Drive, March 2026 — 2,815 files. Search history is absent because the
    # bare-basename lookup collides with the Marketplace file — a defect to
    # fix, not a pin to add. The follow / like files are spelled
    # `who_you_ve_followed` here (Drive delivery replaces the apostrophe) and
    # the reader resolves that spelling.
    "facebook_html_self-alltime-2026-03": _ADS_TABLES | _ACTIVITY_TABLES | {
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
        "comments_to_df",
        "pages_and_profiles_you_follow_to_df",
        "who_youve_followed_to_df",
        "pages_youve_liked_to_df",
    },
    # Real account, device downloads, October 2025: a three-month JSON window
    # (57 files) and a one-year HTML window (980 files). Device downloads keep
    # the apostrophe in file names; both use the grouped interaction layout.
    # The HTML one carries the Marketplace search file, so search is unpinned.
    "facebook_json_self-device-2025-10": _ADS_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
    },
    "facebook_html_self-device-2025-10": _ADS_TABLES | {
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
        "your_events_to_df",
        "your_group_membership_activity_to_df",
        "comments_to_df",
        "likes_and_reactions_to_df",
        "your_posts_check_ins_to_df",
        "your_comments_in_groups_to_df",
    },
    # A third account, device JSON, October 2025, re-zipped on a Mac
    # (__MACOSX entries): a category-restricted export of logged information,
    # other activity and feed preferences only. The one local export with
    # link_history; a heavy feed user (160 posts, 396 videos, 93 ads shown
    # in 90 days).
    "facebook_json_other-device-2025-10": {
        "facebook_reels_usage_to_df",
        "link_history_to_df",
    },
    # Test account, HTML, June 2026 — clicked ads, follows/likes two pages,
    # no group or post activity.
    "facebook_html_testacct-2026-06": _ADS_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "advertisers_youve_interacted_with_to_df",
        "who_youve_followed_to_df",
        "pages_and_profiles_you_follow_to_df",
        "pages_youve_liked_to_df",
    },
}

UNPINNED_KNOWN_GAPS: dict[str, str] = {
    "profile_visits_to_df": "no local export contains logged_information/interactions/profile_visits.*",
    "items_viewed_to_df": "no local export contains logged_information/interactions/items_viewed.*",
    "news_your_locations_to_df": (
        "facebook_news/your_locations.json is absent from every 2026 export seen "
        "(Facebook News was discontinued); registered as PENDING, candidate for removal"
    ),
}


# ---------------------------------------------------------------------------
# Fixture handling
# ---------------------------------------------------------------------------


@dataclass
class _Context:
    part: DiskPart
    validation: ValidateInput
    reader: ZipArchiveReader


_CACHE: dict[Path, _Context] = {}


def _context(fixture: Path) -> _Context:
    """Validate *fixture* once per session and hand back a reader over it."""
    if fixture not in _CACHE:
        part = DiskPart(fixture)
        validation = validate_zip(facebook.DDP_CATEGORIES, part)
        reader = ZipArchiveReader(part, validation.archive_members, Counter())
        _CACHE[fixture] = _Context(part, validation, reader)
    return _CACHE[fixture]


def _expected_filetype(fixture: Path) -> DDPFiletype:
    """The format segment of ``facebook_<format>_<anything>.zip``."""
    segment = fixture.stem.split("_")[1]
    return {"json": DDPFiletype.JSON, "html": DDPFiletype.HTML}[segment]


# ---------------------------------------------------------------------------
# Static: registry coverage (runs in CI without fixtures)
# ---------------------------------------------------------------------------


def test_every_extractor_is_pinned_somewhere():
    """Every registry entry is either pinned non-empty by some fixture or listed
    as a known gap with a reason — an extractor added without either would be
    silently unexercised by every per-fixture canary."""
    pinned = set().union(*EXPECT_NON_EMPTY.values())
    registry = set(facebook.EXTRACTOR_REGISTRY)
    uncovered = registry - pinned - set(UNPINNED_KNOWN_GAPS)
    assert not uncovered, (
        f"Extractor(s) {sorted(uncovered)} are in facebook.EXTRACTOR_REGISTRY but neither "
        "pinned in EXPECT_NON_EMPTY nor explained in UNPINNED_KNOWN_GAPS."
    )
    stale = set(UNPINNED_KNOWN_GAPS) & pinned
    assert not stale, f"{sorted(stale)} are pinned now — drop them from UNPINNED_KNOWN_GAPS."
    unknown = (pinned | set(UNPINNED_KNOWN_GAPS)) - registry
    assert not unknown, f"{sorted(unknown)} are not in facebook.EXTRACTOR_REGISTRY."


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", _PARAMS, ids=_IDS)
def test_fixture_is_recognized(fixture):
    if fixture is None:
        pytest.skip(_NO_FIXTURES_REASON)
    ctx = _context(fixture)
    status = ctx.validation.current_status_code
    category = ctx.validation.current_ddp_category
    assert status is not None and status.id == 0, f"{fixture.name}: validation status {status}"
    assert category is not None and category.ddp_filetype == _expected_filetype(fixture), (
        f"{fixture.name}: recognized as {category} but the name says {_expected_filetype(fixture)}"
    )


# ---------------------------------------------------------------------------
# Per-extractor canaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", _PARAMS, ids=_IDS)
@pytest.mark.parametrize("name", list(facebook.EXTRACTOR_REGISTRY), ids=list(facebook.EXTRACTOR_REGISTRY))
def test_extractor_against_fixture(name, fixture):
    if fixture is None:
        pytest.skip(_NO_FIXTURES_REASON)
    ctx = _context(fixture)
    errors: Counter = Counter()
    df = facebook.EXTRACTOR_REGISTRY[name](ctx.reader, errors, validation=ctx.validation)
    assert not errors, f"{name} on {fixture.name}: errors {dict(errors)}"
    if name in EXPECT_NON_EMPTY.get(fixture.stem, set()):
        assert not df.empty, (
            f"{name} returned an empty DataFrame for {fixture.name} — the extractor may have "
            "crashed, found no matching file, or the DDP format changed."
        )


@pytest.mark.parametrize("fixture", _PARAMS, ids=_IDS)
def test_fixture_has_pins_or_some_table(fixture):
    """A fixture nobody has pinned yet must at least yield one non-empty table,
    so a mis-named or unrecognized zip does not pass as vacuously green."""
    if fixture is None:
        pytest.skip(_NO_FIXTURES_REASON)
    if fixture.stem in EXPECT_NON_EMPTY:
        pytest.skip(f"{fixture.stem} has EXPECT_NON_EMPTY pins — see test_extractor_against_fixture")
    ctx = _context(fixture)
    non_empty = [
        name for name, fn in facebook.EXTRACTOR_REGISTRY.items()
        if not fn(ctx.reader, Counter(), validation=ctx.validation).empty
    ]
    assert non_empty, f"{fixture.name}: every extractor came back empty — add pins or check the fixture"


# ---------------------------------------------------------------------------
# Whole flow: extraction() as the participant flow runs it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", _PARAMS, ids=_IDS)
def test_whole_extraction_keeps_pinned_tables(fixture):
    """``extraction()`` (config load, every extractor, anonymization) runs to
    completion and the review page would carry a table for every pinned
    extractor — empty tables are dropped there, so this is the participant-
    visible form of the pins."""
    if fixture is None:
        pytest.skip(_NO_FIXTURES_REASON)
    ctx = _context(fixture)
    result = facebook.extraction(ctx.part, ctx.validation)
    ids_by_extractor = {
        name: next(cfg.id for cfg in load_port_config(facebook.EXTRACTOR_REGISTRY, "facebook") if cfg.extractor is fn)
        for name, fn in facebook.EXTRACTOR_REGISTRY.items()
    }
    shown = {table.id for table in result.tables}
    missing = {
        name for name in EXPECT_NON_EMPTY.get(fixture.stem, set())
        if ids_by_extractor[name] not in shown
    }
    assert not missing, f"{fixture.name}: pinned table(s) {sorted(missing)} absent from extraction() output"


# ---------------------------------------------------------------------------
# Content canary: HTML tables carry ISO timestamps and come out newest first
# ---------------------------------------------------------------------------

_DATE_COLUMNS = {"Timestamp", "Date", "Created"}


@pytest.mark.parametrize("fixture", _PARAMS, ids=_IDS)
def test_html_tables_carry_iso_timestamps_newest_first(fixture):
    """The HTML export writes display timestamps (``Jun 04, 2025 6:46:10 pm``);
    every HTML table must convert them so the two formats donate the same shape
    and ``_sort_by_date`` can rank them (audit 2026-09-01: HTML tables came out
    in file order because the ISO sort saw nothing parsable)."""
    from datetime import datetime

    if fixture is None:
        pytest.skip(_NO_FIXTURES_REASON)
    if _expected_filetype(fixture) is not DDPFiletype.HTML:
        pytest.skip("JSON export — epoch timestamps are covered by epoch_to_iso")
    ctx = _context(fixture)
    problems: list[str] = []
    for name, fn in facebook.EXTRACTOR_REGISTRY.items():
        df = fn(ctx.reader, Counter(), validation=ctx.validation)
        for column in _DATE_COLUMNS & set(df.columns):
            values = [v for v in df[column].tolist() if v]
            parsed = []
            for v in values:
                try:
                    parsed.append(datetime.fromisoformat(v))
                except ValueError:
                    problems.append(f"{name}.{column}: {v!r} is not ISO 8601")
                    break
            else:
                if parsed != sorted(parsed, reverse=True):
                    problems.append(f"{name}.{column}: not newest first")
    assert not problems, f"{fixture.name}: " + "; ".join(problems)
