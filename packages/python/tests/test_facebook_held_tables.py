"""Unit tests for the Facebook tables that are implemented but held out of the
registry until the researcher meeting (2026-09-02).

Held extractors are not in ``EXTRACTOR_REGISTRY`` and have no entry in the
committed config, so nothing but these tests (and the ``HELD_EXTRACTORS`` pins
in ``test_extractor_integration_facebook.py``) exercises them. Synthetic inputs
cover both interaction layouts Facebook writes: the grouped
``recently_viewed`` file of exports up to June 2026, and the split layout of
the September 2026 device exports — the feed file (one record holding Posts /
Videos / Links lists), ``ads`` and ``shows_you_have_watched`` — with the
synthetic HTML modelled on those pages' markup. The off-Meta
activity table is covered in both of its JSON shapes (the 2025
``off_facebook_activity_v2`` object and the 2026 list of records) and in its
HTML form: an index page plus one page per business, read one at a time.
"""
import io
import json
import textwrap
import zipfile
from collections import Counter
from types import SimpleNamespace

import pytest

import port.helpers.extraction_helpers as eh
import port.platforms.facebook as facebook
from port.helpers.extraction_helpers import ZipArchiveReader
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


def _table_config(fn) -> dict:
    """The ``Table config::`` block of *fn*'s docstring, as the generator reads it."""
    block = fn.__doc__.split("Table config::", 1)[1]
    return json.loads(textwrap.dedent(block))


# ---------------------------------------------------------------------------
# Content shown to you — grouped layout (recently_viewed)
# ---------------------------------------------------------------------------

_GROUPED_JSON = "export/logged_information/interactions/recently_viewed.json"
_GROUPED_HTML = "export/logged_information/interactions/recently_viewed.html"
_FEED_JSON = "export/logged_information/interactions/content_that_has_been_shown_to_you_in_your_feed.json"
_FEED_HTML = "export/logged_information/interactions/content_that_has_been_shown_to_you_in_your_feed.html"
_ADS_JSON = "export/logged_information/interactions/ads.json"
_ADS_HTML = "export/logged_information/interactions/ads.html"
_SHOWS_JSON = "export/logged_information/interactions/shows_you_have_watched.json"
_SHOWS_HTML = "export/logged_information/interactions/shows_you_have_watched.html"

_FEED = "Posts that have been shown to you in your Feed"

# "Café" as Meta writes it: the UTF-8 bytes read back as latin-1 code points.
_MOJIBAKE = "CafÃ©"

# Four days of epoch seconds, one day apart, so the expected ISO strings are
# easy to read: 2023-11-14 .. 2023-11-17, 22:13:20 UTC.
_T1, _T2, _T3, _T4 = 1700000000, 1700086400, 1700172800, 1700259200
_D1, _D2, _D3, _D4 = (
    "2023-11-14 23:13:20",
    "2023-11-15 23:13:20",
    "2023-11-16 23:13:20",
    "2023-11-17 23:13:20",
)


def _grouped_json(feed_name: str = _FEED) -> str:
    return json.dumps({"recently_viewed": [
        {"name": feed_name, "description": "Posts.", "entries": [
            {"timestamp": _T1, "data": {"name": "Older post", "uri": "https://www.facebook.com/p/1"}},
            {"timestamp": _T2, "data": {"name": _MOJIBAKE, "uri": "https://www.facebook.com/p/2"}},
        ]},
        {"name": "Web pages you've visited off Facebook", "description": "Pages.", "entries": [
            {"timestamp": _T3, "data": {"name": "Some site", "share": "https://example.org/article"}},
        ]},
        {"name": "Marketplace Interactions", "description": "Marketplace.", "children": [
            {"name": "Marketplace Searches", "description": "Counter.", "entries": [
                {"data": {"value": "Nov 14, 2023"}},
                {"data": {"value": "Nov 15, 2023"}},
            ]},
            {"name": "Marketplace Items", "description": "Items.", "entries": [
                {"timestamp": _T4, "data": {"name": "A bicycle", "uri": "https://www.facebook.com/marketplace/item/1"}},
            ]},
        ]},
    ]})


