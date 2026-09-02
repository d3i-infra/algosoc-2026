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
from port.helpers.validate import DDPFiletype


def _reader(*entries: tuple[str, str]) -> ZipArchiveReader:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries:
            zf.writestr(name, content)
    buf.seek(0)
    return ZipArchiveReader(buf, [name for name, _ in entries], Counter())


_HTML_VALIDATION = SimpleNamespace(current_ddp_category=SimpleNamespace(ddp_filetype=DDPFiletype.HTML))


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
