"""Which Meta product an export is, judged from the member names in its archive.

Instagram and Facebook "Download your information" archives share a layout but
each has folders the other lacks. This helper scores a list of archive member
paths against each product's markers, so a platform can recognise its export by
structure rather than by file contents. Both Instagram and Facebook validate through it.
It knows nothing about any platform module.

Markers come in three shapes:

- a folder name, matched against every folder segment of every member;
- a consecutive "parent/child" folder pair;
- a "folder/stem" file marker: the folder a file sits directly in and its
  basename without extension.

File markers exist because two Facebook categories, ``ads_information`` and
``security_and_login_information``, write their files directly in the folder
with no subfolder, so an export holding only those categories has no folder
pair to score. Instagram's file-marker set is empty: it always nests one
folder deeper.

Markers fall into two tiers. The **strong** tier is curated: each product's
named roots (``your_<product>_activity``, ``apps_and_websites_off_of_<product>``),
every pair under those roots, and four verified leaves that carry the product's
name. The **weak** tier is everything else: the sample-derived pairs under the
shared top-level folders, and the file markers. Weak markers only argue for a
product; they never count against the other one, so the same weak-only archive
may validate at either product's step.

A third tier, **files**, holds no markers of its own: it is the inputs the
product's extractors declare, resolved the way the extractors resolve them
(``member_matches``: an exact path or a path-boundary suffix, the
apostrophe-to-underscore variant on the request only; a ``re:`` input is a
regex searched against every kept member). The count of inputs with at least
one match is recorded on every basis, and decides only when neither strong nor
weak evidence does. With no strong evidence of either product, validation
accepts whenever a declared input resolves; strong evidence of the other
product, and strong evidence of both (``mixed``), are the deliberate
exceptions, rejected even where an extractor would find a file.

The error ordering behind the tiers: the full extent of participant export
layouts is unknowable, so a false rejection of a genuine export on a layout we
did not anticipate is the worst outcome and a thin, empty or mislabelled
wrong-product donation the lesser one. Only strong evidence can reject.
"""

import logging
import re
import zipfile
from dataclasses import dataclass, field
from typing import Literal

import port.api.props as props
from port.api.file_utils import SeekableBinaryReader
from port.helpers.extraction_helpers import member_matches
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

# Pairs seen in a Facebook sample that also occur inside Instagram's
# ``your_instagram_activity/messages`` tree or are plain media layout; they are
# deleted from the Facebook marker set, not filtered at scoring time.
FACEBOOK_PAIR_ARTIFACTS: frozenset[str] = frozenset(
    {
        "messages/e2ee_cutover",
        "messages/filtered_threads",
        "messages/photos",
        "messages/stickers_used",
        "posts/album",
        "posts/media",
        "media/stickers_used",
        "media/your_posts",
        "comments_and_reactions/icons",
    }
)

