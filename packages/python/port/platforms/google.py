"""
Google

This module provides the flow of a data donation study on the Google Takeout archive.
YouTube is one source within that archive; other sources are added by extending
``TAKEOUT_PATHS`` and registering an extractor per table.

Assumptions:
It handles DDPs in the English, Dutch, German, Spanish, Arabic, Turkish and Chinese language.
Takeout asks for the export format per source, so the watch and search histories are
read as JSON or as HTML depending on what the archive holds; subscriptions and comments
are always CSV. The archive is recognized and its locale determined by ``validate_ddp``
in this module, not by the shared filename matching of ``validate.validate_zip``.

Configuration
-------------
The ``extraction`` function is driven by ``port_config.json``.  Generate one with::

    pnpm generate-config google

Each extractor function carries its own table config in a ``Table config::``
JSON block inside its docstring.  The generator reads those blocks and
assembles the JSON file.

Platform info::

    {
        "name": "Google",
        "filetypes": ["json", "html", "csv"],
        "languages": ["en", "nl", "de", "es", "ar", "tr", "zh"],
        "description": "Handles the Google Takeout archive in English, Dutch, German, Arabic, Turkish and Chinese. Currently extracts the YouTube sources of the archive: watch history, search history, subscriptions and comments. Both JSON and HTML formats are supported for watch and search histories, and may differ per source within one archive. Comments and subscriptions are always extracted in CSV format. Tested for Dutch DDPs with both JSON and HTML formats. DDPs in the other languages have not yet been tested, and the Arabic, Turkish and Chinese paths are unverified translations. If you find anything wrong with this script, report to datadonation@uu.nl and it will be fixed!",
        "time_last_tested": "22-06-2026"
    }
"""
import json
import logging
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
import io
import re
from dateutil import parser
from lxml import etree

import pandas as pd

