"""Facebook recognition is the shared folder-marker validator (made-up members, ADR-0014)."""
import re
from collections import Counter
from unittest.mock import patch

import pytest
from port.api.commands import CommandSystemLog
from port.api.d3i_props import ExtractionResult
from port.helpers.flow_builder import TaskIncompleteError
from port.helpers.meta_recognition import MetaValidation
from port.platforms import facebook
from port.platforms.facebook import MISSING_CATEGORIES, FacebookFlow, validate_ddp
from test_facebook_html import _html_export
from test_flow_builder import advance_past_logs, make_payload, start_and_skip_logs
from test_meta_recognition import INSTAGRAM_JSON, make_zip

import port.helpers.validate as validate

# One member per study category, plus a connections folder: a full json export.
FACEBOOK_JSON = [
    "your_facebook_activity/groups/x.json",
    "connections/friends/your_friends.json",
    "logged_information/search/your_search_history.json",
    "ads_information/ad_preferences.json",
    "preferences/feed/controls.json",
    "personal_information/profile_information/profile_information.json",
    "apps_and_websites_off_of_facebook/apps_and_websites/x.json",
]
FACEBOOK_HTML = [m.replace(".json", ".html") for m in FACEBOOK_JSON]

# Two categories whose files sit directly in the folder: only file markers score.
ADS_ONLY = ["ads_information/ad_preferences.json", "ads_information/subscription_for_no_ads.json"]

# Recognised as Facebook (one folder pair, one file marker) but none of the study's parts.
CONNECTIONS_AND_SECURITY = [
    "connections/friends/your_friends.json",
    "security_and_login_information/logins_and_logouts.json",
]

_FORMAL = re.compile(r"\b(u|uw|alstublieft)\b", re.I)


def upload_payload(members):
    buf = make_zip(members)
    buf.size = len(buf.getvalue())
    return make_payload("PayloadFile", value=buf)


def drive_upload(flow, payload):
    """Start *flow*, send *payload*, and return (milestone messages, next UI command)."""
    gen = flow.start_flow()
    start_and_skip_logs(gen)
    logs = []
    cmd = gen.send(payload)
    while isinstance(cmd, CommandSystemLog):
        logs.append(cmd.message)
        cmd = gen.send(make_payload("PayloadVoid"))
    return gen, logs, cmd


def test_validate_ddp_accepts_json_and_html():
    result = validate_ddp(make_zip(FACEBOOK_JSON))
    assert result.get_status_code_id() == 0
    assert result.reason == "facebook"
    assert result.current_ddp_category.id == "json_en"
    assert result.milestone_detail.startswith("ig=0+0 fb=")

    html = validate_ddp(make_zip(FACEBOOK_HTML))
    assert html.get_status_code_id() == 0
    assert html.reason == "facebook"
    assert html.current_ddp_category.id == "html_en"


def test_validate_ddp_rejects_instagram():
    result = validate_ddp(make_zip(INSTAGRAM_JSON))
    assert result.get_status_code_id() == 1
    assert result.reason == "instagram"
    assert result.current_ddp_category.id == "instagram_detected"


def test_ads_only_export_is_recognised():
    result = validate_ddp(make_zip(ADS_ONLY))
    assert result.get_status_code_id() == 0
    assert result.reason == "facebook"
    assert list(result.missing_study_labels) == [
        key for key in MISSING_CATEGORIES if key != "ads_information"
    ]
    assert len(result.missing_study_labels) == 5


def test_connections_and_security_only_takes_the_retry_path():
    flow = FacebookFlow("s")
    gen, logs, cmd = drive_upload(flow, upload_payload(CONNECTIONS_AND_SECURITY))
    assert any(m.endswith("Validation: invalid (no_study_categories) ig=0+0 fb=0+2 basis=weak") for m in logs)
    assert cmd.page.header.title.translations["en"] == "Try again"
    en = cmd.page.body.toDict()["text"]["translations"]["en"]
    assert en.startswith(
        "Your Facebook file contains none of the parts this study uses: "
        "Your Facebook activity, Logged information, Ads information, "
        "Apps and websites off of Facebook, Preferences, Personal information"
    )
    with pytest.raises(TaskIncompleteError) as exc:
        advance_past_logs(gen, make_payload("PayloadFalse"))
    assert exc.value.reason == "abandoned"


def test_instagram_upload_gets_the_other_product_text():
    flow = FacebookFlow("s")
    _, _, cmd = drive_upload(flow, upload_payload(INSTAGRAM_JSON))
    assert cmd.page.header.title.translations["en"] == "Try again"
    en = cmd.page.body.toDict()["text"]["translations"]["en"]
    assert en.startswith("This looks like your Instagram file, not your Facebook file")


def test_partial_export_proceeds():
    members = ["your_facebook_activity/groups/x.json"]
    result = validate_ddp(make_zip(members))
    assert result.get_status_code_id() == 0
    assert len(result.missing_study_labels) == 5

    flow = FacebookFlow("s")
    with patch.object(FacebookFlow, "extract_data", return_value=ExtractionResult(tables=[], errors=Counter())):
        _, logs, cmd = drive_upload(flow, upload_payload(members))
    assert any(m.endswith("Validation: valid (json_en) ig=0+0 fb=2+0 basis=strong") for m in logs)
    assert not any("Upload incomplete" in m for m in logs)
    # The no-data page is itself a confirm prompt, so tell the soft-confirm
    # apart by its header.
    assert cmd.page.header.title != flow.UI_TEXT["incomplete_upload_header"]


def test_missing_category_labels_nl_are_informal():
    for _folder, label in MISSING_CATEGORIES.values():
        nl = label.translations["nl"]
        assert not _FORMAL.search(nl), nl


def test_validate_file_is_validate_ddp():
    result = FacebookFlow("s").validate_file(make_zip(FACEBOOK_JSON))
    assert isinstance(result, MetaValidation)
    assert result.reason == "facebook"


def test_validate_ddp_recognises_the_hand_built_html_export():
    new = validate_ddp(_html_export())
    assert new.get_status_code_id() == 0
    assert new.reason == "facebook"
    assert new.current_ddp_category.id == "html_en"

    old = validate.validate_zip(facebook.DDP_CATEGORIES, _html_export())
    assert old.current_ddp_category.id == "html_en"

    new_ids = {t.id for t in facebook.extraction(_html_export(), new).tables}
    old_ids = {t.id for t in facebook.extraction(_html_export(), old).tables}
    assert new_ids == old_ids
    assert "facebook_who_youve_followed" in new_ids

    new_tables = facebook.extraction(_html_export(), new).tables
    old_tables = facebook.extraction(_html_export(), old).tables
    new_rows = {t.id: len(t.data_frame) for t in new_tables}
    old_rows = {t.id: len(t.data_frame) for t in old_tables}
    assert new_rows == old_rows
    assert new_rows["facebook_who_youve_followed"] >= 1
