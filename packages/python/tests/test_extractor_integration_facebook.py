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

``HELD_EXTRACTORS`` names the extractors that are implemented and tested but
deliberately kept out of ``EXTRACTOR_REGISTRY`` until the researcher meeting
(2026-09-02). They are pinned and run against the fixtures exactly like
registry entries — the pins cover the union of both — but they cannot appear
in ``extraction()`` output, so the whole-flow test looks only at the registry.
"""
import importlib.util
import io
import json
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import pytest

from extractor_integration_helpers import DDP_DIR, DiskPart, find_fixtures
import port.platforms.facebook as facebook
from port.helpers.extraction_helpers import ZipArchiveReader
from port.helpers.table_extractor import load_port_config
from port.helpers.validate import DDPFiletype, ValidateInput, validate_zip

REPO_ROOT = Path(__file__).resolve().parents[3]
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
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
        "your_activity_off_meta_to_df",
    },
    # Same account and day, HTML. No logged_information/search in this export:
    # its only your_search_history.html is the Marketplace one, which the
    # Searches table deliberately does not read — search stays unpinned. This
    # is Drive part -001: 262 of the 289 linked off-Meta business pages sit in
    # another part, so the held off-Meta table reads the 27 present ones.
    "facebook_html_self-2026-03": _ADS_TABLES | _ACTIVITY_TABLES | {
        "your_activity_off_meta_to_df",
    },
    # Real account, JSON, all time, delivered via Google Drive, March 2026 —
    # 2,209 files, the format participants are instructed to request. Drive
    # delivery spells the follow / like files `who_you_ve_followed` (apostrophe
    # replaced); the reader resolves that spelling, so both are pinned. The
    # grouped interaction layout (recently_viewed / recently_visited) is read
    # by the held content-shown table (79 rows here) and by profile visits
    # (recently_visited, its fallback when the split file is absent). The
    # qualified JSON search path does not collide, so search is pinned here. Reels usage is absent from this export although present
    # eight days earlier — file presence varies between exports of one account.
    "facebook_json_self-alltime-2026-03": _ADS_TABLES | _ACTIVITY_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "comments_to_df",
        "pages_and_profiles_you_follow_to_df",
        "who_youve_followed_to_df",
        "pages_youve_liked_to_df",
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
        "your_activity_off_meta_to_df",
    },
    # Real account, HTML, all time (registered 2005), delivered via Google
    # Drive, March 2026 — 2,815 files. Carries both search-history files
    # (logged_information/search and Marketplace); the extractor reads the
    # qualified path, so search is pinned. The follow / like files are spelled
    # `who_you_ve_followed` here (Drive delivery replaces the apostrophe) and
    # the reader resolves that spelling.
    "facebook_html_self-alltime-2026-03": _ADS_TABLES | _ACTIVITY_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
        "comments_to_df",
        "pages_and_profiles_you_follow_to_df",
        "who_youve_followed_to_df",
        "pages_youve_liked_to_df",
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
        "your_activity_off_meta_to_df",
    },
    # Real account, device downloads, October 2025: a three-month JSON window
    # (57 files) and a one-year HTML window (980 files). Device downloads keep
    # the apostrophe in file names; both use the grouped interaction layout.
    # The HTML one carries both search-history files; the qualified path wins.
    "facebook_json_self-device-2025-10": _ADS_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
        "your_activity_off_meta_to_df",
    },
    "facebook_html_self-device-2025-10": _ADS_TABLES | {
        "your_search_history_to_df",
        "ads_interests_to_df",
        "facebook_reels_usage_to_df",
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
        "your_activity_off_meta_to_df",
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
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
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
        "content_shown_to_you_to_df",
        "profile_visits_to_df",
        "your_activity_off_meta_to_df",
    },
}
# Not pinned on facebook_html_self-2026-03: that Drive part carries no
# logged_information/interactions folder, so the content-shown and profile
# visits tables are absent there (absence, not error).

# Implemented and tested, deliberately outside EXTRACTOR_REGISTRY until the
# researcher meeting (2026-09-02). To activate one: uncomment its registry line
# in facebook.py, add the table to configs/facebook_config.json (rm +
# `pnpm generate-config facebook`, ADR-0030), and move the name from here to the
# registry side — the pins in EXPECT_NON_EMPTY stay as they are.
HELD_EXTRACTORS: dict[str, Callable[..., pd.DataFrame]] = {
    "content_shown_to_you_to_df": facebook.content_shown_to_you_to_df,
    "your_activity_off_meta_to_df": facebook.your_activity_off_meta_to_df,
}

_ALL_EXTRACTORS: dict[str, Callable[..., pd.DataFrame]] = {**facebook.EXTRACTOR_REGISTRY, **HELD_EXTRACTORS}

# Fixture-free smoke input per held extractor: the smallest archive that makes
# it produce a non-empty frame, so its docstring headers can be checked against
# the columns it actually emits without a real export present.
_HELD_SMOKE_INPUTS: dict[str, list[tuple[str, str]]] = {
    "content_shown_to_you_to_df": [(
        "export/logged_information/interactions/recently_viewed.json",
        json.dumps({"recently_viewed": [{"name": "Ads", "description": "", "entries": [
            {"timestamp": 1700000000, "data": {"name": "An ad", "uri": "https://www.facebook.com/ads/1"}},
        ]}]}),
    )],
    "your_activity_off_meta_to_df": [(
        "export/apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.json",
        json.dumps({"off_facebook_activity_v2": [
            {"name": "A shop", "events": [{"id": 1, "type": "PAGE_VIEW", "timestamp": 1700000000}]},
        ]}),
    )],
}

UNPINNED_KNOWN_GAPS: dict[str, str] = {
    "items_viewed_to_df": "no local export contains logged_information/interactions/items_viewed.*",
    "news_your_locations_to_df": (
        "facebook_news/your_locations.json is absent from every 2026 export seen "
        "(Facebook News was discontinued); stays registered until the researcher "
        "meeting decides on its removal"
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
    """Every registry or held entry is either pinned non-empty by some fixture
    or listed as a known gap with a reason — an extractor added without either
    would be silently unexercised by every per-fixture canary."""
    pinned = set().union(*EXPECT_NON_EMPTY.values())
    registry = set(_ALL_EXTRACTORS)
    uncovered = registry - pinned - set(UNPINNED_KNOWN_GAPS)
    assert not uncovered, (
        f"Extractor(s) {sorted(uncovered)} are in facebook.EXTRACTOR_REGISTRY or HELD_EXTRACTORS "
        "but neither pinned in EXPECT_NON_EMPTY nor explained in UNPINNED_KNOWN_GAPS."
    )
    stale = set(UNPINNED_KNOWN_GAPS) & pinned
    assert not stale, f"{sorted(stale)} are pinned now — drop them from UNPINNED_KNOWN_GAPS."
    unknown = (pinned | set(UNPINNED_KNOWN_GAPS)) - registry
    assert not unknown, f"{sorted(unknown)} are neither in facebook.EXTRACTOR_REGISTRY nor in HELD_EXTRACTORS."


def test_held_extractors_are_not_registered():
    """A held extractor that reaches the registry must also leave HELD_EXTRACTORS
    (and gain a config entry) — the two lists are disjoint by construction."""
    registered = set(HELD_EXTRACTORS) & set(facebook.EXTRACTOR_REGISTRY)
    assert not registered, f"{sorted(registered)} are in the registry — drop them from HELD_EXTRACTORS."
    for name, fn in HELD_EXTRACTORS.items():
        assert fn not in facebook.EXTRACTOR_REGISTRY.values(), f"{name} is registered under another key"


def test_held_extractors_carry_valid_table_blocks():
    """A held extractor's docstring must already be what activation needs: both
    ADR-0028 blocks parse with the generator's own parsers, the table id is not
    yet in the committed config, and the headers name exactly the columns the
    extractor emits."""
    scripts = REPO_ROOT / "scripts" / "generate_port_config.py"
    spec = importlib.util.spec_from_file_location("generate_port_config", scripts)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    committed = json.loads((REPO_ROOT / "packages" / "python" / "port" / "configs" / "facebook_config.json").read_text(encoding="utf-8"))
    committed_ids = {table["id"] for table in committed["tables"]}

    for name, fn in HELD_EXTRACTORS.items():
        docstring = fn.__doc__ or ""
        config = generator._parse_table_config_block(name, docstring)
        documentation = generator._parse_table_doc_block(name, docstring)
        assert documentation is not None, f"{name}: no 'Table documentation::' block"
        assert config["id"] not in committed_ids, f"{name}: id {config['id']!r} is already in facebook_config.json"
        for key in ("title", "description"):
            assert set(config[key]) == {"en", "nl"}, f"{name}: {key} must carry en and nl"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for member, content in _HELD_SMOKE_INPUTS[name]:
                zf.writestr(member, content)
        buf.seek(0)
        reader = ZipArchiveReader(buf, [member for member, _ in _HELD_SMOKE_INPUTS[name]], Counter())
        df = fn(reader, Counter())
        assert not df.empty, f"{name}: the smoke input produced no rows"
        assert list(df.columns) == list(config["headers"]), f"{name}: headers do not match the emitted columns"
        assert list(documentation["columns"]) == list(df.columns), f"{name}: documentation columns do not match"


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
@pytest.mark.parametrize("name", list(_ALL_EXTRACTORS), ids=list(_ALL_EXTRACTORS))
def test_extractor_against_fixture(name, fixture):
    if fixture is None:
        pytest.skip(_NO_FIXTURES_REASON)
    ctx = _context(fixture)
    errors: Counter = Counter()
    # The reader keeps its own counter (ambiguous lookups, oversized or
    # unreadable members); extraction() merges the two, so check both.
    reader_errors_before = Counter(ctx.reader.errors)
    df = _ALL_EXTRACTORS[name](ctx.reader, errors, validation=ctx.validation)
    errors.update(ctx.reader.errors - reader_errors_before)
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
    # Held extractors are pinned too but cannot reach extraction() output.
    missing = {
        name for name in EXPECT_NON_EMPTY.get(fixture.stem, set())
        if name in facebook.EXTRACTOR_REGISTRY and ids_by_extractor[name] not in shown
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
    for name, fn in _ALL_EXTRACTORS.items():
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


# ---------------------------------------------------------------------------
# Cross-format pin: the HTML clock, placed in the reference zone, agrees with JSON
# ---------------------------------------------------------------------------


def test_html_clock_agrees_with_json_for_the_same_account():
    """Likes matched by their sentence between the all-time JSON and HTML exports of one
    account must carry the same timestamp once the HTML clock is read from the export's
    timezone file. A one-hour drift across a season means the zone was not honoured."""
    pair = {stem: DDP_DIR / f"{stem}.zip" for stem in ("facebook_json_self-alltime-2026-03", "facebook_html_self-alltime-2026-03")}
    if not all(path.exists() for path in pair.values()):
        pytest.skip("needs both all-time exports of the same account")
    frames = {}
    for stem, path in pair.items():
        ctx = _context(path)
        frames[stem] = facebook.likes_and_reactions_to_df(ctx.reader, Counter(), validation=ctx.validation)
    if pair["facebook_html_self-alltime-2026-03"].exists():
        html_ctx = _context(pair["facebook_html_self-alltime-2026-03"])
        # The whole-extraction path is where the HTML clock is placed.
        result = facebook.extraction(html_ctx.part, html_ctx.validation)
        html = next(t.data_frame for t in result.tables if t.id == "facebook_likes_and_reactions")
    json_times = frames["facebook_json_self-alltime-2026-03"].groupby("Title")["Timestamp"].agg(set)
    matched = [(t, ts) for t, ts in zip(html["Title"], html["Timestamp"]) if t in json_times.index and ts]
    agree = sum(ts in json_times[t] for t, ts in matched)
    assert matched, "no like sentence occurs in both exports"
    assert agree / len(matched) > 0.97, f"{agree} of {len(matched)} HTML timestamps found in the JSON export"
