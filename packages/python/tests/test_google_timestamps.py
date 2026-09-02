"""Tests for reading activity records out of the HTML variant of the Google DDP.

Every source of the archive writes the same cell structure, so one parser reads them all:
the activity text and its link in the body-text content cell, the local time of the account
last. The timestamp is the part that varies most — it is written in the date format and
language of the account.
"""
import io

import pytest

from port.platforms import google


#: The section every caption closes with, on why the activity was kept.
WHY = (
    '<b>Why is this here?</b><br> This activity was saved to your Google Account because the '
    'following settings were on:&nbsp;Web &amp; App Activity.&nbsp;You can control these settings '
    '&nbsp;<a href="https://myaccount.google.com/activitycontrols">here</a>.'
)


def activity_html(cell: str, caption: str = f'<b>Products:</b><br> YouTube<br>{WHY}') -> str:
    """Wrap an activity in the cell structure Takeout writes around it."""
    return (
        '<div class="mdl-grid"><div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        '<div class="mdl-grid">'
        '<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">YouTube</p></div>'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">' + cell + '</div>'
        '<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">' + caption + '</div>'
        '</div></div></div>'
    )


def parse(cell: str) -> list[dict]:
    return google._parse_activity_html(io.BytesIO(activity_html(cell).encode()))


def watch_cell(timestamp: str) -> str:
    return (
        'Watched <a href="https://www.youtube.com/watch?v=abc">A video</a><br>'
        f'<a href="https://www.youtube.com/channel/UC1">A channel</a><br>{timestamp}'
    )


def search_cell(timestamp: str) -> str:
    return f'Searched for <a href="https://www.youtube.com/results?search_query=cats">cats</a><br>{timestamp}'


#: An account standing in the zone the output is expressed in, which is the common case
#: for this study: the local time it writes is already the time that is wanted, so the
#: conversion changes the separator and nothing else.
TIMESTAMPS = [
    # A 12-hour clock writes no leading zero, so the hour is a single digit before 10.
    ("Aug 17, 2026, 1:14:48 PM CEST", "2026-08-17 13:14:48"),
    ("Aug 15, 2026, 11:39:58 AM CEST", "2026-08-15 11:39:58"),
    ("15 jun 2026, 9:30:41 CEST", "2026-06-15 09:30:41"),
    ("15 mrt 2026, 20:30:41 CET", "2026-03-15 20:30:41"),
]

#: Shapes the conversion reads directly, beyond the ones above.
DIRECT = [
    ("Dec 31, 2026, 12:00:00 AM CET", "2026-12-31 00:00:00"),  # midnight is 12 AM
    ("Jan 1, 2026, 12:30:00 PM CET", "2026-01-01 12:30:00"),   # noon is 12 PM
    ("1 mei 2026, 07:05:00 CEST", "2026-05-01 07:05:00"),
    ("17. Aug. 2026, 22:14:48 MESZ", "2026-08-17 22:14:48"),   # ordinal dots, zone in German
    # An account standing somewhere else is moved into the reference zone: three hours
    # ahead of UTC in August is one hour ahead of Amsterdam.
    ("17 Ağu 2026, 22:14:48 GMT+3", "2026-08-17 21:14:48"),
]

#: Shapes it hands to dateutil instead, which reads what it can.
FALLBACK = [
    # No zone to read, so the local time is written as it stands and counted as unconverted.
    ("17.08.2026, 22:14:48", "2026-08-17 22:14:48"),  # no month name to recognize
    ("2026年8月17日 22:14:48", "2026年8月17日 22:14:48"),  # unreadable, kept as it was
]


@pytest.mark.parametrize("timestamp,expected", TIMESTAMPS + DIRECT + FALLBACK)
def test_conversion(timestamp, expected):
    assert google._convert_to_iso8601(timestamp) == expected


@pytest.mark.parametrize("timestamp,_", TIMESTAMPS + DIRECT)
def test_conversion_agrees_with_dateutil(timestamp, _):
    """The shapes read directly are the ones dateutil is bypassed for, so they have to
    come out the same — except where dateutil cannot read them at all, as with Turkish."""
    converted = google._convert_with_dateutil(timestamp)

    if converted != timestamp:
        assert google._convert_to_iso8601(timestamp) == converted


