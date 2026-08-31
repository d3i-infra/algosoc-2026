"""Study-side anonymization helpers (algosoc-2026): email and username redaction.

These helpers are study-local — they are applied inside each platform's
``extraction()`` after the tables are built, so they must leave missing cells
missing (never the literal text "nan") and must not redact inside unrelated
words when the username is short.
"""

import numpy as np
import pandas as pd
import pytest

from port.helpers.extraction_helpers import (
    EMAIL_PATTERN,
    anonymize_dataframe,
    replace_email,
    replace_username,
)


class TestReplaceEmail:
    def test_replaces_every_address(self):
        text = "mail me at jane.doe+x@example.org or JANE@Example.co.uk today"
        assert replace_email(text) == "mail me at [email] or [email] today"

    def test_leaves_text_without_addresses_untouched(self):
        assert replace_email("no address here @ all") == "no address here @ all"

    def test_pattern_is_shared(self):
        assert EMAIL_PATTERN.search("a@b.cc") is not None


class TestReplaceUsername:
    def test_case_insensitive_whole_word(self):
        assert replace_username("Hi Jane, JANE and jane!", "jane") == "Hi [user], [user] and [user]!"

    def test_short_username_does_not_hit_unrelated_words(self):
        # "al" is a plausible two-letter username; it must not redact "already"
        # or "alcohol", only the standalone token.
        assert replace_username("al already drank alcohol, al.", "al") == "[user] already drank alcohol, [user]."

    def test_username_with_regex_metacharacters(self):
        assert replace_username("ping j.doe (j.doe) now", "j.doe") == "ping [user] ([user]) now"

    def test_username_adjacent_to_punctuation(self):
        assert replace_username("@al: al's turn", "al") == "@[user]: [user]'s turn"


class TestAnonymizeDataframe:
    def test_missing_cells_stay_missing(self):
        df = pd.DataFrame({"Title": ["a@b.cc", None, np.nan, "plain"]})
        anonymize_dataframe(df, ["Title"])
        assert df["Title"].tolist()[0] == "[email]"
        assert df["Title"].tolist()[3] == "plain"
        assert df["Title"].isna().tolist() == [False, True, True, False]
        assert "nan" not in df["Title"].dropna().tolist()
        assert "None" not in df["Title"].dropna().tolist()
        # The wire form the consent UI receives: a missing cell is JSON null,
        # exactly like an untouched column, never the text "nan".
        assert '"1":null' in df.to_json() and '"2":null' in df.to_json()

    def test_username_replaced_only_as_whole_word(self):
        df = pd.DataFrame({"Details": ["al liked this", "already", None]})
        anonymize_dataframe(df, ["Details"], username="al")
        assert df["Details"].tolist()[0] == "[user] liked this"
        assert df["Details"].tolist()[1] == "already"
        assert pd.isna(df["Details"].tolist()[2])

    def test_absent_columns_are_skipped_and_frame_mutated_in_place(self):
        df = pd.DataFrame({"Title": ["x@y.zz"], "Other": [1]})
        out = anonymize_dataframe(df, ["Title", "Missing"], username="x")
        assert out is df
        assert df["Title"].tolist() == ["[email]"]
        assert df["Other"].tolist() == [1]

    def test_empty_username_means_no_username_pass(self):
        df = pd.DataFrame({"Title": ["nothing to do"]})
        anonymize_dataframe(df, ["Title"], username="")
        assert df["Title"].tolist() == ["nothing to do"]

    def test_empty_frame_is_a_no_op(self):
        df = pd.DataFrame({"Title": pd.Series([], dtype="object")})
        anonymize_dataframe(df, ["Title"], username="jane")
        assert df.empty
