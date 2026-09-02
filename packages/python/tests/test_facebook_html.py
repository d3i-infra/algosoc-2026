"""Unit tests for the Facebook HTML extraction paths, on synthetic pages.

The integration canaries (``test_extractor_integration_facebook.py``) run the
same code against real exports but only when fixtures are present; these tests
pin the specific defects found in the 2026-09-01 tester-feedback audit so CI
catches a regression without real data (ADR-0014).
"""
import io
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
    extractor: ``extraction()`` shares one counter between reader and extractors."""
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
        assert list(df["Date"]) == ["2026-02-01T09:00:00", "2026-01-01T09:00:00"]

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