class TestCaption:
    """Some sources record lists beside an activity — the locations a Discover card was
    picked for, the topics it covered — which the html writes into the caption cell. They
    details have to come out in the shape the json format writes them in. The locations are
    deliberately not extracted, and recognizing that section is what keeps it from being
    read as the details."""

    LOCATIONS = (
        '<b>Locations:</b><br> At <a href="https://www.google.com/maps/@?api=1&amp;'
        'map_action=map&amp;center=10.000000,20.000000&amp;zoom=12">this general area</a>'
        ' - Based on your past activity<br>'
        ' At <a href="https://www.google.com/maps/@?api=1&amp;map_action=map&amp;'
        'center=11.000000,21.000000&amp;zoom=8">this general area</a> - From your device<br>'
    )
    DETAILS = '<b>Details:</b><br> Birdwatching<br> Cycling - viewed<br> Nordic cuisine<br>'
    CARD = '9 cards in your feed<br>Aug 6, 2026, 4:39:33 PM CEST<br>'

    def record(self, caption: str) -> dict:
        page = activity_html(self.CARD, f'<b>Products:</b><br> Discover<br>{caption}{WHY}')
        return google._parse_activity_html(io.BytesIO(page.encode()))[0]

    def test_the_details_read_as_the_json_writes_them_and_the_locations_are_dropped(self):
        record = self.record(self.LOCATIONS + self.DETAILS)

        assert record["details"] == [
            {"name": "Birdwatching"}, {"name": "Cycling - viewed"}, {"name": "Nordic cuisine"}
        ]
        assert "locationInfos" not in record
        assert "general area" not in str(record)
        assert "maps" not in str(record)

    def test_a_detail_that_links_somewhere_keeps_the_link_in_its_text(self):
        """The html writes such a detail as one line, the name and the url it points to
        behind a colon, and the whole line is what the record carries."""
        caption = ('<b>Details:</b><br> Tried to open in app: '
                   '<a href="https://example.org/groups/abc">https://example.org/groups/abc</a><br>')

        assert self.record(caption)["details"] == [
            {"name": "Tried to open in app: https://example.org/groups/abc"}
        ]

    def test_a_dash_inside_a_detail_is_left_alone(self):
        """Only a location separates its source off the end of the line."""
        assert {"name": "Cycling - viewed"} in self.record(self.DETAILS)["details"]

    def test_a_caption_of_locations_alone_adds_nothing(self):
        """The section is recognized by its links to Maps, so it is dropped rather than
        taken for the details, which is the section a caption is otherwise assumed to
        hold."""
        assert sorted(self.record(self.LOCATIONS)) == ["time", "title", "titleUrl"]

    def test_a_location_without_a_source_is_dropped_too(self):
        """A location whose line does not close with how the area was arrived at is still a
        location, and is recognized by its link the same way."""
        caption = ('<b>Locations:</b><br> <a href="https://www.google.com/maps/@?api=1&amp;'
                   'center=10.000000,20.000000">Somewhere</a><br>')

        record = self.record(caption)

        assert sorted(record) == ["time", "title", "titleUrl"]
        assert "Somewhere" not in str(record)

    def test_a_caption_with_nothing_to_add_adds_nothing(self):
        """Most captions only name the product and say why the activity was kept."""
        record = google._parse_activity_html(io.BytesIO(activity_html(self.CARD).encode()))[0]

        assert sorted(record) == ["time", "title", "titleUrl"]


class TestMicroseconds:
    """The Chrome history writes its timestamps as a number of microseconds since the
    epoch, which the shared ``epoch_to_iso`` reads as seconds and overflows on."""

    def test_a_microsecond_timestamp_reads_as_a_time(self):
        assert google._convert_usec_to_iso8601(1787225185379660) == "2026-08-20 13:26:25"

    def test_a_number_written_as_text_reads_the_same(self):
        assert google._convert_usec_to_iso8601("1787225185379660") == "2026-08-20 13:26:25"

    def test_the_shape_matches_the_activity_timestamps(self):
        """One column holds timestamps from both, so they are written the same way."""
        from_html = google._convert_to_iso8601("Aug 20, 2026, 11:26:25 AM CEST")

        assert len(google._convert_usec_to_iso8601(1787225185379660)) == len(from_html)

    @pytest.mark.parametrize("timestamp", ["", "not a number", None])
    def test_what_is_not_a_number_is_left_as_it_was(self, timestamp):
        assert google._convert_usec_to_iso8601(timestamp) == timestamp


