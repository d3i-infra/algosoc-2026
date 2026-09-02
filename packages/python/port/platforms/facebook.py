"""
Facebook

This module contains an example flow of a Facebook data donation study

Assumptions:
It handles DDPs in the english language with filetype JSON.

Timestamps
----------
Every date column is written as ``YYYY-MM-DD HH:MM:SS`` in the reference timezone named by
``extraction_helpers.REFERENCE_TIMEZONE``, so that a date means the same thing here as it
does in the TikTok, Instagram and Google tables.

The json export records epoch seconds, which name an absolute instant, so placing them in
that zone is exact.

The html export is only half converted, and its date columns are **not** comparable with
the json ones. It writes the time already rendered into the timezone the account is set to
and names no zone beside it, so the shape is normalised here but the clock is left where it
stands.

The offset genuinely varies by account, which is why no constant can be applied.
``scripts/meta_html_timezone_probe.py`` matches records held in both formats and reports
the difference; run over two donated archives it put one squarely in Europe/Amsterdam,
daylight saving and all — +1 through 2026-03-20, +2 from 2026-04-01 — and the other flat at
UTC across six years. Neither is where the participant lives, and the Instagram export of
those same two accounts is on a third clock again, a fixed -8, which ``instagram.py`` does
convert.

Nothing in the export states that offset — there is no file naming the timezone of the
account in either format — so an html donation cannot be placed in the reference zone at
all. Treat an hour of day taken from one as being on an unknown clock: not comparable
across participants, and not comparable with the json export. A participant who can choose
should donate the json format.

Configuration
-------------
The ``extraction`` function is driven by ``port_config.json``.  Generate one with::

    pnpm generate-config facebook

Each extractor function carries its own table config in a ``Table config::``
JSON block inside its docstring.  The generator reads those blocks and
assembles the JSON file.

Platform info::

    {
        "name": "Facebook",
        "filetypes": ["json"],
        "languages": ["en", "nl"],
        "description": "Handles DDPs in English. These data donation flows have not been tested yet, if you find anything wrong with them report to datadonation@uu.nl and they will be fixed!",
        "time_last_tested": "not yet implemented"
    }
"""

import logging
import re
from collections import Counter
from datetime import datetime
from typing import Callable

from lxml import etree

import pandas as pd

import port.helpers.extraction_helpers as eh
import port.helpers.validate as validate
from port.helpers.extraction_helpers import ZipArchiveReader
from port.helpers.flow_builder import FlowBuilder

from port.helpers.validate import (
    DDPCategory,
    DDPFiletype,
    Language,
)
from port.api.d3i_props import ExtractionResult
from port.helpers.table_extractor import (
    load_port_config,
    run_extraction,
)

logger = logging.getLogger(__name__)


#: Months by the first three letters of how the html export abbreviates them, lowercased,
#: across the languages it is written in that use Latin script. An account writes its export
#: in whatever language it is set to, which is not always the language of the study, so the
#: same table the Google extractor reads its html dates with is used here.
_HTML_MONTHS = {
    "jan": 1, "oca": 1, "ene": 1,
    "feb": 2, "şub": 2, "sub": 2,
    "mar": 3, "mrt": 3, "mär": 3, "mrz": 3,
    "apr": 4, "nis": 4, "abr": 4,
    "may": 5, "mei": 5, "mai": 5,
    "jun": 6, "haz": 6,
    "jul": 7, "tem": 7,
    "aug": 8, "ağu": 8, "agu": 8, "ago": 8,
    "sep": 9, "eyl": 9, "set": 9,
    "oct": 10, "okt": 10, "eki": 10,
    "nov": 11, "kas": 11,
    "dec": 12, "dez": 12, "ara": 12, "dic": 12,
}

#: ``Jun 26, 2026 9:05:20 am`` — how the html export writes a timestamp: the month as a word, a 12-hour
#: clock in lower case, and the seconds included. The meridiem is optional so that a
#: 24-hour locale reads too.
_HTML_TIMESTAMP = re.compile(
    r"^([^\s\d]+)\.?\s+(\d{1,2}),?\s+(\d{4})[\s,]+(\d{1,2}):(\d{2})(?::(\d{2}))?"
    r"(?:\s*([AaPp])\.?[Mm]\.?)?\s*$"
)


def _html_timestamp(timestamp: str, errors: Counter | None = None) -> str:
    """Write a timestamp read out of the html export in the shared datetime format.

    Only the shape is changed here; the clock is left where the export put it, which means
    this column is *not* comparable with the json one. The html names no timezone, and
    there is no single offset to supply in its place: Facebook renders each export in the
    timezone that account is set to, and that differs from one archive to the next.

    ``scripts/meta_html_timezone_probe.py`` is what establishes this. It matches records
    held in both export formats and reports the difference per source, and run over two
    donated archives it found two different clocks — one Europe/Amsterdam, following the
    daylight saving of that zone across four years, and one flat at UTC across six. Every
    source within an archive agreed with the others, so the offset belongs to the archive
    rather than to any one table.

    Neither clock is where the participant lives, and neither is a Meta-wide default. The
    Instagram exports of those *same two accounts* are a fixed eight hours behind UTC — see
    ``instagram.HTML_EXPORT_UTC_OFFSET``, which is why that platform can convert and this
    one cannot. What varies is the account, not the person.

    Nor does the export say which clock it used. No file in either format names the
    timezone of the account, so the offset cannot be recovered from the archive the way
    the Google html export's can be — it writes its zone beside each timestamp. An hour of
    day taken from a Facebook html donation is therefore on an unknown clock, and should
    not be compared across participants or against the json export.

    Only a timestamp that cannot be read at all is counted: the absent zone is a property
    of every row here, so counting it would mark them all and say nothing.

    Args:
        timestamp: Text of the date element, e.g. ``Jun 26, 2026 9:05:20 am``.
        errors: Optional counter that aggregates error types.

    Returns:
        str: The formatted timestamp, ``""`` for an absent one, or the input unchanged
        when it cannot be read.
    """
    if not timestamp or not isinstance(timestamp, str):
        return ""

    match = _HTML_TIMESTAMP.match(timestamp.strip())
    if match:
        month, day, year, hour, minute, second, meridiem = match.groups()
        number = _HTML_MONTHS.get(month[:3].lower())

        if number is not None:
            hour = int(hour)
            if meridiem:
                # A 12-hour clock counts noon as 12 pm and midnight as 12 am.
                hour = hour % 12 + (12 if meridiem.lower() == "p" else 0)
            try:
                return datetime(
                    int(year), number, int(day), hour, int(minute), int(second or 0)
                ).strftime(eh.DATETIME_FORMAT)
            except ValueError:
                pass

    logger.error("Could not read an html timestamp: %s", timestamp)
    if errors is not None:
        errors["TimestampParseError"] += 1

    return timestamp


