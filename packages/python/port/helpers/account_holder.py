"""Whose export this is, and the redaction of it from extracted tables.

The convention shared by every platform: each fact about the account holder is
asked of the export's sources in a fixed order, and every source is silent on
absence. Nothing found is an expected outcome, not an error.
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence, TypeVar

import pandas as pd

import port.helpers.extraction_helpers as eh

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class AccountHolder:
    """Whose export this is, as far as the export says: the names the account has
    gone by, longest first, and its username or, for an account without one, its id."""

    names: tuple[str, ...] = ()
    identifier: str | None = None


def attempt(source: Callable[..., T], default: T, *args) -> T:
    """What *source* finds, or *default* when it fails. A source that cannot be read
    is an export of another shape than expected, never a reason to stop extraction."""
    try:
        return source(*args)
    except Exception as e:
        logger.warning("Account holder: %s failed with %s", getattr(source, "__name__", type(source).__name__), type(e).__name__)
        return default


def cleaned(names: Iterable[object]) -> list[str]:
    """The names worth matching, longest first: whitespace evened out, no
    duplicates, nothing shorter than two characters."""
    unique = {" ".join(name.split()) for name in names if isinstance(name, str)}
    return sorted((name for name in unique if len(name) >= 2), key=lambda name: (-len(name), name))


def whole_token(identifier: str) -> str:
    """The expression that matches *identifier* as a whole word, dots literal."""
    return r"(?<!\w)" + re.escape(identifier) + r"(?!\w)"


def redact_account_holder(
    frames: Iterable[pd.DataFrame],
    holder: AccountHolder,
    *,
    text_columns: Sequence[str] | None,
    link_columns: Sequence[str],
    identifier_expression: Callable[[str], str] = whole_token,
    single_words_whole_cell: bool = False,
    skip_columns: Sequence[str] = (),
) -> None:
    """Redact the account holder and e-mail addresses from every frame, in place.

    One pattern for the text columns: an address, which becomes ``[email]``, or a
    name or the identifier, which become ``[user]``. One for the link columns: the
    identifier alone. A name is matched as a whole, its parts separated by any
    whitespace, where a hyphen also counts as part of a name, so that another
    person's double-barrelled name is left. ``text_columns=None`` means every
    column that is not a link column. With *single_words_whole_cell*, a name of one
    word is redacted only where it is the whole cell. Columns named in *skip_columns*
    are left alone by both passes."""
    identifier = identifier_expression(holder.identifier) if holder.identifier else ""
    in_text = [name for name in holder.names if not (single_words_whole_cell and len(name.split()) == 1)]
    words = [name for name in holder.names if single_words_whole_cell and len(name.split()) == 1]
    names = "|".join(r"\s+".join(map(re.escape, name.split())) for name in in_text)
    alternatives = [
        rf"(?P<email>{eh.EMAIL_PATTERN.pattern})",
        rf"(?<![\w-])(?:{names})(?![\w-])" if names else "",
        identifier,
    ]
    text = re.compile("|".join(filter(None, alternatives)), re.IGNORECASE)
    whole_cell = (
        re.compile(r"^\s*(?:" + "|".join(map(re.escape, words)) + r")\s*$", re.IGNORECASE) if words else None
    )
    link = re.compile(identifier, re.IGNORECASE) if identifier else None

    def token(match: re.Match) -> str:
        return "[email]" if match.group("email") else "[user]"

    skipped = list(skip_columns)
    for frame in frames:
        columns = (
            frame.columns.difference(list(link_columns) + skipped, sort=False)
            if text_columns is None
            else frame.columns.intersection(list(text_columns)).difference(skipped, sort=False)
        )
        for column in columns:
            values = frame[column].astype("string")
            if whole_cell:
                values = values.str.replace(whole_cell, "[user]", regex=True)
            frame[column] = values.str.replace(text, token, regex=True)
        if link is not None:
            for column in frame.columns.intersection(list(link_columns)).difference(skipped, sort=False):
                frame[column] = frame[column].astype("string").str.replace(link, "[user]", regex=True)
