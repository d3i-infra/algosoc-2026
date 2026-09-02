"""Tests for reading the timestamps out of the Facebook and Instagram html exports.

Both platforms are Meta and write the same shape — the month as a word, a 12-hour clock in
lower case — so both are read the same way. What they do *not* share is the clock they are
rendered on, and that is what most of this file is about.

Instagram renders at a fixed eight hours behind UTC, so its html can be converted and made
to agree with its json. Facebook renders in the timezone of the account, which differs from
one archive to the next, so its html cannot be converted at all until that offset is read.
Both findings come from ``scripts/meta_html_timezone_probe.py``, which matches records held
in both export formats and reports the difference; the records below are real pairs taken
from donated archives.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

import port.helpers.extraction_helpers as eh
from port.platforms import facebook, instagram


#: Records from a donated Instagram archive, each held in both export formats: what the
#: html shows, and the epoch the json records for the same record. They span winter and
#: summer, and three of them fall inside US daylight saving.
INSTAGRAM_PAIRS = [
    ("Aug 09, 2026 9:49 am", 1786297781),
    ("Apr 05, 2024 3:43 pm", 1712360599),
    ("Mar 11, 2026 2:49 am", 1773226198),
    ("Dec 29, 2025 1:46 pm", 1767044795),
    ("Aug 16, 2026 5:52 am", 1786888345),
]

#: The same, from a donated Facebook archive. This one is rendered at UTC, and another
#: Facebook archive is rendered in Amsterdam — which is the whole problem.
FACEBOOK_SHOWS, FACEBOOK_EPOCH = "Jun 26, 2026 9:05:20 am", 1782464720

#: A search from a donated Facebook archive, cut down to the parts that are read.
FACEBOOK_SEARCH_HTML = (
    '<section class="_a6-g" aria-labelledby="u_0_8c_np">'
    '<h2 class="_2ph_ _a6-h _a6-i" id="u_0_8c_np">You visited on Facebook</h2>'
    '<div class="_2ph_ _a6-p"><div><div class="_2pin"><div><div><div><div>Name redacted'
    '</div></div></div></div></div></div></div>'
    '<footer class="_3-94 _a6-o"><a target="_blank" href="https://www.facebook.com/dyi/l/?l=abc">'
    f'<div class="_a72d">{FACEBOOK_SHOWS}</div></a></footer></section>'
)


@pytest.fixture(params=[facebook, instagram], ids=["facebook", "instagram"])
def platform(request):
    """Both modules carry their own copy of the reader, so both are checked."""
    return request.param


class TestWhatBothPlatformsDo:
    """The reading of the text itself, which is the same for either."""

    @pytest.mark.parametrize("empty", ["", None])
    def test_an_absent_timestamp_is_not_an_error(self, platform, empty):
        errors = Counter()

        assert platform._html_timestamp(empty, errors=errors) == ""
        assert errors == Counter()

    @pytest.mark.parametrize("timestamp", ["nonsense", "15 mei 2026 20:30", "Xyz 26, 2026 9:05 am"])
    def test_what_cannot_be_read_is_kept_and_counted(self, platform, timestamp):
        """Kept as it was rather than guessed at, and counted so the rate can be seen."""
        errors = Counter()

        assert platform._html_timestamp(timestamp, errors=errors) == timestamp
        assert errors["TimestampParseError"] == 1

    def test_the_result_reads_back_as_a_time(self, platform):
        value = platform._html_timestamp("Jun 26, 2026 9:05:20 am")

        assert datetime.strptime(value, eh.DATETIME_FORMAT)


class TestInstagramIsConverted:
    """Instagram renders at ``HTML_EXPORT_UTC_OFFSET``, so its html can be placed in the
    reference zone exactly."""

    @pytest.mark.parametrize("shown,epoch", INSTAGRAM_PAIRS)
    def test_the_html_lands_where_the_json_does(self, shown, epoch):
        """The point of the conversion: one record, two export formats, one answer.

        Instagram writes no seconds in the html, so the two agree to the minute.
        """
        from_html = instagram._html_timestamp(shown)
        from_json = eh.epoch_to_datetime_string(epoch)

        assert from_html[:16] == from_json[:16], f"{shown} does not land where {epoch} does"

    @pytest.mark.parametrize("shown,expected", [
        ("Aug 09, 2026 9:49 am", "2026-08-09 19:49:00"),   # summer, +2 in the reference zone
        ("Dec 29, 2025 1:46 pm", "2025-12-29 22:46:00"),   # winter, +1
    ])
    def test_the_reference_zone_keeps_its_daylight_saving(self, shown, expected):
        assert instagram._html_timestamp(shown) == expected

    @pytest.mark.parametrize("shown,epoch", [p for p in INSTAGRAM_PAIRS if p[0].startswith(("Apr", "Mar", "Aug 16"))])
    def test_the_offset_is_fixed_rather_than_us_pacific(self, shown, epoch):
        """These records fall inside US daylight saving, where Pacific stands seven hours
        behind UTC rather than eight. Reading them as Pacific would put them an hour out,
        so the conversion must not apply a daylight saving rule of its own."""
        instant = datetime.fromtimestamp(epoch, tz=timezone.utc)
        as_pacific = instant.astimezone(timezone(timedelta(hours=-7))).strftime("%I:%M %p").lower()

        assert not shown.lower().endswith(as_pacific.lstrip("0"))
        assert instagram._html_timestamp(shown)[:16] == eh.epoch_to_datetime_string(epoch)[:16]

    @pytest.mark.parametrize("shown,expected", [
        # A 12-hour clock counts midnight as 12 am and noon as 12 pm, and the shift can
        # carry a record into the next day.
        ("Dec 31, 2026 12:00:00 am", "2026-12-31 09:00:00"),
        ("Jan 01, 2026 12:30 pm", "2026-01-01 21:30:00"),
        # The meridiem is optional, so a 24-hour locale reads too.
        ("Jun 26, 2026 21:05:20", "2026-06-27 07:05:20"),
    ])
    def test_the_shape_is_read_before_it_is_shifted(self, shown, expected):
        assert instagram._html_timestamp(shown) == expected


#: ``start_here.html`` as the two donated archives write it. The attribute is the instant
#: in UTC and the text is that instant on the clock the export was requested from.
START_HERE_AMSTERDAM = (
    '<aside role="contentinfo" class="_aoaa">Generated by Name redacted on '
    '<time datetime="2026-08-19T14:33Z">Wednesday, August 19, 2026 at 4:33 PM UTC+02:00</time>'
    '<div>Contains data you requested from <time datetime="2023-08-16T22:00Z">'
    'August 17, 2023 at 12:00 AM</time> to <time datetime="2026-08-18T22:00Z">'
    'August 19, 2026 at 12:00 AM</time></div></aside>'
)
START_HERE_UTC = (
    '<aside role="contentinfo" class="_aoaa">Generated by Name redacted on '
    '<time datetime="2026-08-29T08:10Z">Saturday 29 August 2026 at 08:10 UTC</time>'
    '<div>Contains data that you requested from <time datetime="2025-08-29T08:07Z">'
    '29 August 2025 at 08:07</time> to <time datetime="2026-08-29T08:07Z">'
    '29 August 2026 at 08:07</time></div></aside>'
)


def reader_holding(**pages: str):
    """A reader that serves the named html files and reports the rest as absent."""
    import io
    from unittest.mock import MagicMock

    def raw(name):
        page = pages.get(name.replace(".html", "").replace("/", "_"))
        if page is None:
            return MagicMock(found=False, data=None)
        return MagicMock(found=True, data=io.BytesIO(page.encode()))

    reader = MagicMock()
    reader.raw.side_effect = raw
    return reader


class TestFacebookReadsItsOffsetFromTheExport:
    """Facebook renders in the timezone of the account, and ``start_here.html`` is where
    the export states which one that was."""

    @pytest.mark.parametrize("page,expected", [
        (START_HERE_AMSTERDAM, timedelta(hours=2)),
        (START_HERE_UTC, timedelta(0)),
    ], ids=["amsterdam-export", "utc-export"])
    def test_the_offset_is_read_off_the_front_page(self, page, expected):
        """Both readings come from the attribute against the rendered clock, so no zone
        name and no localised date has to be parsed."""
        offset, instant = facebook._read_export_offset(reader_holding(start_here=page))

        assert offset == expected
        assert instant is not None

    def test_an_export_on_the_reference_zone_is_left_alone(self):
        """Its clock is already the wanted clock, so there is nothing to convert — and
        that is what keeps the export's own daylight saving intact, which a single offset
        could not have reproduced."""
        offset = facebook._export_offset(reader_holding(start_here=START_HERE_AMSTERDAM))

        assert offset is None
        # A winter and a summer record from that archive, both left where they stand.
        assert facebook._html_timestamp("Nov 03, 2025 12:45:47 pm", offset) == "2025-11-03 12:45:47"
        assert facebook._html_timestamp("Aug 09, 2026 9:02:12 pm", offset) == "2026-08-09 21:02:12"

    def test_an_export_on_another_zone_is_converted(self):
        """The archive that renders at UTC now lands where its own json does, which is the
        whole point of reading the offset."""
        offset = facebook._export_offset(reader_holding(start_here=START_HERE_UTC))

        assert offset == timedelta(0)
        assert facebook._html_timestamp(FACEBOOK_SHOWS, offset) == eh.epoch_to_datetime_string(FACEBOOK_EPOCH)

    def test_a_missing_front_page_leaves_the_clock_alone_and_is_counted(self):
        errors = Counter()

        offset = facebook._export_offset(reader_holding(), errors)

        assert offset is None
        assert errors["ExportTimezoneUnknown"] == 1
        assert facebook._html_timestamp(FACEBOOK_SHOWS, offset) == "2026-06-26 09:05:20"

    @pytest.mark.parametrize("shown,expected", [
        ("Jun 26, 2026 9:05:20 am", "2026-06-26 09:05:20"),
        ("Dec 31, 2026 12:00:00 am", "2026-12-31 00:00:00"),
        ("Jan 01, 2026 12:30 pm", "2026-01-01 12:30:00"),
        ("Jun 26, 2026 21:05:20", "2026-06-26 21:05:20"),
    ])
    def test_the_shape_is_read_before_any_shift(self, shown, expected):
        assert facebook._html_timestamp(shown) == expected

    def test_the_instagram_constant_is_not_applied_here(self):
        """The two modules carry separate readers, and Instagram's offset is a constant
        while Facebook's is read per archive."""
        assert not hasattr(facebook, "HTML_EXPORT_UTC_OFFSET")