_GROUPED_ROWS = [
    ("Marketplace Items", "A bicycle", "https://www.facebook.com/marketplace/item/1", _D4),
    ("Web pages you've visited off Facebook", "Some site", "https://example.org/article", _D3),
    (_FEED, "Café", "https://www.facebook.com/p/2", _D2),
    (_FEED, "Older post", "https://www.facebook.com/p/1", _D1),
]


def _leaf(name: str, href: str | None, when: str) -> str:
    """One record section as the grouped HTML writes it: the name in the first
    non-empty div of the ``_a6-p`` body, the time in the footer's ``_a72d``.
    A value-only Marketplace counter has no link and an empty ``_a72d``."""
    body = f'<div><div><div>{name}</div><div></div></div></div><div></div><div></div>'
    if href is None:
        footer = f'<footer class="_a6-o"><div class="_a72d">{when}</div></footer>'
    else:
        footer = f'<footer class="_a6-o"><a target="_blank" href="{href}"><div class="_a72d">{when}</div></a></footer>'
    return f'<section class="_a6-g"><div class="_2ph_ _a6-p">{body}</div>{footer}</section>'


def _group(name: str, inner: str) -> str:
    return f'<section class="_a6-g"><h2 class="_a6-h">{name}</h2><div class="_2ph_ _a6-p"><p>About.</p><div><div>{inner}</div></div></div></section>'


_GROUPED_PAGE = "<html><body><main>" + _group(
    "Marketplace Interactions",
    _group("Marketplace Searches", _leaf("Nov 14, 2023", None, "") + _leaf("Nov 15, 2023", None, ""))
    + _group("Marketplace Items", _leaf("A bicycle", "https://www.facebook.com/marketplace/item/1", "Nov 17, 2023 10:13:20 pm")),
) + _group(
    _FEED,
    _leaf("Older post", "https://www.facebook.com/p/1", "Nov 14, 2023 10:13:20 pm")
    + _leaf("Newer post", "https://www.facebook.com/p/2", "Nov 15, 2023 10:13:20 pm"),
) + "</main></body></html>"

_GROUPED_HTML_ROWS = [
    ("Marketplace Items", "A bicycle", "https://www.facebook.com/marketplace/item/1", "2023-11-17 22:13:20"),
    (_FEED, "Newer post", "https://www.facebook.com/p/2", "2023-11-15 22:13:20"),
    (_FEED, "Older post", "https://www.facebook.com/p/1", "2023-11-14 22:13:20"),
]


class TestContentShownGroupedJson:
    def test_entries_and_children_become_rows_newest_first(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPED_JSON, _grouped_json()), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _GROUPED_ROWS

    def test_value_only_entries_are_not_rows(self):
        reader = _reader((_GROUPED_JSON, _grouped_json()))
        df = facebook.content_shown_to_you_to_df(reader, Counter())
        assert "Marketplace Searches" not in df["Category"].tolist()
        assert len(df) == 4

    @pytest.mark.parametrize("name", ["Videos you've watched", "Videos you have watched", "Video's die je hebt bekeken"])
    def test_section_names_pass_through_as_category(self, name):
        """Meta renames its sections between exports; the extractor keys on the
        structure and reports whatever name the export used."""
        reader = _reader((_GROUPED_JSON, _grouped_json(feed_name=name)))
        df = facebook.content_shown_to_you_to_df(reader, Counter())
        assert df[df["Name"] == "Older post"]["Category"].tolist() == [name]

    def test_absence_is_an_empty_frame_and_no_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/ads_information/ad_preferences.json", "{}"), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert df.empty
        assert not errors


class TestContentShownGroupedHtml:
    def test_linked_leaves_become_rows_newest_first(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPED_HTML, _GROUPED_PAGE), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _GROUPED_HTML_ROWS

    def test_value_only_leaves_with_an_empty_timestamp_are_excluded(self):
        reader = _reader((_GROUPED_HTML, _GROUPED_PAGE))
        df = facebook.content_shown_to_you_to_df(reader, Counter(), validation=_HTML_VALIDATION)
        assert "Marketplace Searches" not in df["Category"].tolist()
        assert "Nov 14, 2023" not in df["Name"].tolist()

    def test_category_is_the_nearest_headed_section(self):
        """A child group's records carry the child's h2, not the parent's."""
        reader = _reader((_GROUPED_HTML, _GROUPED_PAGE))
        df = facebook.content_shown_to_you_to_df(reader, Counter(), validation=_HTML_VALIDATION)
        assert "Marketplace Interactions" not in df["Category"].tolist()
        assert df[df["Name"] == "A bicycle"]["Category"].tolist() == ["Marketplace Items"]

    def test_absence_is_an_empty_frame_and_no_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/ads_information/ad_preferences.html", "<html/>"), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert df.empty
        assert not errors


