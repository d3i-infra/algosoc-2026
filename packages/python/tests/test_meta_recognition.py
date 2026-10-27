import io
import zipfile

import pytest

import port.api.props as props
from port.helpers.validate import DDPCategory, DDPFiletype, Language
from port.helpers.meta_recognition import (
    FACEBOOK_FILE_MARKERS,
    FACEBOOK_FOLDER_MARKERS,
    FACEBOOK_PAIR_ARTIFACTS,
    FILE_MARKERS,
    INSTAGRAM_FOLDER_MARKERS,
    MARKERS,
    OTHER_PRODUCT,
    STRONG_LEAVES,
    STRONG_MARKERS,
    STRONG_ROOTS,
    WEAK_MARKERS,
    FolderScore,
    MetaValidation,
    decide,
    file_stems,
    folder_names,
    folder_pairs,
    missing_study_categories,
    require_study_categories,
    resolved_inputs,
    score_members,
    validate_meta,
)

INSTAGRAM_JSON = [
    "your_instagram_activity/likes/liked_posts.json",
    "connections/followers_and_following/followers_1.json",
    "ads_information/ads_and_topics/posts_viewed.json",
    "personal_information/personal_information/personal_information.json",
]

FACEBOOK_LIST = [
    "your_facebook_activity/groups/x.json",
    "connections/friends/your_friends.json",
    "personal_information/profile_information/profile_information.json",
]


def assert_zero(score: FolderScore, product: str) -> None:
    assert score.strong(product) == 0
    assert score.weak(product) == 0


def test_full_instagram_json_export():
    score = score_members(INSTAGRAM_JSON)
    # The product root and the pair under it are strong; the three pairs under
    # shared top-level folders are weak.
    assert score.instagram_strong == 2
    assert score.instagram_weak == 3
    assert_zero(score, "facebook")
    assert score.json_files > score.html_files
    assert score.strong("instagram") == score.instagram_strong
    assert score.weak("instagram") == score.instagram_weak


def test_thin_researcher_shape():
    score = score_members(
        [
            "personal_information/device_information/device_camera_effects_support.json",
            "personal_information/information_about_you/profile_based_in.json",
        ]
    )
    assert score.instagram_strong == 0
    assert score.instagram_weak == 2
    assert_zero(score, "facebook")


@pytest.mark.parametrize(
    "member",
    [
        "preferences/settings/consents.json",
        "security_and_login_information/login_and_profile_creation/login_activity.json",
        "logged_information/recent_searches/no-data.txt",
        "media/posts/202610/1.jpg",
        "apps_and_websites_off_of_instagram/apps_and_websites/x.json",
    ],
)
def test_single_category_exports_are_recognised(member):
    score = score_members([member])
    assert score.instagram_strong + score.instagram_weak >= 1
    assert_zero(score, "facebook")


def test_facebook_export():
    score = score_members(FACEBOOK_LIST)
    assert score.facebook_strong == 2
    assert score.facebook_weak == 2
    assert_zero(score, "instagram")


def test_facebook_media_folders_do_not_count():
    score = score_members(["your_facebook_activity/posts/media/album/1.jpg", "media/your_posts/x.json"])
    assert_zero(score, "instagram")


def test_shared_folders_do_not_count():
    score = score_members(
        [
            "personal_information/facebook_accounts_center/no-data.txt",
            "messages/inbox/x/message_1.json",
        ]
    )
    assert_zero(score, "instagram")
    assert_zero(score, "facebook")
    # Instagram's ad_preferences sits one folder deeper, so this file is Facebook's.
    alone = score_members(["ads_information/ad_preferences.json"])
    assert alone.facebook_weak == 1
    assert alone.facebook_strong == 0
    assert_zero(alone, "instagram")


def test_file_stems():
    members = [
        "a/ads_information/ad_preferences.json",
        "ads_information/ad_preferences.html",
        "ads_information/",
        "__MACOSX/ads_information/._ad_preferences.json",
        "readme",
    ]
    assert file_stems(members) == {"ads_information/ad_preferences"}


FACEBOOK_WRAPPER = "meta-2026-Oct-02-09-44-02/facebook-x-2026-10-02-abc/"


