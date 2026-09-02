"""Unit tests for the Facebook HTML extraction paths, on synthetic pages.

The integration canaries (``test_extractor_integration_facebook.py``) run the
same code against real exports but only when fixtures are present; these tests
pin the specific defects found in the 2026-09-01 tester-feedback audit so CI
catches a regression without real data (ADR-0014).
"""
import io
import json
import zipfile
from collections import Counter
from types import SimpleNamespace

import pytest

import port.helpers.extraction_helpers as eh
import port.platforms.facebook as facebook
from port.helpers.extraction_helpers import ZipArchiveReader
import port.helpers.validate as validate
from port.helpers.validate import DDPFiletype


def _reader(*entries: tuple[str, str], errors: Counter | None = None) -> ZipArchiveReader:
    """In-memory archive reader. Pass the same ``errors`` Counter you hand the
    extractor: ``extraction()`` shares one counter between reader and
    extractors, so reader-side counts (ambiguous lookups, oversized members)
    are only visible to a test that does the same."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries:
            zf.writestr(name, content)
    buf.seek(0)
    return ZipArchiveReader(buf, [name for name, _ in entries], errors if errors is not None else Counter())


_HTML_VALIDATION = SimpleNamespace(current_ddp_category=SimpleNamespace(ddp_filetype=DDPFiletype.HTML))


def _search_page(*entries: tuple[str, str]) -> str:
    sections = "".join(
        f'<section class="_a6-g"><div class="_2pin"><div>"{term}"</div></div>'
        f'<footer><div class="_a72d">{date}</div></footer></section>'
        for term, date in entries
    )
    return f"<html><body><main>{sections}</main></body></html>"


# ---------------------------------------------------------------------------
# Meta HTML display timestamps → ISO 8601
# ---------------------------------------------------------------------------


class TestMetaHtmlTimestampToDatetimeString:
    def test_display_format_becomes_the_shared_datetime_string(self):
        assert eh.meta_html_timestamp_to_datetime_string("Mar 02, 2026 4:57:45 pm") == "2026-03-02 16:57:45"
        assert eh.meta_html_timestamp_to_datetime_string("Jun 04, 2025 6:46:10 am") == "2025-06-04 06:46:10"
        assert eh.meta_html_timestamp_to_datetime_string("Nov 14, 2025 12:07:06 pm") == "2025-11-14 12:07:06"

    def test_empty_is_an_expected_absence(self):
        errors: Counter = Counter()
        assert eh.meta_html_timestamp_to_datetime_string("", errors=errors) == ""
        assert not errors

    def test_unparsable_text_is_returned_and_counted(self):
        errors: Counter = Counter()
        assert eh.meta_html_timestamp_to_datetime_string("gisteren", errors=errors) == "gisteren"
        assert errors["TimestampParseError"] == 1


# ---------------------------------------------------------------------------
# Search history: the qualified path, not the bare basename
# ---------------------------------------------------------------------------


class TestSearchHistoryHtml:
    def test_reads_logged_information_search_when_marketplace_file_also_present(self):
        reader = _reader(
            ("export/logged_information/search/your_search_history.html",
             _search_page(("older term", "Jan 01, 2026 9:00:00 am"), ("newer term", "Feb 01, 2026 9:00:00 am"))),
            ("export/your_facebook_activity/facebook_marketplace/your_search_history.html",
             _search_page(("a bicycle", "Mar 01, 2026 9:00:00 am"))),
        )
        errors: Counter = Counter()
        df = facebook.your_search_history_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df["Search term"]) == ["newer term", "older term"]
        assert list(df["Date"]) == ["2026-02-01 09:00:00", "2026-01-01 09:00:00"]

    def test_marketplace_only_export_yields_no_searches_table(self):
        reader = _reader(
            ("export/your_facebook_activity/facebook_marketplace/your_search_history.html",
             _search_page(("a bicycle", "Mar 01, 2026 9:00:00 am"))),
        )
        errors: Counter = Counter()
        df = facebook.your_search_history_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert df.empty
        assert not errors


# ---------------------------------------------------------------------------
# Ad preferences: a heading is counted once, for the section that owns it
# ---------------------------------------------------------------------------


_AD_PREFERENCES_PAGE = """<html><body><main>
<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">
  <section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">
    <table>
      <tr><td class="_a6_q">Is opted out of using interests to target ads</td><td class="_2piu _a6_r">True</td></tr>
      <tr><td class="_a6_q" colspan="2">Removed categories
        <div><section class="_a6-g"><div class="_2ph_ _a6-p">Engaged Shoppers</div></section></div>
        <div><section class="_a6-g"><div class="_2ph_ _a6-p">Frequent Travelers</div></section></div>
      </td></tr>
      <tr><td class="_a6_q" colspan="2"><div>
        <section class="_3-95 _a6-g">
          <h2>Ads interests</h2>
          <div><section class="_a6-g"><div class="_2ph_ _a6-p">Portrait photography</div></section></div>
          <div><section class="_a6-g"><div class="_2ph_ _a6-p">Shopping</div></section></div>
        </section>
      </div></td></tr>
    </table>
  </div></section>