# ---------------------------------------------------------------------------
# Content shown to you — split layout (September 2026: the feed file, ads,
# shows_you_have_watched)
# ---------------------------------------------------------------------------


def _vec_item(*entries: dict) -> dict:
    return {"dict": list(entries)}


# The feed file: one bare record whose label_values are the Posts / Videos /
# Links lists, each a vec of Event · URL · Time dicts (the list label is the
# category). The second post has no href on its URL entry, only a value.
_FEED_RECORD = json.dumps({
    "media": [],
    "label_values": [
        {"label": "Posts", "vec": [
            _vec_item({"label": "Event", "value": _MOJIBAKE},
                      {"label": "URL", "value": "https://www.facebook.com/p/2", "href": "https://www.facebook.com/p/2"},
                      {"label": "Time", "timestamp_value": _T2}),
            _vec_item({"label": "Event", "value": "Older post"},
                      {"label": "URL", "value": "https://www.facebook.com/p/1"},
                      {"label": "Time", "timestamp_value": _T1}),
        ]},
        {"label": "Videos", "vec": [
            _vec_item({"label": "Event", "value": "A video"},
                      {"label": "URL", "value": "https://www.facebook.com/v/3", "href": "https://www.facebook.com/v/3"},
                      {"label": "Time", "timestamp_value": _T3}),
        ]},
        {"label": "Links", "vec": []},
    ],
    "fbid": "1",
})

_FEED_ROWS = [
    ("Videos", "A video", "https://www.facebook.com/v/3", _D3),
    ("Posts", "Café", "https://www.facebook.com/p/2", _D2),
    ("Posts", "Older post", "https://www.facebook.com/p/1", _D1),
]

# ads: a list of records with an Ad (value + href) and a Time entry, no
# record-level timestamp.
_ADS_RECORDS = json.dumps([
    {"media": [], "label_values": [
        {"label": "Ad", "value": "An advertiser", "href": "https://www.facebook.com/ads/1"},
        {"label": "Time", "timestamp_value": _T1},
    ], "fbid": "11"},
    {"media": [], "label_values": [
        {"label": "Ad", "value": _MOJIBAKE, "href": "https://www.facebook.com/ads/2"},
        {"label": "Time", "timestamp_value": _T4},
    ], "fbid": "12"},
])

_ADS_ROWS = [
    ("Ads", "Café", "https://www.facebook.com/ads/2", _D4),
    ("Ads", "An advertiser", "https://www.facebook.com/ads/1", _D1),
]

# shows_you_have_watched: records with Title and URL (href) and a record-level timestamp.
_SHOWS_RECORDS = json.dumps([
    {"timestamp": _T3, "media": [], "label_values": [
        {"label": "Title", "value": "A show"},
        {"label": "URL", "value": "https://www.facebook.com/s/1", "href": "https://www.facebook.com/s/1"},
    ], "fbid": "21"},
    {"timestamp": _T2, "media": [], "label_values": [
        {"label": "Title", "value": "Another show"},
        {"label": "URL", "value": "https://www.facebook.com/s/2", "href": "https://www.facebook.com/s/2"},
    ], "fbid": "22"},
])

_SHOWS = "Videos you have watched"

_SHOWS_ROWS = [
    (_SHOWS, "A show", "https://www.facebook.com/s/1", _D3),
    (_SHOWS, "Another show", "https://www.facebook.com/s/2", _D2),
]


def _value_row(label: str, value: str) -> str:
    return f'<tr><td class="_a6_q">{label}</td><td class="_2piu _a6_r">{value}</td></tr>'


def _link_row(label: str, href: str, text: str) -> str:
    """A link row as the September pages write it: the label cell spans both
    columns and holds the anchor; there is no value cell."""
    return f'<tr><td class="_a6_q" colspan="2">{label}<div><a href="{href}">{text}</a></div></td></tr>'