from port.helpers.extraction_helpers import ZipArchiveReader
import port.helpers.extraction_helpers as eh
from port.helpers.flow_builder import FlowBuilder
from port.helpers.validate import BaseValidation
from port.api.d3i_props import ExtractionResult
from port.helpers.table_extractor import (
    load_port_config,
    run_extraction,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Localized archive paths
# ---------------------------------------------------------------------------

#: Locations of the DDP files per locale, keyed by ``source.role``, without extension.
#:
#: Google Takeout translates both folder and file names to the main language of the
#: account, and one archive holds many sources whose filenames collide across folders
#: (every ``My Activity`` product exports a ``MyActivity`` file). Entries are therefore
#: paths, not filenames, and are matched against the end of the archive member paths:
#: ``Verlauf/Wiedergabeverlauf`` resolves ``Takeout/YouTube und YouTube Music/Verlauf/
#: Wiedergabeverlauf.html`` and cannot be confused with a file of the same name in
#: another folder. Only as many trailing segments as are needed to be unambiguous.
#:
#: Each entry lists one or more variants, tried in order. Variants absorb uncertainty:
#: put the exact path first and a shorter, more forgiving one after it. Never fall back
#: to a bare filename that occurs in more than one folder of the archive — that lookup
#: is ambiguous and resolves to nothing.
#:
#: Adding a DDP locale is one block; nothing outside this needs to change to extract the
#: files.
#:
#: Most entries come from real DDPs; the remaining ones are derived from the older labels
#: Google uses/used for these pages in that language. They are kept side by side, where 
#: the extraction will be performed to the first item that matches (``Anzeigen``/``Ads``,
#: ``MyActivity``/``MeineAktivitäten``). Chinese covers Simplified only.
TAKEOUT_PATHS: dict[str, dict[str, list[str]]] = {
    "en": {
        "youtube.watch_history": ["YouTube and YouTube Music/history/watch-history", "My Activity/YouTube/MyActivity"],
        "youtube.search_history": ["YouTube and YouTube Music/history/search-history", "My Activity/YouTube/MyActivity"],
        "youtube.subscriptions": ["YouTube and YouTube Music/subscriptions/subscriptions"],
        "youtube.comments": ["YouTube and YouTube Music/comments/comments"],
        "search.search_history": ["My Activity/Search/MyActivity"],
        "chrome.history": ["Chrome/History", "My Activity/Chrome/MyActivity"],
        "video_search.history": ["My Activity/Video Search/MyActivity"],
        "ads.history": ["My Activity/Ads/MyActivity"],
        "discover.history": ["My Activity/Discover/MyActivity"],
        "google_news.history": ["My Activity/Google News/MyActivity"],
        "news.history": ["My Activity/News/MyActivity"],
    },
    "nl": {
        "youtube.watch_history": ["YouTube en YouTube Music/geschiedenis/kijkgeschiedenis", "Mijn activiteit/YouTube/MyActivity"],
        "youtube.search_history": ["YouTube en YouTube Music/geschiedenis/zoekgeschiedenis", "Mijn activiteit/YouTube/MyActivity"],
        "youtube.subscriptions": ["YouTube en YouTube Music/abonnementen/abonnementen"],
        "youtube.comments": ["YouTube en YouTube Music/reacties/reacties"],
        "search.search_history": ["Mijn activiteit/Zoeken/MyActivity"],
        "chrome.history": ["Chrome/Geschiedenis", "Mijn activiteit/Chrome/MyActivity"],
        "video_search.history": ["Mijn activiteit/Video_s zoeken/MyActivity"],
        "ads.history": ["Mijn activiteit/Advertenties/MyActivity"],
        "discover.history": ["Mijn activiteit/Discover/MyActivity"],
        "google_news.history": ["Mijn activiteit/Google Nieuws/MyActivity"],
        "news.history": ["Mijn activiteit/Nieuws/MyActivity"],
    },
    "de": {
        "youtube.watch_history": ["YouTube und YouTube Music/Verlauf/Wiedergabeverlauf", "Meine Aktivitäten/YouTube/MyActivity", "Meine Aktivitäten/YouTube/MeineAktivitäten"],
        "youtube.search_history": ["YouTube und YouTube Music/Verlauf/Suchverlauf", "Meine Aktivitäten/YouTube/MyActivity", "Meine Aktivitäten/YouTube/MeineAktivitäten"],
        "youtube.subscriptions": ["YouTube und YouTube Music/Abos/Abos"],
        "youtube.comments": ["YouTube und YouTube Music/Kommentare/Kommentare"],
        "search.search_history": ["Meine Aktivitäten/Suche/MyActivity", "Meine Aktivitäten/Google Suche/MyActivity", "Meine Aktivitäten/Google Suche/MeineAktivitäten"],
        "chrome.history": ["Chrome/Verlauf", "Meine Aktivitäten/Chrome/MyActivity", "Meine Aktivitäten/Chrome/MeineAktivitäten"],
        "video_search.history": ["Meine Aktivitäten/Videosuchen/MyActivity", "Meine Aktivitäten/Videosuche/MyActivity", "Meine Aktivitäten/Videosuche/MeineAktivitäten"],
        "ads.history": ["Meine Aktivitäten/Anzeigen/MyActivity", "Meine Aktivitäten/Anzeigen/MeineAktivitäten"],
        "discover.history": ["Meine Aktivitäten/Entdecken/MyActivity", "Meine Aktivitäten/Entdecken/MeineAktivitäten"],
        "google_news.history": ["Meine Aktivitäten/Google News/MyActivity", "Meine Aktivitäten/Google News/MeineAktivitäten"],
        "news.history": ["Meine Aktivitäten/Nachrichten/MyActivity"],
    },
    "es": {
        "youtube.watch_history": ["YouTube y YouTube Music/historial/historial de reproducciones", "YouTube y YouTube Music/historial/historial-de-reproducciones", "Mi actividad/YouTube/MyActivity"],
        "youtube.search_history": ["YouTube y YouTube Music/historial/historial de búsquedas", "YouTube y YouTube Music/historial/historial-de-búsquedas", "Mi actividad/YouTube/MyActivity"],
        "youtube.subscriptions": ["YouTube y YouTube Music/suscripciones/suscripciones"],
        "youtube.comments": ["YouTube y YouTube Music/comentarios/comentarios"],
        "search.search_history": ["Mi actividad/Búsqueda/MyActivity", "Mi actividad/Búsqueda/MiActividad"],
        "chrome.history": ["Chrome/Historial", "Mi actividad/Chrome/MyActivity", "Mi actividad/Chrome/MiActividad"],
        "video_search.history": ["Mi actividad/Búsqueda de videos/MyActivity", "Mi actividad/Búsqueda de videos/MiActividad"],
        "ads.history": ["Mi actividad/Publicidad/MyActivity", "Mi actividad/Publicidad/MiActividad"],
        "discover.history": ["Mi actividad/Discover/MyActivity", "Mi actividad/Discover/MiActividad", "Mi actividad/Descubrir/MyActivity", "Mi actividad/Descubrir/MiActividad"],
        "google_news.history": ["Mi actividad/Google News/MyActivity", "Mi actividad/Google News/MiActividad", "Mi actividad/Google Noticias/MyActivity", "Mi actividad/Google Noticias/MiActividad"],
        "news.history": ["Mi actividad/Noticias/MyActivity", "Mi actividad/Noticias/MiActividad"],
    },
    "ar": {
        "youtube.watch_history": ["YouTube و YouTube Music/سجل/سجل المشاهدة", "YouTube وYouTube Music/السجلّ/سجل المشاهدة", "أنشطتي/YouTube/MyActivity", "نشاطي/YouTube/MyActivity", "نشاطي/YouTube/نشاطي"],
        "youtube.search_history": ["YouTube و YouTube Music/سجل/سجل البحث", "YouTube وYouTube Music/السجلّ/سجلّ البحث", "أنشطتي/YouTube/MyActivity", "نشاطي/YouTube/MyActivity", "نشاطي/YouTube/نشاطي"],
        "youtube.subscriptions": ["YouTube و YouTube Music/اشتراكات/اشتراكات", "YouTube وYouTube Music/اشتراكات/اشتراكات"],
        "youtube.comments": ["YouTube و YouTube Music/تعليقات/تعليقات", "YouTube وYouTube Music/تعليقات/تعليقات"],
        "search.search_history": ["أنشطتي/بحث/MyActivity", "نشاطي/البحث/MyActivity", "نشاطي/البحث/نشاطي"],
        "chrome.history": ["Chrome/السجل", "Chrome/السجلّ", "أنشطتي/Chrome/MyActivity", "نشاطي/Chrome/MyActivity", "نشاطي/Chrome/نشاطي"],
        "video_search.history": ["أنشطتي/البحث عن الفيديو/MyActivity", "نشاطي/بحث الفيديو/MyActivity", "نشاطي/بحث الفيديو/نشاطي"],
        "ads.history": ["أنشطتي/الإعلانات/MyActivity", "نشاطي/الإعلانات/MyActivity", "نشاطي/الإعلانات/نشاطي"],
        "discover.history": ["أنشطتي/اكتشف/MyActivity", "نشاطي/اكتشف/MyActivity", "نشاطي/اكتشف/نشاطي"],
        "google_news.history": ["أنشطتي/أخبار جوجل/MyActivity", "نشاطي/أخبار Google/MyActivity", "نشاطي/أخبار Google/نشاطي"],
        "news.history": ["أنشطتي/الأخبار/MyActivity"],
    },
    "tr": {
        "youtube.watch_history": ["YouTube ve YouTube Music/geçmiş/İzleme geçmişi", "YouTube ve YouTube Music/geçmiş/izleme geçmişi", "Etkinliğim/YouTube/MyActivity", "Etkinliğim/YouTube/Etkinliğim"],
        "youtube.search_history": ["YouTube ve YouTube Music/geçmiş/Arama geçmişi", "YouTube ve YouTube Music/geçmiş/arama geçmişi", "Etkinliğim/YouTube/MyActivity", "Etkinliğim/YouTube/Etkinliğim"],
        "youtube.subscriptions": ["YouTube ve YouTube Music/Abonelikler/Abonelikler"],
        "youtube.comments": ["YouTube ve YouTube Music/Yorumlar/Yorumlar"],
        "search.search_history": ["Etkinliğim/Arama/MyActivity", "Etkinliğim/Arama/Etkinliğim"],
        "chrome.history": ["Chrome/Geçmiş", "Chrome/Tarih", "Etkinliğim/Chrome/MyActivity", "Etkinliğim/Chrome/Etkinliğim"],
        "video_search.history": ["Etkinliğim/Video Arama/MyActivity", "Etkinliğim/Video Arama/Etkinliğim"],
        "ads.history": ["Etkinliğim/Reklamlar/MyActivity", "Etkinliğim/Reklamlar/Etkinliğim"],
        "discover.history": ["Etkinliğim/Keşfet/MyActivity", "Etkinliğim/Keşfet/Etkinliğim"],
        "google_news.history": ["Etkinliğim/Google Haberler/MyActivity", "Etkinliğim/Google Haberler/Etkinliğim"],
        "news.history": ["Etkinliğim/Haberler/MyActivity"],
    },
    "zh": {
        "youtube.watch_history": ["YouTube 和 YouTube Music/记录/观看记录", "YouTube 和 YouTube Music/历史记录/观看记录", "我的活动/YouTube/MyActivity", "我的活动/YouTube/我的活动记录"],
        "youtube.search_history": ["YouTube 和 YouTube Music/记录/搜索记录", "YouTube 和 YouTube Music/历史记录/搜索记录", "我的活动/YouTube/MyActivity", "我的活动/YouTube/我的活动记录"],
        "youtube.subscriptions": ["YouTube 和 YouTube Music/订阅内容/订阅内容"],
        "youtube.comments": ["YouTube 和 YouTube Music/评论/评论"],
        "search.search_history": ["我的活动/搜索/MyActivity", "我的活动/Search/MyActivity", "我的活动/Search/我的活动记录"],
        "chrome.history": ["Chrome/历史记录", "我的活动/Chrome/MyActivity", "我的活动/Chrome/我的活动记录"],
        "video_search.history": ["我的活动/视频搜索/MyActivity", "我的活动/Video Search/MyActivity", "我的活动/Video Search/我的活动记录"],
        "ads.history": ["我的活动/广告/MyActivity", "我的活动/Ads/MyActivity", "我的活动/Ads/我的活动记录"],
        "discover.history": ["我的活动/发现/MyActivity", "我的活动/发现/我的活动记录"],
        "google_news.history": ["我的活动/Google 新闻/MyActivity", "我的活动/Google News/MyActivity", "我的活动/Google News/我的活动记录"],
        "news.history": ["我的活动/新闻/MyActivity"],
    },
}

#: File formats each source can be exported in, tried in this order. Takeout asks for
#: the format per source, so one archive can hold the watch history as JSON and the
#: Chrome history as HTML — the format belongs to the file that is there, not to the DDP.
KEY_FORMATS: dict[str, list[str]] = {
    "youtube.watch_history": ["json", "html"],
    "youtube.search_history": ["json", "html"],
    "youtube.subscriptions": ["csv"],
    "youtube.comments": ["csv"],
    "search.search_history": ["json", "html"],
    "chrome.history": ["json", "html"],
    "video_search.history": ["json", "html"],
    "ads.history": ["json", "html"],
    "discover.history": ["json", "html"],
    "google_news.history": ["json", "html"],
    "news.history": ["json", "html"],
}

@dataclass
class GoogleValidation(BaseValidation):
    """What validating a Google Takeout archive established: whether it was recognized
    (status code 0) or not (1), which locale it is in, and the member paths extraction
    reads from. This platform defines no ``DDP_CATEGORIES``: a category pairs one file
    format with a set of filenames, and a Takeout archive has neither — see
    ``validate_ddp``."""

    archive_members: list[str] = field(default_factory=list)
    locale: str = ""



# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _path_suffixes(archive_members: list[str]) -> set[str]:
    """Returns every trailing path fragment of the archive members, without extension.

    Mirrors how ``ZipArchiveReader.resolve_member`` matches a lookup against a member:
    on a folder boundary, from the right. ``a/b/c.json`` yields ``a/b/c``, ``b/c`` and
    ``c``, so a path from ``TAKEOUT_PATHS`` is present exactly when it is in this set."""

    suffixes = set()
    for member in archive_members:
        segments = member.rsplit(".", 1)[0].split("/")
        for start in range(len(segments)):
            suffixes.add("/".join(segments[start:]))
    return suffixes


def _detect_locale(archive_members: list[str]) -> tuple[str, int]:
    """Returns the locale whose paths best cover the archive, and how many of its
    sources were found.

    Folder-qualified paths decide, and the number of sources found only breaks ties:
    the filename-only variants exist to be forgiving about folders, so letting them
    weigh in equally would drown out the folder evidence. A locale that translates only
    its folder names — leaving every filename in English — is recognized on folders
    alone this way."""

    suffixes = _path_suffixes(archive_members)
    scores = {}
    for locale, keys in TAKEOUT_PATHS.items():
        found = [
            any(path in suffixes for path in paths)
            for paths in keys.values()
        ]
        folders = [
            any(path in suffixes for path in paths if "/" in path)
            for paths in keys.values()
        ]
        scores[locale] = (sum(folders), sum(found))
    best = max(scores, key=lambda locale: scores[locale])

    return best, scores[best][1]


def validate_ddp(archive) -> GoogleValidation:
    """Recognizes a Google Takeout archive and determines its locale.

    Replaces the shared ``validate.validate_zip`` for this platform, which matches bare
    filenames against a DDP category. That does not fit a Takeout archive: it holds many
    sources whose filenames collide across folders, its export format is chosen per
    source rather than for the DDP as a whole, and a locale may translate only its
    folder names. Recognition runs on the member paths instead, which answers all three.

    An archive counts as recognized as soon as one known source is found — the
    participant chooses which sources to export, so any subset is a legitimate DDP."""

    try:
        with zipfile.ZipFile(archive, "r") as zf:
            archive_members = zf.namelist()
    except zipfile.BadZipFile:
        return GoogleValidation(status_code=1)

    locale, sources_found = _detect_locale(archive_members)
    logger.info("Detected DDP locale: %s (%d sources found)", locale, sources_found)

    return GoogleValidation(
        status_code=0 if sources_found else 1,
        archive_members=archive_members,
        locale=locale,
    )


def _read(reader: ZipArchiveReader, key: str, locale: str):
    """Reads the first file present for ``key``, in whichever format it was exported.

    Returns the extension of the file that was found together with the read result, so
    the caller knows how to parse it, or ``(None, None)`` when the archive holds no file
    for this key."""

    readers = {"json": reader.json, "html": reader.raw, "csv": reader.csv}
    for path in TAKEOUT_PATHS.get(locale, {}).get(key, []):
        for extension in KEY_FORMATS[key]:
            result = readers[extension](f"{path}.{extension}")
            if result.found:
                return extension, result
    return None, None


def _parse_activity_html(data: io.BytesIO) -> list[dict]:
    """Reads an activity file in html format and parses it into a list of dictionaries with
    the same shape as the json format: the title of the activity, the url it points to, what
    stands under it and its timestamp.

    Every activity file of the DDP — the YouTube histories as well as the My Activity file
    of any product — is one page of ``outer-cell`` blocks, in which the activity itself
    sits in the ``content-cell`` of body text::

        <div class="content-cell ... mdl-typography--body-1">Watched
            <a href="https://www.youtube.com/watch?v=abc">A video</a><br>
            <a href="https://www.youtube.com/channel/UC1">A channel</a><br>
            15 jun 2026, 20:30:41 CEST
        </div>

    A line between the activity and the timestamp is read by whether it links out. One that
    does is a subtitle — the channel of the video above, which the json writes as
    ``{"name": ..., "url": ...}`` — and one that does not is the ``description`` of the
    activity, such as the "Watched at 11:39 AM" an ad is recorded with. A record carries
    either, both, or neither.

    Selecting those cells by class is what makes one parser enough for every source: the
    activity is read the same way regardless of which product wrote the file, and callers
    select the records that are theirs by url, exactly as they do for the json format.

    The caption cell beside it carries the lists some sources record with an activity —
    the details of a Discover card, say — which ``_parse_activity_caption`` reads onto the
    same record.

    The document is walked as a stream and each cell is dropped once it is read, so peak
    memory stays proportional to one activity rather than to the size of the file — a watch
    history of a heavy user runs to hundreds of megabytes."""

    records = []
    for _, cell in etree.iterparse(data, html=True, tag="div", events=("end",)):
        classes = cell.get("class") or ""
        texts = (
            [text.strip() for text in cell.itertext() if text.strip()]
            if "mdl-typography--body-1" in classes
            else []
        )
        # An activity always carries text, ending in its timestamp. A body cell without
        # any is the empty one the layout puts beside it, right-aligned, and not a record.
        if texts:
            # The activity is the text up to the first line break and the timestamp is the
            # line the cell closes with. What stands in between is told apart by its link:
            # a line that links out is a subtitle, the channel of a video say, and one that
            # does not is the description of the activity.
            lines = _parse_activity_lines(cell)
            middle = lines[1:-1]

            record = {
                "title": lines[0]["text"],
                "titleUrl": _strip_redirect(lines[0]["url"]) if lines[0]["url"] else "",
                "time": _convert_to_iso8601(texts[-1]),
            }
            subtitles = [_subtitle(line) for line in middle if line["url"]]
            if subtitles:
                record["subtitles"] = subtitles
            description = " ".join(line["text"] for line in middle if not line["url"])
            if description:
                record["description"] = description
            records.append(record)
        elif records and "mdl-typography--caption" in classes:
            # The caption follows the activity it belongs to, so it lands on the record
            # that was just read.
            records[-1].update(_parse_activity_caption(cell))

        # Drop every div once it ends — the record it held has been read, and its children
        # ended before it did — so the tree does not grow with the file.
        cell.clear()
        while cell.getprevious() is not None:
            del cell.getparent()[0]

    return records


#: The link that gives away a location, whatever language its section is headed in.
MAPS_LINK = "google.com/maps"


def _close_line(line: dict, section: list) -> dict:
    """Adds the line to the section if it holds anything, and starts an empty one."""

    text = " ".join(part.strip() for part in line["texts"] if part.strip())
    if text or line["url"]:
        section.append({"text": text, "url": line["url"]})
    return {"texts": [], "url": ""}


def _parse_activity_lines(cell) -> list[dict]:
    """Reads a body cell as the lines its line breaks separate, each with the first url it
    links to. A line that holds neither text nor a link is left out, so the break the cell
    tends to close with does not add an empty one."""

    lines: list[dict] = []
    line = {"texts": [cell.text or ""], "url": ""}
    for child in cell:
        if child.tag == "br":
            line = _close_line(line, lines)
        else:
            if child.tag == "a" and not line["url"]:
                line["url"] = child.get("href") or ""
            line["texts"].append("".join(child.itertext()))
        line["texts"].append(child.tail or "")
    _close_line(line, lines)

    return lines


def _subtitle(line: dict) -> dict:
    """Reads a line linking out from under an activity in the shape the json format writes
    it: the name it shows and where it points."""

    return {"name": line["text"], "url": _strip_redirect(line["url"])}


def _parse_activity_caption(cell) -> dict:
    """Reads the lists an activity carries beside it, in the shape the json format writes
    them: ``details`` as ``{"name": ...}``. Returns the list only when it is there, as the
    json does.

    The caption is a run of sections, each headed by a bold label and holding one entry per
    line break::

        <b>Locations:</b><br> At <a href="...maps...">this general area</a> - Based on your
        past activity<br><b>Details:</b><br> Armed forces<br> Business - viewed<br>

    Which section is which is read from where it sits and what it holds, not from the
    labels, which are written in the language of the account: the caption opens with the
    products and closes with why the activity was kept, and in between a section of
    locations links to Maps. What is left is the details.

    Where the participant was is deliberately not extracted, but the locations section is
    still recognized here — telling it apart from the details is what keeps it out of the
    record."""

    sections: list[list[dict]] = [[]]
    line = {"texts": [cell.text or ""], "url": ""}
    for child in cell:
        if child.tag == "b":
            # The label of a section, which the section it opens is recognized without.
            line = _close_line(line, sections[-1])
            sections.append([])
        elif child.tag == "br":
            line = _close_line(line, sections[-1])
        else:
            if child.tag == "a" and not line["url"]:
                line["url"] = child.get("href") or ""
            line["texts"].append(child.text or "")
        line["texts"].append(child.tail or "")
    _close_line(line, sections[-1])

    caption = {}
    filled = [section for section in sections if section]
    for position, section in enumerate(filled):
        if position == 0 or position == len(filled) - 1:
            # A caption opens with the products the activity belongs to and closes with why
            # it was kept, neither of which says anything about the activity itself.
            continue
        if any(MAPS_LINK in line["url"] for line in section):
            # Where the activity was recorded from, which is dropped rather than read.
            continue
        caption["details"] = [{"name": line["text"]} for line in section if line["text"]]

    return caption


def _strip_redirect(url: str) -> str:
    """Returns the destination of a Google redirect url, other urls unchanged. Activities
    that leave Google, such as a visit from the Chrome history, are recorded as one."""

    prefix = "https://www.google.com/url?q="
    return url[len(prefix):] if url.startswith(prefix) else url


def _first_subtitle(item: dict) -> dict:
    """Returns the subtitle an activity stands under, empty when it carries none. A record
    may hold a list of them, but the sources read here name a single one — the channel of a
    video — and only where the account still has it."""

    subtitles = item.get("subtitles") or []
    return next((subtitle for subtitle in subtitles if isinstance(subtitle, dict)), {})


def _join_details(item: dict) -> str:
    """Reads the details an activity carries as one column of text, empty when it carries
    none. Most records have nothing here; the ones that do say how the activity came about,
    such as a video that was watched from an ad.

    A detail that points somewhere is written as its name and that url behind a colon. The
    json format keeps the two apart, in a ``name`` and a ``url``, where the html writes them
    as the one line ``Tried to open in app: https://...`` — so joining them here is what
    makes both formats produce the same column."""

    texts = []
    for detail in item.get("details") or []:
        if not isinstance(detail, dict):
            continue
        texts.append(": ".join(
            part for part in (detail.get("name", ""), detail.get("url", "")) if part
        ))

    return ", ".join(texts)


#: Months as Takeout abbreviates them in the languages it writes in Latin script, by the
#: first three letters, lowercased. Dates in another script are left to ``dateutil``.
MONTHS = {
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

#: ``15 jun 2026, 20:30:41 CEST`` — how most locales write an activity timestamp, some of
#: them with an ordinal dot after the day and after the month, as ``17. Aug. 2026`` is.
DAY_FIRST = re.compile(r"^(\d{1,2})\.? ([^\s,]+),? (\d{4}),? (\d{1,2}):(\d{2}):(\d{2})")

#: ``Aug 17, 2026, 1:14:48 PM CEST`` — how the English locale writes one.
MONTH_FIRST = re.compile(r"^([^\s,\d]+) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}):(\d{2})(?:\s*([AaPp])\.?[Mm])?")


def _convert_to_iso8601(timestamp):
    """Converts a time string extracted from the HTML DDP (e.g. 15 jun 2026, 20:30:41 CEST) to
    ISO8601 format, ignoring timezone abbreviations and translating month abbreviations.

    An activity file holds one timestamp per record, hundreds of thousands of them for a
    heavy user, and reading a date in any format a participant might have is expensive.
    The two formats Takeout actually writes are read directly here, which is some twenty
    times faster; anything else — another script, another separator — falls through to
    ``dateutil``, which reads what it can and leaves the rest as it found it."""

    match = MONTH_FIRST.match(timestamp)
    if match:
        month, day, year, hour, minute, second, meridiem = match.groups()
    else:
        match = DAY_FIRST.match(timestamp)
        if match:
            day, month, year, hour, minute, second = match.groups()
            meridiem = None
        else:
            return _convert_with_dateutil(timestamp)

    number = MONTHS.get(month[:3].lower())
    if number is None:
        return _convert_with_dateutil(timestamp)

    hour = int(hour)
    if meridiem:
        # A 12-hour clock counts noon as 12 PM and midnight as 12 AM.
        hour = hour % 12 + (12 if meridiem.lower() == "p" else 0)

    try:
        return datetime(int(year), number, int(day), hour, int(minute), int(second)).isoformat()
    except ValueError:
        return _convert_with_dateutil(timestamp)


def _convert_usec_to_iso8601(timestamp):
    """Converts a timestamp in microseconds since the epoch, as the Chrome history writes
    them (e.g. 1787225185379660), to ISO 8601. ``eh.epoch_to_iso`` cannot read these
    numbers because it takes them for seconds and a microsecond count overflows the year.

    The time is read in UTC and written without the offset, in the shape the activity
    files record their local time in, so that one column holds one format. Sub-second
    precision is dropped for the same reason. A timestamp that is not a number is
    returned unchanged."""

    try:
        seconds = int(timestamp) // 1_000_000
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None).isoformat()
    except (OverflowError, OSError, TypeError, ValueError):
        return timestamp


def _convert_with_dateutil(timestamp):
    """Converts a timestamp of a shape ``_convert_to_iso8601`` does not read itself,
    returning it unchanged when it cannot be read at all."""
    try:
        parts = timestamp.split(' ')

        # Ignore timezone abbreviation at the end as this is not included in json either
        # and cannot be automatically parsed
        if ':' not in parts[-1]:
            parts.pop()

        # Translate month abbreviations to English
        nl_month_translations = {
            'mrt': 'mar',
            'mei': 'may',
            'okt': 'oct',
            }
        for i in range(len(parts)):
            if parts[i].lower() in nl_month_translations:
                parts[i] = nl_month_translations[parts[i].lower()]

        dt = parser.parse(' '.join(parts))
        return dt.isoformat()
    except (ValueError, TypeError) as e:
        return timestamp


EXPLICIT_KEYWORDS = [
      "outlook.live.com", "mail.google.com/mail", "mail.kpnmail.nl",
      "outlook.office365.com", "porn",
      "xhamster", 
      "erotic", "kinky", "fetish", "jerk off",
     "camgirl",  "hentai", "gangbang",  "femdom",
     "onlyfans", "fansly",  "threesome", "adult video", "adult movie",
     "adult escort", "prostitute", "escort service", "sex worker",
     "stripper", "strip club", "exotic dancer",
     "not safe for work", 
     
     "xvideos.com", "xnxx.com", "redtube.com", "xhamster.com", "deloris.ai",
      "tube8.com", "spankbang.com", "youjizz.com", "fapdu.com", "9xbuddy.xyz",
     "brazzers.com", "mofos.com", "naughtyamerica.com", "bangbros.com", 
      "clips4sale.com", "camsoda.com", "chaturbate.com", "casualdating1.com",
     "myfreecams.com", "livejasmin.com", "streamate.com", "bongacams.com", "deepmode.ai",
     "onlyfans.com", "adultfriendfinder.com", "sextube.com", "beeg.com", "akg01.com",
      "xtube.com", "slutload.com", "tnaflix.com", 
     "javhd.com", "realitykings.com", "metart.com", "eroprofile.com", "nudelive.com",
     "fantasti.cc", "hclips.com", "ashemaletube.com", 
     "playvid.com", "4tube.com", "javfinder.com",  "sex.com", "hentaigasm.com",
     "hentaistream.com", "adulttime.com", "wicked.com", "dogfartnetwork.com", "stripchat.com",
     "keezmovies.com", "xempire.com", 
     "thumzilla.com", "madthumbs.com", "drtuber.com", 
     "fapdu.com", "freeones.com", "twistys.com", "3movs.com",  "candy.ai",
   "recurbate.com", "tubegalore.com",
    "lobstertube.com", "nuvid.com", "sexvid.xxx",
     "xhamsterlive.com", "playboy.tv", "cams.com", "badoinkvr.com", 
     "vrcosplayx.com", "metartx.com", "hegre-art.com", "joymii.com", 
     "spankwire.com", "tingo.ai",
       "boy18tube.com",	
       "fapnfuck.com",
       "fetishbank.net",
       "gonzoxxxmovies.com",
       "ixxx.com",
       "webcamsex.nl",
     
     "jizzbunker.com", "eporner.com", "cam4.com", "sexier.com", "adultempire.com", "basedlabs.ai",
     "joysporn.com", "slutroulette.com", "bigxvideos.com", "hotmovs.com", 

     "siswet", "taylor sands", "naughty celeste",
     "natasha nice", "angela white", "joey mills", "austin young",
     "legrand wolf", "viktor rom", "malik delgaty", "daisy taylor",
     "esluna love", "romy indy", "zara whites", "yasie lee", "tracy oba",
     "nathalie kitten", "sebriena star", "tanya de vries", "logan moore",
     "abella danger", "adriana chechik", "aimi yoshikawa", "amarna miller",
     "angela white", "anna polina", "anri okita", "arabelle raphael",
     "honey_sunshine", "ariana marie", "august ames", "ayu sakurai",
     "belle knox", "bonnie rotten", "brett rossi", "carter cruise",
     "casey calvert", "chanel preston", "charlotte sartre",
     "iori kogawa", "jia lissa", "jessie andrews", "jessie rogers", "lana rhoades",
     "lasirena69", "lauren phillips", "lizz tayler", "maitland ward",
     "mia khalifa", "mia magma", "mia malkova", "nadia ali", "rebecca more",
     "remy lacroix", "renee gracie", "reya sunshine", "rika hoshimi",
     "riley reid", "saki hatsumi", "samantha bentley", "sara tommasi",
     "tasha reign", "tsusaka aoi", "valentina nappi",
     "brendon miller", "griffin barrows", "jordi el nino polla",
     "matthew camp", "rocco steele", "ty mitchell", "amouranth", "belle delphine",
     "cara cunningham", "nang mwe san", "projekt melody",
     
     # Dutch Porn Websites
     "kinky.nl", "geilevrouwen.nl", "sexfilms.nl",
     "echtneuken.nl", "viva.nl", "sexjobs.nl", "vagina.nl", "binkdate.nl", "chatgirl.nl",
 
     # Gay Porn Websites
     "www.men.com", "gaytube.com", "justusboys.com", "gaymaletube.com", "dudetube.com",
     "nextdoorstudios.com", "cockyboys.com", "helixstudios.net", "hothouse.com", "corbinfisher.com",
 
     # Lesbian Porn Websites
     "girlsway.com", "naughtylady.com", "bellesa.co", "sweetsinner.com", "transangelsnetwork.com",
     "girlfriendsfilms.com", "thelesbianexperience.com", "wifelovers.com", "wearehairy.com", "lucasentertainment.com",
 
     # Trans Porn Websites
     "shemale.xxx", "groobygirls.com", "ts-dating.com", "tgirls.com", "trannytube.tv",
     "trans500.com", "pure-ts.com", "transangels.com"
]    


EXPLICIT_REGEX = re.compile("|".join(re.escape(k.lower()) for k in EXPLICIT_KEYWORDS))


def filter_explicit_content(df, columns_to_check):
    """Drops rows where any of the given columns contains an explicit keyword.

    The index is reset because the consent form addresses rows by position,
    so a gapped index renders as empty rows in the table shown to the
    participant.
    """
    if df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns_to_check:
        remaining = ~mask  # only scan rows not already matched
        if not remaining.any():
            break
        mask.loc[remaining] = (
            df.loc[remaining, col]
            .astype("string")
            .str.lower()
            .str.contains(EXPLICIT_REGEX, na=False)
            .fillna(False)
            .astype(bool)
        )
    return df[~mask].reset_index(drop=True)


def redact_emails(df, columns_to_redact):
    """Replaces email addresses in the given columns with ``[email]``.

    Uses the shared ``EMAIL_PATTERN`` so that all platforms agree on what an
    address looks like. Columns that a table does not have are skipped, and
    missing values are left untouched.
    """
    for col in columns_to_redact:
        if col not in df.columns:
            continue
        df[col] = (
            df[col]
            .astype("string")
            .str.replace(eh.EMAIL_PATTERN, "[email]", regex=True)
        )
    return df


# ---------------------------------------------------------------------------
# Extractor functions
# ---------------------------------------------------------------------------


def youtube_watch_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the YouTube watch history from the Google DDP.

    Reads the file at the ``youtube.watch_history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Channel name``, ``Channel URL``, ``Details``,
        ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one video the participant watched on YouTube, including the video title and URL, the channel that published it, how the view came about where the archive says so, and the timestamp.",
          "source_file": "the YouTube watch history, e.g. history/watch-history.json or Verlauf/Wiedergabeverlauf.html",
          "columns": {
            "Title": "Title of the watched video.",
            "URL": "URL of the watched video.",
            "Channel name": "Name of the channel that published the video, empty when the archive does not name one.",
            "Channel URL": "URL of the channel that published the video, empty when the archive does not link to one.",
            "Details": "How the view came about, such as a video watched from an ad. Empty for most videos.",
            "Timestamp": "ISO 8601 timestamp of when the video was watched."
          }
        }

    Table config::

        {
          "id": "youtube_watch_history",
          "title": {"en": "Your YouTube watch history", "nl": "Je YouTube kijkgeschiedenis"},
          "description": {
            "en": "Videos you have watched on YouTube, including timestamps.",
            "nl": "Video's die je op YouTube hebt bekeken, inclusief tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Channel name": {"en": "Channel", "nl": "Kanaal"},
            "Channel URL": {"en": "Channel URL", "nl": "Kanaal-URL"},
            "Details": {"en": "Details", "nl": "Details"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          },
          "visualizations": [
            {
              "title": {
                "en": "Videos watched over time",
                "nl": "Bekeken video's in de loop van de tijd"
              },
              "type": "area",
              "group": {"column": "Timestamp", "dateFormat": "auto", "label": {"en": "Date", "nl": "Datum"}},
              "values": [{"aggregate": "count", "label": {"en": "Number of videos", "nl": "Bekeken video's"}}]
            },
            {
              "title": {
                "en": "Videos watched by hour of the day",
                "nl": "Bekeken video's per uur van de dag"
              },
              "type": "bar",
              "group": {"column": "Timestamp", "dateFormat": "hour_cycle", "label": {"en": "Hour of the day", "nl": "Uur van de dag"}},
              "values": [{"label": {"en": "Number of videos", "nl": "Aantal video's"}}]
            },
            {
              "title": {
                "en": "Words in video titles you watched",
                "nl": "Woorden in titels van bekeken video's"
              },
              "type": "wordcloud",
              "textColumn": "Title",
              "tokenize": true
            }
          ]
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "youtube.watch_history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    # The activity file this falls back to records views and searches together, and
    # neither format tells them apart by itself, so select on the url.
    d = [item for item in d if "/watch?v=" in item.get("titleUrl", "")]

    datapoints = []
    try:
        for item in d:
            channel = _first_subtitle(item)
            datapoints.append((
                item.get("title", ""),
                item.get("titleUrl", ""),
                channel.get("name", ""),
                channel.get("url", ""),
                _join_details(item),
                item.get("time", ""),
            ))
        out = pd.DataFrame(  # pyright: ignore
            datapoints,
            columns=["Title", "URL", "Channel name", "Channel URL", "Details", "Timestamp"],
        )
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def youtube_search_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the YouTube search history from the Google DDP.

    Reads the file at the ``youtube.search_history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Details``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one search query in YouTube search history, including how the search came about where the archive says so.",
          "source_file": "the YouTube search history, e.g. history/search-history.json or Verlauf/Suchverlauf.html",
          "columns": {
            "Title": "Description of the search action.",
            "URL": "URL of the search query.",
            "Details": "How the search came about, such as a search that came from an ad. Empty for most searches.",
            "Timestamp": "ISO 8601 timestamp of when the search was performed."
          }
        }

    Table config::

        {
          "id": "youtube_search_history",
          "title": {
            "en": "Your YouTube search history",
            "nl": "Je YouTube zoekgeschiedenis"
          },
          "description": {
            "en": "Your search queries on YouTube with timestamps.",
            "nl": "Je zoekopdrachten op YouTube met tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Details": {"en": "Details", "nl": "Details"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          },
          "visualizations": [
            {
              "title": {
                "en": "Words in your YouTube search history",
                "nl": "Woorden in je YouTube zoekgeschiedenis"
              },
              "type": "wordcloud",
              "textColumn": "Title",
              "tokenize": true
            }
          ]
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "youtube.search_history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    # The activity file this falls back to records views and searches together, and
    # neither format tells them apart by itself, so select on the url.
    d = [item for item in d if "results?search_query=" in item.get("titleUrl", "")]

    datapoints = []
    try:
        for item in d:
            datapoints.append((
                item.get("title", ""),
                item.get("titleUrl", ""),
                _join_details(item),
                item.get("time", ""),
            ))
        out = pd.DataFrame(datapoints, columns=["Title", "URL", "Details", "Timestamp"])  # pyright: ignore
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1

    return out


def youtube_subscriptions_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the YouTube subscriptions from the Google DDP.

    Reads the CSV at the ``youtube.subscriptions`` paths of the detected locale.
    Normalizes column names to English regardless of export language.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Channel Id``, ``Channel URL``, ``Channel Name``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one YouTube channel the participant is subscribed to.",
          "source_file": "the YouTube subscriptions, e.g. subscriptions/subscriptions.csv or Abos/Abos.csv",
          "columns": {
            "Channel Id": "Unique identifier of the subscribed channel.",
            "Channel URL": "URL of the subscribed channel.",
            "Channel Name": "Display name of the subscribed channel."
          }
        }

    Table config::

        {
          "id": "youtube_subscriptions",
          "title": {"en": "Your YouTube subscriptions", "nl": "Je YouTube abonnementen"},
          "description": {
            "en": "YouTube channels you are subscribed to.",
            "nl": "YouTube-kanalen waarop je bent geabonneerd."
          },
          "headers": {
            "Channel Id": {"en": "Channel Id", "nl": "Kanaal-id"},
            "Channel URL": {"en": "Channel URL", "nl": "Kanaal-URL"},
            "Channel Name": {"en": "Channel Name", "nl": "Kanaalnaam"}
          }
        }
    """
    _, result = _read(reader, "youtube.subscriptions", locale)
    if result is None:
        return pd.DataFrame()
    df = result.data

    if not df.empty:
        df.columns = ["Channel Id", "Channel URL", "Channel Name"]  # pyright: ignore

    return df


def _parse_comment_text(raw: str) -> str:
    try:
        segments = json.loads(f"[{raw}]")
        return " ".join(s["text"] for s in segments if isinstance(s, dict) and s.get("text", "").strip())
    except Exception:
        return raw


def youtube_comments_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the YouTube comments from the Google DDP.

    Reads the CSV at the ``youtube.comments`` paths of the detected locale. Normalizes
    column names to English and parses comment text segments.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Timestamp``, ``Channel ID``, ``Comment text``, ``Comment ID``,
        ``Video ID``, ``Price`` (subset available depends on export).
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::

        {
          "summary": "Each row represents one comment the participant posted on a YouTube video or post.",
          "source_file": "the YouTube comments, e.g. comments/comments.csv or reacties/reacties.csv",
          "columns": {
            "Timestamp": "ISO 8601 timestamp of when the comment was created.",
            "Channel ID": "ID of the channel where the comment was posted.",
            "Comment text": "Full text of the comment.",
            "Comment ID": "Unique identifier for the comment.",
            "Video ID": "ID of the video the comment was posted on.",
            "Price": "Super Chat amount, if applicable."
          }
        }

    Table config::

        {
          "id": "youtube_comments",
          "title": {"en": "Your YouTube comments", "nl": "Je YouTube reacties"},
          "description": {
            "en": "Comments you posted on YouTube videos and posts.",
            "nl": "Reacties die je op YouTube-video's en -posts hebt geplaatst."
          },
          "headers": {
            "Comment ID": {"en": "Comment ID", "nl": "Reactie-ID"},
            "Channel ID": {"en": "Channel ID", "nl": "Kanaal-ID"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"},
            "Price": {"en": "Price", "nl": "Prijs"},
            "Video ID": {"en": "Video ID", "nl": "Video-ID"},
            "Comment text": {"en": "Comment text", "nl": "Reactietekst"}
          },
          "visualizations": [
            {
              "title": {
                "en": "Most common words in your YouTube comments",
                "nl": "Meest voorkomende woorden in je YouTube reacties"
              },
              "type": "wordcloud",
              "textColumn": "Comment text",
              "tokenize": true
            }
          ]
        }
    """
    _, result = _read(reader, "youtube.comments", locale)
    if result is None:
        return pd.DataFrame()
    df = result.data

    if not df.empty:
        df = df.rename(columns={
            "Reactie-ID": "Comment ID",
            "Kanaal-ID": "Channel ID",
            "Aanmaaktijdstempel reactie": "Timestamp",
            "Comment create timestamp": "Timestamp",
            "Comment Create Timestamp": "Timestamp",
            "Prijs": "Price",
            "Video-ID": "Video ID",
            "Reactietekst": "Comment text",
            "Comment Text": "Comment text",
        })
        keep = ["Timestamp", "Channel ID", "Comment text", "Comment ID", "Video ID", "Price"]
        df = df[[col for col in keep if col in df.columns]]  # pyright: ignore
        if "Comment text" in df.columns:
            df["Comment text"] = df["Comment text"].apply(_parse_comment_text)

    return df


def search_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the Google search history from the Google DDP.

    Reads the file at the ``search.search_history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Details``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::
        {
          "summary": "Each row represents one search query in Google search history, including how the search came about where the archive says so.",
          "source_file": "the Google search history, e.g. Search/MyActivity.json or Suche/MyActivity.html",
          "columns": {
            "Title": "Description of the search action.",
            "URL": "URL of the search query.",
            "Details": "How the search came about, such as a search that came from an ad. Empty for most searches.",
            "Timestamp": "ISO 8601 timestamp of when the search was performed."
          }
        }
    Table config::
        {
          "id": "search_history",
          "title": {"en": "Your Google search history", "nl": "Je Google zoekgeschiedenis"},
          "description": {
            "en": "Your search queries on Google with timestamps.",
            "nl": "Je zoekopdrachten op Google met tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Details": {"en": "Details", "nl": "Details"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "search.search_history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
            if not isinstance(d, list):
                return out
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    datapoints = []
    try:
        for item in d:
            datapoints.append((
                item.get("title", ""),
                item.get("titleUrl", ""),
                _join_details(item),
                item.get("time", ""),
            ))
        out = pd.DataFrame(  # pyright: ignore
            datapoints,
            columns=["Title", "URL", "Details", "Timestamp"],
        )
        out = filter_explicit_content(out, ["Title", "URL"])
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return out


def chrome_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the Chrome history from the Google DDP.

    Reads the file at the ``chrome.history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::
        {
          "summary": "Each row represents one website the participant visited in Chrome, including the page title, URL, and timestamp.",
          "source_file": "the Chrome history, e.g. Chrome/MyActivity.json or Chrome/Verlauf.html",
          "columns": {
            "Title": "Title of the visited page.",
            "URL": "URL of the visited page.",
            "Timestamp": "ISO 8601 timestamp of when the page was visited."
          }
        }

    Table config::
        {
          "id": "chrome_history",
          "title": {"en": "Your Chrome browsing history", "nl": "Je Chrome-surfgeschiedenis"},
          "description": {
            "en": "Websites you visited in Chrome, including timestamps.",
            "nl": "Websites die je in Chrome hebt bezocht, inclusief tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "chrome.history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
            if not isinstance(d, list):
                return out
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    datapoints = []
    try:
        if "Browser History" in d:
            for item in d["Browser History"]:
                datapoints.append((
                    item.get("title", ""),
                    item.get("url", ""),
                    _convert_usec_to_iso8601(item.get("time_usec", ""))
                ))
        else:
            for item in d:
                datapoints.append((
                    item.get("title", ""),
                    item.get("titleUrl", ""),
                    item.get("time", "")
                ))
        out = pd.DataFrame(datapoints, columns=["Title", "URL", "Timestamp"])  # pyright: ignore
        out = filter_explicit_content(out, ["Title", "URL"])
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return out


def video_search_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the Google video search history from the Google DDP.

    Reads the file at the ``video_search.history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::
        {
          "summary": "Each row represents one search event in Google video search history.",
          "source_file": "the Google video search history, e.g. Video Search/MyActivity.json",
          "columns": {
            "Title": "Description of the video search action.",
            "URL": "URL of the video search event.",
            "Timestamp": "ISO 8601 timestamp of when the search was performed."
          }
        }

    Table config::
        {
          "id": "video_search_history",
          "title": {"en": "Your Google video search history", "nl": "Je Google-videozoekgeschiedenis"},
          "description": {
            "en": "Your search queries on Google video with timestamps.",
            "nl": "Je zoekopdrachten op Google video met tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """ 
    out = pd.DataFrame()
    extension, result = _read(reader, "video_search.history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
            if not isinstance(d, list):
                return out
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    datapoints = []
    try:
        for item in d:
            datapoints.append((
                item.get("title", ""),
                item.get("titleUrl", ""),
                item.get("time", "")
            ))
        out = pd.DataFrame(datapoints, columns=["Title", "URL", "Timestamp"])  # pyright: ignore
        out = filter_explicit_content(out, ["Title", "URL"])
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return out 


def ads_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the Google ads history from the Google DDP.

    Reads the file at the ``ads.history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction. Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Details``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::
        {
          "summary": "Each row represents one event in Google ads history, including what the archive records about where the ad was shown.",
          "source_file": "the Google ads history, e.g. Ads/MyActivity.json",
          "columns": {
            "Title": "The ad event.",
            "URL": "URL of the ad event.",
            "Details": "What the archive records about the ad event, such as where the ad was shown. Empty for most events.",
            "Timestamp": "ISO 8601 timestamp of when the ad event occurred."
          }
        }
    Table config::
        {
          "id": "ads_history",
          "title": {"en": "Your Google ads history", "nl": "Je Google-advertentiegeschiedenis"},
          "description": {
            "en": "Your ad events on Google with timestamps.",
            "nl": "Je advertentiegebeurtenissen op Google met tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Details": {"en": "Details", "nl": "Details"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "ads.history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
            if not isinstance(d, list):
                return out
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    datapoints = []
    try:
        for item in d:
            datapoints.append((
                item.get("title", ""),
                item.get("titleUrl", ""),
                _join_details(item),
                item.get("time", "")
            ))
        out = pd.DataFrame(datapoints, columns=["Title", "URL", "Details", "Timestamp"])  # pyright: ignore
        out = filter_explicit_content(out, ["Title", "URL"])
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return out


def discover_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the Google Discover history from the Google DDP.

    Reads the file at the ``discover.history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction. Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``Details``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::
        {
          "summary": "Each row represents one event in Google Discover history.",
          "source_file": "the Google Discover history, e.g. Discover/MyActivity.json",
          "columns": {
            "Title": "The title of the Discover event.",
            "Details": "Additional details about the Discover event.",
            "Timestamp": "ISO 8601 timestamp of when the Discover event occurred."
          }
        }
    Table config::
        {
          "id": "discover_history",
          "title": {"en": "Your Google Discover history", "nl": "Je Google Discover-geschiedenis"},
          "description": {
            "en": "Your Discover events on Google with timestamps.",
            "nl": "Je Discover-gebeurtenissen op Google met tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "Details": {"en": "Details", "nl": "Details"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "discover.history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
            if not isinstance(d, list):
                return out
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    datapoints = []
    try:
        for item in d:
            datapoints.append((
                item.get("title", ""),
                _join_details(item),
                item.get("time", "")
            ))
        out = pd.DataFrame(datapoints, columns=["Title", "Details", "Timestamp"])  # pyright: ignore
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return out


def google_news_history_to_df(reader: ZipArchiveReader, errors: Counter, locale: str) -> pd.DataFrame:
    """Extract the Google News history from the Google DDP.

    Reads the file at the ``google_news.history`` paths of the detected locale, as
    JSON or as HTML depending on the format it was exported in.

    Parameters
    ----------
    reader:
        Archive reader used to load files from the DDP zip.
    errors:
        Mutable counter that accumulates error type counts encountered during
        extraction.  Updated in-place.
    locale:
        Locale of the DDP, used to look the file up in ``TAKEOUT_PATHS``.

    Returns
    -------
    pd.DataFrame
        Columns: ``Title``, ``URL``, ``Timestamp``.
        Empty DataFrame when no matching file is found or parsing fails.

    Table documentation::
        {
          "summary": "Each row represents one event in Google News history.",
          "source_file": "the Google News history, e.g. News/MyActivity.json",
          "columns": {
            "Title": "The title of the Google News event.",
            "URL": "URL of the Google News event.",
            "Timestamp": "ISO 8601 timestamp of when the Google News event occured."
          }
        }

    Table config::
        {
          "id": "google_news_history",
          "title": {"en": "Your Google News history", "nl": "Je Google Nieuws-geschiedenis"},
          "description": {
            "en": "Your Google News events with timestamps.",
            "nl": "Je Google Nieuws-gebeurtenissen met tijdstippen."
          },
          "headers": {
            "Title": {"en": "Action", "nl": "Actie"},
            "URL": {"en": "URL", "nl": "URL"},
            "Timestamp": {"en": "Timestamp", "nl": "Datum en tijd"}
          }
        }
    """
    out = pd.DataFrame()
    extension, result = _read(reader, "google_news.history", locale)
    if extension == "json":
        d = result.data
    elif extension == "html":
        try:
            d = _parse_activity_html(result.data)
            if not isinstance(d, list):
                return out
        except Exception as e:
            logger.error("Exception caught: %s", e)
            errors[type(e).__name__] += 1
            return out
    else:
        return out

    datapoints = []
    try:
        for item in d:
            datapoints.append((
                item.get("title", ""),
                item.get("titleUrl", ""),
                item.get("time", "")
            ))
        out = pd.DataFrame(datapoints, columns=["Title", "URL", "Timestamp"])  # pyright: ignore
    except Exception as e:
        logger.error("Exception caught: %s", e)
        errors[type(e).__name__] += 1
    return out



# ---------------------------------------------------------------------------
# Extractor registry & platform info
# ---------------------------------------------------------------------------

#: Mapping from the string names used in port_config.json to actual extractor functions.
EXTRACTOR_REGISTRY: dict[str, Callable[..., pd.DataFrame]] = {
    "youtube_watch_history_to_df": youtube_watch_history_to_df,
    "youtube_search_history_to_df": youtube_search_history_to_df,
    "youtube_subscriptions_to_df": youtube_subscriptions_to_df,
    "youtube_comments_to_df": youtube_comments_to_df,
    "search_history_to_df": search_history_to_df,
    "chrome_history_to_df": chrome_history_to_df,
    "video_search_history_to_df": video_search_history_to_df,
    "ads_history_to_df": ads_history_to_df,
    "discover_history_to_df": discover_history_to_df,
    "google_news_history_to_df": google_news_history_to_df,
}


# ---------------------------------------------------------------------------
# Main extraction & flow
# ---------------------------------------------------------------------------

def extraction(google_zip: str, validation) -> ExtractionResult:
    """Extract data from a Google DDP zip and return consent-form tables.

    Parameters
    ----------
    google_zip:
        Path to the Google DDP zip archive on disk.
    validation:
        ``GoogleValidation`` from ``validate_ddp``, holding the locale of the DDP and
        the archive members that are passed to ``ZipArchiveReader``.
    """
    locale = validation.locale

    config = load_port_config(EXTRACTOR_REGISTRY, "google")
    for table in config: # Pass the locale, extractors need it to find their file
        table.extractor_kwargs = {**table.extractor_kwargs, 'locale': locale}
    errors: Counter = Counter()
    reader = ZipArchiveReader(google_zip, validation.archive_members, errors)

    result = run_extraction(reader, errors, config)

    # The free-text columns can carry addresses of the participant or of third
    # parties, which are not part of what is asked to be donated.
    TEXT_COLUMNS = ["Title", "Details"]
    for table in result.tables:
        redact_emails(table.data_frame, TEXT_COLUMNS)

    return result


class GoogleFlow(FlowBuilder):
    """Flow implementation for the Google data donation study."""

    def __init__(self, session_id: str):
        super().__init__(session_id, "Google")

    def validate_file(self, file):
        return validate_ddp(file)

    def extract_data(self, file, validation):
        return extraction(file, validation)


def process(session_id):
    flow = GoogleFlow(session_id)
    return flow.start_flow()