class TestTheExtractorsUseIt:
    def test_a_facebook_search_row_is_converted_using_the_export_offset(self):
        """End to end, from the markup a donated archive holds: the extractor reads the
        offset off ``start_here.html`` and the row lands where that archive's json does."""
        reader = reader_holding(
            start_here=START_HERE_UTC, your_search_history=FACEBOOK_SEARCH_HTML
        )

        out = facebook._your_search_history_html(reader, Counter())

        assert not out.empty
        assert out["Date"].iloc[0] == eh.epoch_to_datetime_string(FACEBOOK_EPOCH)

    def test_a_facebook_search_row_survives_a_missing_front_page(self):
        """No ``start_here.html`` means no shift, not a crash."""
        reader = reader_holding(your_search_history=FACEBOOK_SEARCH_HTML)
        errors = Counter()

        out = facebook._your_search_history_html(reader, errors)

        assert not out.empty
        assert out["Date"].iloc[0] == "2026-06-26 09:05:20"
        assert errors["ExportTimezoneUnknown"] >= 1

    def test_every_html_extractor_with_a_date_column_reads_it(self):
        """A new html extractor is easy to add without converting its date, so the wiring
        is checked rather than trusted."""
        import re

        missing = []
        for module in (facebook, instagram):
            source = open(module.__file__, encoding="utf-8").read()
            for part in re.split(r"(?=\ndef )", source):
                name = part.lstrip("\n").split("(")[0].replace("def ", "").strip()
                if not name.endswith("_html"):
                    continue
                # Commented-out extractors trail some of these functions, and the columns
                # they name are not columns anything produces.
                live = "\n".join(
                    line for line in part.split("\n") if not line.lstrip().startswith("#")
                )
                columns = " ".join(re.findall(r"columns=\[([^\]]*)\]", live))
                if re.search(r'"(Date|Timestamp)"', columns) and "_html_timestamp" not in live:
                    missing.append(f"{module.__name__}.{name}")

        assert missing == [], f"html extractors that do not convert their date: {missing}"
