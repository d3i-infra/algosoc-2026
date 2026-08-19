"""
Instagram

This module contains an example flow of a Instagram data donation study

Assumptions:
It handles DDPs in the english language with filetype JSON.

Configuration
-------------
The ``extraction`` function is driven by ``port_config.json``.  Generate one with::

    pnpm generate-config instagram

Each extractor function carries its own table config in a ``Table config::``
JSON block inside its docstring.  The generator reads those blocks and
assembles the JSON file.

Platform info::

    {
        "name": "Instagram",
        "filetypes": ["json"],
        "languages": ["en", "nl"],
        "description": "Note that supported DDP language also includes Dutch and probably other languages as well. You get an english DDP regardless of the Dutch language setting. These data donation flows have not been tested yet, if you find anything wrong with them report to datadonation@uu.nl and they will be fixed!",
        "time_last_tested": "not yet implemented"
    }
"""

import logging
from collections import Counter
from typing import Any, Callable

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

DDP_CATEGORIES = [
    DDPCategory(
        id="json_en",
        ddp_filetype=DDPFiletype.JSON,
        language=Language.EN,
        known_files=[
            "secret_conversations.json",
            "personal_information.json",
            "account_privacy_changes.json",
            "account_based_in.json",
            "recently_deleted_content.json",
            "liked_posts.json",
            "stories.json",
            "profile_photos.json",
            "followers.json",
            "signup_information.json",
            "comments_allowed_from.json",
            "login_activity.json",
            "your_topics.json",
            "camera_information.json",
            "recent_follow_requests.json",
            "devices.json",
            "professional_information.json",
            "follow_requests_you've_received.json",
            "eligibility.json",
            "pending_follow_requests.json",
            "videos_watched.json",
            "ads_viewed.json",
            "ads_interests.json",
            "account_searches.json",
            "profile_searches.json",
            "followers_1.json",
            "saved_posts.json",
            "following.json",
            "posts_viewed.json",
            "post_comments_1.json",
            "recently_unfollowed_accounts.json",
            "post_comments.json",
            "account_information.json",
            "accounts_you're_not_interested_in.json",
            "liked_comments.json",
            "story_likes.json",
            "threads_viewed.json",
            "use_cross-app_messaging.json",
            "profile_changes.json",
            "reels.json",
        ],
    )
]



# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _sort_by_date(out: pd.DataFrame, date_column: str) -> pd.DataFrame:
    """Sort *out* by *date_column* using ISO-timestamp ordering.

    Parameters
    ----------
    out:
        DataFrame to sort.
    date_column:
        Name of the column that contains ISO-formatted timestamp strings.
        Rows with empty timestamps are placed last.
    """
    return out.sort_values(by=date_column, key=eh.sort_isotimestamp_empty_timestamp_last)