@pytest.mark.parametrize("timestamp,expected", TIMESTAMPS)
@pytest.mark.parametrize("cell", [watch_cell, search_cell], ids=["watched", "searched"])
def test_timestamp(cell, timestamp, expected):
    assert parse(cell(timestamp))[0]["time"] == expected


class TestRecord:
    def test_a_view_reads_like_its_json_counterpart(self):
        """The json format writes the action into the title and links to the video, so
        the html format has to produce the same record for the same activity."""
        record = parse(watch_cell("15 jun 2026, 20:30:41 CEST"))[0]

        assert record["title"] == "Watched A video"
        assert record["titleUrl"] == "https://www.youtube.com/watch?v=abc"

    def test_details_after_the_activity_stay_out_of_the_title(self):
        """The channel of a video follows the first line break, as further details do for
        every source."""
        record = parse(watch_cell("15 jun 2026, 20:30:41 CEST"))[0]

        assert "A channel" not in record["title"]

    def test_the_line_under_the_activity_reads_as_a_subtitle(self):
        """The json format writes the channel of a video as a subtitle of a name and a
        url, and the html format has to produce the same record for the same activity."""
        record = parse(watch_cell("15 jun 2026, 20:30:41 CEST"))[0]

        assert record["subtitles"] == [
            {"name": "A channel", "url": "https://www.youtube.com/channel/UC1"}
        ]
        assert "description" not in record

    def test_a_line_that_links_nowhere_is_a_description(self):
        """A view from an ad carries the time it was watched at, which the json writes as
        the description of the activity rather than as a subtitle of it."""
        record = parse(
            'Watched <a href="https://www.youtube.com/watch?v=abc">An advert</a><br>'
            'Watched at 11:39 AM<br>15 aug 2026, 11:39:42 CEST'
        )[0]

        assert record["description"] == "Watched at 11:39 AM"
        assert "subtitles" not in record

    def test_an_activity_with_nothing_under_it_carries_neither(self):
        record = parse(search_cell("15 jun 2026, 20:30:41 CEST"))[0]

        assert "subtitles" not in record
        assert "description" not in record

    def test_a_search_keeps_its_query(self):
        record = parse(search_cell("15 jun 2026, 20:30:41 CEST"))[0]

        assert record["title"] == "Searched for cats"
        assert record["titleUrl"] == "https://www.youtube.com/results?search_query=cats"

    def test_a_redirected_link_reads_as_its_destination(self):
        """Activities that leave Google are recorded as a redirect through it."""
        record = parse(
            'Visited <a href="https://www.google.com/url?q=https://example.org/page">Example</a><br>'
            '15 jun 2026, 20:30:41 CEST'
        )[0]

        assert record["titleUrl"] == "https://example.org/page"

    def test_captions_are_not_activities(self):
        """Only the body-text cell holds an activity; the caption cell beside it lists the
        products the record belongs to."""
        assert len(parse(watch_cell("15 jun 2026, 20:30:41 CEST"))) == 1

    def test_the_empty_cell_beside_an_activity_is_not_a_record(self):
        """The layout puts a second, empty body cell beside the activity, and the markup
        around it does not close all of its tags."""
        sample = (
            '<div class="mdl-grid"><div<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
            '<div class="mdl-grid"><div class="header-cell mdl-cell mdl-cell--12-col">'
            '<p class="mdl-typography--title">Search<br></p></div>'
            '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Visited&nbsp;'
            '<a href="https://example.org/a-page">An example page - Example</a><br>'
            'Aug 16, 2026, 5:42:07 PM CEST<br></div>'
            '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 '
            'mdl-typography--text-right"></div>'
            '<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">'
            '<b>Products:</b><br> Search<br><b>Why is this here?</b><br> This activity was saved to '
            'your Google Account because the following settings were on:&nbsp;Web &amp; App Activity.'
            '</div></div></div<div></div>'
        )

        records = google._parse_activity_html(io.BytesIO(sample.encode()))

        assert records == [{
            "title": "Visited An example page - Example",
            "titleUrl": "https://example.org/a-page",
            "time": "2026-08-16 17:42:07",
        }]

    def test_an_activity_without_a_link_reads_as_an_empty_url(self):
        record = parse('Watched a video that has been removed<br>15 jun 2026, 20:30:41 CEST')[0]

        assert record["titleUrl"] == ""
        assert record["title"] == "Watched a video that has been removed"
