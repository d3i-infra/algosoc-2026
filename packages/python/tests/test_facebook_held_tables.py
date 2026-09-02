"""Unit tests for the Facebook tables that are implemented but held out of the
registry until the researcher meeting (2026-09-02).

Held extractors are not in ``EXTRACTOR_REGISTRY`` and have no entry in the
committed config, so nothing but these tests (and the ``HELD_EXTRACTORS`` pins
in ``test_extractor_integration_facebook.py``) exercises them. Synthetic inputs
cover both interaction layouts Facebook writes: the grouped
``recently_viewed`` file every local export uses, and the split
``content_that_has_been_shown_to_you_in_your_feed`` file whose shape is
assumed from the spreadsheet (no local export attests it).
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
_SPLIT_JSON = "export/logged_information/interactions/content_that_has_been_shown_to_you_in_your_feed.json"
_SPLIT_HTML = "export/logged_information/interactions/content_that_has_been_shown_to_you_in_your_feed.html"

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
# Content shown to you — split layout (content_that_has_been_shown_to_you_in_your_feed)
# ---------------------------------------------------------------------------

_SPLIT_RECORDS = json.dumps([
    {
        "timestamp": _T4,
        "label_values": [
            {"label": "Name", "value": "A page's post"},
            {"label": "Link", "href": "https://www.facebook.com/p/9"},
        ],
        "fbid": "9",
        "media": [],
        "title": "Post shown to you",
    },
    {
        "timestamp": _T1,
        "label_values": [{"label": "Link", "href": "https://www.facebook.com/p/8"}],
        "fbid": "8",
        "media": [],
        "title": "Untitled post shown to you",
    },
])

_SPLIT_ROWS = [
    (_FEED, "A page's post", "https://www.facebook.com/p/9", _D4),
    (_FEED, "Untitled post shown to you", "https://www.facebook.com/p/8", _D1),
]

_SPLIT_PAGE = """<html><body><main>
<section class="_a6-g"><div class="_a6-p"><table>
  <tr><td class="_a6_q">Name</td><td class="_a6_r">A page's post</td></tr>
  <tr><td class="_a6_q">Link</td><td class="_a6_r"><a href="https://www.facebook.com/p/9">https://www.facebook.com/p/9</a></td></tr>
</table></div><footer class="_a6-o"><div class="_a72d">Nov 17, 2023 10:13:20 pm</div></footer></section>
<section class="_a6-g"><div class="_a6-p"><table>
  <tr><td class="_a6_q">Link</td><td class="_a6_r"><a href="https://www.facebook.com/p/8">https://www.facebook.com/p/8</a></td></tr>
</table></div><footer class="_a6-o"><div class="_a72d">Nov 14, 2023 10:13:20 pm</div></footer></section>
</main></body></html>"""

_SPLIT_HTML_ROWS = [
    (_FEED, "A page's post", "https://www.facebook.com/p/9", "2023-11-17 22:13:20"),
    (_FEED, "", "https://www.facebook.com/p/8", "2023-11-14 22:13:20"),
]


class TestContentShownSplitJson:
    def test_records_become_rows_under_the_feed_category(self):
        errors: Counter = Counter()
        reader = _reader((_SPLIT_JSON, _SPLIT_RECORDS), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _SPLIT_ROWS

    def test_grouped_and_split_are_concatenated_when_both_present(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPED_JSON, _grouped_json()), (_SPLIT_JSON, _SPLIT_RECORDS), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors)
        assert not errors
        assert len(df) == len(_GROUPED_ROWS) + len(_SPLIT_ROWS)
        assert sorted(df["Date"].tolist(), reverse=True) == df["Date"].tolist()
        assert set(df["Category"]) == {row[0] for row in _GROUPED_ROWS}


class TestContentShownSplitHtml:
    def test_sections_become_rows_under_the_feed_category(self):
        errors: Counter = Counter()
        reader = _reader((_SPLIT_HTML, _SPLIT_PAGE), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert list(df.itertuples(index=False, name=None)) == _SPLIT_HTML_ROWS

    def test_grouped_and_split_are_concatenated_when_both_present(self):
        errors: Counter = Counter()
        reader = _reader((_GROUPED_HTML, _GROUPED_PAGE), (_SPLIT_HTML, _SPLIT_PAGE), errors=errors)
        df = facebook.content_shown_to_you_to_df(reader, errors, validation=_HTML_VALIDATION)
        assert not errors
        assert len(df) == len(_GROUPED_HTML_ROWS) + len(_SPLIT_HTML_ROWS)
        assert sorted(df["Date"].tolist(), reverse=True) == df["Date"].tolist()


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
