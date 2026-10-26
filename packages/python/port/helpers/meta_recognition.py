"""Which Meta product an export is, judged from the folder names in its archive.

Instagram and Facebook "Download your information" archives share a layout but
each has folders the other lacks. This helper scores a list of archive member
paths against each product's folder markers, so a platform can recognise its
export by structure rather than by file contents. Instagram uses it now;
Facebook uses it next. It knows nothing about any platform module.
"""

import logging
import zipfile
from dataclasses import dataclass

from port.api.file_utils import SeekableBinaryReader
from port.helpers.validate import (
    DDPCategory,
    DDPFiletype,
    Language,
    StatusCode,
    ValidateInput,
)

logger = logging.getLogger(__name__)

INSTAGRAM_FOLDER_MARKERS = frozenset(
    {
        "your_instagram_activity",
        "apps_and_websites_off_of_instagram",
        "ads_information/ads_and_topics",
        "ads_information/instagram_ads_and_businesses",
        "apps_and_websites_off_of_instagram/apps_and_websites",
        "connections/contacts",
        "connections/followers_and_following",
        "logged_information/link_history",
        "logged_information/past_instagram_insights",
        "logged_information/policy_updates_and_permissions",
        "logged_information/recent_searches",
        "media/other",
        "media/posts",
        "media/stories",
        "personal_information/autofill_information",
        "personal_information/device_information",
        "personal_information/information_about_you",
        "personal_information/personal_information",
        "preferences/settings",
        "preferences/your_topics",
        "security_and_login_information/login_and_profile_creation",
        "your_instagram_activity/ai",
        "your_instagram_activity/avatars_store",
        "your_instagram_activity/comments",
        "your_instagram_activity/edits",
        "your_instagram_activity/events",
        "your_instagram_activity/fundraisers",
        "your_instagram_activity/gifts",
        "your_instagram_activity/instants",
        "your_instagram_activity/likes",
        "your_instagram_activity/media",
        "your_instagram_activity/messages",
        "your_instagram_activity/meta_spark",
        "your_instagram_activity/monetization",
        "your_instagram_activity/other_activity",
        "your_instagram_activity/reports",
        "your_instagram_activity/saved",
        "your_instagram_activity/shared_access",
        "your_instagram_activity/shopping",
        "your_instagram_activity/story_interactions",
        "your_instagram_activity/subscriptions",
        "your_instagram_activity/threads",
        "your_topics/your_ads_see_more",
    }
)

FACEBOOK_FOLDER_MARKERS = frozenset(
    {
        "your_facebook_activity",
        "apps_and_websites_off_of_facebook",
        "comments_and_reactions/icons",
        "connections/followers",
        "connections/friends",
        "logged_information/activity_messages",
        "logged_information/in-app_messages",
        "logged_information/interactions",
        "logged_information/location",
        "logged_information/notifications",
        "logged_information/other_logged_information",
        "logged_information/search",
        "media/stickers_used",
        "media/your_posts",
        "messages/e2ee_cutover",
        "messages/filtered_threads",
        "messages/photos",
        "messages/stickers_used",
        "personal_information/avatars_store",
        "personal_information/facebook_assistant",
        "personal_information/facebook_portal",
        "personal_information/health_professional",
        "personal_information/other_personal_information",
        "personal_information/profile_information",
        "posts/album",
        "posts/media",
        "preferences/feed",
        "preferences/memories",
        "preferences/preferences",
        "your_facebook_activity/ai",
        "your_facebook_activity/bug_bounty",
        "your_facebook_activity/comments_and_reactions",
        "your_facebook_activity/events",
        "your_facebook_activity/facebook_gaming",
        "your_facebook_activity/facebook_marketplace",
        "your_facebook_activity/facebook_payments",
        "your_facebook_activity/facebook_support",
        "your_facebook_activity/fundraisers",
        "your_facebook_activity/groups",
        "your_facebook_activity/live_videos",
        "your_facebook_activity/messages",
        "your_facebook_activity/meta_spark",
        "your_facebook_activity/navigation_bar",
        "your_facebook_activity/other_activity",
        "your_facebook_activity/pages",
        "your_facebook_activity/polls",
        "your_facebook_activity/posts",
        "your_facebook_activity/reels",
        "your_facebook_activity/reviews",
        "your_facebook_activity/saved_items_and_collections",
        "your_facebook_activity/shops",
        "your_facebook_activity/stories",
        "your_facebook_activity/voting",
        "your_facebook_activity/your_places",
    }
)

MARKERS: dict[str, frozenset[str]] = {
    "instagram": INSTAGRAM_FOLDER_MARKERS,
    "facebook": FACEBOOK_FOLDER_MARKERS,
}

