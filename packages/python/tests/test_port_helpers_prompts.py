import port.api.props as props
from port.helpers import port_helpers as ph


def test_multi_prompt_copy_covers_required_locales():
    prompt = ph.generate_file_prompt("application/zip", multiple=True)
    d = prompt.toDict()
    translations = d["description"]["translations"]
    assert set(translations) >= {"en", "nl", "de", "it", "es"}
    assert "file(s)" in translations["en"] or "files" in translations["en"]


def test_single_prompt_copy_unchanged():
    prompt = ph.generate_file_prompt("application/zip")
    assert prompt.toDict()["__type__"] == "PropsUIPromptFileInput"


def test_multi_prompt_includes_example_covering_required_locales():
    """generate_file_prompt(multiple=True) supplies the Takeout-shaped example
    (ITEM 1): PropsUIPromptFileInputMultiple.toDict() includes an "example"
    key when the field is set, covering all 5 locales."""
    prompt = ph.generate_file_prompt("application/zip", multiple=True)
    d = prompt.toDict()
    assert "example" in d
    translations = d["example"]["translations"]
    assert set(translations) >= {"en", "nl", "de", "it", "es"}


def test_multi_prompt_example_filename_identical_across_locales():
    """Only the leading word ("Example"/"Voorbeeld"/...) is translated; the
    Takeout filename shape itself must not vary by locale."""
    prompt = ph.generate_file_prompt("application/zip", multiple=True)
    translations = prompt.toDict()["example"]["translations"]
    filename_part = "takeout-...-1-001.zip, takeout-...-2-001.zip"
    for locale, text in translations.items():
        assert text.endswith(filename_part), f"locale {locale!r} filename part diverged: {text!r}"


def test_single_prompt_has_no_example_key():
    """The single-file prompt type carries no `example` concept at all —
    only PropsUIPromptFileInputMultiple gained the field."""
    prompt = ph.generate_file_prompt("application/zip")
    assert "example" not in prompt.toDict()


def test_protocol_error_page_covers_required_locales():
    page = ph.render_protocol_error_page("Instagram").toDict()["page"]
    body = page["body"][0]
    assert set(page["header"]["title"]["translations"]) >= {"en", "nl", "de", "it", "es"}
    assert set(body["text"]["translations"]) >= {"en", "nl", "de", "it", "es"}
    assert set(body["ok"]["translations"]) >= {"en", "nl", "de", "it", "es"}


def test_protocol_error_page_has_no_cancel_button():
    """ITEM 3: FlowBuilder discards this Confirm's result and always raises
    TaskIncompleteError("upload_rejected") next regardless of which button is
    pressed — a second identical button would invent a distinction that
    isn't there, so this is a single acknowledging button."""
    body = ph.render_protocol_error_page("Instagram").toDict()["page"]["body"][0]
    assert "cancel" not in body


def test_retry_prompt_single_file_wording_unchanged():
    prompt = ph.generate_retry_prompt("Instagram").toDict()
    assert "select a different file" in prompt["text"]["translations"]["en"]
    assert "ALL" not in prompt["text"]["translations"]["en"]


def test_retry_prompt_multiple_points_at_different_files_not_all():
    """Final copy (2026-09-03): with the soft-confirm in place, this page
    fires only for unrecognised or corrupt files, never for missing parts —
    so it points the participant at different files, not at reselecting
    ALL of them."""
    prompt = ph.generate_retry_prompt("Google", multiple=True).toDict()
    translations = prompt["text"]["translations"]
    assert set(translations) >= {"en", "nl", "de", "it", "es"}
    assert "different files" in translations["en"]
    assert "andere bestanden" in translations["nl"]
    assert "ALL" not in translations["en"]
    assert "ALLE" not in translations["nl"]
    assert "ALLE" not in translations["de"]
    assert "TUTTI" not in translations["it"]
    assert "TODOS" not in translations["es"]


def test_retry_prompt_multiple_ok_cancel_labels_unchanged():
    """Only the body text is multi-aware; the Try again / Continue button
    labels stay the same for both single- and multi-file retries."""
    single = ph.generate_retry_prompt("Instagram").toDict()
    multi = ph.generate_retry_prompt("Google", multiple=True).toDict()
    assert single["ok"]["translations"] == multi["ok"]["translations"]
    assert single["cancel"]["translations"] == multi["cancel"]["translations"]


def test_retry_prompt_cancel_is_stop_for_now():
    for prompt in (ph.generate_retry_prompt("Instagram"), ph.generate_retry_prompt("Google", multiple=True)):
        cancel = prompt.toDict()["cancel"]["translations"]
        assert cancel["en"] == "Stop for now"
        assert cancel["nl"] == "Voorlopig stoppen"
        assert set(cancel) >= {"en", "nl", "de", "it", "es"}


def test_retry_prompt_never_promises_the_file_will_be_accepted():
    """Declining ends as participant-abandoned (ADR-0039), so the copy must
    not suggest the file will be taken as is."""
    for prompt in (ph.generate_retry_prompt("Instagram"), ph.generate_retry_prompt("Google", multiple=True)):
        for text in prompt.toDict()["text"]["translations"].values():
            assert "if you are sure" not in text
            assert "Weet u zeker" not in text


def test_task_incomplete_copy_points_at_close():
    d = ph.render_task_incomplete_page("Google").toDict()
    body = d["page"]["body"]
    prompt = body[0] if isinstance(body, list) else body
    translations = prompt["text"]["translations"]
    assert "Close button" in translations["en"]
    assert "knop Sluiten" in translations["nl"]
    assert "list of tasks" in translations["en"]
    assert "lijst met taken" in translations["nl"]


def _missing():
    return {
        "youtube": props.Translatable({"en": "YouTube", "nl": "YouTube", "de": "YouTube", "it": "YouTube", "es": "YouTube"}),
        "chrome": props.Translatable({"en": "Chrome", "nl": "Chrome", "de": "Chrome", "it": "Chrome", "es": "Chrome"}),
    }


def test_incomplete_upload_prompt_lists_the_missing_products_per_locale():
    d = ph.generate_incomplete_upload_prompt("Google", _missing()).toDict()
    text = d["text"]["translations"]
    assert set(text) >= {"en", "nl", "de", "it", "es"}
    assert "YouTube, Chrome" in text["en"]
    assert "YouTube, Chrome" in text["nl"]
    assert "multiple parts" in text["en"]
    assert "meerdere delen" in text["nl"]


def test_incomplete_upload_prompt_buttons():
    d = ph.generate_incomplete_upload_prompt("Google", _missing()).toDict()
    assert d["ok"]["translations"]["en"] == "No, I have more files"
    assert d["cancel"]["translations"]["en"] == "Yes, I am sure"
    assert d["cancel"]["translations"]["nl"] == "Ja, ik weet het zeker"
