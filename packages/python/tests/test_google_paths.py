"""Tests for the locale-aware path resolution of the Google platform.

The Google DDP holds many sources in one archive, each exported in a format the
participant chooses per source, so the platform validates and looks its files up by
path instead of by filename. These tests cover what that buys: folder-qualified lookups
that survive same-named files elsewhere in the archive, variants per locale, a locale
detected from folder names alone, and formats that differ within one archive.
"""
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

import pytest

from port.platforms import google

def activity_html(cell: str) -> str:
    """Wrap an activity in the cell structure Takeout writes around it."""
    return (
        '<div class="mdl-grid"><div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        '<div class="mdl-grid">'
        '<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">YouTube</p></div>'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">' + cell + '</div>'
        '<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">'
        'Products:<br>&emsp;YouTube<br></div>'
        '</div></div></div>'
    )


WATCH_HTML = activity_html(
    'Watched <a href="https://www.youtube.com/watch?v=abc">A video</a><br>'
    '<a href="https://www.youtube.com/channel/UC1">A channel</a><br>'
    '15 jun 2026, 20:30:41 CEST'
)
WATCH_JSON = (
    '[{"title": "Watched A video", "titleUrl": "https://www.youtube.com/watch?v=abc", '
    '"subtitles": [{"name": "A channel", "url": "https://www.youtube.com/channel/UC1"}], '
    '"time": "2026-06-15T20:30:41Z"}]'
)
SEARCH_HTML = activity_html(
    'Searched for <a href="https://www.youtube.com/results?search_query=cats">cats</a><br>'
    '15 jun 2026, 20:30:41 CEST'
)
SEARCH_JSON = '[{"title": "Searched for cats", "titleUrl": "https://www.youtube.com/results?search_query=cats", "time": "2026-06-15T20:30:41Z"}]'
#: The My Activity file of a product records the activity of several sources together.
ACTIVITY_JSON = f"[{WATCH_JSON[1:-1]}, {SEARCH_JSON[1:-1]}]"
SUBSCRIPTIONS_CSV = "Channel Id,Channel Url,Channel Title\nUC1,https://youtube.com/channel/UC1,A channel\n"
COMMENTS_CSV = (
    "Comment ID,Channel ID,Comment create timestamp,Price,Video ID,Comment text\n"
    'c1,UC1,2026-06-15T20:30:41Z,0,abc,"{""text"":""hello""}"\n'
)


