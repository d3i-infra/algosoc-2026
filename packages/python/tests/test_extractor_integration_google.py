"""Integration tests for Google extractor functions.

Requires a real Google Takeout DDP zip at::

    tests/ddp/Google_<anything>.zip

Tests skip when no fixture is found — CI runs clean without real data.
"""
import pytest

from collections import Counter

from extractor_integration_helpers import ExtractorSpec, find_fixture
from port.helpers.extraction_helpers import ZipArchiveReader
from port.platforms.google import (
    validate_ddp,
    youtube_watch_history_to_df,
    youtube_search_history_to_df,
    youtube_subscriptions_to_df,
    youtube_comments_to_df,
)

SPECS = [
    ExtractorSpec(name="youtube_watch_history_to_df", extractor=youtube_watch_history_to_df),
    ExtractorSpec(name="youtube_search_history_to_df", extractor=youtube_search_history_to_df),
    ExtractorSpec(name="youtube_subscriptions_to_df", extractor=youtube_subscriptions_to_df),
    ExtractorSpec(name="youtube_comments_to_df", extractor=youtube_comments_to_df),
]

@pytest.fixture(scope="module")
def google_reader():
    fixture = find_fixture("google")
    if fixture is None:
        pytest.skip("No Google_*.zip fixture found in tests/ddp/")
    validation = validate_ddp(str(fixture))
    for spec in SPECS: #adds the locale, extractors need it to find their file
        spec.kwargs = {'locale': validation.locale}
    return ZipArchiveReader(str(fixture), validation.archive_members, Counter())

@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_extractor_not_empty(spec, google_reader):
    df = spec.run(google_reader)
    assert not df.empty, (
        f"{spec.name} returned an empty DataFrame — the extractor may have "
        "crashed, found no matching file, or the DDP format changed."
    )
