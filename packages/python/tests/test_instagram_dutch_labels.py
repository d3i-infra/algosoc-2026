"""Dutch label_values labels (Eigenaar, Naam, Gebruikersnaam, Onderschrift) are matched like English.

Test data is made up and built in memory (ADR-0014).
"""

import io
import json
import zipfile
from collections import Counter
from types import SimpleNamespace

import pandas as pd
import pytest
from lxml import etree
from port.helpers.extraction_helpers import ZipArchiveReader
from port.helpers.validate import DDPFiletype
from port.platforms.instagram import (
    _extract_owner_from_html,
    posts_viewed_to_df,
    saved_posts_to_df,
)

HTML_VALIDATION = SimpleNamespace(current_ddp_category=SimpleNamespace(ddp_filetype=DDPFiletype.HTML))


def _owner(heading: str, name: str, username: str) -> str:
    return (
        f"<div><h2>{heading}</h2><table><tr><td>{name}</td><td>Made Up</td></tr>"
        f"<tr><td>{username}</td><td>made.up</td></tr></table></div>"
    )


def _section(inner: str) -> str:
    return f'<div class="_a6-g">{inner}</div>'


def _page(*sections: str) -> str:
    return f"<html><body><main>{''.join(sections)}</main></body></html>"


def _owner_section(heading: str, name: str, username: str):
    tree = etree.HTML(_page(_section(_owner(heading, name, username))))
    return tree.xpath("//main/div")[0]


def _run(fn, entries: dict[str, str], validation=None) -> pd.DataFrame:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    buf.seek(0)
    errors: Counter = Counter()
    reader = ZipArchiveReader(buf, list(entries), errors)
    return fn(reader, errors, validation=validation)


def test_html_owner_dutch():
    section = _owner_section("Eigenaar", "Naam", "Gebruikersnaam")
    assert _extract_owner_from_html(section) == ("Made Up", "made.up")


def test_html_owner_english_still_works():
    section = _owner_section("Owner", "Name", "Username")
    assert _extract_owner_from_html(section) == ("Made Up", "made.up")


def test_posts_viewed_html_dutch_author():
    inner = (
        _owner("Eigenaar", "Naam", "Gebruikersnaam")
        + '<table><tr><td class="_a6_q">URL<div><a href="https://www.instagram.com/p/x/">x</a></div></td></tr></table>'
        + '<div class="_a6-o">Oct 20, 2026 9:49 am</div>'
    )
    df = _run(
        posts_viewed_to_df,
        {"ads_information/ads_and_topics/posts_viewed.html": _page(_section(inner))},
        validation=HTML_VALIDATION,
    )
    assert len(df) == 1
    assert df.iloc[0]["Author"] == "made.up"


def _saved_json(caption: str, owner: str, username: str, name: str) -> str:
    return json.dumps({"saved_saved_media": [{"timestamp": 1760000000, "label_values": [
        {"label": caption, "value": "made up caption"},
        {"label": "URL", "value": "https://www.instagram.com/p/x/"},
        {"title": owner, "dict": [{"dict": [{"label": username, "value": "made.up"}]}]},
        {"title": "Hashtags", "dict": [{"dict": [{"label": name, "value": "#madeup"}]}]},
    ]}]})


@pytest.mark.parametrize(
    "labels",
    [("Onderschrift", "Eigenaar", "Gebruikersnaam", "Naam"), ("Caption", "Owner", "Username", "Name")],
    ids=["dutch", "english"],
)
def test_saved_posts_json(labels):
    df = _run(saved_posts_to_df, {"saved_posts.json": _saved_json(*labels)})
    assert len(df) == 1
    assert df.iloc[0]["Caption"] == "made up caption"
    assert df.iloc[0]["Username"] == "made.up"
    assert df.iloc[0]["Hashtags"] == "#madeup"


def test_saved_posts_html_dutch_caption():
    inner = '<table><tr><td class="_a6_q">Onderschrift</td><td>made up caption</td></tr></table>'
    df = _run(saved_posts_to_df, {"saved_posts.html": _page(_section(inner))}, validation=HTML_VALIDATION)
    assert len(df) == 1
    assert df.iloc[0]["Caption"] == "made up caption"