@pytest.mark.parametrize(
    "members",
    [
        ["ads_information/ad_preferences.json"],
        ["ads_information/ad_preferences.html"],
        ["security_and_login_information/logins_and_logouts.json"],
        [FACEBOOK_WRAPPER + "ads_information/ad_preferences.json"],
        [FACEBOOK_WRAPPER + "security_and_login_information/logins_and_logouts.json"],
    ],
)
def test_single_file_category_facebook_exports_are_recognised(members):
    score = score_members(members)
    assert score.facebook_weak >= 1
    assert score.facebook_strong == 0
    assert_zero(score, "instagram")


def test_file_markers_match_by_stem():
    both_spellings = score_members(
        [
            "ads_information/advertisers_you've_interacted_with.json",
            "ads_information/advertisers_you_ve_interacted_with.json",
        ]
    )
    assert both_spellings.facebook_weak == 2
    both_formats = score_members(
        ["ads_information/ad_preferences.json", "ads_information/ad_preferences.html"]
    )
    assert both_formats.facebook_weak == 1


def test_instagram_ads_folder_is_not_a_facebook_file_marker():
    score = score_members(
        [
            "ads_information/ads_and_topics/ads_viewed.json",
            "ads_information/instagram_ads_and_businesses/ad_preferences.json",
        ]
    )
    assert_zero(score, "facebook")
    assert score.instagram_strong == 1  # the verified leaf
    assert score.instagram_weak == 1


def test_file_marker_tables():
    assert FILE_MARKERS["facebook"] is FACEBOOK_FILE_MARKERS
    assert FILE_MARKERS["instagram"] == frozenset()
    for marker in FACEBOOK_FILE_MARKERS:
        assert marker.count("/") == 1
        assert marker.split("/")[0] in {"ads_information", "security_and_login_information"}
    # File markers are weak: they never appear in a strong set.
    for product in MARKERS:
        assert FILE_MARKERS[product].isdisjoint(STRONG_MARKERS[product])
    instagram_shaped = INSTAGRAM_JSON + ["ads_information/instagram_ads_and_businesses/ad_preferences.json"]
    assert_zero(score_members(instagram_shaped), "facebook")


def test_wrappers_and_macos_junk():
    prefix = "meta-2026-Oct-18-12-34-44/instagram-x-2026-10-18-abc/"
    wrapped = [prefix + m for m in INSTAGRAM_JSON] + [
        "__MACOSX/meta-2026-Oct-18-12-34-44/your_facebook_activity/._x.json",
        prefix + ".DS_Store",
    ]
    score = score_members(wrapped)
    assert score == score_members(INSTAGRAM_JSON)
    assert_zero(score, "facebook")


def test_zip_in_zip():
    score = score_members(["Instagram/instagram-x-2026-10-18-abc.zip"])
    assert score.only_zips is True
    assert_zero(score, "instagram")
    assert_zero(score, "facebook")


def test_zip_in_zip_with_directory_and_macos_entries():
    score = score_members(
        [
            "Instagram/",
            "Instagram/instagram-x-2026-10-18-abc.zip",
            "__MACOSX/Instagram/._instagram-x-2026-10-18-abc.zip",
        ]
    )
    assert score.only_zips is True


def test_marker_shaped_path_inside_facebook_export():
    score = score_members(FACEBOOK_LIST + ["your_facebook_activity/posts/media/your_instagram_activity/1.jpg"])
    assert score.instagram_strong >= 1
    assert score.facebook_strong >= 1


def test_empty_and_directory_only():
    for members in ([], ["a/", "a/b/"]):
        score = score_members(members)
        assert_zero(score, "instagram")
        assert_zero(score, "facebook")
        assert score.only_zips is False


def test_html_export_counts():
    score = score_members(
        [
            "your_instagram_activity/likes/liked_posts.html",
            "connections/followers_and_following/followers_1.html",
            "personal_information/personal_information/personal_information.json",
        ]
    )
    assert score.html_files > score.json_files


def test_folder_names_and_pairs():
    members = ["a/b/c.json", "a/", "__MACOSX/a/b/._c.json"]
    assert folder_names(members) == {"a", "b"}
    assert folder_pairs(members) == {"a/b"}