def _leaf_table(rows: str) -> str:
    return (
        '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">'
        '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">'
        f'<table>{rows}</table></div></section></div>'
    )


def _record_section(rows: str, footer_date: str) -> str:
    """One record as ads.html / shows_you_have_watched.html write it: a top-level
    section holding a leaf table and a footer."""
    return _leaf_table(rows) + f'<footer class="_3-94 _a6-o"><div class="_a72d">{footer_date}</div></footer></section>'


def _feed_leaf(event: str, href: str, when: str) -> str:
    """One feed item: a nested section pair with Event / URL / Time rows and no footer."""
    return f'<div>{_leaf_table(_value_row("Event", event) + _link_row("URL", href, href) + _value_row("Time", when))}</section></div>'


def _feed_list(name: str, leaves: str) -> str:
    """A Posts / Videos list: a colspan label cell of the enclosing table whose
    text is the list name, holding the item sections."""
    return f'<tr><td class="_a6_q" colspan="2">{name}<div><div>{leaves}</div></div></td></tr>'


_MAIN_OPEN = '<html><body><div class="_li"><main class="_a706">'
_MAIN_CLOSE = '</main></div></body></html>'

_FEED_PAGE = (
    _MAIN_OPEN
    + _leaf_table(
        _feed_list("Posts", _feed_leaf("Older post", "https://www.facebook.com/p/1", "Nov 14, 2023 10:13:20 pm")
                   + _feed_leaf("Newer post", "https://www.facebook.com/p/2", "Nov 15, 2023 10:13:20 pm"))
        + _feed_list("Videos", _feed_leaf("A video", "https://www.facebook.com/v/3", "Nov 16, 2023 10:13:20 pm"))
    )
    + '<footer class="_3-94 _a6-o"><div class="_a72d"></div></footer></section>'
    + _MAIN_CLOSE
)

_FEED_HTML_ROWS = [
    ("Videos", "A video", "https://www.facebook.com/v/3", "2023-11-16 22:13:20"),
    ("Posts", "Newer post", "https://www.facebook.com/p/2", "2023-11-15 22:13:20"),
    ("Posts", "Older post", "https://www.facebook.com/p/1", "2023-11-14 22:13:20"),
]

# ads.html: the Ad row is a link row (anchor text = advertiser); the footer's
# _a72d is empty, so the time comes from the Time cell.
_ADS_PAGE = (
    _MAIN_OPEN
    + _record_section(_link_row("Ad", "https://www.facebook.com/ads/1", "An advertiser") + _value_row("Time", "Nov 14, 2023 10:13:20 pm"), "")
    + _record_section(_link_row("Ad", "https://www.facebook.com/ads/2", "Another advertiser") + _value_row("Time", "Nov 17, 2023 10:13:20 pm"), "")
    + _MAIN_CLOSE
)

_ADS_HTML_ROWS = [
    ("Ads", "Another advertiser", "https://www.facebook.com/ads/2", "2023-11-17 22:13:20"),
    ("Ads", "An advertiser", "https://www.facebook.com/ads/1", "2023-11-14 22:13:20"),
]

# shows_you_have_watched.html: Title value row, URL link row, dated footer.
_SHOWS_PAGE = (
    _MAIN_OPEN
    + _record_section(_value_row("Title", "A show") + _link_row("URL", "https://www.facebook.com/s/1", "https://www.facebook.com/s/1"), "Nov 16, 2023 10:13:20 pm")
    + _record_section(_value_row("Title", "Another show") + _link_row("URL", "https://www.facebook.com/s/2", "https://www.facebook.com/s/2"), "Nov 15, 2023 10:13:20 pm")
    + _MAIN_CLOSE
)

_SHOWS_HTML_ROWS = [
    (_SHOWS, "A show", "https://www.facebook.com/s/1", "2023-11-16 22:13:20"),
    (_SHOWS, "Another show", "https://www.facebook.com/s/2", "2023-11-15 22:13:20"),
]


