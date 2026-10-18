"""Each study platform tells the single-file prompt what its export is called
(FlowBuilder.file_example). The names are shapes, never real handles (ADR-0014)."""

import pytest

from port.platforms import facebook, google, instagram, tiktok


@pytest.mark.parametrize(
    "flow_class, expected",
    [
        (instagram.InstagramFlow, "Example: instagram-username-2026-10-10-UQx3SPDb.zip"),
        (facebook.FacebookFlow, "Example: facebook-username-2026-10-10-wjMrFg05.zip"),
        (tiktok.TikTokFlow, "Example: TikTok_Data_1791642231.zip"),
    ],
)
def test_platform_sends_its_export_name(flow_class, expected):
    d = flow_class("session").generate_file_prompt().toDict()
    assert d["__type__"] == "PropsUIPromptFileInputSingle"
    assert d["example"]["translations"]["en"] == expected


def test_google_keeps_the_takeout_example():
    d = google.GoogleFlow("session").generate_file_prompt().toDict()
    assert d["__type__"] == "PropsUIPromptFileInputMultiple"
    assert d["example"]["translations"]["en"] == "Example: takeout-...-1-001.zip, takeout-...-2-001.zip"