def test_marker_tables():
    assert MARKERS["instagram"] is INSTAGRAM_FOLDER_MARKERS
    assert MARKERS["facebook"] is FACEBOOK_FOLDER_MARKERS
    assert OTHER_PRODUCT == {"instagram": "facebook", "facebook": "instagram"}
    assert INSTAGRAM_FOLDER_MARKERS.isdisjoint(FACEBOOK_FOLDER_MARKERS)
    assert set(STRONG_MARKERS) == set(WEAK_MARKERS) == set(MARKERS)
    assert isinstance(score_members([]), FolderScore)


def test_strong_tier_is_derived_mechanically():
    for product in MARKERS:
        roots = STRONG_ROOTS[product]
        under_roots = {m for m in MARKERS[product] if m.split("/")[0] in roots}
        assert STRONG_MARKERS[product] == roots | under_roots | STRONG_LEAVES[product]
        assert STRONG_MARKERS[product] & WEAK_MARKERS[product] == frozenset()
        assert STRONG_MARKERS[product] | WEAK_MARKERS[product] == MARKERS[product]


def test_pinned_non_strong_markers():
    assert "personal_information/facebook_accounts_center" not in (
        STRONG_MARKERS["facebook"] | WEAK_MARKERS["facebook"]
    )
    assert "messages/filtered_threads" not in STRONG_MARKERS["instagram"]
    assert len(FACEBOOK_PAIR_ARTIFACTS) == 9
    for artifact in FACEBOOK_PAIR_ARTIFACTS:
        for product in MARKERS:
            assert artifact not in MARKERS[product]
            assert artifact not in STRONG_MARKERS[product]
            assert artifact not in WEAK_MARKERS[product]
            assert artifact not in FILE_MARKERS[product]