class TestContentShownSplitJson:
    def test_feed_lists_become_rows_under_the_list_label(self):
        errors: Counter = Counter()
        reader = _reader((_FEED_JSON, _FEED_RECORD), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _FEED_ROWS

    def test_ads_become_rows_dated_from_their_time_entry(self):
        errors: Counter = Counter()
        reader = _reader((_ADS_JSON, _ADS_RECORDS), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _ADS_ROWS

    def test_shows_watched_become_rows_dated_from_the_record(self):
        errors: Counter = Counter()
        reader = _reader((_SHOWS_JSON, _SHOWS_RECORDS), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _SHOWS_ROWS

    def test_the_three_split_files_are_concatenated_newest_first(self):
        errors: Counter = Counter()
        reader = _reader((_FEED_JSON, _FEED_RECORD), (_ADS_JSON, _ADS_RECORDS), (_SHOWS_JSON, _SHOWS_RECORDS), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert len(df) == len(_FEED_ROWS) + len(_ADS_ROWS) + len(_SHOWS_ROWS)
        assert sorted(df["Date"].tolist(), reverse=True) == df["Date"].tolist()
        assert set(df["Category"]) == {"Posts", "Videos", "Ads", _SHOWS}

    def test_a_bare_single_record_is_read_like_a_one_element_list(self):
        """Facebook writes an object, not a one-element list, when a file has
        exactly one record."""
        errors: Counter = Counter()
        reader = _reader((_ADS_JSON, json.dumps(json.loads(_ADS_RECORDS)[0])), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == [_ADS_ROWS[1]]

    def test_grouped_and_split_are_concatenated_when_both_present(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPED_JSON, _grouped_json()), (_FEED_JSON, _FEED_RECORD), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert len(df) == len(_GROUPED_ROWS) + len(_FEED_ROWS)
        assert sorted(df["Date"].tolist(), reverse=True) == df["Date"].tolist()
        assert set(df["Category"]) == {row[0] for row in _GROUPED_ROWS} | {"Posts", "Videos"}


class TestContentShownSplitHtml:
    def test_feed_items_take_the_category_of_their_enclosing_list_cell(self):
        errors: Counter = Counter()
        reader = _reader((_FEED_HTML, _FEED_PAGE), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _FEED_HTML_ROWS

    def test_ads_are_dated_from_the_time_cell_when_the_footer_is_empty(self):
        errors: Counter = Counter()
        reader = _reader((_ADS_HTML, _ADS_PAGE), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _ADS_HTML_ROWS

    def test_shows_watched_are_dated_from_the_footer(self):
        errors: Counter = Counter()
        reader = _reader((_SHOWS_HTML, _SHOWS_PAGE), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _SHOWS_HTML_ROWS

    def test_grouped_and_split_are_concatenated_when_both_present(self):
        errors: Counter = Counter()
        reader = _reader(
            (_GROUPED_HTML, _GROUPED_PAGE), (_FEED_HTML, _FEED_PAGE), (_ADS_HTML, _ADS_PAGE), (_SHOWS_HTML, _SHOWS_PAGE),
            errors=errors,
        )
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert len(df) == len(_GROUPED_HTML_ROWS) + len(_FEED_HTML_ROWS) + len(_ADS_HTML_ROWS) + len(_SHOWS_HTML_ROWS)
        assert sorted(df["Date"].tolist(), reverse=True) == df["Date"].tolist()

    def test_absence_of_every_split_file_is_an_empty_frame_and_no_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/logged_information/interactions/items_viewed.html", "<html/>"), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert df.empty
        assert not errors

# ---------------------------------------------------------------------------
# Table contract: columns match the docstring, names are anonymized
# ---------------------------------------------------------------------------


class TestContentShownTableContract:
    def test_columns_match_the_docstring_headers(self):
        reader = _reader((_GROUPED_JSON, _grouped_json()))
        df = facebook.content_shown_to_you_to_df(reader, Counter())
        config = _table_config(facebook.content_shown_to_you_to_df)
        assert config["id"] == "facebook_content_shown_to_you"
        assert list(df.columns) == list(config["headers"])

    def test_name_is_a_text_column_for_anonymization(self):
        reader = _reader((_GROUPED_JSON, _grouped_json()))
        df = facebook.content_shown_to_you_to_df(reader, Counter())
        df.loc[0, "Name"] = "Some Name shared a photo"
        assert "Name" in facebook.TEXT_COLUMNS
        eh.anonymize_dataframe(df, facebook.TEXT_COLUMNS, "Some Name")
        assert not df["Name"].str.contains("Some Name").any()
        assert df.loc[0, "Name"] == "[user] shared a photo"


# ---------------------------------------------------------------------------
# Your activity off Meta technologies — JSON (two shapes)
# ---------------------------------------------------------------------------

_OFF_META_JSON = "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.json"
_OFF_META_INDEX = "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.html"
_OFF_META_PAGES = "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies/"

# The 2025 device export: one object keyed off_facebook_activity_v2 with a
# name and flat events per business.
_OFF_META_V2 = json.dumps({"off_facebook_activity_v2": [
    {"name": _MOJIBAKE, "events": [
        {"id": 1001, "type": "PAGE_VIEW", "timestamp": _T1},
        {"id": 1002, "type": "PURCHASE", "timestamp": _T3},
    ]},
    {"name": "App Beta", "events": [
        {"id": 1003, "type": "CUSTOM", "timestamp": _T2},
    ]},
]})


def _off_meta_event(event_id: int, event: str, when: int) -> dict:
    return {"dict": [
        {"label": "ID", "value": str(event_id)},
        {"label": "Event", "value": event},
        {"label": "Received on", "timestamp_value": when},
    ]}


# The 2026 exports: a top-level list of records whose only label_values entry
# is an Events vec of ID / Event / Received on dicts.
_OFF_META_RECORDS = json.dumps([
    {"title": _MOJIBAKE, "fbid": "10", "media": [], "label_values": [
        {"label": "Events", "vec": [_off_meta_event(1001, "PAGE_VIEW", _T1), _off_meta_event(1002, "PURCHASE", _T3)]},
    ]},
    {"title": "App Beta", "fbid": "11", "media": [], "label_values": [
        {"label": "Events", "vec": [_off_meta_event(1003, "CUSTOM", _T2)]},
    ]},
])

_OFF_META_ROWS = [
    ("Café", "PURCHASE", _D3),
    ("App Beta", "CUSTOM", _D2),
    ("Café", "PAGE_VIEW", _D1),
]


class TestOffMetaJson:
    def test_v2_events_become_rows_newest_first(self):
        errors: Counter = Counter()
        reader = _reader(("export/" + _OFF_META_JSON, _OFF_META_V2), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _OFF_META_ROWS

    def test_record_list_events_become_rows_newest_first(self):
        errors: Counter = Counter()
        reader = _reader(("export/" + _OFF_META_JSON, _OFF_META_RECORDS), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _OFF_META_ROWS

    def test_absence_is_an_empty_frame_and_no_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/ads_information/ad_preferences.json", "{}"), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors)
        assert df.empty
        assert not errors


# ---------------------------------------------------------------------------
# Your activity off Meta technologies — HTML (index plus one page per business)
# ---------------------------------------------------------------------------


def _off_meta_index(*links: tuple[str, str]) -> str:
    """The index page: one top-level section per business whose h2 holds the
    one anchor, root-relative, to that business's page."""
    sections = "".join(
        f'<section class="_a6-g"><h2 class="_2ph_ _a6-h"><a href="{_OFF_META_PAGES}{slug}">{name}</a></h2></section>'
        for name, slug in links
    )
    return f'<html><body><div class="_li"><main class="_a706">{sections}</main></div></body></html>'


def _off_meta_event_table(event_id: int, event: str, when: str) -> str:
    """One event as the business page writes it: a section holding a leaf
    table of ID / Event / Received on rows (label ``_a6_q``, value ``_2piu _a6_r``)."""
    return (
        '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p"><table>'
        f'<tr><td class="_a6_q">ID</td><td class="_2piu _a6_r">{event_id}</td></tr>'
        f'<tr><td class="_a6_q">Event</td><td class="_2piu _a6_r">{event}</td></tr>'
        f'<tr><td class="_a6_q">Received on</td><td class="_2piu _a6_r">{when}</td></tr>'
        '</table></div></section>'
    )


def _off_meta_page(name: str, fbid: str, events: list[tuple[int, str, str]]) -> str:
    """A business page: h2 = business name; a wrapper table with the business
    ID row and an Events row whose label cell nests one event table each."""
    inner = "".join(_off_meta_event_table(*event) for event in events)
    return (
        '<html><body><div class="_li"><main class="_a706">'
        f'<section class="_3-95 _a6-g"><h2 class="_2ph_ _a6-h _a6-i">{name}</h2>'
        '<div class="_2pi8 _2pic _a6-p"><section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p"><table>'
        f'<tr><td class="_a6_q">ID</td><td class="_2piu _a6_r">{fbid}</td></tr>'
        f'<tr><td class="_a6_q" colspan="2">Events<div><div><div>{inner}</div></div></div></td></tr>'
        '</table></div></section></div>'
        '<footer class="_3-94 _a6-o"><div class="_a72d"></div></footer></section>'
        '</main></div></body></html>'
    )


_OFF_META_INDEX_PAGE = _off_meta_index(
    ("Shop Alpha", "shop_alpha_10.html"),
    ("Ghost Co", "ghost_co_99.html"),  # linked but not in the archive (a truncated Drive part)
    ("App Beta", "app_beta_11.html"),
)
_OFF_META_ALPHA = _off_meta_page("Shop Alpha", "10", [
    (1001, "PAGE_VIEW", "Nov 14, 2023 10:13:20 pm"),
    (1002, "PURCHASE", "Nov 16, 2023 10:13:20 pm"),
])
_OFF_META_BETA = _off_meta_page("App Beta", "11", [(1003, "CUSTOM", "Nov 15, 2023 10:13:20 pm")])
# The numbered pages duplicate the linked ones under another name; the index
# never links them and the extractor must not read them.
_OFF_META_NUMBERED = _off_meta_page("Numbered Duplicate", "12", [(1004, "VIEW_CONTENT", "Nov 17, 2023 10:13:20 pm")])

_OFF_META_HTML_ROWS = [
    ("Shop Alpha", "PURCHASE", "2023-11-16 22:13:20"),
    ("App Beta", "CUSTOM", "2023-11-15 22:13:20"),
    ("Shop Alpha", "PAGE_VIEW", "2023-11-14 22:13:20"),
]


def _off_meta_html_entries(root: str = "") -> list[tuple[str, str]]:
    return [
        (root + _OFF_META_INDEX, _OFF_META_INDEX_PAGE),
        (root + _OFF_META_PAGES + "shop_alpha_10.html", _OFF_META_ALPHA),
        (root + _OFF_META_PAGES + "app_beta_11.html", _OFF_META_BETA),
        (root + _OFF_META_PAGES + "0.html", _OFF_META_NUMBERED),
    ]


class TestOffMetaHtml:
    def test_linked_pages_become_rows_newest_first(self):
        errors: Counter = Counter()
        reader = _reader(*_off_meta_html_entries(), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _OFF_META_HTML_ROWS

    def test_unlinked_numbered_pages_are_not_read(self):
        reader = _reader(*_off_meta_html_entries())
        df = facebook.your_activity_off_meta_to_df(reader, Counter(), validation=_HTML_VALIDATION)
        assert "Numbered Duplicate" not in df["Business"].tolist()
        assert "VIEW_CONTENT" not in df["Event"].tolist()

    def test_a_linked_page_missing_from_the_archive_is_skipped_silently(self):
        errors: Counter = Counter()
        reader = _reader(*_off_meta_html_entries(), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert "Ghost Co" not in df["Business"].tolist()
        assert len(df) == 3

    def test_drive_style_root_prefix_is_derived_from_the_index_path(self):
        errors: Counter = Counter()
        reader = _reader(*_off_meta_html_entries(root="meta-x/facebook-y/"), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _OFF_META_HTML_ROWS

    def test_absence_is_an_empty_frame_and_no_error(self):
        errors: Counter = Counter()
        reader = _reader(("export/ads_information/ad_preferences.html", "<html/>"), errors=errors)
        df = facebook.your_activity_off_meta_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert df.empty
        assert not errors


class TestOffMetaTableContract:
    def test_columns_match_the_docstring_headers(self):
        reader = _reader(("export/" + _OFF_META_JSON, _OFF_META_V2))
        df = facebook.your_activity_off_meta_to_df(reader, Counter())
        config = _table_config(facebook.your_activity_off_meta_to_df)
        assert config["id"] == "facebook_activity_off_meta"
        assert list(df.columns) == list(config["headers"]) == ["Business", "Event", "Date"]

    def test_columns_are_not_anonymized(self):
        """Business names and event codes are Meta's vocabulary, not participant text."""
        assert not {"Business", "Event", "Date"} & set(facebook.TEXT_COLUMNS)
