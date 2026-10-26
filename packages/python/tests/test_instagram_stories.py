"""Published stories must be read from media/, not the insights file of the same name.

Newer Instagram exports carry two ``stories.json`` / ``stories.html`` files.
Test data is made up and built in memory (ADR-0014).
"""

import io
import json
import zipfile
from collections import Counter
from types import SimpleNamespace

import pandas as pd
from port.helpers.extraction_helpers import ZipArchiveReader
from port.helpers.validate import DDPFiletype
from port.platforms.instagram import stories_published_to_df

STORIES_JSON = json.dumps(
    {"ig_stories": [{"title": "made up story", "uri": "media/stories/202610/1.jpg", "creation_timestamp": 1760000000}]}
)
INSIGHTS_JSON = json.dumps([{"media": [], "label_values": []}])
STORIES_HTML = (
    '<html><body><main><div class="_a6-g"><h2 class="_a6-h _a6-i">made up story</h2>'
    '<a href="media/stories/202610/1.mp4">x</a><div class="_a6-o">Oct 20, 2026 9:49 am</div></div></main></body></html>'
)
INSIGHTS_HTML = "<html><body><main></main></body></html>"
HTML_VALIDATION = SimpleNamespace(current_ddp_category=SimpleNamespace(ddp_filetype=DDPFiletype.HTML))


def _run(entries: dict[str, str], validation=None) -> tuple[pd.DataFrame, Counter]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    buf.seek(0)
    errors: Counter = Counter()
    reader = ZipArchiveReader(buf, list(entries), errors)
    return stories_published_to_df(reader, errors, validation=validation), errors


def _no_ambiguity(errors: Counter) -> bool:
    return not any(k.startswith("AmbiguousMemberMatch") for k in errors)


def test_json_reads_media_stories_when_insights_also_present():
    df, errors = _run({
        "your_instagram_activity/media/stories.json": STORIES_JSON,
        "logged_information/past_instagram_insights/stories.json": INSIGHTS_JSON,
    })
    assert len(df) == 1
    assert df.iloc[0]["Text"] == "made up story"
    assert df.iloc[0]["Media type"] == ".jpg"
    assert _no_ambiguity(errors)


def test_json_reads_media_stories_inside_a_wrapper_folder():
    prefix = "19-10-2026-JSON-Instagram/instagram-x-2026-10-20-abc/"
    df, errors = _run({
        prefix + "your_instagram_activity/media/stories.json": STORIES_JSON,
        prefix + "logged_information/past_instagram_insights/stories.json": INSIGHTS_JSON,
    })
    assert len(df) == 1
    assert df.iloc[0]["Text"] == "made up story"
    assert df.iloc[0]["Media type"] == ".jpg"
    assert _no_ambiguity(errors)


def test_html_reads_media_stories_when_insights_also_present():
    df, errors = _run(
        {
            "your_instagram_activity/media/stories.html": STORIES_HTML,
            "logged_information/past_instagram_insights/stories.html": INSIGHTS_HTML,
        },
        validation=HTML_VALIDATION,
    )
    assert len(df) == 1
    assert df.iloc[0]["Text"] == "made up story"
    assert df.iloc[0]["Media type"] == ".mp4"
    assert _no_ambiguity(errors)


def test_insights_only_gives_no_table():
    df, errors = _run({"logged_information/past_instagram_insights/stories.json": INSIGHTS_JSON})
    assert df.empty
    assert _no_ambiguity(errors)
