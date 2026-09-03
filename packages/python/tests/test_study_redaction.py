"""The study's redaction layer over the Google tables (algosoc-2026).

Unit-level: the two helpers and ``apply_study_redaction``. The fixture-driven
check that the layer holds over real exports lives in
``test_extractor_integration_google.py``.
"""

from collections import Counter

import numpy as np
import pandas as pd
import pytest

import port.api.props as props
from port.api.d3i_props import ExtractionResult, PropsUIPromptConsentFormTableViz
from port.helpers.study_redaction import (
    EMAIL_COLUMNS,
    EXPLICIT_COLUMNS,
    EXPLICIT_FILTERED_TABLES,
    EXPLICIT_REGEX,
    apply_study_redaction,
    filter_explicit_content,
    redact_emails,
)
from port.helpers.table_extractor import load_port_config
from port.platforms import google

#: The study's Google tables, in consent-form order — nine; Google News dropped
#: from the study 2026-09-03.
STUDY_TABLE_IDS = [
    "youtube_watch_history",
    "youtube_search_history",
    "youtube_subscriptions",
    "youtube_comments",
    "search_history",
    "chrome_history",
    "video_search_history",
    "ads_history",
    "discover_history",
]


def _table(table_id: str, df: pd.DataFrame) -> PropsUIPromptConsentFormTableViz:
    return PropsUIPromptConsentFormTableViz(
        id=table_id, title=props.Translatable({"en": table_id}), data_frame=df
    )


class TestRedactEmails:
    def test_addresses_replaced_and_blanks_stay_blank(self):
        df = pd.DataFrame({"Title": ["mail jane@example.org", None, np.nan, "plain"], "Details": ["x@y.zz", "", None, "d"]})
        out = redact_emails(df, EMAIL_COLUMNS)
        assert out["Title"].tolist()[0] == "mail [email]"
        assert out["Details"].tolist()[0] == "[email]"
        assert out["Title"].isna().tolist() == [False, True, True, False]
        assert "nan" not in out["Title"].dropna().tolist()

    def test_absent_column_is_skipped(self):
        df = pd.DataFrame({"Title": ["a@b.cc"]})
        out = redact_emails(df, ["Title", "Details"])
        assert out["Title"].tolist() == ["[email]"]
        assert list(out.columns) == ["Title"]


class TestFilterExplicitContent:
    def test_matching_rows_dropped_case_insensitively_and_index_reset(self):
        df = pd.DataFrame({
            "Title": ["Searched for cats", "Visited XHAMSTER.com", "Searched for dogs"],
            "URL": ["https://g/1", "https://g/2", "https://g/3"],
        })
        out = filter_explicit_content(df, EXPLICIT_COLUMNS)
        assert out["Title"].tolist() == ["Searched for cats", "Searched for dogs"]
        assert out.index.tolist() == [0, 1]

    def test_match_in_url_alone_drops_the_row(self):
        df = pd.DataFrame({"Title": ["Visited a page", "Visited another"], "URL": ["https://www.xvideos.com/x", "https://example.org"]})
        out = filter_explicit_content(df, EXPLICIT_COLUMNS)
        assert out["Title"].tolist() == ["Visited another"]

    def test_missing_values_never_match(self):
        df = pd.DataFrame({"Title": [None, np.nan], "URL": ["https://example.org", None]})
        out = filter_explicit_content(df, EXPLICIT_COLUMNS)
        assert len(out) == 2

    def test_absent_column_raises_rather_than_passing_rows_through(self):
        df = pd.DataFrame({"Title": ["porn", "ok"]})
        with pytest.raises(KeyError):
            filter_explicit_content(df, ["Title", "URL"])

    def test_empty_frame_returned_as_is(self):
        df = pd.DataFrame({"Title": [], "URL": []})
        assert filter_explicit_content(df, EXPLICIT_COLUMNS).empty

    def test_regex_is_lowercase_only_by_design(self):
        # The keyword list is matched after lowercasing the cell; the compiled
        # regex itself has no IGNORECASE flag, so callers must lowercase first.
        assert EXPLICIT_REGEX.search("xhamster.com") is not None
        assert EXPLICIT_REGEX.search("XHAMSTER.COM") is None


class TestApplyStudyRedaction:
    def _result(self) -> ExtractionResult:
        return ExtractionResult(
            tables=[
                _table("youtube_watch_history", pd.DataFrame({"Title": ["Watched porn documentary review", "x@y.zz wrote"], "Details": [None, "c@d.ee"]})),
                _table("search_history", pd.DataFrame({"Title": ["Searched for porn", "Searched for cats a@b.cc"], "URL": ["u1", "u2"], "Details": ["", ""]})),
                _table("ads_history", pd.DataFrame({"Title": ["porn ad"], "URL": ["u"]})),
            ],
            errors=Counter({"SomeError": 2}),
        )

    def test_only_the_named_tables_are_filtered(self):
        out = apply_study_redaction(self._result())
        by_id = {t.id: t.data_frame for t in out.tables}
        # YouTube keeps both rows — it is not in the filtered set.
        assert by_id["youtube_watch_history"]["Title"].tolist()[0] == "Watched porn documentary review"
        # search_history loses the explicit row and keeps the other, redacted.
        assert by_id["search_history"]["Title"].tolist() == ["Searched for cats [email]"]

    def test_emails_redacted_in_every_table(self):
        out = apply_study_redaction(self._result())
        yt = {t.id: t.data_frame for t in out.tables}["youtube_watch_history"]
        assert yt["Title"].tolist()[1] == "[email] wrote"
        assert yt["Details"].tolist()[1] == "[email]"
        assert pd.isna(yt["Details"].tolist()[0])

    def test_table_emptied_by_the_filter_is_dropped(self):
        out = apply_study_redaction(self._result())
        assert [t.id for t in out.tables] == ["youtube_watch_history", "search_history"]

    def test_errors_and_order_preserved(self):
        out = apply_study_redaction(self._result())
        assert out.errors == Counter({"SomeError": 2})

    def test_filtered_table_without_scanned_columns_fails_closed(self):
        result = ExtractionResult(
            tables=[_table("chrome_history", pd.DataFrame({"Title": ["porn"], "Details": ["x"]}))],
            errors=Counter(),
        )
        with pytest.raises(ValueError, match="chrome_history"):
            apply_study_redaction(result)

    def test_empty_result_stays_empty(self):
        out = apply_study_redaction(ExtractionResult(tables=[], errors=Counter()))
        assert out.tables == []


class TestStudyTableSet:
    """The study's set is expressed by the registry (what every generated config —
    including the one the deployed selector regenerates — is built from) and by
    the committed config; the two must agree."""

    def test_registry_holds_exactly_the_study_extractors_in_order(self):
        assert list(google.EXTRACTOR_REGISTRY) == [f"{tid}_to_df" for tid in STUDY_TABLE_IDS]

    def test_config_lists_exactly_the_study_tables_in_order(self):
        config = load_port_config(google.EXTRACTOR_REGISTRY, "google")
        assert [t.id for t in config] == STUDY_TABLE_IDS

    def test_filtered_tables_are_study_tables(self):
        assert EXPLICIT_FILTERED_TABLES <= set(STUDY_TABLE_IDS)

    def test_no_study_table_carries_a_locations_header(self):
        config = load_port_config(google.EXTRACTOR_REGISTRY, "google")
        for t in config:
            assert "Locations" not in (t.headers or {}), t.id
