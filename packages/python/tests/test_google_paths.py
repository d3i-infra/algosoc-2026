"""Tests for the locale-aware path resolution of the Google platform.

The Google DDP holds many sources in one archive, each exported in a format the
participant chooses per source, so the platform validates and looks its files up by
path instead of by filename. These tests cover what that buys: folder-qualified lookups
that survive same-named files elsewhere in the archive, variants per locale, a locale
detected from folder names alone, and formats that differ within one archive.
"""
import io
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
WATCH_JSON = '[{"title": "Watched A video", "titleUrl": "https://www.youtube.com/watch?v=abc", "time": "2026-06-15T20:30:41Z"}]'
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
