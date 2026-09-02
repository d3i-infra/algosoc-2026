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

The html export renders every record in the timezone the account is set to, and names no
zone beside the timestamp — but it does name the account's zone once, in
``logged_information/location/timezone.html`` (``timezone.json`` in the json export).
``scripts/meta_html_timezone_probe.py`` matched records held in both formats of one
account and found the html clock following exactly the zone that file names, daylight
saving included. So the extractors read each html timestamp as it stands, and
``extraction()`` places every date column in the reference zone through that file
(``_place_html_clock``). An export without the file — a Drive part that lacks
``logged_information``, say — keeps its local clock, counted once as
``HtmlTimezoneUnknown``.

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
from port.api.file_utils import SeekableBinaryReader
from port.helpers.table_extractor import (
    load_port_config,
    run_extraction,
)

logger = logging.getLogger(__name__)


DDP_CATEGORIES = [
    DDPCategory(
        id="json_en",
        ddp_filetype=DDPFiletype.JSON,
        language=Language.EN,
        known_files=[
"subscription_for_no_ads.json", "other_categories_used_to_reach_you.json", "ads_feedback_activity.json", "ads_personalization_consent.json", "advertisers_you've_interacted_with.json", "advertisers_using_your_activity_or_information.json", "story_views_in_past_7_days.json", "ad_preferences.json", "groups_you've_searched_for.json", "your_search_history.json", "primary_public_location.json", "timezone.json", "primary_location.json", "your_privacy_jurisdiction.json", "people_and_friends.json", "ads_interests.json", "notifications.json", "notification_of_meta_privacy_policy_update.json", "recently_viewed.json", "recently_visited.json", "your_avatar.json", "meta_avatars_post_backgrounds.json", "contacts_sync_settings.json", "timezone.json", "autofill_information.json", "profile_information.json", "profile_update_history.json", "your_transaction_survey_information.json", "your_recently_followed_history.json", "your_recently_used_emojis.json", "navigation_bar_activity.json", "pages_and_profiles_you_follow.json", "pages_you've_liked.json", "your_saved_items.json", "fundraiser_posts_you_likely_viewed.json", "your_fundraiser_donations_information.json", "your_events.json", "event_invitations.json", "your_event_invitation_links.json", "likes_and_reactions_1.json", "your_uncategorized_photos.json", "payment_history.json", "your_answers_to_membership_questions.json", "your_group_membership_activity.json", "your_contributions.json", "group_posts_and_comments.json", "your_comments_in_groups.json", "instant_games.json", "your_page_or_groups_badges.json", "instant_games_usage_data.json", "who_you've_followed.json", "people_you_may_know.json", "received_friend_requests.json", "your_friends.json", "likes_and_reactions.json", "controls.json",
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


def _section_timestamp(section, errors: Counter) -> str:
    """Timestamp of one record in an HTML export, in the shared datetime format.

    Meta writes a record's time as a display string (``Jun 04, 2025 6:46:10
    pm``) in a ``_a72d`` div inside the record's footer. Converted here so the
    HTML and JSON paths donate the same shape and ``_sort_by_date`` can rank
    the rows; an empty footer yields ``""``. The clock is left where the export
    put it — see the module docstring.
    """
    divs = section.xpath(".//footer//div[contains(@class, '_a72d')]")
    text = divs[0].text.strip() if divs and divs[0].text else ""
    return eh.meta_html_timestamp_to_datetime_string(text, errors=errors)


def _records(data) -> list:
    """The label/value records of a JSON file, as a list.

    Facebook writes a list of ``{timestamp?, media, label_values, fbid}``
    records — except that a file with exactly one record holds that record
    bare, as an object (``link_history`` in the September 2026 export,
    ``groups_you've_visited`` in the 2025 device export). Anything else is
    not a record file and yields nothing.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "label_values" in data:
        return [data]
    return []


def _leaf_fields(node) -> tuple[dict[str, str], dict[str, str]]:
    """Label → text and label → href of the label/value rows under *node*,
    the first occurrence of a label winning.

    A row is a ``_a6_q`` label cell beside a ``_a6_r`` value cell, or — for a
    link — a colspan label cell that holds the anchor itself (the anchor's
    text is the value, its ``href`` the link). A colspan cell that holds
    neither (a list of nested records) is not a field.
    """
    values: dict[str, str] = {}
    hrefs: dict[str, str] = {}
    for row in eh.xpath_nodes(node, ".//tr[td[contains(@class, '_a6_q')]]"):
        label_td = eh.xpath_nodes(row, "td[contains(@class, '_a6_q')]")[0]
        label = label_td.text.strip() if label_td.text else ""
        if not label or label in values:
            continue
        value_td = eh.xpath_nodes(row, "td[contains(@class, '_a6_r')]")
        if value_td:
            values[label] = value_td[0].text.strip() if value_td[0].text else ""
            continue
        anchors = eh.xpath_nodes(label_td, ".//a[@href]")
        if anchors:
            values[label] = anchors[0].text.strip() if anchors[0].text else ""
            hrefs[label] = str(anchors[0].get("href", ""))
    return values, hrefs


_DATE_COLUMNS = ("Timestamp", "Date", "Created")


def _account_timezone(reader: ZipArchiveReader) -> str | None:
    """The IANA zone the account is set to, as the export names it, or ``None``.

    ``logged_information/location/timezone.json`` writes it as a label/value record;
    the html twin as a two-cell table row whose label reads "Timezone" or "Time zone".
    Absence is an expected shape (a Drive part without ``logged_information``), not an
    error.
    """
    result = reader.json("logged_information/location/timezone.json")
    if result.found:
        try:
            for item in result.data.get("label_values", []):  # pyright: ignore
                value = item.get("value", "")
                if value:
                    return str(value).strip()
        except Exception as e:
            logger.error("Exception caught: %s", e)
            reader.errors[type(e).__name__] += 1
        return None

    raw = reader.raw("logged_information/location/timezone.html")
    if not raw.found:
        return None
    try:
        tree = etree.HTML(raw.data.read())
        cells = eh.xpath_nodes(tree, "//td[contains(@class, '_a6_q')]/following-sibling::td[contains(@class, '_a6_r')]")
        for cell in cells:
            value = cell.text.strip() if cell.text else ""
            if "/" in value:
                return value
    except Exception as e:
        logger.error("Exception caught: %s", e)
        reader.errors[type(e).__name__] += 1
    return None


def _place_html_clock(tables, zone_name: str | None, errors: Counter) -> None:
    """Move every date column of an html export from the account's clock into the
    reference zone, in place.

    The html extractors write each timestamp as the export rendered it (see the module
    docstring); this is the one step that knows the account's zone. A zone the database
    does not know, or none at all, leaves the columns as they are and is counted once —
    per export, not per row, since it is a property of the whole archive.
    """
    zone = eh.resolve_timezone(zone_name)
    if zone is None:
        errors["HtmlTimezoneUnknown"] += 1
        return
    for table in tables:
        df = table.data_frame
        for column in _DATE_COLUMNS:
            if column not in df.columns:
                continue
            df[column] = [
                eh.zone_time_to_datetime_string(datetime.strptime(value, eh.DATETIME_FORMAT), zone, errors=errors)
                if isinstance(value, str) and len(value) == 19 and value[4] == "-" and value[10] == " "
                else value
                for value in df[column]
            ]


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
            "en": "This table lists the people, Pages and profiles you follow on Facebook, with the date you started following each. It can overlap with the tables of Pages you follow or like.",
            "nl": "Deze tabel toont de personen, pagina's en profielen die je volgt op Facebook, met de datum waarop je ze bent gaan volgen. Deze kan overlappen met de tabellen van pagina's die je volgt of leuk vindt."
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

        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            name = h2[0].text.strip() if h2 and h2[0].text else ""
            timestamp = _section_timestamp(section, errors)

            datapoints.append((name, timestamp))

        if datapoints:
            return pd.DataFrame(datapoints, columns=["Name", "Timestamp"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

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
        rows = eh.xpath_nodes(tree, "//tr[td[contains(@class, '_a6_q') and not(@colspan)] and td[contains(@class, '_a6_r')]]")
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
          "source_file": "logged_information/search/your_search_history.json / logged_information/search/your_search_history.html",
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
            "en": "This table contains a record of your search queries on Facebook. Facebook keeps roughly the last year of search history, so older searches are not included.",
            "nl": "Deze tabel bevat een overzicht van je zoekopdrachten op Facebook. Facebook bewaart ongeveer het laatste jaar aan zoekgeschiedenis; oudere zoekopdrachten zijn niet opgenomen."
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
    # Qualified like the JSON twin: exports also carry a Marketplace
    # your_facebook_activity/facebook_marketplace/your_search_history.html,
    # which is a different log (and a different markup).
    result = reader.raw("logged_information/search/your_search_history.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g')]")
        for section in sections:
            term_divs = section.xpath(".//div[contains(@class, '_2pin')]//div[not(div)]")
            term = term_divs[0].text.strip().strip('"') if term_divs and term_divs[0].text else ""
            date = _section_timestamp(section, errors)
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
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g')]")
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


_CONTENT_SHOWN_COLUMNS = ["Category", "Name", "Link", "Date"]

#: Categories of the split files that carry no list label of their own; worded
#: as the grouped layout named the matching sections.
_ADS_CATEGORY = "Ads"
_SHOWS_WATCHED_CATEGORY = "Videos you have watched"

_RECENTLY_VIEWED_JSON = "logged_information/interactions/recently_viewed.json"
_RECENTLY_VIEWED_HTML = "logged_information/interactions/recently_viewed.html"
_CONTENT_SHOWN_FEED_JSON = "logged_information/interactions/content_that_has_been_shown_to_you_in_your_feed.json"
_CONTENT_SHOWN_FEED_HTML = "logged_information/interactions/content_that_has_been_shown_to_you_in_your_feed.html"
_ADS_JSON = "logged_information/interactions/ads.json"
_ADS_HTML = "logged_information/interactions/ads.html"
_SHOWS_WATCHED_JSON = "logged_information/interactions/shows_you_have_watched.json"
_SHOWS_WATCHED_HTML = "logged_information/interactions/shows_you_have_watched.html"


def content_shown_to_you_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract the content Facebook showed the participant (the exposure log).

    Facebook writes this log in one of two layouts. Exports up to June 2026
    use the *grouped* one: ``recently_viewed`` holds sections (feed posts,
    videos, ads, Marketplace, web pages opened off Facebook), each with
    ``entries`` or with ``children`` that hold entries. A record is an entry
    with a ``timestamp``; the section's ``name`` becomes the row's category,
    so Meta's renamings between exports pass through unchanged. Marketplace
    activity counters (entries that carry only a date ``value``) are not
    rows. Marketplace records that do carry a timestamp (e.g. "Marketplace
    Items") are included under their own category for now — a researcher
    decision is pending.

    From September 2026 the log is *split* over files of label/value records
    in ``logged_information/interactions``: the feed file (one record whose
    Posts / Videos / Links lists hold Event · URL · Time items; the list
    label is the category), ``ads`` (Ad · Time records, category "Ads") and
    ``shows_you_have_watched`` (Title · URL records with a record timestamp,
    category "Videos you have watched"). Every file present is read and the
    rows concatenated. ``shows_that_you_have_not_finished_watching`` and
    ``time_spent_watching_facebook_shows`` are candidates for this table
    awaiting the researcher decision; ``items_viewed`` stays its own table.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON or HTML files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    validation:
        Validation result; its DDP category selects the JSON or HTML path.

    Returns
    -------
    pd.DataFrame
        Columns: ``Category``, ``Name``, ``Link``, ``Date``, newest first.
        Empty DataFrame when the files are absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row is an item Facebook showed the participant or the participant watched in roughly the last 90 days: posts shown in the feed, videos watched, ads shown, Marketplace items viewed, web pages opened off Facebook. Read from the grouped recently_viewed file (exports up to June 2026) and, from September 2026, from the split content_that_has_been_shown_to_you_in_your_feed (Posts / Videos / Links lists), ads and shows_you_have_watched files; every file present contributes rows. Marketplace activity counters that carry only a date are not rows.",
          "source_file": "logged_information/interactions/recently_viewed.json (grouped, up to June 2026); content_that_has_been_shown_to_you_in_your_feed.json + ads.json + shows_you_have_watched.json (split, from September 2026); .html twins",
          "columns": {
            "Category": "The export's section or list name for the item (e.g. Posts that have been shown to you in your Feed, Posts, Videos, Ads, Videos you have watched, Marketplace Items).",
            "Name": "Name or title of the item as the export gives it.",
            "Link": "URL of the item (the share URL for web pages opened off Facebook).",
            "Date": "ISO 8601 timestamp of when the item was shown or watched."
          }
        }

    Table config::

        {
          "id": "facebook_content_shown_to_you",
          "title": {
            "en": "Content shown to you on Facebook",
            "nl": "Content die Facebook je heeft laten zien"
          },
          "description": {
            "en": "This table lists the posts, videos and ads Facebook showed you and the items you viewed in roughly the last 90 days.",
            "nl": "Deze tabel toont de berichten, video's en advertenties die Facebook je in ongeveer de laatste 90 dagen heeft laten zien, en de items die je hebt bekeken."
          },
          "headers": {
            "Category": {"en": "Category", "nl": "Categorie"},
            "Name": {"en": "Name", "nl": "Naam"},
            "Link": {"en": "Link", "nl": "Link"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_content_shown_html(reader, errors), "Date")

    return _sort_by_date(_content_shown_json(reader, errors), "Date")


def _content_shown_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    datapoints: list[tuple[str, str, str, str]] = []

    sources: list[tuple[str, Callable[..., list[tuple[str, str, str, str]]]]] = [
        (_RECENTLY_VIEWED_JSON, _content_shown_grouped_json),
        (_CONTENT_SHOWN_FEED_JSON, _content_shown_feed_json),
        (_ADS_JSON, _content_shown_ads_json),
        (_SHOWS_WATCHED_JSON, _content_shown_shows_json),
    ]
    for member, read in sources:
        result = reader.json(member)
        if not result.found:
            continue
        try:
            datapoints.extend(read(result.data, errors))
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1

    if datapoints:
        return pd.DataFrame(datapoints, columns=_CONTENT_SHOWN_COLUMNS)  # pyright: ignore

    return pd.DataFrame()


def _content_shown_grouped_json(d, errors: Counter) -> list[tuple[str, str, str, str]]:
    """Rows of the grouped ``recently_viewed`` file: ``{"recently_viewed":
    [group…]}`` where a group has ``entries`` or ``children`` (never both)."""
    rows = []
    for group in d.get("recently_viewed", []):
        for section in group.get("children") or [group]:
            category = eh.fix_latin1_string(section.get("name", ""))
            for entry in section.get("entries", []):
                if "timestamp" not in entry:
                    continue  # a Marketplace activity counter: only a date value
                data = entry.get("data", {})
                rows.append((
                    category,
                    eh.fix_latin1_string(data.get("name", "")),
                    data.get("uri") or data.get("share") or "",
                    eh.epoch_to_datetime_string(entry["timestamp"], errors=errors),
                ))
    return rows


def _content_shown_feed_json(d, errors: Counter) -> list[tuple[str, str, str, str]]:
    """Rows of the feed file: one record whose ``label_values`` are the lists
    (``{label: "Posts", vec: [{dict: [{label: "Event", value}, {label: "URL",
    value, href}, {label: "Time", timestamp_value}]}…]}``); the list label
    is the category."""
    rows = []
    for record in _records(d):
        for lv in record.get("label_values", []):
            category = eh.fix_latin1_string(lv.get("label", ""))
            for item in lv.get("vec", []):
                name = link = date = ""
                for entry in item.get("dict", []):
                    label = entry.get("label")
                    if label == "Event":
                        name = entry.get("value", "")
                    elif label == "URL":
                        link = entry.get("href") or entry.get("value", "")
                    elif label == "Time":
                        date = eh.epoch_to_datetime_string(entry.get("timestamp_value", ""), errors=errors)
                rows.append((category, eh.fix_latin1_string(name), link, date))
    return rows


def _content_shown_records_json(d, category: str, name_label: str, errors: Counter) -> list[tuple[str, str, str, str]]:
    """Rows of a split file of ``{timestamp?, label_values: [{label, value,
    href?} | {label: "Time", timestamp_value}]}`` records: the name is the
    *name_label* value (its ``href``, if any, the link), a ``URL`` entry the
    link, a ``Time`` entry the date, else the record's own ``timestamp``."""
    rows = []
    for record in _records(d):
        name = link = ""
        date = eh.epoch_to_datetime_string(record.get("timestamp", ""), errors=errors)
        for lv in record.get("label_values", []):
            label = lv.get("label")
            if label == name_label:
                name = lv.get("value", "")
                link = lv.get("href") or link
            elif label == "URL":
                link = lv.get("href") or lv.get("value", "")
            elif label == "Time":
                date = eh.epoch_to_datetime_string(lv.get("timestamp_value", ""), errors=errors)
        rows.append((category, eh.fix_latin1_string(name), link, date))
    return rows


def _content_shown_ads_json(d, errors: Counter) -> list[tuple[str, str, str, str]]:
    return _content_shown_records_json(d, _ADS_CATEGORY, "Ad", errors)


def _content_shown_shows_json(d, errors: Counter) -> list[tuple[str, str, str, str]]:
    return _content_shown_records_json(d, _SHOWS_WATCHED_CATEGORY, "Title", errors)


def _content_shown_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    datapoints: list[tuple[str, str, str, str]] = []

    sources: list[tuple[str, Callable[..., list[tuple[str, str, str, str]]]]] = [
        (_RECENTLY_VIEWED_HTML, _content_shown_grouped_html),
        (_CONTENT_SHOWN_FEED_HTML, _content_shown_feed_html),
        (_ADS_HTML, _content_shown_ads_html),
        (_SHOWS_WATCHED_HTML, _content_shown_shows_html),
    ]
    for member, read in sources:
        result = reader.raw(member)
        if not result.found:
            continue
        try:
            datapoints.extend(read(etree.HTML(result.data.read()), errors))
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1

    if datapoints:
        return pd.DataFrame(datapoints, columns=_CONTENT_SHOWN_COLUMNS)  # pyright: ignore

    return pd.DataFrame()


def _content_shown_grouped_html(tree, errors: Counter) -> list[tuple[str, str, str, str]]:
    """Rows of the grouped ``recently_viewed`` page. A record is a leaf
    ``section._a6-g`` (no section inside it): the name is the first non-empty
    div of its ``_a6-p`` body, the link the footer's anchor, the time the
    footer's ``_a72d``; the category is the nearest enclosing section that
    owns an ``h2``. A Marketplace counter leaf has an empty ``_a72d``."""
    rows = []
    leaves = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(.//section)]")
    for leaf in leaves:
        date = _section_timestamp(leaf, errors)
        if not date:
            continue
        headings = eh.xpath_nodes(leaf, "ancestor::section[contains(@class, '_a6-g')][h2][1]/h2")
        category = headings[0].text.strip() if headings and headings[0].text else ""
        name_divs = eh.xpath_nodes(leaf, ".//div[contains(@class, '_a6-p')]//div[normalize-space(text()) != '']")
        name = name_divs[0].text.strip() if name_divs and name_divs[0].text else ""
        hrefs = eh.xpath_nodes(leaf, ".//footer//a/@href")
        link = str(hrefs[0]) if hrefs else ""
        rows.append((category, name, link, date))
    return rows


def _content_shown_feed_html(tree, errors: Counter) -> list[tuple[str, str, str, str]]:
    """Rows of the feed page. Each item is a leaf ``section._a6-g`` holding an
    Event / URL / Time table (the time a display timestamp in the cell, no
    footer); the items of a list sit inside a colspan label cell of the
    enclosing table whose text is the list name — the nearest such ancestor
    cell is the category."""
    rows = []
    for leaf in eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(.//section)]"):
        values, hrefs = _leaf_fields(leaf)
        if not values:
            continue
        cells = eh.xpath_nodes(leaf, "ancestor::td[contains(@class, '_a6_q')][1]")
        category = cells[0].text.strip() if cells and cells[0].text else ""
        rows.append((
            category,
            values.get("Event", ""),
            hrefs.get("URL") or values.get("URL", ""),
            eh.meta_html_timestamp_to_datetime_string(values.get("Time", ""), errors=errors),
        ))
    return rows


def _content_shown_records_html(tree, category: str, name_label: str, errors: Counter) -> list[tuple[str, str, str, str]]:
    """Rows of a split page of records: one top-level ``section._a6-g`` per
    record with a label/value table and a footer. The name is the
    *name_label* cell (its anchor, if it is a link row, the link), a ``URL``
    row the link; the date is a ``Time`` cell when there is one (``ads``
    writes an empty footer), else the footer's ``_a72d``."""
    rows = []
    for section in eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]"):
        values, hrefs = _leaf_fields(section)
        if not values:
            continue
        date = eh.meta_html_timestamp_to_datetime_string(values.get("Time", ""), errors=errors)
        rows.append((
            category,
            values.get(name_label, ""),
            hrefs.get(name_label) or hrefs.get("URL") or values.get("URL", ""),
            date or _section_timestamp(section, errors),
        ))
    return rows


def _content_shown_ads_html(tree, errors: Counter) -> list[tuple[str, str, str, str]]:
    return _content_shown_records_html(tree, _ADS_CATEGORY, "Ad", errors)


def _content_shown_shows_html(tree, errors: Counter) -> list[tuple[str, str, str, str]]:
    return _content_shown_records_html(tree, _SHOWS_WATCHED_CATEGORY, "Title", errors)


_OFF_META_JSON = "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.json"
_OFF_META_HTML = "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.html"
_OFF_META_COLUMNS = ["Business", "Event", "Date"]


def your_activity_off_meta_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract the activity businesses reported to Meta about the participant
    from their own websites and apps.

    Facebook writes the JSON in one of two shapes. The 2025 device export
    holds one object keyed ``off_facebook_activity_v2``: a list of businesses,
    each with a ``name`` and flat ``events`` (``id``, ``type``, epoch
    ``timestamp``). The 2026 exports write a top-level list of records
    (``title``, ``fbid``, ``label_values``) whose ``Events`` entry holds a
    ``vec`` of ``ID`` / ``Event`` / ``Received on`` dicts. The two are told
    apart on the top-level type. The HTML export is an index page with one
    section per business linking, root-relative, to that business's own page
    (``h2`` = name; one leaf table per event with ``ID`` / ``Event`` /
    ``Received on`` rows). The linked pages are read one at a time by exact
    path; a page the archive does not hold (a truncated Drive part) is an
    absence, not an error (ADR-0024). The unlinked numbered pages in the same
    folder duplicate the linked ones and are never read.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON or HTML files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    validation:
        Validation result; its DDP category selects the JSON or HTML path.

    Returns
    -------
    pd.DataFrame
        Columns: ``Business``, ``Event``, ``Date``, newest first.
        Empty DataFrame when the files are absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row is one activity that a business or organisation reported to Meta about the participant on its own website or app (page view, search, purchase, app open, ...). JSON has two shapes (off_facebook_activity_v2 with events[]; 2026 record format with label_values); HTML is an index page plus one page per business, read one at a time.",
          "source_file": "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.json / .html + your_activity_off_meta_technologies/<business>.html",
          "columns": {
            "Business": "Name of the business or app that reported the activity.",
            "Event": "Meta's event code (PAGE_VIEW, VIEW_CONTENT, SEARCH, PURCHASE, CUSTOM, ...).",
            "Date": "Timestamp of when Meta received the event, in the reference zone."
          }
        }

    Table config::

        {
          "id": "facebook_activity_off_meta",
          "title": {
            "en": "Your activity off Meta technologies",
            "nl": "Je activiteit buiten Meta"
          },
          "description": {
            "en": "Businesses and apps share with Meta what you do on their websites and apps, such as page views, searches and purchases. This table lists what they reported about you.",
            "nl": "Bedrijven en apps delen met Meta wat je op hun websites en apps doet, zoals paginaweergaven, zoekopdrachten en aankopen. Deze tabel toont wat zij over jou hebben doorgegeven."
          },
          "headers": {
            "Business": {"en": "Business", "nl": "Bedrijf"},
            "Event": {"en": "Event", "nl": "Gebeurtenis"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_your_activity_off_meta_html(reader, errors), "Date")

    return _sort_by_date(_your_activity_off_meta_json(reader, errors), "Date")


def _your_activity_off_meta_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    result = reader.json(_OFF_META_JSON)
    if not result.found:
        return pd.DataFrame()

    datapoints: list[tuple[str, str, str]] = []
    try:
        if isinstance(result.data, dict):
            datapoints = _off_meta_v2_json(result.data, errors)
        else:
            datapoints = _off_meta_records_json(result.data, errors)
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    if datapoints:
        return pd.DataFrame(datapoints, columns=_OFF_META_COLUMNS)  # pyright: ignore

    return pd.DataFrame()


def _off_meta_v2_json(d, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the 2025 shape: ``{"off_facebook_activity_v2": [{name,
    events: [{id, type, timestamp}]}]}``."""
    rows = []
    for business in d.get("off_facebook_activity_v2", []):
        name = eh.fix_latin1_string(business.get("name", ""))
        for event in business.get("events", []):
            rows.append((
                name,
                event.get("type", ""),
                eh.epoch_to_datetime_string(event.get("timestamp", ""), errors=errors),
            ))
    return rows


def _off_meta_records_json(d, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the 2026 shape: a list of ``{title, fbid, media, label_values:
    [{label: "Events", vec: [{dict: [{label, value|timestamp_value}]}]}]}``
    records."""
    rows = []
    for record in _records(d):
        name = eh.fix_latin1_string(record.get("title", ""))
        for lv in record.get("label_values", []):
            if lv.get("label") != "Events":
                continue
            for item in lv.get("vec", []):
                event = ""
                received = ""
                for entry in item.get("dict", []):
                    label = entry.get("label")
                    if label == "Event":
                        event = entry.get("value", "")
                    elif label == "Received on":
                        received = eh.epoch_to_datetime_string(entry.get("timestamp_value", ""), errors=errors)
                rows.append((name, event, received))
    return rows


def _your_activity_off_meta_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    index = reader.raw(_OFF_META_HTML)
    if not index.found:
        return pd.DataFrame()

    # The index links each business page root-relative; the export root is
    # whatever precedes the index's own path in the archive (a Drive delivery
    # wraps the export in one or two folders, a device download in none).
    member_path = index.member_path or _OFF_META_HTML
    root = member_path[: -len(_OFF_META_HTML)] if member_path.endswith(_OFF_META_HTML) else ""

    links: list[tuple[str, str]] = []
    try:
        tree = etree.HTML(index.data.read())
        for anchor in eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g')]//a[@href]"):
            links.append((anchor.text.strip() if anchor.text else "", str(anchor.get("href"))))
        del tree
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
        return pd.DataFrame()

    datapoints: list[tuple[str, str, str]] = []
    for linked_name, href in links:
        page = reader.raw(root + href)
        if not page.found:
            continue  # the page sits in another part of a split export (ADR-0024)
        try:
            datapoints.extend(_off_meta_page_html(etree.HTML(page.data.read()), linked_name, errors))
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1

    if datapoints:
        return pd.DataFrame(datapoints, columns=_OFF_META_COLUMNS)  # pyright: ignore

    return pd.DataFrame()


def _off_meta_page_html(tree, linked_name: str, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of one business page. The business is the page's ``h2`` (the
    index's anchor text when the page has none). Each event is a leaf table
    (no table nested inside it) of ``ID`` / ``Event`` / ``Received on`` rows;
    the wrapper table that holds the business ID and nests the event tables
    has no ``Event`` row and yields nothing."""
    headings = eh.xpath_nodes(tree, "//h2")
    name = headings[0].text.strip() if headings and headings[0].text else ""
    rows = []
    for table in eh.xpath_nodes(tree, "//table[not(.//table)]"):
        lv_map: dict[str, str] = {}
        for row in eh.xpath_nodes(table, "./tr[td[contains(@class, '_a6_q')] and td[contains(@class, '_a6_r')]]"):
            label_td = eh.xpath_nodes(row, "td[contains(@class, '_a6_q')]")
            value_td = eh.xpath_nodes(row, "td[contains(@class, '_a6_r')]")
            label = label_td[0].text.strip() if label_td and label_td[0].text else ""
            value = value_td[0].text.strip() if value_td and value_td[0].text else ""
            if label and label not in lv_map:
                lv_map[label] = value
        if "Event" not in lv_map:
            continue
        rows.append((
            name or linked_name,
            lv_map["Event"],
            eh.meta_html_timestamp_to_datetime_string(lv_map.get("Received on", ""), errors=errors),
        ))
    return rows


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
          "source_file": "your_facebook_activity/events/your_events.json / your_facebook_activity/events/your_events.html",
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
    result = reader.raw("your_facebook_activity/events/your_events.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            h2 = section.xpath(".//h2")
            name = h2[0].text.strip() if h2 and h2[0].text else ""
            created = _section_timestamp(section, errors)
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
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]")
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
            timestamp = _section_timestamp(section, errors)

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
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""
            date = _section_timestamp(section, errors)
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
            "en": "This table lists the Facebook Pages and professional profiles you follow, as recorded in your Pages activity. Liking a Page also follows it, so this can overlap with the other two tables.",
            "nl": "Deze tabel toont de Facebookpagina's en professionele profielen die je volgt, zoals vastgelegd in je pagina-activiteit. Een pagina leuk vinden betekent ook dat je die volgt, dus deze kan overlappen met de andere twee tabellen."
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

        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""
            timestamp = _section_timestamp(section, errors)

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
            "en": "This table lists the Facebook Pages you have liked, with the date of each like. Liking a Page is recorded separately from following it.",
            "nl": "Deze tabel toont de Facebookpagina's die je leuk vindt, met de datum van elke like. Een pagina leuk vinden wordt apart vastgelegd van een pagina volgen."
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

        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            name = h2[0].text.strip() if h2 and h2[0].text else ""

            url_anchors = section.xpath(".//footer//a/@href")
            url = url_anchors[0] if url_anchors else ""
            timestamp = _section_timestamp(section, errors)

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
          "source_file": "your_facebook_activity/comments_and_reactions/comments.json / your_facebook_activity/comments_and_reactions/comments.html",
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
    result = reader.raw("your_facebook_activity/comments_and_reactions/comments.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//h2]")
        for section in sections:
            h2 = section.xpath(".//h2")
            title = h2[0].text.strip() if h2 and h2[0].text else ""

            comment_divs = section.xpath(".//div[contains(@class, '_2pin')]/div[not(div)]")
            comment = comment_divs[0].text.strip() if comment_divs and comment_divs[0].text else ""
            timestamp = _section_timestamp(section, errors)

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

            sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//h2]")
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
                timestamp = _section_timestamp(section, errors)

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

            sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//h2]")
            for section in sections:
                h2 = section.xpath(".//h2")
                title = h2[0].text.strip() if h2 and h2[0].text else ""

                # Post text from the first _2pin div's text content
                post_divs = section.xpath(".//div[contains(@class, '_2pin')]/div[not(div)]")
                post = post_divs[0].text.strip() if post_divs and post_divs[0].text else ""

                # URL from a link in the content area (not footer)
                content_links = section.xpath(".//div[contains(@class, '_2pin')]//a/@href")
                url = content_links[0] if content_links else ""
                timestamp = _section_timestamp(section, errors)

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


_PROFILE_VISITS_COLUMNS = ["Category", "Name", "Timestamp"]
#: Category of every row of the split profile_visits file, which holds profile visits only.
_PROFILE_VISITS_SPLIT_CATEGORY = "Profile visits"
#: Categories of the split groups-and-events file, worded as the grouped layout
#: named the matching sections.
_EVENTS_VISITED_CATEGORY = "Events visited"
_GROUPS_VISITED_CATEGORY = "Groups visited"
#: A groups-and-events record carrying either of these is an event; a group has only a Name.
_EVENT_LABELS = frozenset({"Start time", "End time"})
_PROFILE_VISITS_SPLIT_JSON = "logged_information/interactions/profile_visits.json"
_PROFILE_VISITS_SPLIT_HTML = "profile_visits.html"
_GROUPS_AND_EVENTS_JSON = "logged_information/interactions/groups_and_events_you've_visited.json"
_GROUPS_AND_EVENTS_HTML = "logged_information/interactions/groups_and_events_you've_visited.html"
_RECENTLY_VISITED_JSON = "logged_information/interactions/recently_visited.json"
_RECENTLY_VISITED_HTML = "logged_information/interactions/recently_visited.html"


def profile_visits_to_df(reader: ZipArchiveReader, errors: Counter, validation=None) -> pd.DataFrame:
    """Extract the profiles, pages, groups and events the participant opened.

    Facebook writes these visits in one of two layouts. Exports up to June
    2026 use the *grouped* one: ``recently_visited`` holds sections (Profile
    visits, Page visits, Events visited, Groups visited, Marketplace Visits),
    each with ``entries``. A record is an entry with a ``timestamp``; the
    section's ``name`` becomes the row's category, so Meta's renamings
    between exports pass through unchanged. Marketplace visit counters
    (entries that carry only a date ``value``) are not rows. From September
    2026 the *split* layout writes two files of label/value records in
    ``logged_information/interactions``: ``profile_visits`` (Name records,
    category "Profile visits") and ``groups_and_events_you've_visited``,
    where a record with a Start time or End time is an event ("Events
    visited") and one with only a Name a group ("Groups visited"). The split
    files are read, and concatenated, when either is present; otherwise the
    grouped one.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON or HTML files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    validation:
        Validation result; its DDP category selects the JSON or HTML path.

    Returns
    -------
    pd.DataFrame
        Columns: ``Category``, ``Name``, ``Timestamp``, newest first.
        Empty DataFrame when the files are absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row is a Facebook profile, page, group or event the participant opened in roughly the last 90 days. Read from the grouped recently_visited file (exports up to June 2026) or, from September 2026, from the split profile_visits and groups_and_events_you've_visited files (an event carries a Start time or End time, a group only a Name). Marketplace visit counters that carry only a date are not rows.",
          "source_file": "logged_information/interactions/recently_visited.json (grouped, up to June 2026); profile_visits.json + groups_and_events_you've_visited.json (split, from September 2026); .html twins",
          "columns": {
            "Category": "The export's section name for the visit (Profile visits, Page visits, Events visited, Groups visited); in the split layout Profile visits for the profile_visits file and Events visited or Groups visited for the groups-and-events file.",
            "Name": "Name of the visited profile, page, group or event.",
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
            "en": "This table shows the Facebook profiles, pages, groups and events you opened in roughly the last 90 days.",
            "nl": "Deze tabel toont de Facebook-profielen, pagina's, groepen en evenementen die je in ongeveer de laatste 90 dagen hebt geopend."
          },
          "headers": {
            "Category": {"en": "Category", "nl": "Categorie"},
            "Name": {"en": "Name", "nl": "Naam"},
            "Timestamp": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    if validation and validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        return _sort_by_date(_profile_visits_html(reader, errors), "Timestamp")

    return _sort_by_date(_profile_visits_json(reader, errors), "Timestamp")


def _profile_visits_json(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    datapoints: list[tuple[str, str, str]] = []

    split_layout = False
    sources: list[tuple[str, Callable[..., list[tuple[str, str, str]]]]] = [
        (_PROFILE_VISITS_SPLIT_JSON, _profile_visits_split_json),
        (_GROUPS_AND_EVENTS_JSON, _groups_and_events_visited_json),
    ]
    for member, read in sources:
        result = reader.json(member)
        if not result.found:
            continue
        split_layout = True
        try:
            datapoints.extend(read(result.data, errors))
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
    if not split_layout:
        grouped = reader.json(_RECENTLY_VISITED_JSON)
        if grouped.found:
            try:
                datapoints = _profile_visits_grouped_json(grouped.data, errors)
            except Exception as e:
                logger.error("Exception caught: %s", e)
                errors[type(e).__name__] += 1

    if datapoints:
        return pd.DataFrame(datapoints, columns=_PROFILE_VISITS_COLUMNS)  # pyright: ignore

    return pd.DataFrame()


def _profile_visits_split_json(d, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the split ``profile_visits`` file: ``{timestamp, label_values:
    [{label: "Name", value}]}`` records; the name is the first value."""
    rows = []
    for item in _records(d):
        denested_dict = eh.dict_denester(item)
        rows.append((
            _PROFILE_VISITS_SPLIT_CATEGORY,
            eh.fix_latin1_string(eh.find_item(denested_dict, "-value")),
            eh.epoch_to_datetime_string(item.get("timestamp", ""), errors=errors),
        ))
    return rows


def _groups_and_events_visited_json(d, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the split ``groups_and_events_you've_visited`` file:
    ``{timestamp, label_values: [{label: "Name", value}, …]}`` records where
    an event also carries Start time / End time (``timestamp_value``),
    Description and URL (``href``) entries and a group only the Name."""
    rows = []
    for record in _records(d):
        label_values = record.get("label_values", [])
        labels = {lv.get("label") for lv in label_values}
        name = next((lv.get("value", "") for lv in label_values if lv.get("label") == "Name"), "")
        rows.append((
            _EVENTS_VISITED_CATEGORY if labels & _EVENT_LABELS else _GROUPS_VISITED_CATEGORY,
            eh.fix_latin1_string(name),
            eh.epoch_to_datetime_string(record.get("timestamp", ""), errors=errors),
        ))
    return rows


def _profile_visits_grouped_json(d, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the grouped ``recently_visited`` file: ``{"visited_things_v2":
    [{name, description, entries}…]}``."""
    rows = []
    for section in d.get("visited_things_v2", []):
        category = eh.fix_latin1_string(section.get("name", ""))
        for entry in section.get("entries", []):
            if "timestamp" not in entry:
                continue  # a Marketplace visit counter: only a date value
            rows.append((
                category,
                eh.fix_latin1_string(entry.get("data", {}).get("name", "")),
                eh.epoch_to_datetime_string(entry["timestamp"], errors=errors),
            ))
    return rows


def _profile_visits_html(reader: ZipArchiveReader, errors: Counter) -> pd.DataFrame:
    datapoints: list[tuple[str, str, str]] = []

    split_layout = False
    sources: list[tuple[str, Callable[..., list[tuple[str, str, str]]]]] = [
        (_PROFILE_VISITS_SPLIT_HTML, _profile_visits_split_html),
        (_GROUPS_AND_EVENTS_HTML, _groups_and_events_visited_html),
    ]
    for member, read in sources:
        result = reader.raw(member)
        if not result.found:
            continue
        split_layout = True
        try:
            datapoints.extend(read(etree.HTML(result.data.read()), errors))
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
    if not split_layout:
        grouped = reader.raw(_RECENTLY_VISITED_HTML)
        if grouped.found:
            try:
                datapoints = _profile_visits_grouped_html(etree.HTML(grouped.data.read()), errors)
            except Exception as e:
                logger.error("Exception caught: %s", e)
                errors[type(e).__name__] += 1

    if datapoints:
        return pd.DataFrame(datapoints, columns=_PROFILE_VISITS_COLUMNS)  # pyright: ignore

    return pd.DataFrame()


def _profile_visits_split_html(tree, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the split ``profile_visits`` page: one top-level section per
    record with the name in a ``_a6_r`` cell and a dated footer."""
    rows = []
    sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]")
    for section in sections:
        name_td = section.xpath(".//td[contains(@class, '_a6_r')]")
        name = name_td[0].text.strip() if name_td and name_td[0].text else ""
        date = _section_timestamp(section, errors)
        if name or date:
            rows.append((_PROFILE_VISITS_SPLIT_CATEGORY, name, date))
    return rows


def _groups_and_events_visited_html(tree, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the split ``groups_and_events_you've_visited`` page: one
    top-level section per record with a Name row — an event also has Start
    time / End time, Description and URL rows — and a dated footer."""
    rows = []
    for section in eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]"):
        values, _ = _leaf_fields(section)
        if not values:
            continue
        rows.append((
            _EVENTS_VISITED_CATEGORY if _EVENT_LABELS & values.keys() else _GROUPS_VISITED_CATEGORY,
            values.get("Name", ""),
            _section_timestamp(section, errors),
        ))
    return rows


def _profile_visits_grouped_html(tree, errors: Counter) -> list[tuple[str, str, str]]:
    """Rows of the grouped ``recently_visited`` page. A record is a leaf
    ``section._a6-g`` (no section inside it): the name is the first non-empty
    div of its ``_a6-p`` body, the time the footer's ``_a72d``; the category
    is the nearest enclosing section that owns an ``h2``. A Marketplace
    counter leaf has an empty ``_a72d``."""
    rows = []
    leaves = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(.//section)]")
    for leaf in leaves:
        date = _section_timestamp(leaf, errors)
        if not date:
            continue
        headings = eh.xpath_nodes(leaf, "ancestor::section[contains(@class, '_a6-g')][h2][1]/h2")
        category = headings[0].text.strip() if headings and headings[0].text else ""
        name_divs = eh.xpath_nodes(leaf, ".//div[contains(@class, '_a6-p')]//div[normalize-space(text()) != '']")
        name = name_divs[0].text.strip() if name_divs and name_divs[0].text else ""
        rows.append((category, name, date))
    return rows


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
        rows = eh.xpath_nodes(tree, "//tr[td[contains(@class, '_a6_q')] and td[contains(@class, '_a6_r')]]")
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
        for item in _records(d):
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
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and not(ancestor::section)]")
        for section in sections:
            a_tags = section.xpath(".//a[@href]")
            url = a_tags[0].get("href", "") if a_tags else ""
            title_tds = section.xpath(".//tr[td[contains(@class, '_a6_q') and contains(text(), 'Title of website page you visited')]]/td[contains(@class, '_a6_r')]")
            title = title_tds[0].text.strip() if title_tds and title_tds[0].text else ""
            date = _section_timestamp(section, errors)
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
        kv_rows = eh.xpath_nodes(tree, "//tr[td[contains(@class, '_a6_q') and not(@colspan)] and td[contains(@class, '_a6_r')]]")
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

        # 2. Labelled lists: a colspan cell whose own text is the label and whose
        # nested sections hold one value each ("Removed categories") — the HTML
        # form of the JSON `vec` entries, one row per value. The Ads-interests
        # block also sits in a colspan cell, but under an <h2> (step 3).
        list_cells = eh.xpath_nodes(tree, "//td[contains(@class, '_a6_q') and @colspan and not(.//h2)]")
        for cell in list_cells:
            label = cell.text.strip() if cell.text else ""
            if not label:
                continue
            for div in cell.xpath(".//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]"):
                value = div.text.strip() if div.text else ""
                if value:
                    datapoints.append((label, value))

        # 3. Headed subsections: <h2> is the label, values depend on content type.
        # The page nests three `_a6-g` wrappers around one <h2>, so anchor on
        # the section that directly owns each heading — matching every section
        # with an <h2> somewhere below it appends the same interests once per
        # wrapper, and the outermost wrapper also holds a colspan-labelled
        # block whose values are not interests.
        headed_sections = eh.xpath_nodes(tree, "//h2/ancestor::section[contains(@class, '_a6-g')][1]")
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
        value_divs = eh.xpath_nodes(tree, "//td[contains(@class, '_a6_q') and @colspan]//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]")
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
        headed_tds = eh.xpath_nodes(tree, "//td[contains(@class, '_a6_q') and @colspan]")
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
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//table and .//footer]")
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
            timestamp = _section_timestamp(section, errors)

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
          "source_file": "your_facebook_activity/groups/your_contributions.json / your_facebook_activity/groups/your_contributions.html",
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
    result = reader.raw("your_facebook_activity/groups/your_contributions.html")
    if not result.found:
        return pd.DataFrame()

    datapoints = []

    try:
        tree = etree.HTML(result.data.read())

        # Top-level sections with table + footer
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//table and .//footer]")
        for section in sections:
            # Collect all text values from nested _a6-p divs inside the section's table
            value_divs = section.xpath(".//table//section[contains(@class, '_a6-g')]/div[contains(@class, '_a6-p')]")
            values = []
            for div in value_divs:
                text = div.text.strip() if div.text else ""
                if text:
                    values.append(text)
            value = ", ".join(values) if values else ""
            date = _section_timestamp(section, errors)

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
        for item in _records(d):
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
        sections = eh.xpath_nodes(tree, "//section[contains(@class, '_a6-g') and .//table and .//footer]")
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
            date = _section_timestamp(section, errors)

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

#: Free-text columns that may carry the participant's own name or an e-mail
#: address; ``extraction()`` redacts them before the tables are shown.
TEXT_COLUMNS = ["Title", "Comment", "Post", "Reaction", "Name"]

#: Mapping from the string names used in port_config.json to actual extractor functions.
EXTRACTOR_REGISTRY: dict[str, Callable[..., pd.DataFrame]] = {
    # --- Ordered to match the spreadsheet ---
    "your_search_history_to_df": your_search_history_to_df,                                      # logged_information/search/your_search_history.json
    "ads_interests_to_df": ads_interests_to_df,                                                  # logged_information/other_logged_information/ads_interests.json
    "profile_visits_to_df": profile_visits_to_df,                                                # logged_information/interactions/profile_visits.json
    "content_shown_to_you_to_df": content_shown_to_you_to_df,                                    # logged_information/interactions/recently_viewed.json (to June 2026) | content_that_has_been_shown_to_you_in_your_feed.json + ads.json + shows_you_have_watched.json
    "facebook_reels_usage_to_df": facebook_reels_usage_to_df,                                    # logged_information/other_logged_information/facebook_reels_usage_information.json
    #"video_consumption_summary_to_df": video_consumption_summary_to_df,                          # your_facebook_activity/other_activity/your_video_consumption_summary.json
    "link_history_to_df": link_history_to_df,                                                    # your_facebook_activity/other_activity/link_history.json
    "your_events_to_df": your_events_to_df,                                                      # your_facebook_activity/events/your_events.json
    "your_group_membership_activity_to_df": your_group_membership_activity_to_df,                 # your_facebook_activity/groups/your_group_membership_activity.json
    "ad_preferences_to_df": ad_preferences_to_df,                                                # ads_information/ad_preferences.json
    "other_categories_used_to_reach_you_to_df": other_categories_used_to_reach_you_to_df,        # ads_information/other_categories_used_to_reach_you.json
    "advertisers_using_your_activity_to_df": advertisers_using_your_activity_to_df,               # ads_information/advertisers_using_your_activity_or_information.json
    "advertisers_youve_interacted_with_to_df": advertisers_youve_interacted_with_to_df,           # ads_information/advertisers_you've_interacted_with
    "your_activity_off_meta_to_df": your_activity_off_meta_to_df,                                # apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.json | .html + your_activity_off_meta_technologies/<business>.html
    "comments_to_df": comments_to_df,                                                            # your_facebook_activity/comments_and_reactions/comments.json
    "likes_and_reactions_to_df": likes_and_reactions_to_df,                                       # your_facebook_activity/comments_and_reactions/likes_and_reactions_1.json
    "your_posts_check_ins_to_df": your_posts_check_ins_to_df,                                    # your_facebook_activity/posts/your_posts__check_ins__photos_and_videos_1.json
    "your_contributions_to_df": your_contributions_to_df,                                        # your_facebook_activity/groups/your_contributions.json
    "your_comments_in_groups_to_df": your_comments_in_groups_to_df,                              # your_facebook_activity/comments_and_reactions/comments.json (group scope)
    "who_youve_followed_to_df": who_youve_followed_to_df,                                        # connections/followers/who_you've_followed.json
    "pages_and_profiles_you_follow_to_df": pages_and_profiles_you_follow_to_df,                   # your_facebook_activity/pages/pages_and_profiles_you_follow.json
    "pages_youve_liked_to_df": pages_youve_liked_to_df,                                          # your_facebook_activity/pages/pages_you've_liked.json
    "items_viewed_to_df": items_viewed_to_df,                                                    # logged_information/interactions/items_viewed.json
    #"your_comment_active_days_to_df": your_comment_active_days_to_df,                            # PENDING — Days with active commenting
    # --- Not in spreadsheet — commented out ---
    # "notifications_to_df": notifications_to_df,
    # "content_sharing_you_have_created_to_df": content_sharing_you_have_created_to_df,
    # "last_28_days_to_df": last_28_days_to_df,
    # "your_friends_to_df": your_friends_to_df,
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


def extraction(facebook_zip: SeekableBinaryReader, validation) -> ExtractionResult:
    """Extract data from a Facebook DDP zip and return consent-form tables.

    Parameters
    ----------
    facebook_zip:
        Seekable binary reader over the Facebook DDP zip — the upload
        adapter itself, never a path (ADR-0026).
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

    if validation.current_ddp_category.ddp_filetype == DDPFiletype.HTML:
        _place_html_clock(result.tables, _account_timezone(reader), errors)

    username = _extract_username(reader)
    if username:
        logger.info("Extracted Facebook username for anonymization.")

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
