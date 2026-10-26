"""Instagram recognition is the shared folder-marker validator (made-up members, ADR-0014)."""
from port.helpers.meta_recognition import MetaValidation
from port.platforms.instagram import DDP_CATEGORIES, InstagramFlow, validate_ddp
from test_meta_recognition import FACEBOOK_LIST, INSTAGRAM_JSON, make_zip


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


def test_known_files_name_signup_details():
    assert "signup_details.json" in DDP_CATEGORIES[0].known_files
    assert "signup_information.json" not in DDP_CATEGORIES[0].known_files