def make_zip(members: dict[str, str]) -> io.BytesIO:
    """Build an in-memory DDP zip from a member path → content mapping."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        for path, content in members.items():
            zf.writestr(path, content)
    archive.seek(0)
    return archive


def extract(members: dict[str, str]) -> dict[str, int]:
    """Validate and extract an in-memory DDP, returning row counts per table id."""
    archive = make_zip(members)
    validation = google.validate_ddp(archive)
    result = google.extraction(archive, validation)
    return {table.id: len(table.data_frame) for table in result.tables}


class TestValidation:
    def test_archive_is_recognized_and_its_locale_reported(self):
        archive = make_zip({
            "Takeout/YouTube en YouTube Music/geschiedenis/kijkgeschiedenis.html": WATCH_HTML,
            "Takeout/YouTube en YouTube Music/abonnementen/abonnementen.csv": SUBSCRIPTIONS_CSV,
        })

        validation = google.validate_ddp(archive)

        assert validation.get_status_code_id() == 0
        assert validation.locale == "nl"

    def test_archive_without_a_known_source_is_rejected(self):
        archive = make_zip({"Takeout/Chrome/BrowserHistory.json": "{}"})

        assert google.validate_ddp(archive).get_status_code_id() == 1

    def test_bad_zipfile_is_rejected(self):
        assert google.validate_ddp(io.BytesIO(b"not a zip")).get_status_code_id() == 1


class TestPathResolution:
    def test_folder_qualifier_ignores_a_same_named_file_elsewhere(self):
        rows = extract({
            "Takeout/YouTube und YouTube Music/Verlauf/Wiedergabeverlauf.html": WATCH_HTML,
            "Takeout/Irgendwas anderes/Wiedergabeverlauf.html": "",
        })

        assert rows["youtube_watch_history"] == 1

    def test_next_variant_resolves_when_the_first_is_absent(self):
        """The watch history falls back to the YouTube activity file, so an archive
        exported without the history folder still yields the table."""
        rows = extract({
            "Takeout/My Activity/YouTube/MyActivity.json": WATCH_JSON,
        })

        assert rows["youtube_watch_history"] == 1

    def test_missing_source_yields_no_table_and_no_error(self):
        archive = make_zip({
            "Takeout/YouTube and YouTube Music/history/watch-history.json": WATCH_JSON,
        })
        validation = google.validate_ddp(archive)

        result = google.extraction(archive, validation)

        assert [table.id for table in result.tables] == ["youtube_watch_history"]
        assert result.errors == Counter()


class TestActivityFile:
    def test_views_and_searches_are_split_when_read_from_the_activity_file(self):
        """Both YouTube histories fall back to the same activity file, which records
        views and searches together — each table must take only its own records."""
        rows = extract({
            "Takeout/My Activity/YouTube/MyActivity.json": ACTIVITY_JSON,
        })

        assert rows == {"youtube_watch_history": 1, "youtube_search_history": 1}


class TestWatchHistoryRow:
    """The table carries the channel a video was published by, which both formats write
    under the title, and the details a view sometimes records, such as an ad it came
    from — a row that has neither leaves those columns empty rather than dropping out."""

    #: A view from an ad names no channel, and the line it does carry under the title is
    #: the time it was watched at — a description, which is not the channel of anything.
    ADVERT_JSON = (
        '[{"title": "Watched An advert", "titleUrl": "https://www.youtube.com/watch?v=abc", '
        '"description": "Watched at 11:39 AM", "details": [{"name": "From Google Ads"}], '
        '"time": "2026-06-15T20:30:41Z"}]'
    )
    ADVERT_HTML = activity_html(
        'Watched <a href="https://www.youtube.com/watch?v=abc">An advert</a><br>'
        'Watched at 11:39 AM<br>'
        '15 jun 2026, 20:30:41 CEST'
    )

    def row(self, content: str, extension: str) -> dict:
        archive = make_zip({
            f"Takeout/YouTube and YouTube Music/history/watch-history.{extension}": content,
        })
        result = google.extraction(archive, google.validate_ddp(archive))
        return result.tables[0].data_frame.iloc[0].to_dict()

    @pytest.mark.parametrize(
        "content,extension", [(WATCH_JSON, "json"), (WATCH_HTML, "html")], ids=["json", "html"]
    )
    def test_the_channel_comes_out_the_same_from_either_format(self, content, extension):
        row = self.row(content, extension)

        assert row["Channel name"] == "A channel"
        assert row["Channel URL"] == "https://www.youtube.com/channel/UC1"

    def test_a_view_that_came_from_an_ad_says_so(self):
        assert self.row(self.ADVERT_JSON, "json")["Details"] == "From Google Ads"

    @pytest.mark.parametrize("extension", ["json", "html"])
    def test_a_view_without_a_channel_keeps_its_row_and_names_none(self, extension):
        """The description an ad carries under its title is not a channel, so it stays out
        of the columns naming one — the row is still the video that was watched."""
        row = self.row(getattr(self, f"ADVERT_{extension.upper()}"), extension)

        assert row["Title"] == "Watched An advert"
        assert row["Channel name"] == ""
        assert row["Channel URL"] == ""


class TestSearchLocations:
    """A Google search is recorded with the general area it was made from, which the table
    carries as the area, its link to Maps and, behind a dash, how it was arrived at."""

    AREA = "https://www.google.com/maps/@?api=1&map_action=map&center=10.000000,20.000000"

    def row(self, item: dict) -> dict:
        archive = make_zip({"Takeout/My Activity/Search/MyActivity.json": json.dumps([item])})
        result = google.extraction(archive, google.validate_ddp(archive))
        tables = {table.id: table.data_frame for table in result.tables}
        return tables["search_history"].iloc[0].to_dict()

    def search(self, **extra) -> dict:
        return {
            "title": "Searched for cats",
            "titleUrl": "https://www.google.com/search?q=cats",
            "time": "2026-06-15T20:30:41Z",
            **extra,
        }

    def test_a_location_reads_as_its_area_link_and_source(self):
        row = self.row(self.search(locationInfos=[
            {"name": "At this general area", "url": self.AREA, "source": "From your device"}
        ]))

        assert row["Locations"] == f"At this general area {self.AREA} - From your device"

    def test_several_locations_stand_beside_each_other(self):
        row = self.row(self.search(locationInfos=[
            {"name": "At this general area", "url": self.AREA, "source": "From your device"},
            {"name": "Somewhere else", "url": self.AREA, "source": "Based on your past activity"},
        ]))

        assert row["Locations"].count(" - ") == 2
        assert "Somewhere else" in row["Locations"]

    def test_a_location_without_a_source_carries_no_dash(self):
        row = self.row(self.search(locationInfos=[{"name": "Somewhere", "url": self.AREA}]))

        assert row["Locations"] == f"Somewhere {self.AREA}"

    def test_a_search_placed_nowhere_leaves_the_column_empty(self):
        assert self.row(self.search())["Locations"] == ""


class TestDetailsColumn:
    """The activity files record how some activity came about — a search or an ad shown
    from Google Ads — beside the activity itself. Every table that reads such a file has
    to carry it, so the row says where the activity came from and not only what it was."""

    #: The path of the source in an English archive, the table its extractor produces and
    #: an url the table takes, since two of them select their records by url.
    SOURCES = [
        ("YouTube and YouTube Music/history/search-history", "youtube_search_history",
         "https://www.youtube.com/results?search_query=cats"),
        ("My Activity/Search/MyActivity", "search_history",
         "https://www.google.com/search?q=cats"),
        ("My Activity/Ads/MyActivity", "ads_history", "https://example.org/an-advert"),
    ]

    def table(self, path: str, content: str, table_id: str):
        archive = make_zip({f"Takeout/{path}.json": content})
        result = google.extraction(archive, google.validate_ddp(archive))
        return {table.id: table.data_frame for table in result.tables}[table_id]

    @pytest.mark.parametrize("path,table_id,title_url", SOURCES, ids=[s[1] for s in SOURCES])
    def test_details_reach_the_table(self, path, table_id, title_url):
        content = json.dumps([{
            "title": "An activity",
            "titleUrl": title_url,
            "details": [{"name": "From Google Ads"}],
            "time": "2026-06-15T20:30:41Z",
        }])

        assert self.table(path, content, table_id)["Details"].tolist() == ["From Google Ads"]

    def test_a_detail_that_links_somewhere_keeps_its_url(self):
        """The json keeps the name of such a detail and the url it points to apart, where
        the html writes them as one line — and the column has to read the same either way,
        so the json is joined back into the line the html already produces."""
        content = json.dumps([{
            "title": "Visited a page",
            "titleUrl": "https://www.google.com/search?q=cats",
            "details": [{
                "name": "Tried to open in app",
                "url": "https://example.org/groups/abc",
            }],
            "time": "2026-06-15T20:30:41Z",
        }])

        table = self.table("My Activity/Search/MyActivity", content, "search_history")

        assert table["Details"].tolist() == [
            "Tried to open in app: https://example.org/groups/abc"
        ]

    @pytest.mark.parametrize("path,table_id,title_url", SOURCES, ids=[s[1] for s in SOURCES])
    def test_an_activity_without_details_leaves_the_column_empty(self, path, table_id, title_url):
        content = json.dumps([
            {"title": "An activity", "titleUrl": title_url, "time": "2026-06-15T20:30:41Z"}
        ])

        assert self.table(path, content, table_id)["Details"].tolist() == [""]


class TestFormats:
    def test_sources_may_use_different_formats_in_one_archive(self):
        rows = extract({
            "Takeout/YouTube and YouTube Music/history/watch-history.json": WATCH_JSON,
            "Takeout/YouTube and YouTube Music/history/search-history.html": SEARCH_HTML,
            "Takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv": SUBSCRIPTIONS_CSV,
        })

        assert rows == {
            "youtube_watch_history": 1,
            "youtube_search_history": 1,
            "youtube_subscriptions": 1,
        }


class TestLocaleDetection:
    def test_locale_comes_from_folders_when_filenames_are_identical(self, monkeypatch):
        """A locale that translates only its folder names leaves every filename in
        English, which is exactly what filename matching cannot see."""
        paths = dict(google.TAKEOUT_PATHS)
        paths["xx"] = {"youtube.watch_history": ["mijn activiteit/watch-history"]}
        monkeypatch.setattr(google, "TAKEOUT_PATHS", paths)

        members = ["Takeout/mijn activiteit/watch-history.json"]

        assert google._detect_locale(members)[0] == "xx"

    def test_translated_folder_identifies_the_locale_of_an_english_filename(self):
        """The real case the rule above exists for: Dutch translates the activity
        folder but leaves the file called MyActivity."""
        members = ["Takeout/Mijn activiteit/YouTube/MyActivity.json"]

        locale, sources_found = google._detect_locale(members)

        assert locale == "nl"
        assert sources_found > 0

    def test_nothing_recognized_reports_no_sources(self):
        assert google._detect_locale(["Takeout/nothing/we/know.json"])[1] == 0


class TestEveryLocale:
    """Builds a DDP from the paths of each locale, so a table entry that no extractor
    can reach fails here instead of silently producing an empty table in the field.

    Covers the keys that have an extractor today; a key added to ``TAKEOUT_PATHS``
    joins in once it produces a table and gets sample content here."""

    #: key → the table id its extractor produces.
    TABLES = {
        "youtube.watch_history": "youtube_watch_history",
        "youtube.search_history": "youtube_search_history",
        "youtube.subscriptions": "youtube_subscriptions",
        "youtube.comments": "youtube_comments",
    }

    CONTENT = {
        ("youtube.watch_history", "json"): WATCH_JSON,
        ("youtube.watch_history", "html"): WATCH_HTML,
        ("youtube.search_history", "json"): SEARCH_JSON,
        ("youtube.search_history", "html"): SEARCH_HTML,
        ("youtube.subscriptions", "csv"): SUBSCRIPTIONS_CSV,
        ("youtube.comments", "csv"): COMMENTS_CSV,
    }

    @pytest.mark.parametrize("preferred_format", ["json", "html"])
    @pytest.mark.parametrize("locale", list(google.TAKEOUT_PATHS))
    def test_all_tables_extract(self, locale, preferred_format):
        members = {}
        for key in self.TABLES:
            formats = google.KEY_FORMATS[key]
            extension = preferred_format if preferred_format in formats else formats[0]
            path = google.TAKEOUT_PATHS[locale][key][0]
            members[f"Takeout/{path}.{extension}"] = self.CONTENT[(key, extension)]

        rows = extract(members)

        assert rows == {table_id: 1 for table_id in self.TABLES.values()}


class TestTableConsistency:
    @pytest.mark.parametrize("locale", list(google.TAKEOUT_PATHS))
    def test_every_locale_covers_every_key(self, locale):
        assert set(google.TAKEOUT_PATHS[locale]) == set(google.KEY_FORMATS)

    @pytest.mark.parametrize("locale", list(google.TAKEOUT_PATHS))
    def test_paths_are_extension_less(self, locale):
        for paths in google.TAKEOUT_PATHS[locale].values():
            for path in paths:
                assert not path.rsplit("/", 1)[-1].count(".")

    def test_every_key_has_at_least_one_format(self):
        assert all(google.KEY_FORMATS.values())

    def test_every_key_an_extractor_reads_exists(self):
        """A key that is not in the table resolves to no paths at all, so its table comes
        out empty and is dropped from the consent form without anything going wrong —
        which is exactly how a mistyped key hides."""
        source = Path(google.__file__).read_text(encoding="utf-8")
        looked_up = set(re.findall(r'_read\(reader, "([^"]+)"', source))

        assert looked_up, "no lookups found — the pattern this test scans for has changed"
        assert looked_up <= set(google.KEY_FORMATS)