FACEBOOK_FOLDER_MARKERS = frozenset(
    {
        "your_facebook_activity",
        "apps_and_websites_off_of_facebook",
        "connections/followers",
        "connections/friends",
        "logged_information/activity_messages",
        "logged_information/in-app_messages",
        "logged_information/interactions",
        "logged_information/location",
        "logged_information/notifications",
        "logged_information/other_logged_information",
        "logged_information/search",
        "personal_information/avatars_store",
        "personal_information/facebook_assistant",
        "personal_information/facebook_portal",
        "personal_information/health_professional",
        "personal_information/other_personal_information",
        "personal_information/profile_information",
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

# The strong tier: product-named roots, every pair under them, and four leaves
# verified to carry the product's name. Only these can reject an upload.
STRONG_ROOTS: dict[str, frozenset[str]] = {
    "instagram": frozenset({"your_instagram_activity", "apps_and_websites_off_of_instagram"}),
    "facebook": frozenset({"your_facebook_activity", "apps_and_websites_off_of_facebook"}),
}

STRONG_LEAVES: dict[str, frozenset[str]] = {
    "instagram": frozenset(
        {
            "ads_information/instagram_ads_and_businesses",
            "logged_information/past_instagram_insights",
        }
    ),
    "facebook": frozenset(
        {
            "personal_information/facebook_portal",
            "personal_information/facebook_assistant",
        }
    ),
}


def _strong_markers(product: str) -> frozenset[str]:
    roots = STRONG_ROOTS[product]
    under_roots = frozenset(m for m in MARKERS[product] if m.split("/")[0] in roots)
    return roots | under_roots | STRONG_LEAVES[product]


STRONG_MARKERS: dict[str, frozenset[str]] = {p: _strong_markers(p) for p in MARKERS}

# The weak tier: every other folder marker. File markers (below) are weak too.
WEAK_MARKERS: dict[str, frozenset[str]] = {p: MARKERS[p] - STRONG_MARKERS[p] for p in MARKERS}

INSTAGRAM_FILE_MARKERS: frozenset[str] = frozenset()

# Both spellings where Meta writes an apostrophe or an underscore.
FACEBOOK_FILE_MARKERS = frozenset(
    {
        "ads_information/ad_preferences",
        "ads_information/advertisers_using_your_activity_or_information",
        "ads_information/advertisers_you've_interacted_with",
        "ads_information/advertisers_you_ve_interacted_with",
        "ads_information/apps_detected_from_your_activity",
        "ads_information/apps_detected_on_your_account",
        "ads_information/meta_ad_library_profiles",
        "ads_information/other_categories_used_to_reach_you",
        "ads_information/settings_for_ads_shown_outside_of_meta",
        "ads_information/story_views_in_past_7_days",
        "ads_information/subscription_for_no_ads",
        "ads_information/your_pages_mentions",
        "ads_information/your_recent_reported_conversions",
        "ads_information/your_sampled_locations",
        "security_and_login_information/account_activity",
        "security_and_login_information/browser_cookies",
        "security_and_login_information/device_login_cookies",
        "security_and_login_information/email_address_verifications",
        "security_and_login_information/information_about_your_last_login",
        "security_and_login_information/ip_address_activity",
        "security_and_login_information/login_messages_we_have_shown",
        "security_and_login_information/login_protection_data",
        "security_and_login_information/logins_and_logouts",
        "security_and_login_information/recognized_devices",
        "security_and_login_information/record_details",
        "security_and_login_information/registration_information",
        "security_and_login_information/two-factor_authentication",
        "security_and_login_information/where_you're_logged_in",
        "security_and_login_information/where_you_re_logged_in",
        "security_and_login_information/your_facebook_activity_history",
        "security_and_login_information/your_profile_confirmation_information",
    }
)

FILE_MARKERS: dict[str, frozenset[str]] = {
    "instagram": INSTAGRAM_FILE_MARKERS,
    "facebook": FACEBOOK_FILE_MARKERS,
}

OTHER_PRODUCT: dict[str, str] = {"instagram": "facebook", "facebook": "instagram"}

# A study's categories: key -> (export folder, soft-confirm label).
StudyCategories = dict[str, tuple[str, props.Translatable]]


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


def file_stems(members: list[str]) -> frozenset[str]:
    """Every "folder/stem" of every kept file member that sits inside a folder.

    The stem is the basename without its final extension; a basename with no
    dot keeps its full name.
    """
    stems: set[str] = set()
    for member in kept(members):
        if member.endswith("/"):
            continue
        segments = [s for s in member.split("/") if s]
        if len(segments) < 2:
            continue
        folder, basename = segments[-2], segments[-1]
        stem = basename.rsplit(".", 1)[0]
        stems.add(f"{folder}/{stem}")
    return frozenset(stems)


@dataclass(frozen=True)
class FolderScore:
    """How many distinct strong and weak markers of each product the members
    match, how many JSON and HTML files there are, and whether the archive
    holds only zips."""

    instagram_strong: int
    instagram_weak: int
    facebook_strong: int
    facebook_weak: int
    json_files: int
    html_files: int
    only_zips: bool

    def strong(self, product: str) -> int:
        """The strong-marker count for *product*, "instagram" or "facebook"."""
        return getattr(self, f"{product}_strong")

    def weak(self, product: str) -> int:
        """The weak-marker count for *product*, "instagram" or "facebook"."""
        return getattr(self, f"{product}_weak")


def score_members(members: list[str]) -> FolderScore:
    """Score *members* against each product's folder and file markers, by tier."""
    present = folder_names(members) | folder_pairs(members)
    stems = file_stems(members)
    files = [m for m in kept(members) if not m.endswith("/")]

    def weak(product: str) -> int:
        return len(WEAK_MARKERS[product] & present) + len(FILE_MARKERS[product] & stems)

    return FolderScore(
        instagram_strong=len(STRONG_MARKERS["instagram"] & present),
        instagram_weak=weak("instagram"),
        facebook_strong=len(STRONG_MARKERS["facebook"] & present),
        facebook_weak=weak("facebook"),
        json_files=sum(m.endswith(".json") for m in files),
        html_files=sum(m.endswith(".html") for m in files),
        only_zips=bool(files) and all(m.lower().endswith(".zip") for m in files),
    )


REGEX_INPUT = "re:"


def resolved_inputs(members: list[str], inputs: frozenset[str]) -> int:
    """How many of *inputs* have at least one kept member matching, resolved
    as the extractors resolve them: ``member_matches`` for a plain name, or
    ``re.search`` over every kept member for a ``re:<pattern>`` input.

    Presence is what counts; a name matching several members is extraction's
    concern (``ZipArchiveReader.resolve_member``), not validation's.
    """
    files = [m for m in kept(members) if not m.endswith("/")]
    count = 0
    for name in inputs:
        if name.startswith(REGEX_INPUT):
            pattern = re.compile(name[len(REGEX_INPUT):])
            if any(pattern.search(m) for m in files):
                count += 1
        elif any(member_matches(m, name) for m in files):
            count += 1
    return count


Basis = Literal["strong", "weak", "files", "none"]


def decide(score: FolderScore, product: str, files: int) -> tuple[str, Basis]:
    """The reason and basis for *product*'s step, from *score* and the number
    of extractor input *files* that resolved.

    Strong evidence decides first: ours alone accepts, theirs alone names the
    other product, both is ``mixed``. With no strong evidence either way, any
    weak marker of ours accepts, then any resolved file; otherwise the archive
    is ``nested_zip`` or ``unknown``. Weak markers of the other product never
    count against ours.
    """
    other = OTHER_PRODUCT[product]
    ours, theirs = score.strong(product), score.strong(other)
    if ours and not theirs:
        return product, "strong"
    if theirs and not ours:
        return other, "none"
    if ours and theirs:
        return "mixed", "none"
    if score.weak(product) >= 1:
        return product, "weak"
    if files >= 1:
        return product, "files"
    if score.only_zips:
        return "nested_zip", "none"
    return "unknown", "none"


@dataclass
class MetaValidation(ValidateInput):
    """A ValidateInput that also records why an archive was or was not accepted."""

    reason: str = "unknown"
    basis: Basis = "none"
    files: int = 0
    score: FolderScore | None = None
    missing_study_labels: dict[str, props.Translatable] = field(default_factory=dict)

    @property
    def milestone_detail(self) -> str:
        """Tiered marker counts and the basis for a host milestone; never a
        path or member name."""
        if self.score is None:
            return ""
        s = self.score
        detail = (
            f"ig={s.instagram_strong}+{s.instagram_weak}"
            f" fb={s.facebook_strong}+{s.facebook_weak}"
            f" basis={self.basis}"
        )
        if self.basis == "files":
            detail += f" files={self.files}"
        return detail


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
    inputs: frozenset[str] = frozenset(),
) -> MetaValidation:
    """Accept *archive* if its folder names show it is *product*'s export,
    on the strong or the weak basis, or if any of the extractor *inputs*
    resolves in it, on the files basis; reject only on strong evidence of
    the other product, or when nothing argues for ours.

    The resolved-input count is a fact about the archive and is recorded
    whatever basis wins. Reads only the member list (ADR-0026) and leaves
    the upload open.
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
    validation.files = resolved_inputs(members, inputs)
    reason, basis = decide(score, product, validation.files)
    validation.reason, validation.basis = reason, basis

    if reason == product:
        wanted = DDPFiletype.HTML if score.html_files > score.json_files else DDPFiletype.JSON
        validation.set_current_status_code_by_id(0)
        validation.current_ddp_category = next(
            (c for c in categories if c.ddp_filetype == wanted), None
        )
    else:
        category_id = f"{other}_detected" if reason == other else reason
        validation.set_current_status_code_by_id(1)
        validation.current_ddp_category = _rejection(category_id)

    logger.info(
        "Meta validation: product=%s reason=%s %s",
        product, validation.reason, validation.milestone_detail,
    )
    return validation


def missing_study_categories(
    validation: MetaValidation, table: StudyCategories
) -> dict[str, props.Translatable]:
    """The entries of *table* whose folder is absent from the archive, in
    table order. The folder matches at any depth on purpose: Drive downloads
    wrap the export in two folders, so "top-level" is not knowable from the
    member list. A nested folder that shares a category name counts as present;
    that errs toward accepting the export, which is the safe side now that
    ``require_study_categories`` rejects on this result.

    This is not the ``FlowBuilder.missing_products`` hook: the Meta platforms
    keep the base hook, which returns ``{}``."""
    present = folder_names(validation.archive_members)
    return {key: label for key, (folder, label) in table.items() if folder not in present}


def require_study_categories(validation: MetaValidation, table: StudyCategories) -> MetaValidation:
    """Record which of *table*'s categories a recognised export lacks, and
    downgrade one holding none of them to a rejection: continuing would end
    on the no-data page, which the host counts as a completion with nothing
    donated. A rejected validation passes through untouched.

    An export in which an extractor input resolved (``files >= 1``) is never
    rejected here, whatever its basis: an extractor would read it, so the
    study has something to show. On the files basis the folder table says
    nothing about the layout, so no category is reported missing.

    *table* must be non-empty: with an empty table every recognised export
    holding no resolvable input would count as missing everything and be
    rejected."""
    if validation.get_status_code_id() != 0:
        return validation
    if validation.basis == "files":
        validation.missing_study_labels = {}
    else:
        validation.missing_study_labels = missing_study_categories(validation, table)
    if len(validation.missing_study_labels) == len(table) and validation.files == 0:
        validation.reason = "no_study_categories"
        validation.current_ddp_category = _rejection("no_study_categories")
        validation.set_current_status_code_by_id(1)
    return validation
