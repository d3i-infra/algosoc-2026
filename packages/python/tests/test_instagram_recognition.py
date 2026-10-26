"""Instagram recognition is the shared folder-marker validator (made-up members, ADR-0014)."""
import pytest
from port.helpers.meta_recognition import MetaValidation
from port.platforms.instagram import DDP_CATEGORIES, InstagramFlow, validate_ddp
from test_flow_builder import advance_past_logs, make_payload, start_and_skip_logs
from test_meta_recognition import FACEBOOK_LIST, INSTAGRAM_JSON, NESTED, make_zip


def test_validate_ddp_is_the_meta_validator():
    ig = validate_ddp(make_zip(INSTAGRAM_JSON))
    assert isinstance(ig, MetaValidation)
    assert ig.reason == "instagram"
    assert ig.current_ddp_category.id == "json_en"

    fb = validate_ddp(make_zip(FACEBOOK_LIST))
    assert isinstance(fb, MetaValidation)
    assert fb.reason == "facebook"
    assert fb.current_ddp_category.id == "facebook_detected"


def test_validate_file_keeps_the_latest_validation():
    flow = InstagramFlow("s")
    assert flow.last_validation is None
    result = flow.validate_file(make_zip(INSTAGRAM_JSON))
    assert isinstance(result, MetaValidation)
    assert flow.last_validation is result

    second = flow.validate_file(make_zip(FACEBOOK_LIST))
    assert flow.last_validation is second
    assert second is not result
    assert second.reason == "facebook"


def test_known_files_name_signup_details():
    assert "signup_details.json" in DDP_CATEGORIES[0].known_files
    assert "signup_information.json" not in DDP_CATEGORIES[0].known_files


def upload_payload(members):
    buf = make_zip(members)
    buf.size = len(buf.getvalue())
    return make_payload("PayloadFile", value=buf)


def test_retry_text_follows_latest_validation():
    flow = InstagramFlow("s")
    gen = flow.start_flow()
    start_and_skip_logs(gen)
    cmd = advance_past_logs(gen, upload_payload(FACEBOOK_LIST))
    en = cmd.page.body.toDict()["text"]["translations"]["en"]
    assert en.startswith("This looks like your Facebook file")
    cmd = advance_past_logs(gen, make_payload("PayloadTrue"))
    cmd = advance_past_logs(gen, upload_payload(NESTED))
    en = cmd.page.body.toDict()["text"]["translations"]["en"]
    assert en.startswith("This zip file contains another zip file")


import port.helpers.port_helpers as ph
from port.helpers.flow_builder import TaskIncompleteError
from port.platforms.instagram import MISSING_CATEGORIES, missing_study_categories, require_study_categories
from test_meta_recognition import THIN

ALL_FOUR = [
    "your_instagram_activity/likes/liked_posts.json",
    "connections/followers_and_following/followers_1.json",
    "ads_information/ads_and_topics/posts_viewed.json",
    "logged_information/policy_updates_and_permissions/notification_settings.json",
]
WRAPPER = "meta-2026-10-18/instagram-x-2026-10-18-abc/"


def _missing_for(members):
    return missing_study_categories(validate_ddp(make_zip(members)))


def test_missing_products_thin_export():
    assert list(_missing_for(THIN)) == list(MISSING_CATEGORIES)


def test_missing_products_full_export():
    assert _missing_for(ALL_FOUR) == {}


def test_missing_products_one_category():
    result = _missing_for(ALL_FOUR[:3])
    assert list(result) == ["logged_information"]
    assert result["logged_information"] is MISSING_CATEGORIES["logged_information"][1]


def test_missing_products_empty_category_counts_as_present():
    members = ["connections/contacts/no-data.txt"] + [ALL_FOUR[0], ALL_FOUR[2], ALL_FOUR[3]]
    assert _missing_for(members) == {}


def test_missing_products_ignores_wrapper_and_junk():
    members = [WRAPPER + m for m in ALL_FOUR[:3]] + [
        "__MACOSX/" + WRAPPER + "logged_information/._x.json"
    ]
    assert list(_missing_for(members)) == ["logged_information"]


def test_require_study_categories_rejects_export_without_any():
    original = validate_ddp(make_zip(THIN))
    members = list(original.archive_members)
    result = require_study_categories(original)
    assert result.get_status_code_id() == 1
    assert result.reason == "no_study_categories"
    assert result.current_ddp_category.id == "no_study_categories"
    assert result.archive_members == members
    assert result.milestone_detail == "ig=2 fb=0"


def test_require_study_categories_keeps_partial_export():
    partial = require_study_categories(validate_ddp(make_zip(["connections/contacts/no-data.txt"])))
    assert partial.get_status_code_id() == 0
    assert partial.reason == "instagram"
    rejected = validate_ddp(make_zip(FACEBOOK_LIST))
    assert require_study_categories(rejected) is rejected
    assert rejected.reason == "facebook"


def test_partial_export_proceeds_without_a_page():
    from collections import Counter
    from unittest.mock import patch

    from port.api.commands import CommandSystemLog
    from port.api.d3i_props import ExtractionResult
    flow = InstagramFlow("s")
    gen = flow.start_flow()
    start_and_skip_logs(gen)
    logs = []
    with patch.object(InstagramFlow, "extract_data", return_value=ExtractionResult(tables=[], errors=Counter())):
        cmd = gen.send(upload_payload(ALL_FOUR[:3]))
        while isinstance(cmd, CommandSystemLog):
            logs.append(cmd.message)
            cmd = gen.send(make_payload("PayloadVoid"))
    assert any(m.endswith("Validation: valid (json_en) ig=4 fb=0") for m in logs)
    assert not any("Upload incomplete" in m for m in logs)
    # The no-data page is itself a confirm prompt, so tell the soft-confirm
    # apart by its header.
    assert cmd.page.header.title != flow.UI_TEXT["incomplete_upload_header"]


def test_thin_export_takes_the_retry_path_and_declining_stays_pending():
    from port.api.commands import CommandSystemLog

    flow = InstagramFlow("s")
    gen = flow.start_flow()
    start_and_skip_logs(gen)
    logs = []
    cmd = gen.send(upload_payload(THIN))
    while isinstance(cmd, CommandSystemLog):
        logs.append(cmd.message)
        cmd = gen.send(make_payload("PayloadVoid"))
    assert cmd.page.header.title.translations["en"] == "Try again"
    en = cmd.page.body.toDict()["text"]["translations"]["en"]
    assert en.startswith(
        "Your Instagram file contains none of the parts this study uses: "
        "Your Instagram activity, Connections, Ads information, Logged information"
    )
    assert any(m.endswith("Validation: invalid (no_study_categories) ig=2 fb=0") for m in logs)
    with pytest.raises(TaskIncompleteError) as exc:
        advance_past_logs(gen, make_payload("PayloadFalse"))
    assert exc.value.reason == "abandoned"


def test_retry_prompt_unknown_reason_keeps_default_text():
    default = ph.generate_retry_prompt("Instagram")
    for reason in ("detected_product", "bogus"):
        assert ph.generate_retry_prompt("Instagram", reason=reason) == default