DDP_CATEGORIES = [
    DDPCategory(
        id="json_en",
        ddp_filetype=DDPFiletype.JSON,
        language=Language.EN,
        known_files=[
"subscription_for_no_ads.json", "other_categories_used_to_reach_you.json", "ads_feedback_activity.json", "ads_personalization_consent.json", "advertisers_you've_interacted_with.json", "advertisers_using_your_activity_or_information.json", "story_views_in_past_7_days.json", "ad_preferences.json", "groups_you've_searched_for.json", "your_search_history.json", "primary_public_location.json", "primary_location.json", "your_privacy_jurisdiction.json", "people_and_friends.json", "ads_interests.json", "notifications.json", "notification_of_meta_privacy_policy_update.json", "recently_viewed.json", "recently_visited.json", "your_avatar.json", "meta_avatars_post_backgrounds.json", "contacts_sync_settings.json", "autofill_information.json", "profile_information.json", "profile_update_history.json", "your_transaction_survey_information.json", "your_recently_followed_history.json", "your_recently_used_emojis.json", "navigation_bar_activity.json", "pages_and_profiles_you_follow.json", "pages_you've_liked.json", "your_saved_items.json", "fundraiser_posts_you_likely_viewed.json", "your_fundraiser_donations_information.json", "your_events.json", "event_invitations.json", "your_event_invitation_links.json", "likes_and_reactions_1.json", "your_uncategorized_photos.json", "payment_history.json", "your_answers_to_membership_questions.json", "your_group_membership_activity.json", "your_contributions.json", "group_posts_and_comments.json", "your_comments_in_groups.json", "instant_games.json", "your_page_or_groups_badges.json", "instant_games_usage_data.json", "who_you've_followed.json", "people_you_may_know.json", "received_friend_requests.json", "your_friends.json", "likes_and_reactions.json", "controls.json",
        ],
    ),
    DDPCategory(
        id="html_en",
        ddp_filetype=DDPFiletype.HTML,
        language=Language.EN,
        known_files=[
"subscription_for_no_ads.html", "other_categories_used_to_reach_you.html", "ads_feedback_activity.html", "advertisers_you've_interacted_with.html", "advertisers_using_your_activity_or_information.html", "story_views_in_past_7_days.html", "ad_preferences.html", "your_search_history.html", "primary_public_location.html", "primary_location.html", "your_privacy_jurisdiction.html", "people_and_friends.html", "ads_interests.html", "notifications.html", "contacts_sync_settings.html", "autofill_information.html", "profile_information.html", "profile_update_history.html", "your_transaction_survey_information.html", "your_recently_used_emojis.html", "pages_and_profiles_you_follow.html", "pages_you've_liked.html", "your_saved_items.html", "fundraiser_posts_you_likely_viewed.html", "your_fundraiser_donations_information.html", "your_events.html", "event_invitations.html", "your_event_invitation_links.html", "likes_and_reactions_1.html", "payment_history.html", "your_group_membership_activity.html", "your_contributions.html", "your_page_or_groups_badges.html", "who_you've_followed.html", "people_you_may_know.html", "received_friend_requests.html", "your_friends.html", "likes_and_reactions.html", "comments.html", "your_posts__check_ins__photos_and_videos_1.html", "archived_stories.html", "connected_apps_and_websites.html", "your_activity_off_meta_technologies.html", "content_that_has_been_shown_to_you_in_your_feed.html", "items_viewed.html", "profile_visits.html", "start_here.html", "your_comments_in_groups.html"
        ],
    ),
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _sort_by_date(out: pd.DataFrame, date_column: str) -> pd.DataFrame:
    """Order *out* from most recent to oldest on *date_column*.

    Every Facebook table that carries a date is returned newest first so that
    participants see their most recent activity at the top.

    Parameters
    ----------
    out:
        DataFrame to sort.
    date_column:
        Name of the column that contains ISO-formatted timestamp strings.
        Rows with empty or unparsable timestamps are placed last.

    Returns
    -------
    pd.DataFrame
        Sorted DataFrame with a fresh index.  Returned unchanged when it is
        empty or does not contain *date_column*.
    """
    if out.empty or date_column not in out.columns:
        return out

    return out.sort_values(
        by=date_column, key=eh.sort_isotimestamp_empty_timestamp_last
    ).reset_index(drop=True)


def who_youve_followed_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract the list of profiles and pages you follow on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Name``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook profile or page that the participant follows, including the name and the time they started following.",
          "source_file": "who_you_ve_followed.json / who_you've_followed.html",
          "columns": {
            "Name": "Name of the followed profile or page.",
            "Timestamp": "ISO 8601 timestamp of when the participant started following."
          }
        }

    Table config::

        {
          "id": "facebook_who_youve_followed",
          "title": {
            "en": "Followed accounts",
            "nl": "Gevolgde accounts"
          },
          "description": {
            "en": "This table shows the Facebook profiles and pages you currently follow.",
            "nl": "Deze tabel toont de Facebook-profielen en -pagina's die je momenteel volgt."
          },
          "headers": {
            "Name": {"en": "Name", "nl": "Naam"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_who_youve_followed_html(reader, errors), "Timestamp")

    return _sort_by_date(_who_youve_followed_json(reader, errors), "Timestamp")


def _who_youve_followed_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("who_you've_followed.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["following_v3"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("name", "")),
                eh.epoch_to_datetime_string(item.get("timestamp", {}), errors=errors)
            ))
        out = pd.DataFrame(datapoints, columns=["Name", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _who_youve_followed_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("who_you've_followed.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            name = h2[0].text.strip() if h2 and h2[0].text else ""

            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            timestamp = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            datapoints.append((name, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Name", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def news_your_locations_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract the locations Facebook News is configured to show.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Location``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a geographical location for which the participant's Facebook News feed is configured.",
          "source_file": "facebook_news/your_locations.json",
          "columns": {
            "Location": "Name of the configured location."
          }
        }

    Table config::

        {
          "id": "facebook_news_your_locations",
          "title": {
            "en": "The locations Facebook news is set to",
            "nl": "De locaties waar Facebook Nieuws op is ingesteld"
          },
          "description": {
            "en": "This table displays the geographical locations for which your Facebook News feed is configured.",
            "nl": "Deze tabel toont de geografische locaties waarvoor je Facebook Nieuwsfeed is geconfigureerd."
          },
          "headers": {
            "Location": {"en": "Location", "nl": "Locatie"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _news_your_locations_html(reader, errors)

    return _news_your_locations_json(reader, errors)


def _news_your_locations_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("facebook_news/your_locations.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["news_your_locations_v2"]  # pyright: ignore
        for item in items:
            datapoints.append(
                item
            )
        out = pd.DataFrame(datapoints, columns=["Location"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _news_your_locations_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    return pd.DataFrame()


def notifications_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract Facebook notifications history.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Text``, ``Link``, ``Read``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a notification the participant received from Facebook, including the text, link, read status, and timestamp.",
          "source_file": "notifications/notifications.json",
          "columns": {
            "Text": "Text content of the notification.",
            "Link": "URL the notification links to.",
            "Read": "Whether the notification was read.",
            "Date": "ISO 8601 timestamp of the notification."
          }
        }

    Table config::

        {
          "id": "facebook_notifications",
          "title": {
            "en": "Notifications Facebook sent you",
            "nl": "Notificaties die Facebook je stuurde"
          },
          "description": {
            "en": "This table contains a history of the notifications you've received from Facebook.",
            "nl": "Deze tabel bevat een overzicht van de notificaties die je van Facebook hebt ontvangen."
          },
          "headers": {
            "Text": {"en": "Text", "nl": "Tekst"},
            "Link": {"en": "Link", "nl": "Link"},
            "Read": {"en": "Read", "nl": "Gelezen"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("notifications/notifications.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["notifications_v2"]  # pyright: ignore
        for item in items:
            denested_dict = eh.dict_denester(item)
            datapoints.append((
                eh.find_item(denested_dict, "text"),
                eh.find_item(denested_dict, "href"),
                eh.find_item(denested_dict, "unread"),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Text", "Link", "Read", "Date"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Date")


def content_sharing_you_have_created_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract content sharing links you have created on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Link``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an external link the participant shared on Facebook, including the URL and date.",
          "source_file": "content_sharing_links_you_have_created.json",
          "columns": {
            "Link": "URL of the shared link.",
            "Date": "ISO 8601 timestamp of when the link was shared."
          }
        }

    Table config::

        {
          "id": "facebook_content_sharing_links_you_created",
          "title": {
            "en": "Links you shared",
            "nl": "Links die je hebt gedeeld"
          },
          "description": {
            "en": "This table displays the external links you have shared on Facebook.",
            "nl": "Deze tabel toont de externe links die je op Facebook hebt gedeeld."
          },
          "headers": {
            "Link": {"en": "Link", "nl": "Link"},
            "Date": {"en": "Date", "nl": "Datum en Tijd"}
          }
        }
    """
    result = reader.json("content_sharing_links_you_have_created.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d:
            denested_dict = eh.dict_denester(item)
            datapoints.append((
                eh.find_item(denested_dict, "href"),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Link", "Date"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Date")


def facebook_reels_usage_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook Reels usage information.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Reel interaction``, ``Value``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a type of interaction the participant had with Facebook Reels and its associated value.",
          "source_file": "facebook_reels_usage_information.json / facebook_reels_usage_information.html",
          "columns": {
            "Reel interaction": "Type of interaction with Facebook Reels.",
            "Value": "Value associated with the interaction."
          }
        }

    Table config::

        {
          "id": "facebook_reels_usage",
          "title": {
            "en": "Interactions with Facebook Reels",
            "nl": "Interacties met Facebook Reels"
          },
          "description": {
            "en": "This table shows your interactions with Facebook Reels, such as videos you've watched or engaged with.",
            "nl": "Deze tabel toont je interacties met Facebook Reels, zoals video's die je hebt bekeken of waarmee je hebt gecommuniceerd."
          },
          "headers": {
            "Reel interaction": {"en": "Statistic", "nl": "Statistiek"},
            "Value": {"en": "Value", "nl": "Waarde"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _facebook_reels_usage_html(reader, errors)

    return _facebook_reels_usage_json(reader, errors)


def _facebook_reels_usage_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("facebook_reels_usage_information.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d.get("label_values", []) #pyright: ignore
        d = items[0]
        for item in d["dict"]:
            denested_dict = eh.dict_denester(item)
            datapoints.append((
                eh.find_item(denested_dict, "label"),
                eh.find_item(denested_dict, "value"),
            ))

        out = pd.DataFrame(datapoints, columns=["Reel interaction", "Value"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _facebook_reels_usage_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("facebook_reels_usage_information.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        rows = tree.xpath("//tr[td[contains(@class, '_a6_q') and not(@colspan)] and td[contains(@class, '_a6_r')]]")
        for row in rows:
            label_td = row.xpath("td[contains(@class, '_a6_q')]")
            value_td = row.xpath("td[contains(@class, '_a6_r')]")
            label = label_td[0].text.strip() if label_td and label_td[0].text else ""
            value = value_td[0].text.strip() if value_td and value_td[0].text else ""
            if label:
                datapoints.append((label, value))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Reel interaction", "Value"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def last_28_days_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract how many videos you watched in the last 28 days on Facebook Watch.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Count``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Contains the number of videos the participant watched on Facebook in the past 28 days.",
          "source_file": "your_facebook_watch_activity_in_the_last_28_days.json",
          "columns": {
            "Count": "Number of videos watched in the last 28 days."
          }
        }

    Table config::

        {
          "id": "facebook_last_28",
          "title": {
            "en": "How many videos you watched in the last 28 days",
            "nl": "Hoeveel video's je de afgelopen 28 dagen hebt bekeken"
          },
          "description": {
            "en": "This table indicates the number of videos you have watched on Facebook in the past 28 days.",
            "nl": "Deze tabel geeft het aantal video's aan dat je de afgelopen 28 dagen op Facebook hebt bekeken."
          },
          "headers": {
            "Count": {"en": "Count", "nl": "Aantal"}
          }
        }
    """
    result = reader.json("your_facebook_watch_activity_in_the_last_28_days.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        denested_dict = eh.dict_denester(d)
        datapoints.append((
            eh.find_item(denested_dict, "-value"),
        ))

        out = pd.DataFrame(datapoints, columns=["Count"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def your_search_history_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook search history.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Search term``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a search query the participant made on Facebook, including the search term and date.",
          "source_file": "logged_information/search/your_search_history.json / your_search_history.html",
          "columns": {
            "Search term": "The search query entered by the participant.",
            "Date": "ISO 8601 timestamp of when the search was made."
          }
        }

    Table config::

        {
          "id": "facebook_search_history",
          "title": {
            "en": "Searches",
            "nl": "Zoekopdrachten"
          },
          "description": {
            "en": "This table contains a record of your search queries on Facebook.",
            "nl": "Deze tabel bevat een overzicht van je zoekopdrachten op Facebook."
          },
          "headers": {
            "Search term": {"en": "Search term", "nl": "Zoekterm"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          },
          "visualizations": [
            {
              "title": {"en": "Terms you searched for", "nl": "Zoektermen waar je naar zocht"},
              "type": "wordcloud",
              "textColumn": "Search term",
              "tokenize": false
            }
          ]
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_search_history_html(reader, errors), "Date")

    return _sort_by_date(_your_search_history_json(reader, errors), "Date")


def _your_search_history_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("logged_information/search/your_search_history.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["searches_v2"]  # pyright: ignore
        for item in items:
            denested_dict = eh.dict_denester(item)

            datapoints.append((
                eh.fix_latin1_string(eh.find_item(denested_dict, "text")),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Search term", "Date"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_search_history_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("your_search_history.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g')]")
        for section in sections:
            term_divs = section.xpath(".//div[contains(@class, '_2pin')]//div[not(div)]")
            term = term_divs[0].text.strip().strip('"') if term_divs and term_divs[0].text else ""
            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            date = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)
            datapoints.append((term, date))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Search term", "Date"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def your_friends_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract the number of Facebook friends.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Number of friends``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Contains the total number of friends the participant has on Facebook.",
          "source_file": "your_friends.json",
          "columns": {
            "Number of friends": "Total count of Facebook friends."
          }
        }

    Table config::

        {
          "id": "facebook_your_friends",
          "title": {
            "en": "Your friends on Facebook",
            "nl": "Je vrienden op Facebook"
          },
          "description": {
            "en": "This table lists your current friends on Facebook.",
            "nl": "Deze tabel toont je huidige vrienden op Facebook."
          },
          "headers": {
            "Number of friends": {"en": "Number of friends", "nl": "Aantal vrienden op facebook"}
          }
        }
    """
    result = reader.json("your_friends.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["friends_v2"]  # pyright: ignore
        datapoints.append((len(items)))

        out = pd.DataFrame(datapoints, columns=["Number of friends"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def ads_interests_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook ad interests.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Ad``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an interest topic Facebook has associated with the participant for ad targeting purposes.",
          "source_file": "ads_interests.json / ads_interests.html",
          "columns": {
            "Ad": "Interest topic used for ad targeting."
          }
        }

    Table config::

        {
          "id": "facebook_ads_interests",
          "title": {
            "en": "Your ad interests",
            "nl": "Je advertentie-interesses"
          },
          "description": {
            "en": "This table shows the interests Facebook has identified for showing you personalized ads.",
            "nl": "Deze tabel toont de interesses die Facebook heeft geïdentificeerd om je gepersonaliseerde advertenties te tonen."
          },
          "headers": {
            "Ad": {"en": "Interest", "nl": "Interesse"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _ads_interests_html(reader, errors)

    return _ads_interests_json(reader, errors)


def _ads_interests_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("ads_interests.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["topics_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item),
            ))
        out = pd.DataFrame(datapoints, columns=["Ad"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _ads_interests_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("ads_interests.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g')]")
        for section in sections:
            h2 = section.xpath(".//h2")
            ad = h2[0].text.strip() if h2 and h2[0].text else ""
            if ad:
                datapoints.append((ad,))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Ad"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def recently_viewed_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract Facebook items recently viewed.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Category``, ``Name``, ``Link``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook post, video, or other item the participant recently viewed, including the category, name, link, and date.",
          "source_file": "recently_viewed.json",
          "columns": {
            "Category": "Content category (e.g. Videos, Marketplace).",
            "Name": "Name or title of the viewed item.",
            "Link": "URL of the viewed item.",
            "Date": "ISO 8601 timestamp of when the item was viewed."
          }
        }

    Table config::

        {
          "id": "facebook_recently_viewed",
          "title": {
            "en": "Facebook items you recently viewed",
            "nl": "Facebook items die je recentelijk hebt bekeken"
          },
          "description": {
            "en": "This table shows the Facebook posts, videos, and other items you have recently viewed.",
            "nl": "Deze tabel toont de Facebook-posts, video's en andere items die je recentelijk hebt bekeken."
          },
          "headers": {
            "Category": {"en": "Category", "nl": "Categorie"},
            "Name": {"en": "Name", "nl": "Naam"},
            "Link": {"en": "Link", "nl": "Link"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("recently_viewed.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["recently_viewed"] # pyright: ignore
        for item in items:

            if "entries" in item:
                for entry in item["entries"]:
                    datapoints.append((
                        eh.fix_latin1_string(item.get("name", "")),
                        eh.fix_latin1_string(entry.get("data", {}).get("name", "")),
                        entry.get("data", {}).get("uri", ""),
                        eh.epoch_to_datetime_string(entry.get("timestamp", ""), errors=errors)
                    ))

            # The nesting goes deeper
            if "children" in item:
                for child in item["children"]:
                    for entry in child["entries"]:
                        datapoints.append((
                            eh.fix_latin1_string(child.get("name", "")),
                            eh.fix_latin1_string(entry.get("data", {}).get("name", "")),
                            entry.get("data", {}).get("uri", ""),
                            eh.epoch_to_datetime_string(entry.get("timestamp", ""), errors=errors)
                        ))

        out = pd.DataFrame(datapoints, columns=["Category", "Name", "Link", "Date"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Date")


def recently_visited_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract Facebook profiles recently visited.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Category``, ``Name``, ``Link``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook profile or page the participant recently visited, including the category, name, link, and date.",
          "source_file": "recently_visited.json",
          "columns": {
            "Category": "Category of the visited item.",
            "Name": "Name or title of the visited profile or page.",
            "Link": "URL of the visited profile or page.",
            "Date": "ISO 8601 timestamp of when the visit occurred."
          }
        }

    Table config::

        {
          "id": "facebook_recently_visited",
          "title": {
            "en": "Profiles you visited recently",
            "nl": "Profielen die je recentelijk hebt bezocht"
          },
          "description": {
            "en": "This table lists the Facebook profiles you have visited most recently.",
            "nl": "Deze tabel toont de Facebook-profielen die je recentelijk hebt bezocht."
          },
          "headers": {
            "Category": {"en": "Category", "nl": "Categorie"},
            "Name": {"en": "Name", "nl": "Naam"},
            "Link": {"en": "Link", "nl": "Link"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("recently_visited.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["visited_things_v2"]  # pyright: ignore
        for item in items:
            if "entries" in item:
                for entry in item["entries"]:
                    datapoints.append((
                        item.get("name", ""),
                        eh.fix_latin1_string(entry.get("data", {}).get("name", "")),
                        entry.get("data", {}).get("uri", ""),
                        eh.epoch_to_datetime_string(entry.get("timestamp", ""), errors=errors)
                    ))

        out = pd.DataFrame(datapoints, columns=["Category", "Name", "Link", "Date"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Date")


def profile_update_history_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract Facebook profile update history.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a change the participant made to their Facebook profile, including the title of the change and the timestamp.",
          "source_file": "profile_update_history.json",
          "columns": {
            "Title": "Description of the profile change.",
            "Timestamp": "ISO 8601 timestamp of when the change was made."
          }
        }

    Table config::

        {
          "id": "facebook_profile_update_history",
          "title": {
            "en": "History of your profile updates",
            "nl": "Geschiedenis van je profielupdates"
          },
          "description": {
            "en": "This table contains a log of changes you've made to your Facebook profile information.",
            "nl": "Deze tabel bevat een logboek van de wijzigingen die je in je Facebook-profielinformatie hebt aangebracht."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("profile_update_history.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["profile_updates_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("title", "")),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors)
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return _sort_by_date(out, "Timestamp")


def your_events_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook events the participant created or was invited to.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Name``, ``Created``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook event the participant created or was invited to, including the event name and creation timestamp.",
          "source_file": "your_facebook_activity/events/your_events.json / your_events.html",
          "columns": {
            "Name": "Name of the Facebook event.",
            "Created": "ISO 8601 timestamp of when the event was created."
          }
        }

    Table config::

        {
          "id": "facebook_your_events",
          "title": {
            "en": "Events",
            "nl": "Evenementen"
          },
          "description": {
            "en": "This table contains Facebook events you created or were invited to.",
            "nl": "Deze tabel bevat Facebook-evenementen die je hebt aangemaakt of waarvoor je bent uitgenodigd."
          },
          "headers": {
            "Name": {"en": "Name", "nl": "Naam"},
            "Created": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_events_html(reader, errors), "Created")

    return _sort_by_date(_your_events_json(reader, errors), "Created")


def _your_events_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_facebook_activity/events/your_events.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["your_events_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("name", "")),
                eh.epoch_to_datetime_string(item.get("create_timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Name", "Created"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_events_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("your_events.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            h2 = section.xpath(".//h2")
            name = h2[0].text.strip() if h2 and h2[0].text else ""
            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            created = date_divs[0].text.strip() if date_divs and date_divs[0].text else ""
            if name or created:
                datapoints.append((name, created))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Name", "Created"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def group_posts_and_comments_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract posts and comments you made in Facebook groups.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Post``, ``Date``, ``URL``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a post or comment the participant made in a Facebook group, including the title, post content, date, and URL.",
          "source_file": "group_posts_and_comments.json",
          "columns": {
            "Title": "Title of the group post.",
            "Post": "Text content of the post.",
            "Date": "ISO 8601 timestamp of when the post was made.",
            "URL": "URL of the group post."
          }
        }

    Table config::

        {
          "id": "facebook_group_posts_and_comments",
          "title": {
            "en": "Your posts and comments in groups",
            "nl": "Je berichten en comments in groepen"
          },
          "description": {
            "en": "This table shows your posts and comments within Facebook groups.",
            "nl": "Deze tabel toont je berichten en comments in Facebook-groepen."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Post": {"en": "Post", "nl": "Bericht"},
            "Date": {"en": "Date", "nl": "Datum en tijd"},
            "URL": {"en": "URL", "nl": "URL"}
          }
        }
    """
    result = reader.json("group_posts_and_comments.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        l = d["group_posts_v2"]  # pyright: ignore
        for item in l:
            denested_dict = eh.dict_denester(item)

            datapoints.append((
                eh.fix_latin1_string(eh.find_item(denested_dict, "title")),
                eh.fix_latin1_string(eh.find_item(denested_dict, "post")),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
                eh.find_item(denested_dict, "url"),
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Post", "Date", "URL"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Date")


def your_answers_to_membership_questions_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract your answers to Facebook group membership questions.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Group name``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook group the participant answered membership questions for when requesting to join.",
          "source_file": "your_answers_to_membership_questions.json",
          "columns": {
            "Group name": "Name of the Facebook group."
          }
        }

    Table config::

        {
          "id": "facebook_your_answers_to_membership_questions",
          "title": {
            "en": "Your answers to group membership questions",
            "nl": "Je antwoorden op vragen voor groepslidmaatschap"
          },
          "description": {
            "en": "This table contains the answers you provided when requesting to join Facebook groups.",
            "nl": "Deze tabel bevat de antwoorden die je hebt gegeven bij het aanvragen van lidmaatschap van Facebook-groepen."
          },
          "headers": {
            "Group name": {"en": "Group name", "nl": "Groepsnaam"}
          }
        }
    """
    result = reader.json("your_answers_to_membership_questions.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:

        items = d["group_membership_questions_answers_v2"]["group_answers"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("group_name", "")),
            ))
        out = pd.DataFrame(datapoints, columns=["Group name"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def your_comments_in_groups_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract your comments in Facebook groups.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Comment``, ``Group``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a comment the participant made in a Facebook group, including the title, comment text, group name, and timestamp.",
          "source_file": "your_comments_in_groups.json",
          "columns": {
            "Title": "Title of the post the comment was made on.",
            "Comment": "Text content of the comment.",
            "Group": "Name of the Facebook group.",
            "Timestamp": "ISO 8601 timestamp of when the comment was made."
          }
        }

    Table config::

        {
          "id": "facebook_your_comments_in_groups",
          "title": {
            "en": "Comments in groups",
            "nl": "Reacties in groepen"
          },
          "description": {
            "en": "This table specifically lists the comments you have made in Facebook groups.",
            "nl": "Deze tabel toont specifiek de comments die je in Facebook-groepen hebt geplaatst."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Comment": {"en": "Comment", "nl": "Reactie"},
            "Group": {"en": "Group", "nl": "Groep"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_comments_in_groups_html(reader, errors), "Timestamp")

    return _sort_by_date(_your_comments_in_groups_json(reader, errors), "Timestamp")


def _your_comments_in_groups_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_comments_in_groups.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        l = d["group_comments_v2"]  # pyright: ignore
        for item in l:
            denested_dict = eh.dict_denester(item)

            datapoints.append((
                eh.fix_latin1_string(eh.find_item(denested_dict, "title")),
                eh.fix_latin1_string(eh.find_item(denested_dict, "comment-comment")),
                eh.fix_latin1_string(eh.find_item(denested_dict, "group")),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Comment", "Group", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_comments_in_groups_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("your_comments_in_groups.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""

            # The group is the value of a labelled row, and the comment is the text that
            # follows that row inside the same block::
            #
            #     <div class="_3-95"><span class="_a6_m">Group: </span>A group</div>A comment
            group = ""
            comment = ""
            label_divs = section.xpath(".//div[contains(@class, '_2pin')]//div[contains(@class, '_3-95') and span]")
            if label_divs:
                group = (label_divs[0].xpath("span")[0].tail or "").strip()
                comment = (label_divs[0].tail or "").strip()
            if not comment:
                # A comment on a post outside a group has no labelled row above it.
                comment_divs = section.xpath(".//div[contains(@class, '_2pin')]//div[not(div) and not(span)]")
                comment = comment_divs[0].text.strip() if comment_divs and comment_divs[0].text else ""

            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            timestamp = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            if title or comment or group or timestamp:
                datapoints.append((title, comment, group, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Comment", "Group", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def your_group_membership_activity_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook group membership activity.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Group name``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook group the participant joined, including the title, group name, and the time of joining.",
          "source_file": "your_group_membership_activity.json / your_group_membership_activity.html",
          "columns": {
            "Title": "Title or description of the membership activity.",
            "Group name": "Name of the Facebook group.",
            "Timestamp": "ISO 8601 timestamp of when the participant joined."
          }
        }

    Table config::

        {
          "id": "facebook_your_group_membership_activity",
          "title": {
            "en": "Group membership",
            "nl": "Groepslidmaatschap"
          },
          "description": {
            "en": "This table lists the Facebook groups you are currently a member of.",
            "nl": "Deze tabel toont de Facebookgroepen waar je momenteel lid van bent."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Group name": {"en": "Group name", "nl": "Groepsnaam"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_group_membership_activity_html(reader, errors), "Timestamp")

    return _sort_by_date(_your_group_membership_activity_json(reader, errors), "Timestamp")


def _your_group_membership_activity_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_group_membership_activity.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["groups_joined_v2"]  # pyright: ignore
        for item in items:
            denested_dict = eh.dict_denester(item)

            datapoints.append((
                eh.fix_latin1_string(eh.find_item(denested_dict, "title")),
                eh.fix_latin1_string(eh.find_item(denested_dict, "name")),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Group name", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_group_membership_activity_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """HTML variant.

    Table documentation::

        {
          "summary": "Each row represents a Facebook group the participant joined. In the HTML format the title contains the full membership sentence (e.g. 'You became a member of X.') because separating the group name from the sentence is fragile and language-dependent.",
          "source_file": "your_group_membership_activity.html",
          "columns": {
            "Title": "Full membership activity sentence from the HTML export.",
            "Group name": "Not extracted separately from HTML; see Title column.",
            "Timestamp": "Timestamp string as shown in the HTML export."
          }
        }
    """
    result = reader.raw("your_group_membership_activity.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""
            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            date = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)
            if title or date:
                datapoints.append((title, "See first column", date))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Group name", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def pages_and_profiles_you_follow_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract pages and profiles you follow on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook Page or profile the participant follows, including the title and time they started following.",
          "source_file": "pages_and_profiles_you_follow.json / pages_and_profiles_you_follow.html",
          "columns": {
            "Title": "Title of the followed Page or profile.",
            "Timestamp": "ISO 8601 timestamp of when the participant started following."
          }
        }

    Table config::

        {
          "id": "facebook_pages_and_profiles_you_follow",
          "title": {
            "en": "Pages and profiles that you follow",
            "nl": "Pagina's en profielen die je volgt"
          },
          "description": {
            "en": "This table displays the Facebook Pages and profiles that you actively follow.",
            "nl": "Deze tabel toont de Facebookpagina's en -profielen die je actief volgt."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_pages_and_profiles_you_follow_html(reader, errors), "Timestamp")

    return _sort_by_date(_pages_and_profiles_you_follow_json(reader, errors), "Timestamp")


def _pages_and_profiles_you_follow_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("pages_and_profiles_you_follow.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["pages_followed_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("title", "")),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors)
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _pages_and_profiles_you_follow_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("pages_and_profiles_you_follow.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""

            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            timestamp = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            datapoints.append((title, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def pages_youve_liked_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook pages you have liked.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Name``, ``URL``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook Page the participant has liked, including the page name, URL, and timestamp.",
          "source_file": "pages_you_ve_liked.json / pages_you've_liked.html",
          "columns": {
            "Name": "Name of the liked Facebook Page.",
            "URL": "URL of the liked Facebook Page.",
            "Timestamp": "ISO 8601 timestamp of when the page was liked."
          }
        }

    Table config::

        {
          "id": "facebook_pages_youve_liked",
          "title": {
            "en": "Pages that you have liked",
            "nl": "Pagina's die je leuk vindt"
          },
          "description": {
            "en": "This table contains a history of the Facebook Pages you have liked.",
            "nl": "Deze tabel bevat een overzicht van de Facebookpagina's die je leuk vindt."
          },
          "headers": {
            "Name": {"en": "Name", "nl": "Naam"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_pages_youve_liked_html(reader, errors), "Timestamp")

    return _sort_by_date(_pages_youve_liked_json(reader, errors), "Timestamp")


def _pages_youve_liked_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("pages_you've_liked.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["page_likes_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("name", "")),
                item.get("url", ""),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors)
            ))

        out = pd.DataFrame(datapoints, columns=["Name", "URL", "Timestamp"]) # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _pages_youve_liked_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("pages_you've_liked.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            name = h2[0].text.strip() if h2 and h2[0].text else ""

            url_anchors = section.xpath(".//footer//a/@href")
            url = url_anchors[0] if url_anchors else ""

            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            timestamp = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            datapoints.append((name, url, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Name", "URL", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def your_saved_items_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract your saved items on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a post, video, or other item the participant saved on Facebook, including the title and timestamp.",
          "source_file": "your_saved_items.json",
          "columns": {
            "Title": "Title of the saved item.",
            "Timestamp": "ISO 8601 timestamp of when the item was saved."
          }
        }

    Table config::

        {
          "id": "facebook_your_saved_items",
          "title": {
            "en": "Your saved items",
            "nl": "Je opgeslagen items"
          },
          "description": {
            "en": "This table contains the posts, videos, and other content you have saved on Facebook.",
            "nl": "Deze tabel bevat de berichten, video's en andere content die je op Facebook hebt opgeslagen."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("your_saved_items.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["saves_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("title", "")),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors)
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Timestamp")


def comments_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract all comments you made on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Comment``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a comment the participant made on a Facebook post or other content, including the title, comment text, and timestamp.",
          "source_file": "comments_and_reactions/comments.json / comments.html",
          "columns": {
            "Title": "Title of the post the comment was made on.",
            "Comment": "Text content of the comment.",
            "Timestamp": "ISO 8601 timestamp of when the comment was made."
          }
        }

    Table config::

        {
          "id": "facebook_comments",
          "title": {
            "en": "Comments",
            "nl": "Reacties"
          },
          "description": {
            "en": "This table shows all the comments you have made on Facebook posts and other content.",
            "nl": "Deze tabel toont alle comments die je op Facebook-berichten en andere content hebt geplaatst."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Comment": {"en": "Comment", "nl": "Reactie"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_comments_html(reader, errors), "Timestamp")

    return _sort_by_date(_comments_json(reader, errors), "Timestamp")


def _comments_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("comments_and_reactions/comments.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["comments_v2"]  # pyright: ignore
        for item in items:
            denested_dict = eh.dict_denester(item)

            datapoints.append((
                eh.fix_latin1_string(eh.find_item(denested_dict, "title")),
                eh.fix_latin1_string(eh.find_item(denested_dict, "comment-comment")),
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Comment", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _comments_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("comments.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""

            comment_divs = section.xpath(".//div[contains(@class, '_2pin')]/div[not(div)]")
            comment = comment_divs[0].text.strip() if comment_divs and comment_divs[0].text else ""

            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            timestamp = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            datapoints.append((title, comment, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Comment", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def likes_and_reactions_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract likes and reactions with titles from Facebook.

    Reads ``likes_and_reactions_x`` numbered files.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Reaction``, ``Timestamp``.
        Empty DataFrame when no matching files are found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a post the participant liked or reacted to on Facebook, including the post title, reaction type, and timestamp.",
          "source_file": "likes_and_reactions_1.json (and numbered variants) / likes_and_reactions_*.html",
          "columns": {
            "Title": "Title of the post that was liked or reacted to.",
            "Reaction": "Type of reaction (e.g. Like, Love, Haha).",
            "Timestamp": "ISO 8601 timestamp of when the reaction was made."
          }
        }

    Table config::

        {
          "id": "facebook_likes_and_reactions",
          "title": {
            "en": "Posts you liked",
            "nl": "Posts die je leuk vond"
          },
          "description": {
            "en": "This table shows the titles of posts you liked on Facebook.",
            "nl": "Deze tabel toont de titels van posts die je leuk vond op Facebook."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Reaction": {"en": "Reaction", "nl": "Reactie"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_likes_and_reactions_html(reader, errors), "Timestamp")

    return _sort_by_date(_likes_and_reactions_json(reader, errors), "Timestamp")


def _likes_and_reactions_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    out = pd.DataFrame()
    datapoints = []

    results = reader.json_all(r"(^|/)likes_and_reactions_\d+\.json$")
    if not results:
        return pd.DataFrame()

    try:
        for result in results:
            for item in result.data:
                denested_dict = eh.dict_denester(item)

                datapoints.append((
                    eh.fix_latin1_string(eh.find_item(denested_dict, "title")),
                    eh.fix_latin1_string(eh.find_item(denested_dict, "reaction-reaction")),
                    eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
                ))

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
        return pd.DataFrame()

    out = pd.DataFrame(datapoints, columns=["Title", "Reaction", "Timestamp"]) #pyright: ignore

    return out


def _likes_and_reactions_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    results = reader.raw_all(r"(^|/)likes_and_reactions_\d+\.html$")
    if not results:
        return pd.DataFrame()

    datapoints = []

    try:
        for result in results:
            tree = etree.HTML(result.data.read())

            sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
            for section in sections:
                h2 = section.xpath(".//h2")
                title = h2[0].text.strip() if h2 and h2[0].text else ""

                # Reaction type from icon img filename (e.g. icons/like.png -> Like)
                img = section.xpath(".//img/@src")
                reaction = ""
                if img:
                    fname = img[0].rsplit("/", 1)[-1] if "/" in img[0] else img[0]
                    reaction = fname.rsplit(".", 1)[0] if "." in fname else fname
                    reaction = reaction.capitalize()

                date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
                timestamp = _html_timestamp(
                    date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors
                )

                datapoints.append((title, reaction, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Reaction", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def your_comment_active_days_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract days you actively commented on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Label``, ``Value``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a label-value pair indicating the days on which the participant actively commented on Facebook.",
          "source_file": "your_comment_active_days.json",
          "columns": {
            "Label": "Label describing the activity metric.",
            "Value": "Value associated with the label."
          }
        }

    Table config::

        {
          "id": "facebook_your_comment_active_days",
          "title": {
            "en": "Days you actively commented",
            "nl": "Dagen waarop je actief comments hebt geplaatst"
          },
          "description": {
            "en": "This table indicates the days on which you made comments on Facebook.",
            "nl": "Deze tabel toont de dagen waarop je comments op Facebook hebt geplaatst."
          },
          "headers": {
            "Label": {"en": "Label", "nl": "Label"},
            "Value": {"en": "Value", "nl": "Waarde"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _your_comment_active_days_html(reader, errors)

    return _your_comment_active_days_json(reader, errors)


def _your_comment_active_days_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_comment_active_days.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["label_values"]  # pyright: ignore
        for item in items:
            datapoints.append((
                item.get("label", ""),
                item.get("value", ""),
            ))

        out = pd.DataFrame(datapoints, columns=["Label", "Value"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_comment_active_days_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    return pd.DataFrame()


def your_pages_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract the Facebook pages you manage.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Name``, ``URL``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook Page the participant administers, including the page name, URL, and creation timestamp.",
          "source_file": "your_pages.json",
          "columns": {
            "Name": "Name of the Facebook Page.",
            "URL": "URL of the Facebook Page.",
            "Timestamp": "ISO 8601 timestamp of when the page was created."
          }
        }

    Table config::

        {
          "id": "facebook_your_pages",
          "title": {
            "en": "Pages you manage",
            "nl": "Pagina's die je beheert"
          },
          "description": {
            "en": "This table lists the Facebook Pages that you administer.",
            "nl": "Deze tabel toont de Facebookpagina's die je beheert."
          },
          "headers": {
            "Name": {"en": "Name", "nl": "Naam"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("your_pages.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["pages_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("name", "")),
                item.get("url", ""),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Name", "URL", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Timestamp")


def story_reactions_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract your reactions to Facebook Stories.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook Story the participant reacted to, identified by its title.",
          "source_file": "story_reactions.json",
          "columns": {
            "Title": "Title of the story that was reacted to."
          }
        }

    Table config::

        {
          "id": "facebook_story_reactions",
          "title": {
            "en": "Your story reactions",
            "nl": "Je story-reacties"
          },
          "description": {
            "en": "This table contains your reactions to Facebook Stories.",
            "nl": "Deze tabel bevat je reacties op Facebook Stories."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"}
          }
        }
    """
    result = reader.json("story_reactions.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d["stories_feedback_v2"]  # pyright: ignore
        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("title", "")),
            ))

        out = pd.DataFrame(datapoints, columns=["Title"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def your_posts_check_ins_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract your posts and check-ins on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Post``, ``URL``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a post or check-in the participant made on Facebook, including the title, post content, URL, and timestamp.",
          "source_file": "your_posts__check_ins__photos_and_videos_1.json (and numbered variants) / your_posts__check_ins__photos_and_videos_*.html",
          "columns": {
            "Title": "Title of the post or check-in.",
            "Post": "Text content of the post.",
            "URL": "URL associated with the post or check-in.",
            "Timestamp": "ISO 8601 timestamp of when the post or check-in was made."
          }
        }

    Table config::

        {
          "id": "facebook_your_posts_and_check_ins",
          "title": {
            "en": "Your posts and check-ins",
            "nl": "Je posts en check-ins"
          },
          "description": {
            "en": "This table shows the posts and places you have checked into on Facebook.",
            "nl": "Deze tabel toont de berichten en plaatsen waar je op Facebook hebt ingecheckt."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Post": {"en": "Post", "nl": "Bericht"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_posts_check_ins_html(reader, errors), "Timestamp")

    return _sort_by_date(_your_posts_check_ins_json(reader, errors), "Timestamp")


def _your_posts_check_ins_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    datapoints = []

    def _parse_items(d: list) -> None:
        for item in d:
            denested_dict = eh.dict_denester(item)
            datapoints.append((
                eh.fix_latin1_string(item.get("title", "")),
                eh.fix_latin1_string(eh.find_item(denested_dict, "post")),
                eh.find_item(denested_dict, "url"),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
            ))

    try:
        results = reader.json_all(r"(^|/)your_posts__check_ins__photos_and_videos_\d+\.json$")
        for r in results:
            _parse_items(r.data)  # pyright: ignore

        out = pd.DataFrame(datapoints, columns=["Title", "Post", "URL", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_posts_check_ins_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    results = reader.raw_all(r"(^|/)your_posts__check_ins__photos_and_videos_\d+\.html$")
    if not results:
        return pd.DataFrame()

    datapoints = []

    try:
        for result in results:
            tree = etree.HTML(result.data.read())

            sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
            for section in sections:
                h2 = section.xpath(".//h2")
                title = h2[0].text.strip() if h2 and h2[0].text else ""

                # Post text from the first _2pin div's text content
                post_divs = section.xpath(".//div[contains(@class, '_2pin')]/div[not(div)]")
                post = post_divs[0].text.strip() if post_divs and post_divs[0].text else ""

                # URL from a link in the content area (not footer)
                content_links = section.xpath(".//div[contains(@class, '_2pin')]//a/@href")
                url = content_links[0] if content_links else ""

                date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
                timestamp = _html_timestamp(
                    date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors
                )

                datapoints.append((title, post, url, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Post", "URL", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def likes_and_reactions_base_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract likes and reactions from Facebook (base format).

    Reads ``likes_and_reactions.json`` (no number suffix) or, if absent, the
    numbered variants ``likes_and_reactions_1.json``, ``_2.json``, etc.
    Each item is structured with ``label_values`` containing Reaction, Name,
    and URL.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Reaction``, ``Name``, ``URL``, ``Timestamp``.
        Empty DataFrame when no matching files are found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a like or reaction the participant gave on Facebook, including the reaction type, name, URL, and timestamp.",
          "source_file": "likes_and_reactions.json or likes_and_reactions_1.json (and numbered variants) / likes_and_reactions_*.html",
          "columns": {
            "Reaction": "Type of reaction (e.g. Like, Love, Haha).",
            "Name": "Name of the content that was reacted to.",
            "URL": "URL of the content that was reacted to.",
            "Timestamp": "ISO 8601 timestamp of when the reaction was made."
          }
        }

    Table config::

        {
          "id": "facebook_likes_and_reactions_base",
          "title": {
            "en": "Likes and reactions on Facebook",
            "nl": "Likes en reacties op Facebook"
          },
          "description": {
            "en": "This table shows your likes and reactions to posts and other content on Facebook.",
            "nl": "Deze tabel toont je likes en reacties op berichten en andere content op Facebook."
          },
          "headers": {
            "Reaction": {"en": "Reaction", "nl": "Reactie"},
            "Name": {"en": "Name", "nl": "Naam"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    datapoints = []

    def _parse_items(d: list) -> None:
        for item in d:
            lv = {x.get("label", ""): x.get("value", "") for x in item.get("label_values", [])}
            datapoints.append((
                lv.get("Reaction", ""),
                eh.fix_latin1_string(lv.get("Name", "")),
                lv.get("URL", ""),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
            ))

    try:
        result = reader.json("likes_and_reactions.json")
        if result.found:
            _parse_items(result.data)  # pyright: ignore
        else:
            # Fall back to numbered files for DDPs that only export _1, _2, ...
            results = reader.json_all(r"(^|/)likes_and_reactions_\d+\.json$")
            for r in results:
                _parse_items(r.data)  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    out = pd.DataFrame(datapoints, columns=["Reaction", "Name", "URL", "Timestamp"]) if datapoints else pd.DataFrame()  # pyright: ignore
    return _sort_by_date(out, "Timestamp")


def controls_to_df(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    """Extract feed controls (show more / show less) from Facebook.

    Reads ``preferences/feed/controls.json``.  The top-level key ``controls``
    is a list of groups (e.g. "Show more", "Show less"), each with an
    ``entries`` list.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Action``, ``Content``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an action the participant took to customise their Facebook feed (show more or show less of certain content), including the action type, content affected, and date.",
          "source_file": "preferences/feed/controls.json",
          "columns": {
            "Action": "Feed control action taken (e.g. Show more, Show less).",
            "Content": "Content or topic the action was applied to.",
            "Date": "ISO 8601 timestamp of when the action was taken."
          }
        }

    Table config::

        {
          "id": "facebook_feed_controls",
          "title": {
            "en": "Feed controls (show more / show less)",
            "nl": "Feed-voorkeuren (meer zien / minder zien)"
          },
          "description": {
            "en": "This table shows the actions you've taken to customise what content you see more or less of on Facebook.",
            "nl": "Deze tabel toont de acties die je hebt ondernomen om aan te passen welke content je meer of minder ziet op Facebook."
          },
          "headers": {
            "Action": {"en": "Action", "nl": "Actie"},
            "Content": {"en": "Content", "nl": "Inhoud"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json("preferences/feed/controls.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        groups = d["controls"]  # pyright: ignore
        for group in groups:
            action = group.get("name", "")
            for entry in group.get("entries", []):
                denested = eh.dict_denester(entry)
                datapoints.append((
                    action,
                    eh.fix_latin1_string(eh.find_item(denested, "value")),
                    eh.epoch_to_datetime_string(eh.find_item(denested, "timestamp"), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Action", "Content", "Date"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return _sort_by_date(out, "Date")


# ---------------------------------------------------------------------------
# Extractors added based on old algosoc, NOT TESTED yet
# ---------------------------------------------------------------------------


def profile_visits_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract profiles visited recently on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Name``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook profile the participant recently visited, including the name and timestamp.",
          "source_file": "logged_information/interactions/profile_visits.json / profile_visits.html",
          "columns": {
            "Name": "Name of the visited profile.",
            "Timestamp": "ISO 8601 timestamp of when the visit occurred."
          }
        }

    Table config::

        {
          "id": "facebook_profile_visits",
          "title": {
            "en": "Profiles you visited recently",
            "nl": "Profielen die je recentelijk hebt bezocht"
          },
          "description": {
            "en": "This table shows the Facebook profiles you have recently visited.",
            "nl": "Deze tabel toont de Facebook-profielen die je recentelijk hebt bezocht."
          },
          "headers": {
            "Name": {"en": "Name", "nl": "Naam"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_profile_visits_html(reader, errors), "Timestamp")

    return _sort_by_date(_profile_visits_json(reader, errors), "Timestamp")


def _profile_visits_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("logged_information/interactions/profile_visits.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d:
            denested_dict = eh.dict_denester(item)
            datapoints.append((
                eh.fix_latin1_string(eh.find_item(denested_dict, "-value")),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Name", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _profile_visits_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("profile_visits.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            name_td = section.xpath(".//td[contains(@class, '_a6_r')]")
            name = name_td[0].text.strip() if name_td and name_td[0].text else ""
            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            date = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)
            if name or date:
                datapoints.append((name, date))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Name", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def video_consumption_summary_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract video consumption summary from Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Label``, ``Value``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a video consumption metric for the participant on Facebook, bucketed by time period.",
          "source_file": "your_facebook_activity/other_activity/your_video_consumption_summary.json / your_video_consumption_summary.html",
          "columns": {
            "Label": "Description of the video consumption metric.",
            "Value": "Value of the metric."
          }
        }

    Table config::

        {
          "id": "facebook_video_consumption_summary",
          "title": {
            "en": "Videos watched in the last 28 days",
            "nl": "Video's bekeken in de afgelopen 28 dagen"
          },
          "description": {
            "en": "This table shows how much time you spent watching videos on Facebook, bucketed by time period.",
            "nl": "Deze tabel toont hoeveel tijd je hebt besteed aan het bekijken van video's op Facebook, ingedeeld per tijdsperiode."
          },
          "headers": {
            "Label": {"en": "Type of consumption", "nl": "Soort weergave"},
            "Value": {"en": "Value", "nl": "Waarde"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _video_consumption_summary_html(reader, errors)

    return _video_consumption_summary_json(reader, errors)


def _video_consumption_summary_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_facebook_activity/other_activity/your_video_consumption_summary.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d["label_values"]: #pyright: ignore
            denested_dict = eh.dict_denester(item)
            datapoints.append((
                eh.find_item(denested_dict, "label"),
                eh.find_item(denested_dict, "value"),
            ))

        out = pd.DataFrame(datapoints, columns=["Label", "Value"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _video_consumption_summary_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("your_video_consumption_summary.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        rows = tree.xpath("//tr[td[contains(@class, '_a6_q')] and td[contains(@class, '_a6_r')]]")
        for row in rows:
            label_td = row.xpath("td[contains(@class, '_a6_q')]")
            value_td = row.xpath("td[contains(@class, '_a6_r')]")
            label = label_td[0].text.strip() if label_td and label_td[0].text else ""
            value = value_td[0].text.strip() if value_td and value_td[0].text else ""
            if label:
                datapoints.append((label, value))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Label", "Value"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def link_history_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract links visited from Facebook's in-app browser.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``URL``, ``Title``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an outbound link the participant opened in Facebook's in-app browser, with a timestamp.",
          "source_file": "your_facebook_activity/other_activity/link_history.json / link_history.html",
          "columns": {
            "URL": "URL of the link visited.",
            "Title": "Title of the website page visited.",
            "Timestamp": "ISO 8601 timestamp of when the link was visited."
          }
        }

    Table config::

        {
          "id": "facebook_link_history",
          "title": {
            "en": "Links visited from Facebook",
            "nl": "Links bezocht vanuit Facebook"
          },
          "description": {
            "en": "This table shows outbound links you opened in Facebook's in-app browser.",
            "nl": "Deze tabel toont uitgaande links die je hebt geopend in de in-app browser van Facebook."
          },
          "headers": {
            "URL": {"en": "URL", "nl": "URL"},
            "Title": {"en": "Title", "nl": "Titel"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_link_history_html(reader, errors), "Timestamp")

    return _sort_by_date(_link_history_json(reader, errors), "Timestamp")


def _link_history_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_facebook_activity/other_activity/link_history.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d:
            denested_dict = eh.dict_denester(item)
            title = ""
            label_values = item.get("label_values", [])
            for lv in label_values:
                if lv.get("label") == "Title of website page you visited":
                    title = lv.get("value", "Pagina heeft geen titel")
                    break
            datapoints.append((
                eh.find_item(denested_dict, "href"),
                title,
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["URL", "Title", "Timestamp"])

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _link_history_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("link_history.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = tree.xpath("//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            a_tags = section.xpath(".//a[@href]")
            url = a_tags[0].get("href", "") if a_tags else ""
            title_tds = section.xpath(".//tr[td[contains(@class, '_a6_q') and contains(text(), 'Title of website page you visited')]]/td[contains(@class, '_a6_r')]")
            title = title_tds[0].text.strip() if title_tds and title_tds[0].text else ""
            date_divs = section.xpath(".//div[contains(@class, '_a72d')]")
            date = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)
            if url or title or date:
                datapoints.append((url, title, date))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["URL", "Title", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def ad_preferences_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract ad-preference settings from Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Label``, ``Value``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an ad-preference setting the participant has on Facebook, such as targeting toggles and opt-outs.",
          "source_file": "ads_information/ad_preferences.json / ad_preferences.html",
          "columns": {
            "Label": "Name of the ad-preference setting.",
            "Value": "Current value of the setting."
          }
        }

    Table config::

        {
          "id": "facebook_ad_preferences",
          "title": {
            "en": "Ad-preference settings",
            "nl": "Advertentievoorkeuren"
          },
          "description": {
            "en": "This table shows your ad-preference settings on Facebook, including targeting toggles and opt-outs.",
            "nl": "Deze tabel toont je advertentievoorkeuren op Facebook, inclusief targetinginstellingen en opt-outs."
          },
          "headers": {
            "Label": {"en": "Setting", "nl": "Instelling"},
            "Value": {"en": "Value", "nl": "Waarde"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _ad_preferences_html(reader, errors)

    return _ad_preferences_json(reader, errors)


def _ad_preferences_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("ads_information/ad_preferences.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d["label_values"]:  # pyright: ignore
            if "value" in item:
                # Flavour 1: {"label": "...", "value": "..."}
                datapoints.append((eh.fix_latin1_string(item.get("label", "")), eh.fix_latin1_string(item.get("value", ""))))
            elif "vec" in item:
                # Flavour 2: {"label": "...", "vec": [...]}
                label = eh.fix_latin1_string(item.get("label", ""))
                vec = item.get("vec", [])
                if not vec:
                    datapoints.append((label, "No data"))
                else:
                    for vec_item in vec:
                        datapoints.append((label, eh.fix_latin1_string(vec_item.get("value", ""))))
            elif "title" in item:
                # Flavour 3: {"title": "...", "dict": [{...}, ...]}
                title = eh.fix_latin1_string(item.get("title", ""))
                dict_list = item.get("dict", [])
                if not dict_list:
                    datapoints.append((title, "No data"))
                else:
                    for dict_item in dict_list:
                        denested = eh.dict_denester(dict_item)
                        datapoints.append((title, eh.find_item(denested, "value")))

        out = pd.DataFrame(datapoints, columns=["Label", "Value"])

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _ad_preferences_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("ad_preferences.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        # 1. Simple key-value rows: <tr> with _a6_q (no colspan) + _a6_r
        kv_rows = tree.xpath("//tr[td[contains(@class, '_a6_q') and not(@colspan)] and td[contains(@class, '_a6_r')]]")
        for row in kv_rows:
            label_td = row.xpath("td[contains(@class, '_a6_q')]")
            value_td = row.xpath("td[contains(@class, '_a6_r')]")
            label = label_td[0].text.strip() if label_td and label_td[0].text else ""
            value = value_td[0].text.strip() if value_td and value_td[0].text else ""
            # Skip rows that are inside a headed subsection (these are details like "Creation time")
            if label in ("Ad title", "Advertiser", "Event", "Creation time", "Name"):
                continue
            if label:
                datapoints.append((label, value))

        # 2. Headed subsections: <h2> is the label, values depend on content type
        headed_sections = tree.xpath("//section[contains(@class, '_a6-g') and .//h2]")
        for section in headed_sections:
            h2 = section.xpath(".//h2")
            heading = h2[0].text.strip() if h2 and h2[0].text else ""
            if not heading:
                continue

            # Try "Ad title" rows (for "Hidden ads")
            ad_titles = section.xpath(".//tr[td[contains(@class, '_a6_q') and text()='Ad title']]/td[contains(@class, '_a6_r')]")
            if ad_titles:
                for td in ad_titles:
                    value = td.text.strip() if td.text else ""
                    if value:
                        datapoints.append((heading, value))
                continue

            # Try "Advertiser" rows (for "Hidden advertisers")
            advertisers = section.xpath(".//tr[td[contains(@class, '_a6_q') and text()='Advertiser']]/td[contains(@class, '_a6_r')]")
            if advertisers:
                for td in advertisers:
                    value = td.text.strip() if td.text else ""
                    if value:
                        datapoints.append((heading, value))
                continue

            # Div-based list items (for "Ads interests")
            interest_divs = section.xpath(".//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]")
            if interest_divs:
                for div in interest_divs:
                    value = div.text.strip() if div.text else ""
                    if value:
                        datapoints.append((heading, value))
                continue

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Label", "Value"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def other_categories_used_to_reach_you_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract other targeting categories advertisers used to reach you.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Category``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a targeting category advertisers used to reach the participant on Facebook.",
          "source_file": "ads_information/other_categories_used_to_reach_you.json / other_categories_used_to_reach_you.html",
          "columns": {
            "Category": "Targeting category used by advertisers."
          }
        }

    Table config::

        {
          "id": "facebook_other_categories_used_to_reach_you",
          "title": {
            "en": "Other targeting categories used to reach you",
            "nl": "Overige targetingcategorieën die zijn gebruikt om je te bereiken"
          },
          "description": {
            "en": "This table shows other categories advertisers used to target you on Facebook.",
            "nl": "Deze tabel toont overige categorieën die adverteerders hebben gebruikt om je te bereiken op Facebook."
          },
          "headers": {
            "Category": {"en": "Category", "nl": "Categorie"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _other_categories_used_to_reach_you_html(reader, errors)

    return _other_categories_used_to_reach_you_json(reader, errors)


def _other_categories_used_to_reach_you_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("ads_information/other_categories_used_to_reach_you.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d["label_values"]:  # pyright: ignore
            if "vec" in item:
                vec = item.get("vec", [])
                for vec_item in vec:
                    datapoints.append((eh.fix_latin1_string(vec_item.get("value", "")),))
            elif "value" in item:
                datapoints.append((eh.fix_latin1_string(item.get("value", "")),))
            elif "title" in item:
                dict_list = item.get("dict", [])
                for dict_item in dict_list:
                    denested = eh.dict_denester(dict_item)
                    datapoints.append((eh.find_item(denested, "value"),))

        out = pd.DataFrame(datapoints, columns=["Category"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _other_categories_used_to_reach_you_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("other_categories_used_to_reach_you.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        value_divs = tree.xpath("//td[contains(@class, '_a6_q') and @colspan]//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]")
        for div in value_divs:
            value = div.text.strip() if div.text else ""
            if value:
                datapoints.append((value,))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Category"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def advertisers_using_your_activity_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract advertisers who used your activity or information to target you.

    The source JSON uses a ``label_values`` structure where each entry has a
    ``label`` (e.g. "A list uploaded or used by the advertiser") and a ``vec``
    array of advertiser names.  Each vec item becomes its own row.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Label``, ``Value``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an advertiser who used the participant's activity or information for ad targeting on Facebook, grouped by targeting method.",
          "source_file": "ads_information/advertisers_using_your_activity_or_information.json / advertisers_using_your_activity_or_information.html",
          "columns": {
            "Label": "The method used by the advertiser to target the participant (e.g. a list uploaded by the advertiser).",
            "Value": "Name of the advertiser or value of the setting."
          }
        }

    Table config::

        {
          "id": "facebook_advertisers_using_your_activity",
          "title": {
            "en": "Advertisers using your activity or information",
            "nl": "Adverteerders die je activiteit of informatie gebruiken"
          },
          "description": {
            "en": "This table shows advertisers who used your activity or information to target you on Facebook.",
            "nl": "Deze tabel toont adverteerders die je activiteit of informatie hebben gebruikt om je te targeten op Facebook."
          },
          "headers": {
            "Label": {"en": "How they reached you", "nl": "Hoe zij u bereikten"},
            "Value": {"en": "Advertiser", "nl": "Adverteerder"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _advertisers_using_your_activity_html(reader, errors)

    return _advertisers_using_your_activity_json(reader, errors)


def _advertisers_using_your_activity_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("ads_information/advertisers_using_your_activity_or_information.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d["label_values"]:  # pyright: ignore
            if "value" in item:
                datapoints.append((eh.fix_latin1_string(item.get("label", "")), eh.fix_latin1_string(item.get("value", ""))))
            elif "vec" in item:
                label = eh.fix_latin1_string(item.get("label", ""))
                vec = item.get("vec", [])
                if not vec:
                    datapoints.append((label, "No data"))
                else:
                    for vec_item in vec:
                        datapoints.append((label, eh.fix_latin1_string(vec_item.get("value", ""))))
            elif "title" in item:
                title = eh.fix_latin1_string(item.get("title", ""))
                dict_list = item.get("dict", [])
                if not dict_list:
                    datapoints.append((title, "No data"))
                else:
                    for dict_item in dict_list:
                        denested = eh.dict_denester(dict_item)
                        datapoints.append((title, eh.find_item(denested, "value")))

        out = pd.DataFrame(datapoints, columns=["Label", "Value"])

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _advertisers_using_your_activity_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("advertisers_using_your_activity_or_information.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        # Each <td colspan class="_a6_q"> contains a label (first text node)
        # followed by nested sections with advertiser names
        headed_tds = tree.xpath("//td[contains(@class, '_a6_q') and @colspan]")
        for td in headed_tds:
            # The label is the direct text content of the td
            label = td.text.strip() if td.text else ""
            if not label:
                continue

            value_divs = td.xpath(".//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]")
            if not value_divs:
                datapoints.append((label, "No data"))
            else:
                for div in value_divs:
                    value = div.text.strip() if div.text else ""
                    if value:
                        datapoints.append((label, value))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Label", "Value"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def advertisers_youve_interacted_with_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract ads you clicked or engaged with on Facebook.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Action``, ``Title``, ``URL``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents an ad the participant clicked or engaged with on Facebook, including the action taken, ad title, URL, and timestamp.",
          "source_file": "ads_information/advertisers_you've_interacted_with.json / advertisers_you've_interacted_with.html",
          "columns": {
            "Action": "Type of interaction with the ad (e.g. Click).",
            "Title": "Title of the ad interacted with.",
            "URL": "URL of the ad or post interacted with.",
            "Timestamp": "ISO 8601 timestamp of when the interaction occurred."
          }
        }

    Table config::

        {
          "id": "facebook_advertisers_youve_interacted_with",
          "title": {
            "en": "Ads you clicked or engaged with",
            "nl": "Advertenties waarop je hebt geklikt of gereageerd"
          },
          "description": {
            "en": "This table shows the ads you have clicked or otherwise engaged with on Facebook.",
            "nl": "Deze tabel toont de advertenties waarop je hebt geklikt of waarmee je hebt gecommuniceerd op Facebook."
          },
          "headers": {
            "Action": {"en": "Action", "nl": "Actie"},
            "Title": {"en": "Title", "nl": "Titel"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_advertisers_youve_interacted_with_html(reader, errors), "Timestamp")

    return _sort_by_date(_advertisers_youve_interacted_with_json(reader, errors), "Timestamp")


def _advertisers_youve_interacted_with_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("ads_information/advertisers_you've_interacted_with.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d:
            label_values = item.get("label_values", [])
            lv_map = {}
            for lv in label_values:
                lv_map[lv.get("label", "")] = lv.get("value", "")
            datapoints.append((
                eh.fix_latin1_string(lv_map.get("Action", "")),
                eh.fix_latin1_string(lv_map.get("Title", "")),
                lv_map.get("URL", ""),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Action", "Title", "URL", "Timestamp"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _advertisers_youve_interacted_with_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("advertisers_you've_interacted_with.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        # Each top-level section contains a table with key-value rows and a footer with timestamp
        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//table and .//footer]")
        for section in sections:
            kv_rows = section.xpath(".//tr[td[contains(@class, '_a6_q') and not(@colspan)] and td[contains(@class, '_a6_r')]]")
            lv_map = {}
            for row in kv_rows:
                label_td = row.xpath("td[contains(@class, '_a6_q')]")
                value_td = row.xpath("td[contains(@class, '_a6_r')]")
                label = label_td[0].text.strip() if label_td and label_td[0].text else ""
                value = value_td[0].text.strip() if value_td and value_td[0].text else ""
                if label:
                    lv_map[label] = value

            # URL is in a colspan td with an <a> tag
            url_anchors = section.xpath(".//td[contains(@class, '_a6_q') and @colspan]//a/@href")
            url = ""
            for href in url_anchors:
                if href:
                    url = href
                    break

            # Timestamp from footer
            footer_div = section.xpath(".//footer//div[contains(@class, '_a72d')]")
            timestamp = _html_timestamp(footer_div[0].text.strip() if footer_div and footer_div[0].text else "", errors)

            datapoints.append((
                lv_map.get("Action", ""),
                lv_map.get("Title", ""),
                url,
                timestamp,
            ))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Action", "Title", "URL", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def your_contributions_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract posts and comments you made in Facebook groups (contributions).

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Value``, ``Date``, ``URL``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a post or comment the participant contributed to a Facebook group, including the content, date, and URL.",
          "source_file": "your_facebook_activity/groups/your_contributions.json / your_contributions.html",
          "columns": {
            "Value": "Concatenated text content of the contribution.",
            "Date": "ISO 8601 timestamp of when the contribution was made.",
            "URL": "URL of the contribution."
          }
        }

    Table config::

        {
          "id": "facebook_your_contributions",
          "title": {
            "en": "Contributions in groups",
            "nl": "Berichten in groepen"
          },
          "description": {
            "en": "This table shows your posts and comments contributed to Facebook groups.",
            "nl": "Deze tabel toont je berichten en comments die je hebt bijgedragen in Facebook-groepen."
          },
          "headers": {
            "Value": {"en": "Value", "nl": "Waarde"},
            "Date": {"en": "Date", "nl": "Datum en tijd"},
            "URL": {"en": "URL", "nl": "URL"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_contributions_html(reader, errors), "Date")

    return _sort_by_date(_your_contributions_json(reader, errors), "Date")


def _your_contributions_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("your_facebook_activity/groups/your_contributions.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = d if isinstance(d, list) else [d]
        for item in items:
            denested_dict = eh.dict_denester(item)
            values = eh.find_items(denested_dict, "value")
            value = eh.fix_latin1_string(", ".join(str(v) for v in values if v))
            datapoints.append((
                value,
                eh.epoch_to_datetime_string(eh.find_item(denested_dict, "timestamp"), errors=errors),
                eh.find_item(denested_dict, "url"),
            ))

        out = pd.DataFrame(datapoints, columns=["Value", "Date", "URL"]) #pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _your_contributions_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("your_contributions.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        # Top-level sections with table + footer
        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//table and .//footer]")
        for section in sections:
            # Collect all text values from nested _a6-p divs inside the section's table
            value_divs = section.xpath(".//table//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]")
            values = []
            for div in value_divs:
                text = div.text.strip() if div.text else ""
                if text:
                    values.append(text)
            value = ", ".join(values) if values else ""

            date_divs = section.xpath(".//footer//div[contains(@class, '_a72d')]")
            date = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            url_anchors = section.xpath(".//footer//a/@href")
            url = url_anchors[0] if url_anchors else ""

            datapoints.append((value, date, url))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Value", "Date", "URL"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()


def items_viewed_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract Facebook items recently viewed (from interactions).

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Product Name``, ``Description``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a Facebook item the participant recently viewed, including the title, product name, description, and date.",
          "source_file": "logged_information/interactions/items_viewed.json / items_viewed.html",
          "columns": {
            "Title": "Title of the viewed item.",
            "Product Name": "Product name of the viewed item.",
            "Description": "Description of the viewed item.",
            "Date": "ISO 8601 timestamp of when the item was viewed."
          }
        }

    Table config::

        {
          "id": "facebook_items_viewed",
          "title": {
            "en": "Facebook items recently viewed",
            "nl": "Facebook-items die je recentelijk hebt bekeken"
          },
          "description": {
            "en": "This table shows the Facebook items you have recently viewed.",
            "nl": "Deze tabel toont de Facebook-items die je recentelijk hebt bekeken."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Product Name": {"en": "Product Name", "nl": "Productnaam"},
            "Description": {"en": "Description", "nl": "Beschrijving"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_items_viewed_html(reader, errors), "Date")

    return _sort_by_date(_items_viewed_json(reader, errors), "Date")


def _items_viewed_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json("logged_information/interactions/items_viewed.json")
    if not result.found:
        return pd.DataFrame()
    d = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        for item in d:
            lv_map = {}
            for lv in item.get("label_values", []):
                label = lv.get("label", "")
                value = lv.get("value", "")
                if label and label not in lv_map:
                    lv_map[label] = value

            datapoints.append((
                eh.fix_latin1_string(lv_map.get("Title", "")),
                eh.fix_latin1_string(lv_map.get("Product name", "")),
                eh.fix_latin1_string(lv_map.get("Description", "")),
                eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "Product Name", "Description", "Date"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def _items_viewed_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.raw("items_viewed.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        # Each item is a top-level section with a table and footer
        sections = tree.xpath("//section[contains(@class, '_a6-g') and .//table and .//footer]")
        for section in sections:
            kv_rows = section.xpath(".//tr[td[contains(@class, '_a6_q') and not(@colspan)] and td[contains(@class, '_a6_r')]]")
            lv_map = {}
            for row in kv_rows:
                label_td = row.xpath("td[contains(@class, '_a6_q')]")
                value_td = row.xpath("td[contains(@class, '_a6_r')]")
                label = label_td[0].text.strip() if label_td and label_td[0].text else ""
                value = value_td[0].text.strip() if value_td and value_td[0].text else ""
                if label and label not in lv_map:
                    lv_map[label] = value

            date_divs = section.xpath(".//footer//div[contains(@class, '_a72d')]")
            date = _html_timestamp(date_divs[0].text.strip() if date_divs and date_divs[0].text else "", errors)

            datapoints.append((
                lv_map.get("Title", ""),
                lv_map.get("Product name", ""),
                lv_map.get("Description", ""),
                date,
            ))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Title", "Product Name", "Description", "Date"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return pd.DataFrame()



# ---------------------------------------------------------------------------
# Extractor registry & platform info
# ---------------------------------------------------------------------------

#: Mapping from the string names used in port_config.json to actual extractor functions.
EXTRACTOR_REGISTRY: dict[str, Callable[..., pd.DataFrame]] = {
    # --- Ordered to match the spreadsheet ---
    "your_search_history_to_df": your_search_history_to_df,                                      # logged_information/search/your_search_history.json
    "ads_interests_to_df": ads_interests_to_df,                                                  # logged_information/other_logged_information/ads_interests.json
    "profile_visits_to_df": profile_visits_to_df,                                                # logged_information/interactions/profile_visits.json
    "facebook_reels_usage_to_df": facebook_reels_usage_to_df,                                    # logged_information/other_logged_information/facebook_reels_usage_information.json
    #"video_consumption_summary_to_df": video_consumption_summary_to_df,                          # your_facebook_activity/other_activity/your_video_consumption_summary.json
    "link_history_to_df": link_history_to_df,                                                    # your_facebook_activity/other_activity/link_history.json
    "your_events_to_df": your_events_to_df,                                                      # your_facebook_activity/events/your_events.json
    "your_group_membership_activity_to_df": your_group_membership_activity_to_df,                 # your_facebook_activity/groups/your_group_membership_activity.json
    "ad_preferences_to_df": ad_preferences_to_df,                                                # ads_information/ad_preferences.json
    "other_categories_used_to_reach_you_to_df": other_categories_used_to_reach_you_to_df,        # ads_information/other_categories_used_to_reach_you.json
    "advertisers_using_your_activity_to_df": advertisers_using_your_activity_to_df,               # ads_information/advertisers_using_your_activity_or_information.json
    "advertisers_youve_interacted_with_to_df": advertisers_youve_interacted_with_to_df,           # ads_information/advertisers_you've_interacted_with
    "comments_to_df": comments_to_df,                                                            # your_facebook_activity/comments_and_reactions/comments.json
    "likes_and_reactions_to_df": likes_and_reactions_to_df,                                       # your_facebook_activity/comments_and_reactions/likes_and_reactions_1.json
    "your_posts_check_ins_to_df": your_posts_check_ins_to_df,                                    # your_facebook_activity/posts/your_posts__check_ins__photos_and_videos_1.json
    "your_contributions_to_df": your_contributions_to_df,                                        # your_facebook_activity/groups/your_contributions.json
    "your_comments_in_groups_to_df": your_comments_in_groups_to_df,                              # your_facebook_activity/comments_and_reactions/comments.json (group scope)
    "who_youve_followed_to_df": who_youve_followed_to_df,                                        # connections/followers/who_you've_followed.json
    "pages_and_profiles_you_follow_to_df": pages_and_profiles_you_follow_to_df,                   # your_facebook_activity/pages/pages_and_profiles_you_follow.json
    "pages_youve_liked_to_df": pages_youve_liked_to_df,                                          # your_facebook_activity/pages/pages_you've_liked.json
    "items_viewed_to_df": items_viewed_to_df,                                                    # logged_information/interactions/items_viewed.json
    "news_your_locations_to_df": news_your_locations_to_df,                                      # PENDING — Locations Facebook News is set to
    #"your_comment_active_days_to_df": your_comment_active_days_to_df,                            # PENDING — Days with active commenting
    # --- Not in spreadsheet — commented out ---
    # "notifications_to_df": notifications_to_df,
    # "content_sharing_you_have_created_to_df": content_sharing_you_have_created_to_df,
    # "last_28_days_to_df": last_28_days_to_df,
    # "your_friends_to_df": your_friends_to_df,
    # "recently_viewed_to_df": recently_viewed_to_df,
    # "recently_visited_to_df": recently_visited_to_df,
    # "profile_update_history_to_df": profile_update_history_to_df,
    # "group_posts_and_comments_to_df": group_posts_and_comments_to_df,
    # "your_answers_to_membership_questions_to_df": your_answers_to_membership_questions_to_df,
    # "your_saved_items_to_df": your_saved_items_to_df,
    # "your_pages_to_df": your_pages_to_df,
    # "story_reactions_to_df": story_reactions_to_df,
    # "likes_and_reactions_base_to_df": likes_and_reactions_base_to_df,
    # "controls_to_df": controls_to_df,
}


# ---------------------------------------------------------------------------
# Main extraction & flow
# ---------------------------------------------------------------------------

def _extract_username(reader: ZipArchiveReader) -> str | None:
    """Try to extract the participant's name from profile_information.json."""
    result = reader.json("profile_information/profile_information.json")
    if not result.found:
        return None
    try:
        d = result.data
        denested = eh.dict_denester(d)
        name = eh.find_item(denested, "name-full_name")
        if not name:
            name = eh.find_item(denested, "name")
        if name and isinstance(name, str) and len(name) >= 2:
            return eh.fix_latin1_string(name)
    except Exception as e:
        logger.warning("Could not extract Facebook username: %s", e)
    return None


def extraction(facebook_zip: str, validation) -> ExtractionResult:
    """Extract data from a Facebook DDP zip and return consent-form tables.

    Parameters
    ----------
    facebook_zip:
        Path to the Facebook DDP zip archive on disk.
    validation:
        Validation result object whose ``archive_members`` attribute is passed
        to ``ZipArchiveReader``.
    """
    config = load_port_config(EXTRACTOR_REGISTRY, "facebook")
    for table in config:
        table.extractor_kwargs = {'validation': validation}
    errors: Counter = Counter()
    reader = ZipArchiveReader(facebook_zip, validation.archive_members, errors)

    result = run_extraction(reader, errors, config)

    username = _extract_username(reader)
    if username:
        logger.info("Extracted Facebook username for anonymization.")

    TEXT_COLUMNS = ["Title", "Comment", "Post", "Reaction"]
    for table in result.tables:
        eh.anonymize_dataframe(table.data_frame, TEXT_COLUMNS, username)

    return result


class FacebookFlow(FlowBuilder):
    """Flow implementation for the Facebook data donation study."""

    def __init__(self, session_id: str):
        super().__init__(session_id, "Facebook")

    def validate_file(self, file):
        return validate.validate_zip(DDP_CATEGORIES, file)

    def extract_data(self, file_value, validation):
        return extraction(file_value, validation)


def process(session_id):
    flow = FacebookFlow(session_id)
    return flow.start_flow()
