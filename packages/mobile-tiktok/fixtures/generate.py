"""Build synthetic TikTok exports and the desktop extractor's output on them.

Run from packages/python with its poetry environment:
    poetry run python ../mobile-tiktok/fixtures/generate.py

Writes fixtures/generated/<name>.zip and <name>.expected.json. Only synthetic
data (ADR-0014). Every free-text cell carries an email and the username so
redaction parity is exercised; timestamps straddle both DST transitions.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

# Desktop has no Pyodide `js` module; stand one in before importing `port`, the
# same way scripts/validate_port_config.py does for its own standalone run
# (packages/python/tests/conftest.py does this for pytest, but this script
# runs outside pytest). See ADR-0015.
sys.modules.setdefault("js", MagicMock())

from port.helpers import extraction_helpers as eh
from port.helpers.validate import validate_zip
from port.platforms import tiktok

OUT = Path(__file__).resolve().parent / "generated"
USERNAME = "synth_user_42"
TEXT_COLUMNS = ["Comment", "SearchTerm", "SharedContent"]

# UTC instants around the 2026 DST changes plus ordinary ones, deliberately
# not in chronological order so export-order handling is visible.
DATES = [
    "2026-03-29 00:59:59", "2026-03-29 01:00:00", "2026-10-25 00:59:59",
    "2026-10-25 01:00:00", "2025-12-31 23:30:00", "2024-06-15 12:00:00",
]

def dates_txt():
    return [d + " UTC" for d in DATES]

def json_export() -> dict:
    return {
        "Profile And Settings": {
            "Profile Info": {"ProfileMap": {"userName": USERNAME, "displayName": "Synth"}},
            "Settings": {"SettingsMap": {"Content Preferences": {
                "Keyword filters for videos in For You feed": ["cats", "dogs"],
                "Keyword filters for videos in Following feed": [],
            }}},
            "Follower": {"FansList": [{"Date": DATES[0], "UserName": "fan_one"}, {"Date": DATES[5], "UserName": None}]},
            "Following": {"Following": [{"Date": DATES[1], "UserName": "creator_a"}]},
            "Off TikTok Activity": {"OffTikTokActivityDataList": [{"TimeStamp": DATES[2], "Source": "shop.example", "Event": "purchase"}]},
        },
        "Your Activity": {
            "Activity Summary": {"ActivitySummaryMap": {
                "videosWatchedToTheEndSinceAccountRegistration": 1234,
                "videosCommentedOnSinceAccountRegistration": "7",
                "videosSharedSinceAccountRegistration": 0,
            }},
            "Watch History": {"VideoList": [
                {"Date": d, "Link": f"https://www.tiktokv.com/share/video/{i}/"} for i, d in enumerate(DATES)
            ]},
            "Favorite Videos": {"FavoriteVideoList": [{"Date": DATES[3], "Link": "https://f/1"}]},
            "Hashtag": {"HashtagList": [{"HashtagName": "fyp", "HashtagLink": "https://h/fyp"}]},
            "Like List": {"ItemFavoriteList": [{"Date": DATES[4], "Link": "https://l/1"}, {"Date": "", "Link": "https://l/2"}]},
            "Searches": {"SearchList": [
                {"Date": DATES[0], "SearchTerm": f"{USERNAME} videos"},
                {"Date": DATES[1], "SearchTerm": "contact me@example.com"},
                {"Date": "not a date", "SearchTerm": "plain"},
            ]},
            "Share History": {"ShareHistoryList": [{"Date": DATES[2], "SharedContent": f"by {USERNAME}", "Link": "https://s/1", "Method": "copy"}]},
            # Desktop's ad_interests_to_df always raises (2 columns passed, data
            # had 1) for any non-empty input, so this table is unreachable and
            # absent from every expected file until that column-count bug is fixed.
            "Ad Interests": [{"AdInterestCategories": "Cars"}],
        },
        "Comment": {"Comments": {"CommentsList": [
            {"Date": DATES[3], "Comment": f"Hi {USERNAME.upper()}, write a.b@c.de", "Photo": "", "Url": "https://c/1"},
            {"Date": DATES[4], "Comment": "plain", "Photo": None, "Url": None},
        ]}},
    }

def records(lines: list[dict]) -> str:
    return "\n\n".join("\n".join(f"{k}: {v}" for k, v in r.items()) for r in lines) + "\n"

def txt_export(lang: str) -> dict[str, str]:
    d = dates_txt()
    if lang == "en":
        base = "TikTok"
        return {
            f"{base}/Profile and Settings/Profile Information.txt": f"Username: {USERNAME}\nNickname: Synth\n",
            f"{base}/Profile and Settings/Settings.txt": "Private Account: Off\n\nContent Preferences:\nKeyword filters for videos in For You feed: [cats, dogs]\nKeyword filters for videos in Following feed: []\n",
            f"{base}/Your Activity/Activity Summary.txt": "(Note: counts since registration\n\nVideos shared since account registration: 0\nVideos watched to the end since account registration: 1234\nVideos commented on since account registration: 7\n",
            f"{base}/Your Activity/Watch History.txt": records([{"Date": x, "Link": f"https://www.tiktokv.com/share/video/{i}/"} for i, x in enumerate(d)]),
            f"{base}/Likes and Favorites/Favorite Videos.txt": records([{"Date": d[3], "Link": "https://f/1"}]),
            f"{base}/Profile and Settings/Follower.txt": records([{"Date": d[0], "UserName": "fan_one"}, {"Date": d[5], "UserName": "None"}]),
            f"{base}/Profile and Settings/Following.txt": records([{"Date": d[1], "UserName": "creator_a"}]),
            f"{base}/Your Activity/Hashtag.txt": records([{"Hashtag Name": "fyp", "Hashtag Link": "https://h/fyp"}]),
            f"{base}/Likes and Favorites/Like List.txt": records([{"Date": d[4], "Link": "https://l/1"}]),
            f"{base}/Your Activity/Searches.txt": records([{"Date": d[0], "Search Term": f"{USERNAME} videos"}, {"Date": d[1], "Search Term": "contact me@example.com"}]),
            f"{base}/Your Activity/Share History.txt": records([{"Date": d[2], "Shared Content": f"by {USERNAME}", "Link": "https://s/1", "Method": "copy"}]),
            f"{base}/Comments/Comments.txt": records([{"Date": d[3], "Comment": f"Hi {USERNAME.upper()}, write a.b@c.de", "Photo": "N/A", "Url": "https://c/1"}]),
            f"{base}/Ads and data/Off-TikTok Activities.txt": records([{"Date": d[2], "Source": "shop.example", "Event": "purchase"}]),
            f"{base}/Ads and data/Ad Interests.txt": "You have no data in this section\n",
            f"{base}/Direct Messages/Direct Messages.txt": "must never be read\n",
        }
    base = "TikTok"
    return {
        f"{base}/Profiel en instellingen/Profielinformatie.txt": f"Gebruikersnaam: {USERNAME}\nBijnaam: Synth\n",
        f"{base}/Profiel en instellingen/Instellingen.txt": "Privéaccount: Uit\n\nContentvoorkeuren:\nTrefwoordfilters voor video's in de 'Voor jou'-feed: [katten, honden]\n",
        f"{base}/Je activiteit/Samenvatting van activiteit.txt": "Video's gedeeld sinds accountregistratie: 0\nVideo's tot het einde bekeken sinds accountregistratie: 1234\nVideo's waarop is gereageerd sinds accountregistratie: 7\n",
        f"{base}/Je activiteit/Kijkgeschiedenis.txt": records([{"Datum": x, "Link": f"https://www.tiktokv.com/share/video/{i}/"} for i, x in enumerate(d)]),
        f"{base}/Likes en favorieten/Favoriete video's.txt": records([{"Datum": d[3], "Link": "https://f/1"}]),
        f"{base}/Profiel en instellingen/Volger.txt": records([{"Datum": d[0], "Gebruikersnaam": "fan_one"}]),
        f"{base}/Profiel en instellingen/Volgend.txt": records([{"Datum": d[1], "Gebruikersnaam": "creator_a"}]),
        f"{base}/Je activiteit/Hashtag.txt": "Dit gedeelte bevat geen gegevens\n",
        f"{base}/Likes en favorieten/Likelijst.txt": records([{"Datum": d[4], "Link": "https://l/1"}]),
        f"{base}/Je activiteit/Zoekopdrachten.txt": records([{"Datum": d[0], "Zoekterm": f"{USERNAME} videos"}, {"Datum": d[1], "Zoekterm": "contact me@example.com"}]),
        f"{base}/Je activiteit/Geschiedenis delen.txt": records([{"Datum": d[2], "Gedeelde inhoud": f"by {USERNAME}", "Link": "https://s/1", "Methode": "kopiëren"}]),
        f"{base}/Reacties/Reacties.txt": records([{"Datum": d[3], "Reactie": f"Hoi {USERNAME}, mail a.b@c.de", "Foto": "n.v.t.", "Originele link naar bericht": "https://c/1"}]),
        f"{base}/Advertenties en gegevens/Activiteit buiten TikTok.txt": records([{"Datum": d[2], "Bron": "shop.example", "Evenement": "aankoop"}]),
        f"{base}/Berichten/Directe berichten.txt": "mag nooit gelezen worden\n",
    }

def sparse_json() -> dict:
    return {"Profile And Settings": {"Profile Info": {"ProfileMap": {"userName": USERNAME}}}, "Your Activity": {}}

def write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in members.items():
            zf.writestr(name, text.encode("utf-8"))

def expected(zip_path: Path) -> dict:
    validation = validate_zip(tiktok.DDP_CATEGORIES, str(zip_path))
    result = tiktok.extraction(io.BytesIO(zip_path.read_bytes()), validation)
    tables = []
    for table in result.tables:
        df = table.data_frame
        assert isinstance(df, pd.DataFrame)
        eh.anonymize_dataframe(df, TEXT_COLUMNS, USERNAME)
        tables.append({"id": table.id, "data_frame": df.to_json()})
    return {"username": USERNAME, "tables": tables, "errors": dict(Counter(result.errors))}

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "json_en": {"user_data_tiktok.json": json.dumps(json_export(), ensure_ascii=False)},
        "json_sparse": {"user_data.json": json.dumps(sparse_json())},
        "txt_en": txt_export("en"),
        "txt_nl": txt_export("nl"),
    }
    for name, members in fixtures.items():
        zip_path = OUT / f"{name}.zip"
        write_zip(zip_path, members)
        (OUT / f"{name}.expected.json").write_text(json.dumps(expected(zip_path), ensure_ascii=False, indent=1))
        print("wrote", zip_path.name)

if __name__ == "__main__":
    main()
