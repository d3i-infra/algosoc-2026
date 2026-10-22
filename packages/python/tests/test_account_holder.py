import functools

import pandas as pd

from port.helpers.account_holder import AccountHolder, attempt, cleaned, redact_account_holder, whole_token

JANE = AccountHolder(names=("Jane Example",), identifier="jane.example")

def test_attempt_returns_the_default_when_the_source_raises():
    def boom(): raise ValueError("x")
    assert attempt(boom, []) == []

def test_cleaned_sorts_longest_first_and_drops_short_and_duplicate_names():
    assert cleaned(["Jo", "Jane  Example", "jane example", "Jane Example", "J", None]) == ["Jane Example", "jane example", "Jo"]

def test_whole_token_keeps_dots_literal():
    assert whole_token("jane.example") == r"(?<!\w)jane\.example(?!\w)"

def test_text_columns_none_means_every_non_link_column():
    frame = pd.DataFrame({"Author": ["jane.example", "other"], "URL": ["https://x/jane.example/p/1", "https://x/other/p/2"]})
    redact_account_holder([frame], JANE, text_columns=None, link_columns=["URL"])
    assert list(frame["Author"]) == ["[user]", "other"]
    assert list(frame["URL"]) == ["https://x/[user]/p/1", "https://x/other/p/2"]

def test_an_explicit_text_column_list_leaves_other_columns():
    frame = pd.DataFrame({"Title": ["Jane Example"], "Other": ["Jane Example"]})
    redact_account_holder([frame], JANE, text_columns=["Title"], link_columns=[])
    assert list(frame["Title"]) == ["[user]"] and list(frame["Other"]) == ["Jane Example"]

def test_missing_values_stay_missing():
    frame = pd.DataFrame({"Title": ["Jane Example", None]})
    redact_account_holder([frame], JANE, text_columns=None, link_columns=[])
    assert list(frame["Title"].isna()) == [False, True]

def test_single_words_whole_cell_keeps_a_one_word_name_out_of_longer_text():
    donald = AccountHolder(names=("Donald", "Jane Example"), identifier=None)
    frame = pd.DataFrame({"Author": ["Donald", " donald ", "Donald Trump", "thanks Donald!", "Jane Example wrote"]})
    redact_account_holder([frame], donald, text_columns=None, link_columns=[], single_words_whole_cell=True)
    assert list(frame["Author"]) == ["[user]", "[user]", "Donald Trump", "thanks Donald!", "[user] wrote"]

def test_the_default_matches_a_one_word_name_wherever_it_stands_alone():
    donald = AccountHolder(names=("Donald",), identifier=None)
    frame = pd.DataFrame({"Author": ["Donald Trump"]})
    redact_account_holder([frame], donald, text_columns=None, link_columns=[])
    assert list(frame["Author"]) == ["[user] Trump"]  # Facebook's behaviour, unchanged

def test_skip_columns_are_left_alone():
    holder = AccountHolder(names=(), identifier="1998")
    frame = pd.DataFrame({"Author": ["1998", "other"], "Date": ["1998-10-22 09:46:00"] * 2})
    redact_account_holder([frame], holder, text_columns=None, link_columns=[], skip_columns=["Date"])
    assert list(frame["Author"]) == ["[user]", "other"]
    assert list(frame["Date"]) == ["1998-10-22 09:46:00"] * 2

def test_attempt_survives_a_source_without_a_name():
    assert attempt(functools.partial(lambda x: 1 / x, 0), "default") == "default"