OTHER_PRODUCT: dict[str, str] = {"instagram": "facebook", "facebook": "instagram"}


def kept(members: list[str]) -> list[str]:
    """The members worth looking at: no macOS resource-fork copies, no dotfiles."""
    result = []
    for member in members:
        segments = [s for s in member.split("/") if s]
        if "__MACOSX" in segments or (segments and segments[-1].startswith(".")):
            continue
        result.append(member)
    return result


def folder_names(members: list[str]) -> frozenset[str]:
    """Every folder segment of every kept member."""
    names: set[str] = set()
    for member in kept(members):
        segments = [s for s in member.split("/") if s]
        names.update(segments if member.endswith("/") else segments[:-1])
    return frozenset(names)


def folder_pairs(members: list[str]) -> frozenset[str]:
    """Every consecutive "parent/child" of the folders of every kept member."""
    pairs: set[str] = set()
    for member in kept(members):
        segments = [s for s in member.split("/") if s]
        folders = segments if member.endswith("/") else segments[:-1]
        pairs.update(f"{parent}/{child}" for parent, child in zip(folders, folders[1:]))
    return frozenset(pairs)


@dataclass(frozen=True)
class FolderScore:
    """How many distinct markers of each product the members match, how many
    JSON and HTML files there are, and whether the archive holds only zips."""

    instagram: int
    facebook: int
    json_files: int
    html_files: int
    only_zips: bool

    def count(self, product: str) -> int:
        """The marker count for *product*, "instagram" or "facebook"."""
        return getattr(self, product)


def score_members(members: list[str]) -> FolderScore:
    """Score *members* against each product's folder markers."""
    present = folder_names(members) | folder_pairs(members)
    files = [m for m in kept(members) if not m.endswith("/")]
    return FolderScore(
        instagram=len(INSTAGRAM_FOLDER_MARKERS & present),
        facebook=len(FACEBOOK_FOLDER_MARKERS & present),
        json_files=sum(m.endswith(".json") for m in files),
        html_files=sum(m.endswith(".html") for m in files),
        only_zips=bool(files) and all(m.lower().endswith(".zip") for m in files),
    )


@dataclass
class MetaValidation(ValidateInput):
    """A ValidateInput that also records why an archive was or was not accepted."""

    reason: str = "unknown"
    score: FolderScore | None = None

    @property
    def milestone_detail(self) -> str:
        """Marker counts for a host milestone; never a path or member name."""
        if self.score is None:
            return ""
        return f"ig={self.score.instagram} fb={self.score.facebook}"


def _rejection(reason_id: str) -> DDPCategory:
    return DDPCategory(
        id=reason_id,
        ddp_filetype=DDPFiletype.UNKOWN,
        language=Language.UNKNOWN,
        known_files=[],
    )


def validate_meta(
    archive: SeekableBinaryReader,
    product: str,
    categories: list[DDPCategory],
) -> MetaValidation:
    """Accept *archive* if its folder names show it is *product*'s export.

    Reads only the member list (ADR-0026) and leaves the upload open.
    """
    validation = MetaValidation(
        [
            StatusCode(id=0, description="Recognised export"),
            StatusCode(id=1, description="Not a recognised export"),
        ],
        categories,
    )
    other = OTHER_PRODUCT[product]

    try:
        with zipfile.ZipFile(archive, "r") as zf:
            members = zf.namelist()
    except zipfile.BadZipFile:
        validation.reason = "bad_zip"
        validation.set_current_status_code_by_id(1)
        validation.current_ddp_category = _rejection("bad_zip")
        logger.info("Meta validation: product=%s reason=bad_zip", product)
        return validation

    validation.archive_members = members
    score = score_members(members)
    validation.score = score
    ours, theirs = score.count(product), score.count(other)

    if ours >= 1 and theirs == 0:
        wanted = DDPFiletype.HTML if score.html_files > score.json_files else DDPFiletype.JSON
        validation.reason = product
        validation.set_current_status_code_by_id(0)
        validation.current_ddp_category = next(
            (c for c in categories if c.ddp_filetype == wanted), None
        )
    else:
        if theirs >= 1 and ours == 0:
            validation.reason = other
            category_id = f"{other}_detected"
        elif ours >= 1 and theirs >= 1:
            validation.reason = category_id = "mixed"
        elif score.only_zips:
            validation.reason = category_id = "nested_zip"
        else:
            validation.reason = category_id = "unknown"
        validation.set_current_status_code_by_id(1)
        validation.current_ddp_category = _rejection(category_id)

    logger.info(
        "Meta validation: product=%s reason=%s own=%d other=%d",
        product, validation.reason, ours, theirs,
    )
    return validation