def make_zip(members: list[str]) -> io.BytesIO:
    """An in-memory zip holding an empty file per member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member in members:
            zf.writestr(member, b"")
    buf.seek(0)
    return buf


def instagram_categories() -> list[DDPCategory]:
    return [
        DDPCategory(id="json_en", ddp_filetype=DDPFiletype.JSON, language=Language.EN, known_files=[]),
        DDPCategory(id="html_en", ddp_filetype=DDPFiletype.HTML, language=Language.EN, known_files=[]),
    ]


INSTAGRAM_HTML = [m.replace(".json", ".html") for m in INSTAGRAM_JSON]
THIN = [
    "personal_information/device_information/device_camera_effects_support.json",
    "personal_information/information_about_you/profile_based_in.json",
]
MIXED_FEW_FB = INSTAGRAM_JSON + ["your_facebook_activity/groups/x.json"]
MIXED_FEW_IG = FACEBOOK_LIST + ["your_instagram_activity/likes/x.json"]
NESTED = ["Instagram/instagram-x-2026-10-18-abc.zip"]
UNKNOWN = ["data_logs/content/1/page_1.json", "readme.txt"]
WEAK_INSTAGRAM = [
    "connections/contacts/x.json",
    "preferences/settings/x.json",
    "media/posts/x.jpg",
    "personal_information/device_information/x.json",
    "logged_information/link_history/x.json",
]


def run(members, product="instagram", inputs=frozenset()):
    return validate_meta(make_zip(members), product, instagram_categories(), inputs=inputs)


def test_validate_meta_accepts_json_and_html():
    json_result = run(INSTAGRAM_JSON)
    assert json_result.get_status_code_id() == 0
    assert json_result.reason == "instagram"
    assert json_result.current_ddp_category.id == "json_en"
    html_result = run(INSTAGRAM_HTML)
    assert html_result.get_status_code_id() == 0
    assert html_result.current_ddp_category.id == "html_en"


def test_validate_meta_thin_export_accepted():
    result = run(THIN)
    assert result.get_status_code_id() == 0
    assert result.reason == "instagram"


def test_validate_meta_other_product():
    result = run(FACEBOOK_LIST, "instagram")
    assert result.get_status_code_id() == 1
    assert result.reason == "facebook"
    assert result.current_ddp_category.id == "facebook_detected"
    again = run(FACEBOOK_LIST, "facebook")
    assert again.get_status_code_id() == 0
    assert again.reason == "facebook"


@pytest.mark.parametrize("members", [MIXED_FEW_FB, MIXED_FEW_IG])
@pytest.mark.parametrize("product", ["instagram", "facebook"])
def test_validate_meta_mixed_is_never_accepted(members, product):
    result = run(members, product)
    assert result.get_status_code_id() == 1
    assert result.reason == "mixed"


def test_strong_evidence_beats_weak_other_product():
    # The participant skeleton: an Instagram export whose messages/photos pair
    # looks like Facebook's (and a stray Facebook-shaped connections pair).
    skeleton = INSTAGRAM_JSON + [
        "your_instagram_activity/messages/photos/1.jpg",
        "connections/friends/x.json",
    ]
    result = run(skeleton, "instagram")
    assert result.get_status_code_id() == 0
    assert result.reason == "instagram"
    assert result.basis == "strong"
    mirror = run(FACEBOOK_LIST + ["ads_information/ads_and_topics/x.json"], "facebook")
    assert mirror.get_status_code_id() == 0
    assert mirror.reason == "facebook"
    assert mirror.basis == "strong"


@pytest.mark.parametrize("members", [MIXED_FEW_FB, MIXED_FEW_IG])
@pytest.mark.parametrize("product", ["instagram", "facebook"])
def test_strong_tie_is_mixed_regardless_of_weak(members, product):
    plain = run(members, product)
    assert plain.get_status_code_id() == 1
    assert plain.reason == "mixed"
    assert plain.basis == "none"
    padded = run(members + WEAK_INSTAGRAM, product)
    assert padded.get_status_code_id() == 1
    assert padded.reason == "mixed"
    assert padded.current_ddp_category.id == "mixed"


def test_other_strong_rejects():
    result = run(FACEBOOK_LIST, "instagram")
    assert result.get_status_code_id() == 1
    assert result.reason == "facebook"
    assert result.current_ddp_category.id == "facebook_detected"
    assert result.basis == "none"


def test_weak_only_is_accepted_at_either_step():
    thin = run(THIN, "instagram")
    assert thin.get_status_code_id() == 0
    assert thin.reason == "instagram"
    assert thin.basis == "weak"
    # Weak evidence never yields <other>_detected: at the Facebook step the
    # same archive is merely unknown.
    thin_fb = run(THIN, "facebook")
    assert thin_fb.get_status_code_id() == 1
    assert thin_fb.reason == "unknown"
    assert thin_fb.current_ddp_category.id == "unknown"
    assert thin_fb.basis == "none"

    both_products_weak = ["connections/friends/x.json", "connections/followers_and_following/x.json"]
    for product in ("instagram", "facebook"):
        result = run(both_products_weak, product)
        assert result.get_status_code_id() == 0
        assert result.reason == product
        assert result.basis == "weak"


def test_artifact_pairs_do_not_score():
    inside = score_members(["your_facebook_activity/messages/photos/1.jpg"])
    assert inside.facebook_strong == 2  # the root and the your_facebook_activity/messages pair
    assert inside.facebook_weak == 0
    alone = score_members(["messages/photos/1.jpg"])
    assert_zero(alone, "facebook")
    assert_zero(alone, "instagram")
    for product in ("instagram", "facebook"):
        assert run(["messages/photos/1.jpg"], product).reason == "unknown"


def test_nested_and_unknown_still_reachable():
    nested = run(NESTED)
    assert nested.get_status_code_id() == 1
    assert nested.reason == "nested_zip"
    assert nested.basis == "none"
    unknown = run(UNKNOWN)
    assert unknown.get_status_code_id() == 1
    assert unknown.reason == "unknown"
    assert unknown.basis == "none"
    bad = validate_meta(io.BytesIO(b"not a zip"), "instagram", instagram_categories())
    assert bad.get_status_code_id() == 1
    assert bad.reason == "bad_zip"
    assert bad.basis == "none"


def test_decide_is_pure_over_counts():
    def score(ig_strong=0, ig_weak=0, fb_strong=0, fb_weak=0, only_zips=False):
        return FolderScore(ig_strong, ig_weak, fb_strong, fb_weak, 0, 0, only_zips)

    assert decide(score(ig_strong=1), "instagram", 0) == ("instagram", "strong")
    assert decide(score(fb_strong=1), "instagram", 0) == ("facebook", "none")
    assert decide(score(ig_strong=1, fb_strong=1, ig_weak=9), "instagram", 0) == ("mixed", "none")
    assert decide(score(ig_weak=1, fb_weak=9), "instagram", 0) == ("instagram", "weak")
    assert decide(score(fb_weak=9), "instagram", 1) == ("instagram", "files")
    assert decide(score(only_zips=True), "instagram", 0) == ("nested_zip", "none")
    assert decide(score(), "instagram", 0) == ("unknown", "none")
    assert decide(score(fb_strong=1), "facebook", 0) == ("facebook", "strong")


def test_validate_meta_zip_in_zip():
    result = run(NESTED)
    assert result.get_status_code_id() == 1
    assert result.reason == "nested_zip"
    assert result.current_ddp_category.id == "nested_zip"


def test_validate_meta_unknown_and_bad_zip():
    unknown = run(UNKNOWN)
    assert unknown.get_status_code_id() == 1
    assert unknown.reason == "unknown"
    assert unknown.current_ddp_category.id == "unknown"
    bad = validate_meta(io.BytesIO(b"not a zip"), "instagram", instagram_categories())
    assert bad.get_status_code_id() == 1
    assert bad.reason == "bad_zip"
    assert bad.current_ddp_category.id == "bad_zip"
    assert bad.score is None


def test_validate_meta_leaves_upload_open():
    buf = make_zip(INSTAGRAM_JSON)
    validate_meta(buf, "instagram", instagram_categories())
    assert buf.closed is False
    assert buf.seek(0) == 0


def test_validate_meta_sets_archive_members():
    assert run(INSTAGRAM_JSON).archive_members == INSTAGRAM_JSON


def test_milestone_detail():
    accepted = run(INSTAGRAM_JSON)
    s = accepted.score
    assert accepted.milestone_detail == f"ig={s.instagram_strong}+{s.instagram_weak} fb=0+0 basis=strong"
    bad = validate_meta(io.BytesIO(b"not a zip"), "instagram", instagram_categories())
    assert bad.milestone_detail == ""
    assert isinstance(bad, MetaValidation)


def test_milestone_detail_renders_tiers():
    assert run(INSTAGRAM_JSON).milestone_detail == "ig=2+3 fb=0+0 basis=strong"
    assert run(THIN).milestone_detail == "ig=0+2 fb=0+0 basis=weak"
    zero = MetaValidation([], [], score=FolderScore(0, 0, 0, 0, 0, 0, False))
    assert zero.basis == "none"
    assert zero.files == 0
    assert zero.milestone_detail == "ig=0+0 fb=0+0 basis=none"
    on_files = MetaValidation([], [], score=FolderScore(0, 0, 0, 0, 0, 0, False), basis="files", files=3)
    assert on_files.milestone_detail == "ig=0+0 fb=0+0 basis=files files=3"


def test_category_ids_are_constants():
    allowed = {"json_en", "html_en", "facebook_detected", "instagram_detected", "mixed", "nested_zip", "unknown", "bad_zip"}
    for members in (INSTAGRAM_JSON, INSTAGRAM_HTML, THIN, FACEBOOK_LIST, MIXED_FEW_FB, MIXED_FEW_IG, NESTED, UNKNOWN):
        for product in ("instagram", "facebook"):
            assert run(members, product).current_ddp_category.id in allowed
    bad = validate_meta(io.BytesIO(b"not a zip"), "instagram", instagram_categories())
    assert bad.current_ddp_category.id in allowed


STUDY_TABLE = {
    "a": ("alpha", props.Translatable({"en": "Alpha", "nl": "Alfa"})),
    "b": ("beta", props.Translatable({"en": "Beta", "nl": "Beta"})),
}


def test_missing_study_categories_in_table_order():
    only_beta = run(INSTAGRAM_JSON + ["beta/x.json"])
    assert missing_study_categories(only_beta, STUDY_TABLE) == {"a": STUDY_TABLE["a"][1]}
    both = run(INSTAGRAM_JSON + ["alpha/x.json", "beta/x.json"])
    assert missing_study_categories(both, STUDY_TABLE) == {}
    neither = run(INSTAGRAM_JSON)
    assert list(missing_study_categories(neither, STUDY_TABLE)) == ["a", "b"]


def test_require_study_categories_marks_missing_and_rejects_when_all_absent():
    neither = run(INSTAGRAM_JSON)
    members = list(neither.archive_members)
    detail = neither.milestone_detail
    result = require_study_categories(neither, STUDY_TABLE)
    assert result.get_status_code_id() == 1
    assert result.reason == "no_study_categories"
    assert result.current_ddp_category.id == "no_study_categories"
    assert result.missing_study_labels == {"a": STUDY_TABLE["a"][1], "b": STUDY_TABLE["b"][1]}
    assert result.archive_members == members
    assert result.milestone_detail == detail

    partial = require_study_categories(run(INSTAGRAM_JSON + ["beta/x.json"]), STUDY_TABLE)
    assert partial.get_status_code_id() == 0
    assert partial.reason == "instagram"
    assert partial.missing_study_labels == {"a": STUDY_TABLE["a"][1]}

    rejected = run(FACEBOOK_LIST, "instagram")
    assert require_study_categories(rejected, STUDY_TABLE) is rejected
    assert rejected.reason == "facebook"
    assert rejected.missing_study_labels == {}


# A made-up extractor input set (ADR-0014): a plain name, a numbered-file
# pattern and a folder-qualified name.
TEST_INPUTS = frozenset({"following.json", r"re:(^|/)post_comments(?:_\d+)?\.json$", "media/stories.json"})


def test_resolved_inputs_counts_presence():
    members = [
        "following.json",
        "a/following.json",
        "post_comments_2.json",
        "media/stories.json",
        "x/stories.json",
    ]
    assert resolved_inputs(members, TEST_INPUTS) == 3
    assert resolved_inputs(members, frozenset()) == 0
    assert resolved_inputs(["x/stories.json"], TEST_INPUTS) == 0


def test_flattened_export_accepted_on_files_basis():
    flat = run(["following.json", "liked_posts.json"], inputs=TEST_INPUTS)
    assert flat.get_status_code_id() == 0
    assert flat.reason == "instagram"
    assert flat.basis == "files"
    assert flat.files == 1
    assert flat.current_ddp_category.id == "json_en"
    assert flat.milestone_detail.endswith("basis=files files=1")

    html = run(["following.html", "liked_posts.html", "x.json"], inputs=frozenset({"following.html"}))
    assert html.get_status_code_id() == 0
    assert html.basis == "files"
    assert html.current_ddp_category.id == "html_en"


def test_files_tier_only_after_weak():
    # The other product's weak marker never counts against ours, so the
    # files tier decides.
    other_weak = run(["following.json", "connections/friends/x.json"], inputs=TEST_INPUTS)
    assert other_weak.basis == "files"
    assert other_weak.reason == "instagram"
    # Our own weak marker wins over the files tier; the count is still recorded.
    own_weak = run(["following.json", "connections/followers_and_following/x.json"], inputs=TEST_INPUTS)
    assert own_weak.basis == "weak"
    assert own_weak.files == 1


def test_strong_other_still_rejects_with_files():
    result = run(["your_facebook_activity/x/y.json", "following.json"], inputs=TEST_INPUTS)
    assert result.get_status_code_id() == 1
    assert result.reason == "facebook"
    assert result.basis == "none"
    assert result.current_ddp_category.id == "facebook_detected"
    assert result.files == 1


def test_files_count_is_recorded_on_every_basis():
    members = INSTAGRAM_JSON + ["connections/followers_and_following/following.json"]
    result = run(members, inputs=TEST_INPUTS)
    assert result.basis == "strong"
    assert result.files == 1
    assert result.milestone_detail.endswith("basis=strong")
    assert run(INSTAGRAM_JSON, inputs=TEST_INPUTS).files == 0