def _first_present(data: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """Return the first dict value found for the given keys, or empty dict.

    Parameters
    ----------
    data:
        Dictionary to search.
    keys:
        Ordered list of keys to try; the value of the first key whose
        corresponding value is a ``dict`` is returned.
    """
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _extract_owner_details(label_values: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Extract ``(owner_name, owner_username, url)`` from a nested label_values structure.

    This structure is used in newer Instagram export formats.

    Parameters
    ----------
    label_values:
        Nested list/dict structure from the Instagram DDP containing labelled
        metadata fields such as ``"Name"``, ``"Username"``, and ``"URL"``.

    Returns
    -------
    tuple[str, str, str]
        A three-tuple of ``(owner_name, owner_username, url)``.  Any field
        not found in *label_values* is returned as an empty string.
    """
    owner_name = ""
    owner_username = ""
    url = ""

    def visit(node: Any) -> None:
        nonlocal owner_name, owner_username, url

        if isinstance(node, list):
            for item in node:
                visit(item)
            return

        if not isinstance(node, dict):
            return

        label = str(node.get("label", ""))
        value = str(node.get("value", ""))
        href = str(node.get("href", ""))

        if label == "URL" and not url:
            url = href or value
        elif label in {"Naam", "Name"} and not owner_name:
            owner_name = eh.fix_latin1_string(value)
        elif label in {"Gebruikersnaam", "Username", "Author"} and not owner_username:
            owner_username = eh.fix_latin1_string(value)

        for child in node.values():
            visit(child)

    visit(label_values)
    return owner_name, owner_username, url


# ---------------------------------------------------------------------------
# Per-table extraction functions
# ---------------------------------------------------------------------------
# Ordered to match the algosoc-2026 extraction list.
# Extractors not in the list are commented out at the end.
# Missing extractors are marked with TODO comments.
# ---------------------------------------------------------------------------

def following_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "following.json",
) -> pd.DataFrame:
    """Extract the list of followed accounts into a DataFrame.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"following.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Account``, ``URL``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one account that the participant follows on Instagram, including when they started following.",
          "source_file": "following.json",
          "columns": {
            "Account": "Username or display name of the followed account.",
            "URL": "Direct URL to the followed account's Instagram profile.",
            "Date": "ISO 8601 timestamp of when the participant started following this account."
          }
        }

    Table config::

        {
          "id": "instagram_following",
          "title": {
            "en": "Accounts that you follow on Instagram",
            "nl": "Accounts die je volgt op Instagram"
          },
          "description": {
            "en": "In this table, you find the accounts that you follow on Instagram.",
            "nl": "In deze tabel zie je de accounts die je volgt op Instagram."
          },
          "headers": {
            "Account": {"en": "Account", "nl": "Account"},
            "URL": {"en": "URL", "nl": "URL"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = data["relationships_following"]  # pyright: ignore
        for item in items:
            d = eh.dict_denester(item)
            datapoints.append((
                eh.fix_latin1_string(eh.find_item(d, "title") or eh.find_item(d, "value")),
                eh.find_item(d, "href"),
                eh.epoch_to_iso(eh.find_item(d, "timestamp"), errors=errors),
            ))
        out = pd.DataFrame(datapoints, columns=["Account", "URL", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def posts_viewed_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "posts_viewed.json",
) -> pd.DataFrame:
    """Extract the list of viewed posts into a DataFrame.

    Handles both the older ``string_map_data`` format (dict root keyed by
    ``"impressions_history_posts_seen"``) and the newer ``label_values``
    list-at-root format.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"posts_viewed.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Author``, ``URL``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one post that appeared in the participant's Instagram feed and was registered as viewed. Captures the author and timing of each impression.",
          "source_file": "posts_viewed.json",
          "columns": {
            "Author": "Username or display name of the account that published the viewed post.",
            "URL": "Direct URL to the viewed post.",
            "Date": "ISO 8601 timestamp of when the post was viewed."
          }
        }

    Table config::

        {
          "id": "instagram_posts_viewed",
          "title": {
            "en": "Posts viewed on Instagram",
            "nl": "Berichten bekeken op Instagram"
          },
          "description": {
            "en": "In this table you find the accounts of posts you viewed on Instagram sorted over time. Below, you find visualizations of different parts of this table. First, you find a timeline showing you the number of posts you viewed over time. Next, you find a histogram indicating how many posts you have viewed per hour of the day.",
            "nl": "In deze tabel zie je de accounts van berichten die je op Instagram hebt bekeken, gesorteerd op tijd. Hieronder vind je visualisaties van verschillende onderdelen van deze tabel. Eerst zie je een tijdlijn met het aantal berichten dat je in de loop van de tijd hebt bekeken. Daarna zie je een histogram dat aangeeft hoeveel berichten je per uur van de dag hebt bekeken."
          },
          "headers": {
            "Author": {"en": "Author", "nl": "Auteur"},
            "URL": {"en": "URL", "nl": "URL"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          },
          "visualizations": [
            {
              "title": {
                "en": "The total number of Instagram posts you viewed over time",
                "nl": "Het totale aantal Instagram-berichten dat je in de loop van de tijd hebt bekeken"
              },
              "type": "area",
              "group": {"column": "Date", "dateFormat": "auto"},
              "values": [{"label": "Count", "aggregate": "count"}]
            },
            {
              "title": {
                "en": "The total number of Instagram posts you have viewed per hour of the day",
                "nl": "Het totale aantal Instagram-berichten dat je per uur van de dag hebt bekeken"
              },
              "type": "bar",
              "group": {"column": "Date", "dateFormat": "hour_cycle", "label": "Hour of the day"},
              "values": [{"label": "Count"}]
            }
          ]
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data["impressions_history_posts_seen"]  # pyright: ignore
            for item in items:
                string_map_data = item.get("string_map_data", {})
                author = _first_present(string_map_data, ["Author", "Auteur"])
                time = _first_present(string_map_data, ["Time", "Tijd"])
                url = _first_present(string_map_data, ["URL"])
                datapoints.append((
                    eh.fix_latin1_string(str(author.get("value", ""))),
                    url.get("href", ""),
                    eh.epoch_to_iso(time.get("timestamp", ""), errors=errors),
                ))
        else:
            for item in data:  # pyright: ignore
                owner_name, owner_username, url = _extract_owner_details(item.get("label_values", []))
                datapoints.append((
                    owner_username or owner_name,
                    url,
                    eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Author", "URL", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def videos_watched_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "videos_watched.json",
) -> pd.DataFrame:
    """Extract the list of watched videos into a DataFrame.

    Handles both the older ``string_map_data`` format (dict root keyed by
    ``"impressions_history_videos_watched"``) and the newer ``label_values``
    list-at-root format.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"videos_watched.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Author``, ``URL``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one video (including Reels) that the participant watched on Instagram. Captures the creator and timing of each view event.",
          "source_file": "videos_watched.json",
          "columns": {
            "Author": "Username or display name of the account that published the watched video.",
            "URL": "Direct URL to the watched video.",
            "Date": "ISO 8601 timestamp of when the video was watched."
          }
        }

    Table config::

        {
          "id": "instagram_videos_watched",
          "title": {
            "en": "Videos watched on Instagram",
            "nl": "Video's bekeken op Instagram"
          },
          "description": {
            "en": "In this table you find the accounts of videos you watched on Instagram sorted over time. Below, you find a timeline showing you the number of videos you watched over time.",
            "nl": "In deze tabel zie je de accounts van video's die je op Instagram hebt bekeken, gesorteerd op tijd. Hieronder zie je een tijdlijn met het aantal video's dat je in de loop van de tijd hebt bekeken."
          },
          "headers": {
            "Author": {"en": "Author", "nl": "Auteur"},
            "URL": {"en": "URL", "nl": "URL"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          },
          "visualizations": [
            {
              "title": {
                "en": "The total number of videos watched on Instagram over time",
                "nl": "Het totale aantal video's dat je op Instagram hebt bekeken in de loop van de tijd"
              },
              "type": "area",
              "group": {"column": "Date", "dateFormat": "auto"},
              "values": [{"aggregate": "count", "label": "Count"}]
            }
          ]
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data["impressions_history_videos_watched"]  # pyright: ignore
            for item in items:
                string_map_data = item.get("string_map_data", {})
                author = _first_present(string_map_data, ["Author", "Auteur"])
                time = _first_present(string_map_data, ["Time", "Tijd"])
                url = _first_present(string_map_data, ["URL"])
                datapoints.append((
                    eh.fix_latin1_string(str(author.get("value", ""))),
                    url.get("href", ""),
                    eh.epoch_to_iso(time.get("timestamp", ""), errors=errors),
                ))
        else:
            for item in data:  # pyright: ignore
                owner_name, owner_username, url = _extract_owner_details(item.get("label_values", []))
                datapoints.append((
                    owner_username or owner_name,
                    url,
                    eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Author", "URL", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def post_comments_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename_pattern: str = r"(^|/)post_comments(?:_\d+)?\.json$",
) -> pd.DataFrame:
    """Extract all post comments across multiple matching files into a DataFrame.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename_pattern:
        Regular expression matched against archive member paths.  All matching
        files are read and combined.  Defaults to a pattern that matches
        ``post_comments.json``, ``post_comments_1.json``, etc.

    Returns
    -------
    pd.DataFrame
        Columns: ``Comment``, ``Media owner``, ``Date``.
        Empty DataFrame when no matching files are found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one comment the participant posted on an Instagram post. Covers all matching comment files in the archive (e.g. post_comments.json, post_comments_1.json).",
          "source_file": "post_comments*.json",
          "columns": {
            "Comment": "The full text of the comment posted by the participant.",
            "Media owner": "Username of the account that owns the post the comment was placed on.",
            "Date": "ISO 8601 timestamp of when the comment was posted."
          }
        }

    Table config::

        {
          "id": "instagram_post_comments",
          "title": {
            "en": "Comments posted on Instagram",
            "nl": "Reacties geplaatst op Instagram"
          },
          "description": {
            "en": "List of comments you posted on Instagram.",
            "nl": "Lijst van reacties die je op Instagram hebt geplaatst."
          },
          "headers": {
            "Comment": {"en": "Comment", "nl": "Reactie"},
            "Media owner": {"en": "Media owner", "nl": "Media-eigenaar"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    datapoints = []

    try:
        results = reader.json_all(filename_pattern)
        
        if not results:
            return pd.DataFrame()

        for result in results:
            data = result.data
            if isinstance(data, list):
                items = data
            elif "string_map_data" in data:
                items = [data]
            else:
                items = data.get("comments_media_comments", [])
            for item in items:  # pyright: ignore[assignment]
                string_map_data = item.get("string_map_data", {})
                comment = _first_present(string_map_data, ["Comment", "Opmerking"])
                owner = _first_present(string_map_data, ["Media Owner", "Media-eigenaar"])
                time = _first_present(string_map_data, ["Time", "Tijd"])
                datapoints.append((
                    eh.fix_latin1_string(str(comment.get("value", ""))),
                    eh.fix_latin1_string(str(owner.get("value", ""))),
                    eh.epoch_to_iso(time.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Comment", "Media owner", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def liked_comments_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "liked_comments.json",
) -> pd.DataFrame:
    """Extract the list of liked comments into a DataFrame.

    Handles both the older ``string_list_data`` format (dict root keyed by
    ``"likes_comment_likes"``) and the newer ``label_values`` list-at-root
    format.  Note that the comment text is not available in the newer format.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"liked_comments.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Account name``, ``Value``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one comment the participant liked on Instagram. Comment text may be absent in newer export formats.",
          "source_file": "liked_comments.json",
          "columns": {
            "Account name": "Username of the account whose comment was liked.",
            "Value": "Text of the liked comment, if available in the export (empty in newer export formats).",
            "Date": "ISO 8601 timestamp of when the comment was liked."
          }
        }

    Table config::

        {
          "id": "instagram_liked_comments",
          "title": {
            "en": "Instagram liked comments",
            "nl": "Instagram-reacties die je leuk vond"
          },
          "description": {
            "en": "List of comments that you liked on Instagram.",
            "nl": "Lijst van reacties die je leuk vond op Instagram."
          },
          "headers": {
            "Account name": {"en": "Account name", "nl": "Accountnaam"},
            "Value": {"en": "Value", "nl": "Waarde"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data["likes_comment_likes"]  # pyright: ignore
            for item in items:
                entry = item.get("string_list_data", [{}])[0]
                datapoints.append((
                    eh.fix_latin1_string(item.get("title", "")),
                    eh.fix_latin1_string(entry.get("value", "")),
                    eh.epoch_to_iso(entry.get("timestamp", ""), errors=errors),
                ))
        else:
            for item in data:  # pyright: ignore
                owner_name, owner_username, url = _extract_owner_details(item.get("label_values", []))
                datapoints.append((
                    owner_username or owner_name,
                    "",  # comment text not available in label_values format
                    eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Account name", "Value", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def liked_posts_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "liked_posts.json",
) -> pd.DataFrame:
    """Extract the list of liked posts into a DataFrame.

    Handles both the older ``dict_denester`` format (dict root keyed by
    ``"likes_media_likes"``) and the newer ``label_values`` list-at-root
    format.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"liked_posts.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Account name``, ``Value``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one post the participant liked on Instagram, including the account whose post was liked and when the like was given.",
          "source_file": "liked_posts.json",
          "columns": {
            "Account name": "Username of the account whose post was liked.",
            "Value": "Display name or additional label for the liked post, depending on export format.",
            "Date": "ISO 8601 timestamp of when the post was liked."
          }
        }

    Table config::

        {
          "id": "instagram_liked_posts",
          "title": {
            "en": "Instagram liked posts",
            "nl": "Instagram-berichten die je leuk vond"
          },
          "description": {"en": "", "nl": ""},
          "headers": {
            "Account name": {"en": "Account name", "nl": "Accountnaam"},
            "Value": {"en": "Value", "nl": "Waarde"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          },
          "visualizations": [
            {
              "title": {"en": "Most liked accounts", "nl": "Meest gelikete accounts"},
              "type": "wordcloud",
              "textColumn": "Account name",
              "tokenize": false
            }
          ]
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data["likes_media_likes"]  # pyright: ignore
            for item in items:
                d = eh.dict_denester(item)
                datapoints.append((
                    eh.fix_latin1_string(eh.find_item(d, "title")),
                    eh.fix_latin1_string(eh.find_item(d, "value")),
                    eh.epoch_to_iso(eh.find_item(d, "timestamp"), errors=errors),
                ))
        else:
            for item in data:  # pyright: ignore
                owner_name, owner_username, url = _extract_owner_details(item.get("label_values", []))
                datapoints.append((
                    owner_username or owner_name,
                    owner_name,
                    eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Account name", "Value", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def story_likes_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "story_likes.json",
) -> pd.DataFrame:
    """Extract the list of liked stories into a DataFrame.

    Handles both the older ``string_list_data`` format (dict root keyed by
    ``"story_activities_story_likes"``) and the newer ``label_values``
    list-at-root format.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"story_likes.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Account name``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one Instagram Story the participant liked, recording the account whose story was liked and when.",
          "source_file": "story_likes.json",
          "columns": {
            "Account name": "Username of the account whose story was liked.",
            "Date": "ISO 8601 timestamp of when the story was liked."
          }
        }

    Table config::

        {
          "id": "instagram_story_likes",
          "title": {"en": "Story likes on Instagram", "nl": "Story-likes op Instagram"},
          "description": {
            "en": "List of Instagram stories you liked.",
            "nl": "Lijst van Instagram-stories die je leuk vond."
          },
          "headers": {
            "Account name": {"en": "Account name", "nl": "Accountnaam"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data["story_activities_story_likes"]  # pyright: ignore
            for item in items:
                entry = item.get("string_list_data", [{}])[0]
                datapoints.append((
                    eh.fix_latin1_string(item.get("title", "")),
                    eh.epoch_to_iso(entry.get("timestamp", ""), errors=errors),
                ))
        else:
            for item in data:  # pyright: ignore
                owner_name, owner_username, _ = _extract_owner_details(item.get("label_values", []))
                datapoints.append((
                    owner_username or owner_name,
                    eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Account name", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def saved_posts_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "saved_posts.json",
) -> pd.DataFrame:
    """Extract the list of saved posts into a DataFrame.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"saved_posts.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Value``, ``Timestamp``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one post the participant bookmarked (saved) on Instagram for later viewing.",
          "source_file": "saved_posts.json",
          "columns": {
            "Title": "Concatenated title labels from the saved post metadata.",
            "Value": "Concatenated values (caption, URL, owner info) from the saved post.",
            "Timestamp": "ISO 8601 timestamp of when the post was saved."
          }
        }

    Table config::

        {
          "id": "instagram_saved_posts",
          "title": {
            "en": "Your saved posts on Instagram",
            "nl": "Je opgeslagen berichten op Instagram"
          },
          "description": {
            "en": "List of posts you have saved on Instagram.",
            "nl": "Lijst van berichten die je hebt opgeslagen op Instagram."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Value": {"en": "Value", "nl": "Waarde"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = data if isinstance(data, list) else data.get("saved_saved_media", [])  # pyright: ignore
        for item in items:
            d = eh.dict_denester(item)
            value = " ".join(
                eh.fix_latin1_string(str(v)) for v in eh.find_items(d, "value") if v
            )
            title = " ".join(
                eh.fix_latin1_string(str(v)) for v in eh.find_items(d, "title") if v
            )
            datapoints.append((
                title,
                value,
                eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
            ))
        out = pd.DataFrame(datapoints, columns=["Title", "Value", "Timestamp"])  # pyright: ignore
        out = _sort_by_date(out, "Timestamp")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


# ---------------------------------------------------------------------------
# RECREATED FROM algosoc-dd-old — NEEDS MANUAL VERIFICATION
# Source: algosoc-dd-old/src/framework/processing/py/port/instagram.py parse_searches()
# ---------------------------------------------------------------------------
def word_or_phrase_searches_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "word_or_phrase_searches.json",
) -> pd.DataFrame:
    """Extract keyword searches into a DataFrame.

    Reads the older ``string_map_data`` format keyed by
    ``"searches_keyword"``.  Each entry contains a search term and timestamp.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"word_or_phrase_searches.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Search term``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one keyword or phrase search the participant performed on Instagram.",
          "source_file": "word_or_phrase_searches.json",
          "columns": {
            "Search term": "The word or phrase that was searched for.",
            "Date": "ISO 8601 timestamp of when the search was performed."
          }
        }

    Table config::

        {
          "id": "instagram_word_or_phrase_searches",
          "title": {
            "en": "Your keyword searches on Instagram",
            "nl": "Je zoekwoorden op Instagram"
          },
          "description": {
            "en": "List of words or phrases you have searched for on Instagram.",
            "nl": "Lijst van woorden of zinnen die je op Instagram hebt gezocht."
          },
          "headers": {
            "Search term": {"en": "Search term", "nl": "Zoekterm"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data.get("searches_keyword", [])
        else:
            items = data  # pyright: ignore

        for item in items:
            string_map_data = item.get("string_map_data", {})
            search = _first_present(string_map_data, ["Search", "Zoekopdracht", "Zoeken"])
            time = _first_present(string_map_data, ["Time", "Tijd"])
            datapoints.append((
                eh.fix_latin1_string(str(search.get("value", ""))),
                eh.epoch_to_iso(time.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Search term", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def stories_published_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "stories.json",
) -> pd.DataFrame:
    """Extract published stories into a DataFrame.

    Reads the ``"ig_stories"`` key from the JSON.  Each entry contains a
    title and a ``creation_timestamp``.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"stories.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URI``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one Instagram Story published by the participant.",
          "source_file": "stories.json",
          "columns": {
            "Title": "Caption or title text of the story, if any.",
            "URI": "Internal media URI of the story asset in the export archive.",
            "Date": "ISO 8601 timestamp of when the story was created."
          }
        }

    Table config::

        {
          "id": "instagram_stories_published",
          "title": {
            "en": "Stories you published on Instagram",
            "nl": "Stories die je op Instagram hebt geplaatst"
          },
          "description": {
            "en": "List of stories you have published on Instagram.",
            "nl": "Lijst van stories die je op Instagram hebt geplaatst."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "URI": {"en": "URI", "nl": "URI"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data.get("ig_stories", [])
        else:
            items = data  # pyright: ignore

        for item in items:
            datapoints.append((
                eh.fix_latin1_string(item.get("title", "")),
                item.get("uri", ""),
                eh.epoch_to_iso(item.get("creation_timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Title", "URI", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


# ---------------------------------------------------------------------------
# RECREATED FROM algosoc-dd-old — NEEDS MANUAL VERIFICATION
# Source: algosoc-dd-old/src/framework/processing/py/port/instagram.py parse_advertisers_using_activity()
# ---------------------------------------------------------------------------
def advertisers_using_activity_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "advertisers_using_your_activity_or_information.json",
) -> pd.DataFrame:
    """Extract advertisers using participant activity into a DataFrame.

    Handles the newer ``label_values`` format where advertisers are grouped
    under category labels, and the older format keyed by
    ``"ig_custom_audiences_all_types"``.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"advertisers_using_your_activity_or_information.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Advertiser``, ``Category``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one advertiser that used the participant's activity or information to target them on Instagram.",
          "source_file": "advertisers_using_your_activity_or_information.json",
          "columns": {
            "Advertiser": "Name of the advertiser.",
            "Category": "Category describing how the advertiser used the participant's data."
          }
        }

    Table config::

        {
          "id": "instagram_advertisers_using_activity",
          "title": {
            "en": "Advertisers using your activity or information",
            "nl": "Adverteerders die je activiteit of informatie gebruiken"
          },
          "description": {
            "en": "List of advertisers that used your activity or information to reach you on Instagram.",
            "nl": "Lijst van adverteerders die je activiteit of informatie hebben gebruikt om je te bereiken op Instagram."
          },
          "headers": {
            "Advertiser": {"en": "Advertiser", "nl": "Adverteerder"},
            "Category": {"en": "Category", "nl": "Categorie"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            # Newer format: label_values at root level
            label_values = data.get("label_values", [])
            if label_values:
                for group in label_values:
                    category = group.get("label", "")
                    for entry in group.get("vec", []):
                        datapoints.append((
                            eh.fix_latin1_string(entry.get("value", "")),
                            category,
                        ))
            else:
                # Older format: ig_custom_audiences_all_types
                items = data.get("ig_custom_audiences_all_types", [])
                for item in items:
                    datapoints.append((
                        eh.fix_latin1_string(item.get("advertiser_name", "")),
                        "",
                    ))

        out = pd.DataFrame(datapoints, columns=["Advertiser", "Category"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def ads_viewed_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "ads_viewed.json",
) -> pd.DataFrame:
    """Extract the list of viewed ads into a DataFrame.

    Supports both the list-at-root format and the dict format keyed by
    ``"impressions_history_ads_seen"``.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"ads_viewed.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Account name``, ``Name``, ``URL``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one advertisement impression shown to the participant on Instagram. Includes the advertiser identity and when the ad was displayed.",
          "source_file": "ads_viewed.json",
          "columns": {
            "Account name": "Username of the advertiser's Instagram account.",
            "Name": "Display name of the advertiser.",
            "URL": "URL associated with the advertisement.",
            "Date": "ISO 8601 timestamp of when the ad was shown to the participant."
          }
        }

    Table config::

        {
          "id": "instagram_ads_viewed",
          "title": {
            "en": "Ads viewed on Instagram",
            "nl": "Advertenties bekeken op Instagram"
          },
          "description": {
            "en": "List of ads that you viewed on Instagram.",
            "nl": "Lijst van advertenties die je op Instagram hebt bekeken."
          },
          "headers": {
            "Account name": {"en": "Account name", "nl": "Accountnaam"},
            "Name": {"en": "Name", "nl": "Naam"},
            "URL": {"en": "URL", "nl": "URL"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("impressions_history_ads_seen", [])  # pyright: ignore
        else:
            items = []

        for item in items:  # pyright: ignore
            owner_name, owner_username, url = _extract_owner_details(item.get("label_values", []))
            datapoints.append((
                owner_username or owner_name,
                owner_name,
                url,
                eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Account name", "Name", "URL", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def profile_searches_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "profile_searches.json",
) -> pd.DataFrame:
    """Extract the list of profile searches into a DataFrame.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"profile_searches.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Timestamp``, ``Name``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one profile search performed by the participant on Instagram, recording what was searched and when.",
          "source_file": "profile_searches.json",
          "columns": {
            "Name": "Username or display name that was searched for.",
            "Timestamp": "ISO 8601 timestamp of when the search was performed."
          }
        }

    Table config::

        {
          "id": "instagram_profile_searches",
          "title": {
            "en": "Your Instagram profile searches",
            "nl": "Je Instagram-profielzoekopdrachten"
          },
          "description": {
            "en": "List of profiles you have searched for on Instagram.",
            "nl": "Lijst van profielen die je op Instagram hebt gezocht."
          },
          "headers": {
            "Name": {"en": "Name", "nl": "Naam"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = data["searches_user"]  # pyright: ignore
        for item in items:
            d = eh.dict_denester(item)
            datapoints.append((
                eh.epoch_to_iso(eh.find_item(d, "timestamp"), errors=errors),
                eh.fix_latin1_string(eh.find_item(d, "title") or eh.find_item(d, "value")),
            ))
        out = pd.DataFrame(datapoints, columns=["Timestamp", "Name"])  # pyright: ignore
        out = _sort_by_date(out, "Timestamp")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def threads_viewed_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "threads_viewed.json",
) -> pd.DataFrame:
    """Extract the list of viewed Threads posts into a DataFrame.

    Handles both the older ``string_map_data`` format (dict root keyed by
    ``"text_post_app_text_post_app_posts_seen"``) and the newer
    ``label_values`` list-at-root format.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"threads_viewed.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Author``, ``URL``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one post on Threads (Meta's text-based social network linked to Instagram) that the participant viewed, including the author and timing.",
          "source_file": "threads_viewed.json",
          "columns": {
            "Author": "Username or display name of the account that published the viewed Threads post.",
            "URL": "Direct URL to the viewed Threads post.",
            "Date": "ISO 8601 timestamp of when the post was viewed."
          }
        }

    Table config::

        {
          "id": "instagram_threads_viewed",
          "title": {"en": "Threads viewed", "nl": "Threads bekeken"},
          "description": {
            "en": "List of Threads posts you viewed.",
            "nl": "Lijst van Threads-berichten die je hebt bekeken."
          },
          "headers": {
            "Author": {"en": "Author", "nl": "Auteur"},
            "URL": {"en": "URL", "nl": "URL"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            items = data["text_post_app_text_post_app_posts_seen"]  # pyright: ignore
            for item in items:
                string_map_data = item.get("string_map_data", {})
                author = _first_present(string_map_data, ["Author", "Auteur"])
                time = _first_present(string_map_data, ["Time", "Tijd"])
                url = _first_present(string_map_data, ["URL"])
                datapoints.append((
                    eh.fix_latin1_string(str(author.get("value", ""))),
                    url.get("href", ""),
                    eh.epoch_to_iso(time.get("timestamp", ""), errors=errors),
                ))
        else:
            for item in data:  # pyright: ignore
                owner_name, owner_username, url = _extract_owner_details(item.get("label_values", []))
                datapoints.append((
                    owner_username or owner_name,
                    url,
                    eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Author", "URL", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def ads_clicked_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "ads_clicked.json",
) -> pd.DataFrame:
    """Extract the list of clicked ads into a DataFrame.

    Reads the older format keyed by ``"impressions_history_ads_clicked"``
    where each entry has a title and a timestamp in ``string_list_data``.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"ads_clicked.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Value``, ``URL``, ``Date``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one advertisement the participant clicked on Instagram.",
          "source_file": "ads_clicked.json",
          "columns": {
            "Value": "Concatenated values from the ad metadata.",
            "URL": "URL of the clicked advertisement.",
            "Date": "ISO 8601 timestamp of when the ad was clicked."
          }
        }

    Table config::

        {
          "id": "instagram_ads_clicked",
          "title": {
            "en": "Ads clicked on Instagram",
            "nl": "Advertenties aangeklikt op Instagram"
          },
          "description": {
            "en": "List of ads you clicked on Instagram.",
            "nl": "Lijst van advertenties die je op Instagram hebt aangeklikt."
          },
          "headers": {
            "Value": {"en": "Value", "nl": "Waarde"},
            "URL": {"en": "URL", "nl": "URL"},
            "Date": {"en": "Date", "nl": "Datum en tijd"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        items = data if isinstance(data, list) else data.get("impressions_history_ads_clicked", [])  # pyright: ignore
        for item in items:
            d = eh.dict_denester(item)
            value = " ".join(
                eh.fix_latin1_string(str(v)) for v in eh.find_items(d, "value") if v
            )
            href = eh.find_item(d, "href")
            datapoints.append((
                value,
                href,
                eh.epoch_to_iso(item.get("timestamp", ""), errors=errors),
            ))

        out = pd.DataFrame(datapoints, columns=["Value", "URL", "Date"])  # pyright: ignore
        out = _sort_by_date(out, "Date")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def posts_published_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename_pattern: str = r"(^|/)posts(?:_\d+)?\.json$",
) -> pd.DataFrame:
    """Extract published posts across multiple matching files into a DataFrame.

    Reads files matching ``posts_1.json``, ``posts_2.json``, etc.  Each entry
    contains a title and a ``creation_timestamp``.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename_pattern:
        Regular expression matched against archive member paths.  Defaults to
        a pattern that matches ``posts.json``, ``posts_1.json``, etc.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Timestamp``.
        Empty DataFrame when no matching files are found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one post published by the participant on Instagram.",
          "source_file": "posts_*.json",
          "columns": {
            "Title": "Caption or title text of the post.",
            "Timestamp": "ISO 8601 timestamp of when the post was created."
          }
        }

    Table config::

        {
          "id": "instagram_posts_published",
          "title": {
            "en": "Posts you published on Instagram",
            "nl": "Berichten die je op Instagram hebt geplaatst"
          },
          "description": {
            "en": "List of posts you have published on Instagram.",
            "nl": "Lijst van berichten die je op Instagram hebt geplaatst."
          },
          "headers": {
            "Title": {"en": "Title", "nl": "Titel"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    datapoints = []

    try:
        results = reader.json_all(filename_pattern)
        if not results:
            return pd.DataFrame()

        for result in results:
            data = result.data
            # Posts can be a list at root or nested under a key
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
            else:
                items = []

            for item in items:  # pyright: ignore
                dd = eh.dict_denester(item)
                datapoints.append((
                    eh.fix_latin1_string(eh.find_item(dd, "title")),
                    eh.epoch_to_iso(eh.find_item(dd, "creation_timestamp"), errors=errors),
                ))

        out = pd.DataFrame(datapoints, columns=["Title", "Timestamp"])  # pyright: ignore
        out = _sort_by_date(out, "Timestamp")

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


# ---------------------------------------------------------------------------
# RECREATED FROM algosoc-dd-old — NEEDS MANUAL VERIFICATION
# Source: algosoc-dd-old/src/framework/processing/py/port/instagram.py parse_subscription_for_no_ads()
# ---------------------------------------------------------------------------
def subscription_for_no_ads_to_df(
    reader: ZipArchiveReader,
    errors: Counter,
    *,
    filename: str = "subscription_for_no_ads.json",
) -> pd.DataFrame:
    """Extract ad-free subscription status into a DataFrame.

    Reads the ``label_values`` structure from the subscription file.

    Parameters
    ----------
    reader:
        Archive reader used to load JSON files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    filename:
        Path inside the zip archive to read.  Defaults to
        ``"subscription_for_no_ads.json"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Label``, ``Value``.
        Empty DataFrame when the file is absent or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents a field from the participant's ad-free subscription status on Instagram.",
          "source_file": "subscription_for_no_ads.json",
          "columns": {
            "Label": "Description label for the subscription field.",
            "Value": "Value of the subscription field."
          }
        }

    Table config::

        {
          "id": "instagram_subscription_for_no_ads",
          "title": {
            "en": "Ad-free subscription status",
            "nl": "Status advertentievrij abonnement"
          },
          "description": {
            "en": "Your ad-free subscription status on Instagram.",
            "nl": "Je status van het advertentievrije abonnement op Instagram."
          },
          "headers": {
            "Label": {"en": "Label", "nl": "Label"},
            "Value": {"en": "Value", "nl": "Waarde"}
          }
        }
    """
    result = reader.json(filename)
    if not result.found:
        return pd.DataFrame()
    data = result.data

    out = pd.DataFrame()
    datapoints = []

    try:
        if isinstance(data, dict):
            label_values = data.get("label_values", [])
        elif isinstance(data, list):
            label_values = data
        else:
            label_values = []

        for item in label_values:
            datapoints.append((
                item.get("label", ""),
                item.get("value", ""),
            ))

        out = pd.DataFrame(datapoints, columns=["Label", "Value"])  # pyright: ignore

    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


# ---------------------------------------------------------------------------
# Commented out: not in algosoc-2026 extraction list
# ---------------------------------------------------------------------------

# def followers_to_df(
#     reader: ZipArchiveReader,
#     errors: Counter,
#     *,
#     filename: str = "followers_1.json",
# ) -> pd.DataFrame:
#     """Extract the list of followers into a DataFrame.
#
#     Handles both the newer bare top-level list format and the older format
#     where entries are wrapped under a ``"relationships_followers"`` key.
#
#     Parameters
#     ----------
#     reader:
#         Archive reader used to load JSON files from the DDP zip.
#     errors:
#         Mutable counter that accumulates error type counts encountered during
#         extraction.  Updated in-place.
#     filename:
#         Path inside the zip archive to read.  Defaults to
#         ``"followers_1.json"``.
#
#     Returns
#     -------
#     pd.DataFrame
#         Columns: ``Account``, ``URL``, ``Date``.
#         Empty DataFrame when the file is absent or parsing fails.
#
#     Table documentation::
#
#         {
#           "summary": "Each row represents one account that follows the participant on Instagram, including when they started following.",
#           "source_file": "followers_1.json",
#           "columns": {
#             "Account": "Username or display name of the follower account.",
#             "URL": "Direct URL to the follower's Instagram profile.",
#             "Date": "ISO 8601 timestamp of when the account started following the participant."
#           }
#         }
#
#     Table config::
#
#         {
#           "id": "instagram_followers",
#           "title": {"en": "Your Instagram followers", "nl": "Je Instagram-volgers"},
#           "description": {
#             "en": "List of accounts that follow you on Instagram.",
#             "nl": "Lijst van accounts die jou op Instagram volgen."
#           },
#           "headers": {
#             "Account": {"en": "Account", "nl": "Account"},
#             "URL": {"en": "URL", "nl": "URL"},
#             "Date": {"en": "Date", "nl": "Datum en tijd"}
#           }
#         }
#     """
#     result = reader.json(filename)
#     if not result.found:
#         return pd.DataFrame()
#     data = result.data
#
#     out = pd.DataFrame()
#     datapoints = []
#
#     try:
#         if isinstance(data, dict):
#             items = data.get("relationships_followers", [])
#         else:
#             items = data  # pyright: ignore
#
#         for item in items:
#             d = eh.dict_denester(item)
#             datapoints.append((
#                 eh.fix_latin1_string(eh.find_item(d, "value") or eh.find_item(d, "title")),
#                 eh.find_item(d, "href"),
#                 eh.epoch_to_iso(eh.find_item(d, "timestamp"), errors=errors),
#             ))
#         out = pd.DataFrame(datapoints, columns=["Account", "URL", "Date"])  # pyright: ignore
#         out = _sort_by_date(out, "Date")
#
#     except Exception as e:
#         logger.error("Exception caught: %s", e)
#         errors[type(e).__name__] += 1
#
#     return out


# ---------------------------------------------------------------------------
# Extractor registry & platform info
# ---------------------------------------------------------------------------

#: Mapping from the string names used in port_config.json to actual extractor functions.
EXTRACTOR_REGISTRY: dict[str, Callable[..., pd.DataFrame]] = {
    "following_to_df": following_to_df,
    "posts_viewed_to_df": posts_viewed_to_df,
    "videos_watched_to_df": videos_watched_to_df,
    "post_comments_to_df": post_comments_to_df,
    "liked_comments_to_df": liked_comments_to_df,
    "liked_posts_to_df": liked_posts_to_df,
    "story_likes_to_df": story_likes_to_df,
    "saved_posts_to_df": saved_posts_to_df,
    "word_or_phrase_searches_to_df": word_or_phrase_searches_to_df,
    "stories_published_to_df": stories_published_to_df,
    "advertisers_using_activity_to_df": advertisers_using_activity_to_df,
    "ads_viewed_to_df": ads_viewed_to_df,
    "profile_searches_to_df": profile_searches_to_df,
    "threads_viewed_to_df": threads_viewed_to_df,
    "ads_clicked_to_df": ads_clicked_to_df,
    "posts_published_to_df": posts_published_to_df,
    "subscription_for_no_ads_to_df": subscription_for_no_ads_to_df,
    # "followers_to_df": followers_to_df,  # not in algosoc-2026 list
}


# ---------------------------------------------------------------------------
# Main extraction & flow
# ---------------------------------------------------------------------------

def extraction(
    instagram_zip: str,
    validation,
) -> ExtractionResult:
    """Extract data from an Instagram DDP zip and return consent-form tables.

    Parameters
    ----------
    instagram_zip:
        Path to the Instagram DDP zip archive on disk.
    validation:
        Validation result object whose ``archive_members`` attribute is passed
        to ``ZipArchiveReader``.
    """
    config = load_port_config(EXTRACTOR_REGISTRY, "instagram")
    errors: Counter = Counter()
    reader = ZipArchiveReader(instagram_zip, validation.archive_members, errors)
    return run_extraction(reader, errors, config)


class InstagramFlow(FlowBuilder):
    """Flow implementation for the Instagram data donation study.

    Parameters
    ----------
    session_id:
        Unique identifier for the current participant session.
    """

    def __init__(self, session_id: str):
        super().__init__(session_id, "Instagram")

    def validate_file(self, file):
        return validate.validate_zip(DDP_CATEGORIES, file)

    def extract_data(self, file_value, validation):
        return extraction(file_value, validation)


def process(session_id):
    flow = InstagramFlow(session_id)
    return flow.start_flow()