</div><footer class="_3-94 _a6-o"><div class="_a72d"/></footer></section>
</main></body></html>"""


class TestAdPreferencesHtml:
    def test_each_interest_appears_once(self):
        reader = _reader(("export/ads_information/ad_preferences.html", _AD_PREFERENCES_PAGE))
        errors: Counter = Counter()
        df = facebook.ad_preferences_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        interests = df[df["Label"] == "Ads interests"]["Value"].tolist()
        assert sorted(interests) == ["Portrait photography", "Shopping"]

    def test_values_outside_the_headed_section_are_not_given_its_label(self):
        reader = _reader(("export/ads_information/ad_preferences.html", _AD_PREFERENCES_PAGE))
        df = facebook.ad_preferences_to_df(reader, Counter(), validation=_HTML_VALIDATION)
        assert "Engaged Shoppers" not in df[df["Label"] == "Ads interests"]["Value"].tolist()
        assert ("Is opted out of using interests to target ads", "True") in list(df.itertuples(index=False, name=None))

    def test_colspan_labelled_lists_become_rows_like_the_json_vec_entries(self):
        """The JSON path emits one row per value of a list entry such as
        "Removed categories"; the HTML renders that list as a colspan-labelled
        cell, which must yield the same rows."""
        reader = _reader(("export/ads_information/ad_preferences.html", _AD_PREFERENCES_PAGE))
        df = facebook.ad_preferences_to_df(reader, Counter(), validation=_HTML_VALIDATION)
        removed = df[df["Label"] == "Removed categories"]["Value"].tolist()
        assert removed == ["Engaged Shoppers", "Frequent Travelers"]


# ---------------------------------------------------------------------------
# Generic names are looked up by folder, so a same-named file elsewhere in the
# export cannot make the lookup ambiguous (and therefore empty)
# ---------------------------------------------------------------------------


_EMPTY_PAGE = "<html><body><main></main></body></html>"


class TestGenericLookupsAreFolderQualified:
    @pytest.mark.parametrize(
        "extractor, member",
        [
            (facebook.comments_to_df, "your_facebook_activity/comments_and_reactions/comments.html"),
            (facebook.your_contributions_to_df, "your_facebook_activity/groups/your_contributions.html"),
            (facebook.your_events_to_df, "your_facebook_activity/events/your_events.html"),
        ],
        ids=["comments", "contributions", "events"],
    )
    def test_decoy_with_the_same_basename_does_not_collide(self, extractor, member):
        decoy = "export/decoy/" + member.rsplit("/", 1)[-1]
        errors: Counter = Counter()
        reader = _reader(("export/" + member, _EMPTY_PAGE), (decoy, _EMPTY_PAGE), errors=errors)
        extractor(reader, errors, validation=_HTML_VALIDATION)
        assert not any(key.startswith("AmbiguousMemberMatch") for key in errors), dict(errors)


# ---------------------------------------------------------------------------
# Every HTML table carries ISO timestamps and comes out newest first
# ---------------------------------------------------------------------------


_FOLLOWED_PAGE = """<html><body><main>
<section class="_a6-g"><h2>Oldest Page</h2><footer><div class="_a72d">Jan 05, 2024 1:00:00 pm</div></footer></section>
<section class="_a6-g"><h2>Newest Page</h2><footer><div class="_a72d">Jun 04, 2025 6:46:10 pm</div></footer></section>
<section class="_a6-g"><h2>Middle Page</h2><footer><div class="_a72d">Nov 14, 2024 10:21:53 am</div></footer></section>
</main></body></html>"""


class TestHtmlTimestampsAreIsoAndSorted:
    @pytest.mark.parametrize("member", ["export/connections/followers/who_you've_followed.html",
                                        "export/connections/followers/who_you_ve_followed.html"])
    def test_who_youve_followed_html(self, member):
        reader = _reader((member, _FOLLOWED_PAGE))
        errors: Counter = Counter()
        df = facebook.who_youve_followed_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df["Name"]) == ["Newest Page", "Middle Page", "Oldest Page"]
        assert list(df["Timestamp"]) == ["2025-06-04 18:46:10", "2024-11-14 10:21:53", "2024-01-05 13:00:00"]


# ---------------------------------------------------------------------------
# The HTML export's clock: the account's timezone, named in a file of the export
# ---------------------------------------------------------------------------


_TIMEZONE_JSON = '{"media": [], "label_values": [{"label": "Timezone", "value": "Europe/Amsterdam"}], "fbid": "1"}'
_TIMEZONE_HTML = (
    '<html><body><main><section class="_a6-g"><table><tr>'
    '<td class="_a6_q">Time zone</td><td class="_2piu _a6_r">Europe/London</td>'
    '</tr></table></section></main></body></html>'
)


class TestAccountTimezone:
    def test_read_from_the_json_export(self):
        reader = _reader(("export/logged_information/location/timezone.json", _TIMEZONE_JSON))
        assert facebook._account_timezone(reader) == "Europe/Amsterdam"

    def test_read_from_the_html_export(self):
        reader = _reader(("export/logged_information/location/timezone.html", _TIMEZONE_HTML))
        assert facebook._account_timezone(reader) == "Europe/London"

    def test_absent_is_none_and_not_an_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/nothing.html", "<html/>"), errors=errors)
        assert facebook._account_timezone(reader) is None
        assert not errors


# An HTML export small enough to build by hand but recognised by validate_zip
# (three of the category's known file names is enough), with one dated record.
def _html_export(*extra: tuple[str, str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("export/connections/followers/who_you've_followed.html", _FOLLOWED_PAGE)
        zf.writestr("export/logged_information/search/your_search_history.html", "<html/>")
        zf.writestr("export/ads_information/ad_preferences.html", "<html/>")
        for name, content in extra:
            zf.writestr(name, content)
    buf.seek(0)
    return buf


def _extract(buf: io.BytesIO):
    validation = validate.validate_zip(facebook.DDP_CATEGORIES, buf)
    assert validation.current_ddp_category.ddp_filetype is DDPFiletype.HTML
    result = facebook.extraction(buf, validation)
    return {t.id: t.data_frame for t in result.tables}, result.errors


class TestHtmlClockIsPlacedInTheReferenceZone:
    def test_an_account_in_london_moves_an_hour_forward(self):
        tables, errors = _extract(_html_export(("export/logged_information/location/timezone.html", _TIMEZONE_HTML)))
        # 6:46:10 pm British Summer Time is 7:46:10 pm in Amsterdam.
        assert list(tables["facebook_who_youve_followed"]["Timestamp"]) == [
            "2025-06-04 19:46:10", "2024-11-14 11:21:53", "2024-01-05 14:00:00",
        ]
        assert "HtmlTimezoneUnknown" not in errors

    def test_without_the_file_the_clock_is_left_and_counted_once(self):
        tables, errors = _extract(_html_export())
        assert list(tables["facebook_who_youve_followed"]["Timestamp"]) == [
            "2025-06-04 18:46:10", "2024-11-14 10:21:53", "2024-01-05 13:00:00",
        ]
        assert errors["HtmlTimezoneUnknown"] == 1


# ---------------------------------------------------------------------------
# Profile visits: the split file when present, else the grouped recently_visited
# ---------------------------------------------------------------------------


_PROFILE_VISITS_SPLIT_JSON = "export/logged_information/interactions/profile_visits.json"
_PROFILE_VISITS_SPLIT_HTML = "export/logged_information/interactions/profile_visits.html"
_RECENTLY_VISITED_JSON = "export/logged_information/interactions/recently_visited.json"
_RECENTLY_VISITED_HTML = "export/logged_information/interactions/recently_visited.html"

# Four days of epoch seconds, one day apart (22:13:20 UTC = 23:13:20 Amsterdam).
_V1, _V2, _V3, _V4 = 1700000000, 1700086400, 1700172800, 1700259200

# The split layout (not attested locally): one label/value record per visit.
_SPLIT_VISITS_JSON = json.dumps([
    {"timestamp": _V1, "label_values": [{"label": "Name", "value": "Split Older"}]},
    {"timestamp": _V2, "label_values": [{"label": "Name", "value": "Split Newer"}]},
])

# The grouped layout as every local export writes it: one section per kind of
# thing visited; the Marketplace section is a value-only date counter.
_GROUPED_VISITS_JSON = json.dumps({"visited_things_v2": [
    {"name": "Profile visits", "description": "People whose profiles you've visited", "entries": [
        {"timestamp": _V1, "data": {"name": "A Person", "uri": "https://www.facebook.com/a.person"}},
        {"timestamp": _V4, "data": {"name": "CafÃ© Owner", "uri": "https://www.facebook.com/cafe.owner"}},
    ]},
    {"name": "Page visits", "description": "Pages you've visited", "entries": [
        {"timestamp": _V2, "data": {"name": "A Page", "uri": "https://facebook.com/apage"}},
    ]},
    {"name": "Events visited", "description": "Events you've visited", "entries": [
        {"timestamp": _V3, "data": {"name": "An Event", "uri": "https://www.facebook.com/events/1/"}},
    ]},
    {"name": "Groups visited", "description": "Groups you've visited", "entries": [
        {"timestamp": _V3, "data": {"name": "A Group", "uri": "https://www.facebook.com/groups/1/"}},
    ]},
    {"name": "Marketplace Visits", "description": "Days you visited Marketplace", "entries": [
        {"data": {"value": "Jun 4, 2025"}},
    ]},
]})

_GROUPED_VISITS_ROWS = [
    ("Profile visits", "Café Owner", "2023-11-17 23:13:20"),
    ("Events visited", "An Event", "2023-11-16 23:13:20"),
    ("Groups visited", "A Group", "2023-11-16 23:13:20"),
    ("Page visits", "A Page", "2023-11-15 23:13:20"),
    ("Profile visits", "A Person", "2023-11-14 23:13:20"),
]


def _split_visits_page(*entries: tuple[str, str]) -> str:
    """The split page as ``profile_visits.html`` writes it: one top-level
    record section with a one-row table and a dated footer."""
    sections = "".join(
        f'<section class="_a6-g"><div class="_a6-p"><table><tr>'
        f'<td class="_a6_q">Name</td><td class="_2piu _a6_r">{name}</td>'
        f'</tr></table></div><footer><div class="_a72d">{when}</div></footer></section>'
        for name, when in entries
    )
    return f"<html><body><main>{sections}</main></body></html>"


def _visited_leaf(name: str, when: str) -> str:
    """One record of the grouped page: the name in the first non-empty div
    of the ``_a6-p`` body, the time in the footer's ``_a72d`` (empty for a
    value-only Marketplace counter)."""
    body = f'<div><div><div>{name}</div><div></div></div></div><div></div><div></div>'
    footer = f'<footer class="_a6-o"><a target="_blank" href="https://www.facebook.com/dyi/l/?l=x"><div class="_a72d">{when}</div></a></footer>'
    return f'<section class="_a6-g"><div class="_2ph_ _a6-p">{body}</div>{footer}</section>'


def _visited_group(name: str, inner: str) -> str:
    return f'<section class="_a6-g"><h2 class="_a6-h">{name}</h2><div class="_2ph_ _a6-p"><p>About.</p><div><div>{inner}</div></div></div></section>'


_GROUPED_VISITS_PAGE = "<html><body><main>" + _visited_group(
    "Profile visits",
    _visited_leaf("A Person", "Nov 14, 2023 10:13:20 pm") + _visited_leaf("Another Person", "Nov 17, 2023 10:13:20 pm"),
) + _visited_group(
    "Page visits", _visited_leaf("A Page", "Nov 15, 2023 10:13:20 pm"),
) + _visited_group(
    "Events visited", _visited_leaf("An Event", "Nov 16, 2023 10:13:20 pm"),
) + _visited_group(
    "Groups visited", _visited_leaf("A Group", "Nov 16, 2023 10:13:20 pm"),
) + _visited_group(
    "Marketplace Visits", _visited_leaf("Jun 4, 2025", ""),
) + "</main></body></html>"

_GROUPED_VISITS_HTML_ROWS = [
    ("Profile visits", "Another Person", "2023-11-17 22:13:20"),
    ("Events visited", "An Event", "2023-11-16 22:13:20"),
    ("Groups visited", "A Group", "2023-11-16 22:13:20"),
    ("Page visits", "A Page", "2023-11-15 22:13:20"),
    ("Profile visits", "A Person", "2023-11-14 22:13:20"),
]


class TestProfileVisitsFallsBackToRecentlyVisited:
    def test_split_json_is_used_when_present(self):
        errors: Counter = Counter()
        reader = _reader(
            (_PROFILE_VISITS_SPLIT_JSON, _SPLIT_VISITS_JSON),
            (_RECENTLY_VISITED_JSON, _GROUPED_VISITS_JSON),
            errors=errors,
        )
        df = facebook.profile_visits_to_df(reader, errors)
        assert not errors
        assert list(df.columns) == ["Category", "Name", "Timestamp"]
        assert list(df.itertuples(index=False, name=None)) == [
            ("Profile visits", "Split Newer", "2023-11-15 23:13:20"),
            ("Profile visits", "Split Older", "2023-11-14 23:13:20"),
        ]

    def test_grouped_json_sections_become_rows_with_their_category(self):
        errors: Counter = Counter()
        reader = _reader((_RECENTLY_VISITED_JSON, _GROUPED_VISITS_JSON), errors=errors)
        df = facebook.profile_visits_to_df(reader, errors)
        assert not errors
        assert list(df.columns) == ["Category", "Name", "Timestamp"]
        assert list(df.itertuples(index=False, name=None)) == _GROUPED_VISITS_ROWS
        assert "Marketplace Visits" not in df["Category"].tolist()

    def test_split_html_is_used_when_present(self):
        errors: Counter = Counter()
        reader = _reader(
            (_PROFILE_VISITS_SPLIT_HTML, _split_visits_page(
                ("Split Older", "Nov 14, 2023 10:13:20 pm"), ("Split Newer", "Nov 15, 2023 10:13:20 pm"),
            )),
            (_RECENTLY_VISITED_HTML, _GROUPED_VISITS_PAGE),
            errors=errors,
        )
        df = facebook.profile_visits_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.columns) == ["Category", "Name", "Timestamp"]
        assert list(df.itertuples(index=False, name=None)) == [
            ("Profile visits", "Split Newer", "2023-11-15 22:13:20"),
            ("Profile visits", "Split Older", "2023-11-14 22:13:20"),
        ]

    def test_grouped_html_leaves_become_rows_with_the_nearest_heading(self):
        errors: Counter = Counter()
        reader = _reader((_RECENTLY_VISITED_HTML, _GROUPED_VISITS_PAGE), errors=errors)
        df = facebook.profile_visits_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.columns) == ["Category", "Name", "Timestamp"]
        assert list(df.itertuples(index=False, name=None)) == _GROUPED_VISITS_HTML_ROWS
        assert "Marketplace Visits" not in df["Category"].tolist()

    def test_absence_of_both_files_is_empty_and_not_an_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/ads_information/ad_preferences.json", "{}"), errors=errors)
        assert facebook.profile_visits_to_df(reader, errors).empty
        assert facebook.profile_visits_to_df(reader, errors, validation=_HTML_VALIDATION).empty
        assert not errors


# The September 2026 split layout also writes groups_and_events_you've_visited:
# a record with Start time / End time (and a URL) is an event, one with only a
# Name is a group. The categories match the grouped layout's section names.
_GROUPS_AND_EVENTS_JSON = "export/logged_information/interactions/groups_and_events_you've_visited.json"
_GROUPS_AND_EVENTS_HTML = "export/logged_information/interactions/groups_and_events_you've_visited.html"

_GROUPS_AND_EVENTS_RECORDS = json.dumps([
    {"timestamp": _V3, "media": [], "label_values": [
        {"label": "Name", "value": "An Event"},
        {"label": "Start time", "timestamp_value": _V4},
        {"label": "Description", "value": "About the event."},
        {"label": "End time", "timestamp_value": _V4},
        {"label": "URL", "value": "https://www.facebook.com/events/1/", "href": "https://www.facebook.com/events/1/"},
    ], "fbid": "1"},
    {"timestamp": _V4, "media": [], "label_values": [{"label": "Name", "value": "CafÃ© Group"}], "fbid": "2"},
    {"timestamp": _V1, "media": [], "label_values": [
        {"label": "Name", "value": "An Open-Ended Event"},
        {"label": "Start time", "timestamp_value": _V2},
        {"label": "URL", "value": "https://www.facebook.com/events/2/", "href": "https://www.facebook.com/events/2/"},
    ], "fbid": "3"},
])

_GROUPS_AND_EVENTS_ROWS = [
    ("Groups visited", "Café Group", "2023-11-17 23:13:20"),
    ("Events visited", "An Event", "2023-11-16 23:13:20"),
    ("Events visited", "An Open-Ended Event", "2023-11-14 23:13:20"),
]


def _visited_record(rows: str, when: str) -> str:
    """One record as the September pages write it: a top-level section holding
    a nested leaf section with the label/value table, then a dated footer."""
    return (
        '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">'
        '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">'
        f'<table>{rows}</table></div></section></div>'
        f'<footer class="_3-94 _a6-o"><div class="_a72d">{when}</div></footer></section>'
    )


def _cell_row(label: str, value: str) -> str:
    return f'<tr><td class="_a6_q">{label}</td><td class="_2piu _a6_r">{value}</td></tr>'


def _url_row(href: str) -> str:
    return f'<tr><td class="_a6_q" colspan="2">URL<div><a href="{href}">{href}</a></div></td></tr>'


_GROUPS_AND_EVENTS_PAGE = '<html><body><div class="_li"><main class="_a706">' + _visited_record(
    _cell_row("Name", "An Event") + _cell_row("Start time", "Nov 17, 2023 10:13:20 pm") + _cell_row("Description", "About the event.")
    + _cell_row("End time", "Nov 17, 2023 11:13:20 pm") + _url_row("https://www.facebook.com/events/1/"),
    "Nov 16, 2023 10:13:20 pm",
) + _visited_record(
    _cell_row("Name", "A Group"), "Nov 17, 2023 10:13:20 pm",
) + _visited_record(
    _cell_row("Name", "An Open-Ended Event") + _cell_row("Start time", "Nov 15, 2023 10:13:20 pm") + _url_row("https://www.facebook.com/events/2/"),
    "Nov 14, 2023 10:13:20 pm",
) + '</main></div></body></html>'

_GROUPS_AND_EVENTS_HTML_ROWS = [
    ("Groups visited", "A Group", "2023-11-17 22:13:20"),
    ("Events visited", "An Event", "2023-11-16 22:13:20"),
    ("Events visited", "An Open-Ended Event", "2023-11-14 22:13:20"),
]


class TestProfileVisitsReadsGroupsAndEvents:
    def test_json_events_and_groups_are_categorised_by_their_labels(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPS_AND_EVENTS_JSON, _GROUPS_AND_EVENTS_RECORDS), errors=errors)
        df = facebook.profile_visits_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _GROUPS_AND_EVENTS_ROWS

    def test_json_is_concatenated_after_profile_visits(self):
        errors: Counter = Counter()
        reader = _reader(
            (_PROFILE_VISITS_SPLIT_JSON, _SPLIT_VISITS_JSON),
            (_GROUPS_AND_EVENTS_JSON, _GROUPS_AND_EVENTS_RECORDS),
            (_RECENTLY_VISITED_JSON, _GROUPED_VISITS_JSON),
            errors=errors,
        )
        df = facebook.profile_visits_to_df(reader, errors)
        assert not errors
        assert len(df) == 2 + len(_GROUPS_AND_EVENTS_ROWS)
        assert sorted(df["Timestamp"].tolist(), reverse=True) == df["Timestamp"].tolist()
        assert set(df["Category"]) == {"Profile visits", "Events visited", "Groups visited"}
        assert "A Person" not in df["Name"].tolist()  # the grouped file is not read in the split layout

    def test_html_events_and_groups_are_categorised_by_their_rows(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPS_AND_EVENTS_HTML, _GROUPS_AND_EVENTS_PAGE), errors=errors)
        df = facebook.profile_visits_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _GROUPS_AND_EVENTS_HTML_ROWS

    def test_html_is_concatenated_after_profile_visits(self):
        errors: Counter = Counter()
        reader = _reader(
            (_PROFILE_VISITS_SPLIT_HTML, _split_visits_page(("Split Older", "Nov 14, 2023 10:13:20 pm"))),
            (_GROUPS_AND_EVENTS_HTML, _GROUPS_AND_EVENTS_PAGE),
            errors=errors,
        )
        df = facebook.profile_visits_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert len(df) == 1 + len(_GROUPS_AND_EVENTS_HTML_ROWS)
        assert sorted(df["Timestamp"].tolist(), reverse=True) == df["Timestamp"].tolist()
        assert ("Profile visits", "Split Older", "2023-11-14 22:13:20") in list(df.itertuples(index=False, name=None))


# ---------------------------------------------------------------------------
# A bare single record: Facebook writes an object, not a one-element list,
# when a file has exactly one item
# ---------------------------------------------------------------------------


_BARE_LINK_HISTORY = json.dumps({
    "timestamp": _V2,
    "media": [],
    "label_values": [
        {"label": "Website link you visited", "value": "https://example.org/article", "href": "https://example.org/article"},
        {"label": "Title of website page you visited", "value": "An article"},
        {"label": "Website session start time", "value": "Nov 15, 2023 11:13:20 pm"},
        {"label": "Website session end time", "value": "Nov 15, 2023 11:20:00 pm"},
    ],
    "fbid": "1",
})


class TestBareSingleRecord:
    def test_link_history_with_one_record_yields_one_row(self):
        errors: Counter = Counter()
        reader = _reader(("export/your_facebook_activity/other_activity/link_history.json", _BARE_LINK_HISTORY), errors=errors)
        df = facebook.link_history_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == [
            ("https://example.org/article", "An article", "2023-11-15 23:13:20"),
        ]

    @pytest.mark.parametrize(
        "data, expected",
        [
            ([{"label_values": []}, {"label_values": []}], 2),
            ({"timestamp": 1, "label_values": [{"label": "Name", "value": "x"}]}, 1),
            ({"recently_viewed": []}, 0),
            ("not records", 0),
        ],
        ids=["list", "bare-record", "other-dict", "not-json-records"],
    )
    def test_records_helper(self, data, expected):
        assert len(facebook._records(data)) == expected
