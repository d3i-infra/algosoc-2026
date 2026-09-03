"""Tests for PropsUIPromptConfirm serialization — cancel is optional."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from port.api import props
from port.api.props import PropsUIPromptConfirm, Translatable


def _t(en: str) -> Translatable:
    return Translatable({"en": en, "nl": en})


def test_confirm_with_cancel_serializes_cancel():
    prompt = PropsUIPromptConfirm(text=_t("Are you sure?"), ok=_t("Yes"), cancel=_t("No"))
    d = prompt.toDict()
    assert d["__type__"] == "PropsUIPromptConfirm"
    assert d["ok"]["translations"]["en"] == "Yes"
    assert "cancel" in d
    assert d["cancel"]["translations"]["en"] == "No"


def test_confirm_without_cancel_omits_cancel():
    prompt = PropsUIPromptConfirm(text=_t("Try again?"), ok=_t("Try again"))
    d = prompt.toDict()
    assert d["__type__"] == "PropsUIPromptConfirm"
    assert d["ok"]["translations"]["en"] == "Try again"
    assert "cancel" not in d


def test_notice_serializes_type_and_text():
    from port.api import d3i_props
    notice = d3i_props.PropsUIPromptNotice(text=props.Translatable({"en": "a", "nl": "b"}))
    d = notice.toDict()
    assert d["__type__"] == "PropsUIPromptNotice"
    assert d["text"]["translations"] == {"en": "a", "nl": "b"}
    assert "ok" not in d and "cancel" not in d
