import re

import port.api.props as props
from port.helpers import port_helpers as ph


def test_multi_prompt_copy_covers_required_locales():
    prompt = ph.generate_file_prompt("Google", "application/zip", multiple=True)
    d = prompt.toDict()
    translations = d["description"]["translations"]
    assert set(translations) >= {"en", "nl", "de", "it", "es"}
    assert "file(s)" in translations["en"] or "files" in translations["en"]


def test_single_prompt_is_the_d3i_single_prompt():
    """Every single-file flow renders the D3I prompt, which has the drop zone;
    feldspar's PropsUIPromptFileInput is no longer sent by any flow."""
    prompt = ph.generate_file_prompt("Instagram", "application/zip")
    d = prompt.toDict()
    assert d["__type__"] == "PropsUIPromptFileInputSingle"
    assert d["extensions"] == "application/zip"


def test_single_prompt_copy_covers_required_locales():
    prompt = ph.generate_file_prompt("Instagram", "application/zip")
    translations = prompt.toDict()["description"]["translations"]
    assert set(translations) >= {"en", "nl", "de", "it", "es"}
    assert all("Instagram" in text for text in translations.values())


def test_multi_prompt_includes_example_covering_required_locales():
    """generate_file_prompt(multiple=True) supplies the Takeout-shaped example
    (ITEM 1): PropsUIPromptFileInputMultiple.toDict() includes an "example"
    key when the field is set, covering all 5 locales."""
    prompt = ph.generate_file_prompt("Google", "application/zip", multiple=True)
    d = prompt.toDict()
    assert "example" in d
    translations = d["example"]["translations"]
    assert set(translations) >= {"en", "nl", "de", "it", "es"}


def test_multi_prompt_example_filename_identical_across_locales():
    """Only the leading word ("Example"/"Voorbeeld"/...) is translated; the
    Takeout filename shape itself must not vary by locale."""
    prompt = ph.generate_file_prompt("Google", "application/zip", multiple=True)
    translations = prompt.toDict()["example"]["translations"]
    filename_part = "takeout-...-1-001.zip, takeout-...-2-001.zip"
    for locale, text in translations.items():
        assert text.endswith(filename_part), f"locale {locale!r} filename part diverged: {text!r}"


def test_single_prompt_without_example_has_no_example_key():
    """No name given → the key is absent, so the component's own fallback shows
    (the example platform relies on this; tests/donation.spec.ts asserts it)."""
    prompt = ph.generate_file_prompt("Instagram", "application/zip")
    assert "example" not in prompt.toDict()


def test_single_prompt_example_translates_only_the_leading_word():
    prompt = ph.generate_file_prompt(
        "Instagram", "application/zip", example="instagram-username-2026-10-10-UQx3SPDb.zip"
    )
    assert prompt.toDict()["example"]["translations"] == {
        "en": "Example: instagram-username-2026-10-10-UQx3SPDb.zip",
        "nl": "Voorbeeld: instagram-username-2026-10-10-UQx3SPDb.zip",
        "de": "Beispiel: instagram-username-2026-10-10-UQx3SPDb.zip",
        "it": "Esempio: instagram-username-2026-10-10-UQx3SPDb.zip",
        "es": "Ejemplo: instagram-username-2026-10-10-UQx3SPDb.zip",
    }


def test_empty_example_is_no_example():
    """An empty name behaves exactly like None: the single prompt omits the key,
    the multi prompt keeps its Takeout default."""
    assert "example" not in ph.generate_file_prompt("Instagram", "application/zip", example="").toDict()
    multi = ph.generate_file_prompt("Google", "application/zip", multiple=True, example="").toDict()
    assert multi["example"]["translations"]["en"] == "Example: takeout-...-1-001.zip, takeout-...-2-001.zip"


def test_multi_prompt_explicit_example_wins():
    prompt = ph.generate_file_prompt("Google", "application/zip", multiple=True, example="other-1.zip")
    assert prompt.toDict()["example"]["translations"]["nl"] == "Voorbeeld: other-1.zip"


# The complete wire payload of the Google prompt as it is on master (36baea2),
# captured before any change.
GOOGLE_PROMPT_ON_MASTER = {
    "__type__": "PropsUIPromptFileInputMultiple",
    "description": {
        "translations": {
            "en": "Choose ALL the Google files that you requested in the previous steps and stored on your device. Google Takeout usually delivers several files that belong together.",
            "nl": "Kies ALLE Google-bestanden die je in de vorige stappen hebt aangevraagd en op je apparaat hebt opgeslagen. Google Takeout levert meestal meerdere zipbestanden die bij elkaar horen.",
            "de": "Wählen Sie ALLE Google-Dateien aus, die Sie in den vorherigen Schritten angefordert und auf Ihrem Gerät gespeichert haben. Google Takeout liefert meist mehrere Dateien, die zusammengehören.",
            "it": "Scelga TUTTI i file di Google che ha richiesto nei passaggi precedenti e salvato sul suo dispositivo. Google Takeout di solito fornisce più file che vanno insieme.",
            "es": "Elija TODOS los archivos de Google que solicitó en los pasos anteriores y guardó en su dispositivo. Google Takeout suele entregar varios archivos que van juntos."
        }
    },
    "extensions": "application/zip",
    "example": {
        "translations": {
            "en": "Example: takeout-...-1-001.zip, takeout-...-2-001.zip",
            "nl": "Voorbeeld: takeout-...-1-001.zip, takeout-...-2-001.zip",
            "de": "Beispiel: takeout-...-1-001.zip, takeout-...-2-001.zip",
            "it": "Esempio: takeout-...-1-001.zip, takeout-...-2-001.zip",
            "es": "Ejemplo: takeout-...-1-001.zip, takeout-...-2-001.zip"
        }
    }
}


def test_google_payload_is_unchanged():
    """Every field, not just the example: the refactor to _example_text must not move a byte."""
    assert ph.generate_file_prompt("Google", "application/zip", multiple=True).toDict() == GOOGLE_PROMPT_ON_MASTER


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
    """Only the body text is multi-aware; the Try again / Stop for now button
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
    assert "task list" in translations["en"]
    assert "lijst met taken" in translations["nl"]


def _missing():
    return {
        "youtube": props.Translatable({"en": "YouTube", "nl": "YouTube", "de": "YouTube", "it": "YouTube", "es": "YouTube"}),
        "chrome": props.Translatable({"en": "Chrome", "nl": "Chrome", "de": "Chrome", "it": "Chrome", "es": "Chrome"}),
    }


def test_incomplete_upload_prompt_lists_the_missing_products_per_locale():
    d = ph.generate_incomplete_upload_prompt(_missing()).toDict()
    text = d["text"]["translations"]
    assert set(text) >= {"en", "nl", "de", "it", "es"}
    assert "YouTube, Chrome" in text["en"]
    assert "YouTube, Chrome" in text["nl"]
    assert "multiple parts" in text["en"]
    assert "meerdere delen" in text["nl"]


def test_incomplete_upload_prompt_buttons():
    d = ph.generate_incomplete_upload_prompt(_missing()).toDict()
    assert d["ok"]["translations"]["en"] == "No, I have more files"
    assert d["cancel"]["translations"]["en"] == "Yes, I am sure"
    assert d["cancel"]["translations"]["nl"] == "Ja, ik weet het zeker"


RETRY_REASON_TEXTS = {
    ("Instagram", "facebook"): {
        "en": "This looks like your Facebook file, not your Instagram file. Choose your Instagram file here; you can add your Facebook file at the Facebook step.",
        "nl": "Dit lijkt je Facebook-bestand te zijn, niet je Instagram-bestand. Kies hier je Instagram-bestand; je Facebook-bestand kun je bij de Facebook-stap toevoegen.",
    },
    ("Facebook", "instagram"): {
        "en": "This looks like your Instagram file, not your Facebook file. Choose your Facebook file here; you can add your Instagram file at the Instagram step.",
        "nl": "Dit lijkt je Instagram-bestand te zijn, niet je Facebook-bestand. Kies hier je Facebook-bestand; je Instagram-bestand kun je bij de Instagram-stap toevoegen.",
    },
    ("Instagram", "nested_zip"): {
        "en": "This zip file contains another zip file. Open it on your computer and choose the zip file inside it.",
        "nl": "Dit zipbestand bevat nog een zipbestand. Open het op je computer en kies het zipbestand dat erin zit.",
    },
    ("Instagram", "bad_zip"): {
        "en": "We couldn't open this file as a zip file. Download your Instagram file again and choose the new download.",
        "nl": "We konden dit bestand niet openen als zipbestand. Download je Instagram-bestand opnieuw en kies de nieuwe download.",
    },
}


def test_retry_prompt_reason_texts():
    baseline = ph.generate_retry_prompt("Instagram").toDict()
    for (platform, reason), expected in RETRY_REASON_TEXTS.items():
        prompt = ph.generate_retry_prompt(platform, reason=reason).toDict()
        translations = prompt["text"]["translations"]
        assert translations["en"] == expected["en"]
        assert translations["nl"] == expected["nl"]
        assert prompt["ok"] == baseline["ok"]
        assert prompt["cancel"] == baseline["cancel"]
    for reason in (None, "mixed", "unknown"):
        assert ph.generate_retry_prompt("Instagram", reason=reason).toDict() == baseline


def test_retry_prompt_reason_text_names_both_products():
    fb = ph.generate_retry_prompt("Instagram", reason="facebook").toDict()["text"]["translations"]["en"]
    assert "Facebook" in fb and "Instagram" in fb
    ig = ph.generate_retry_prompt("Facebook", reason="instagram").toDict()["text"]["translations"]["en"]
    assert "Facebook" in ig and "Instagram" in ig


def test_retry_prompt_nl_is_informal():
    formal = re.compile(r"\b(u|uw|alstublieft)\b", re.I)
    prompts = [ph.generate_retry_prompt("Instagram", reason=r) for r in (None, "facebook", "instagram", "nested_zip", "bad_zip")]
    prompts.append(ph.generate_retry_prompt("Instagram", multiple=True))
    for prompt in prompts:
        d = prompt.toDict()
        for part in ("text", "ok", "cancel"):
            assert not formal.search(d[part]["translations"]["nl"])
    single = ph.generate_retry_prompt("Instagram").toDict()["text"]["translations"]["nl"]
    assert single == "Helaas kunnen we je Instagram-bestand niet verwerken. Het lijkt niet het bestand te zijn dat we verwachtten. Probeer opnieuw om een ander bestand te kiezen, of stop voorlopig — je kunt later naar deze taak terugkeren."
    multi = ph.generate_retry_prompt("Instagram", multiple=True).toDict()["text"]["translations"]["nl"]
    assert multi == "Helaas kunnen we je Instagram-bestand(en) niet verwerken, omdat ze er niet uitzien zoals we verwachten. Probeer het opnieuw met andere bestanden, of stop voorlopig. Je kunt later naar deze taak terugkeren."


def _items_two():
    return {
        "a": props.Translatable({"en": "Alpha", "nl": "Alfa"}),
        "b": props.Translatable({"en": "Beta", "nl": "Bèta"}),
    }


_FORMAL = re.compile(r"\b(u|uw|alstublieft)\b", re.I)


def test_missing_category_labels_nl_are_informal():
    from port.platforms.instagram import MISSING_CATEGORIES

    for _folder, label in MISSING_CATEGORIES.values():
        assert not _FORMAL.search(label.translations["nl"])


def test_no_study_data_prompt_text():
    from port.platforms.instagram import MISSING_CATEGORIES

    items = {key: label for key, (_folder, label) in MISSING_CATEGORIES.items()}
    d = ph.generate_no_study_data_prompt("Instagram", items).toDict()
    assert d["text"]["translations"]["en"] == (
        "Your Instagram file contains none of the parts this study uses: Your Instagram activity, Connections, "
        "Ads information, Logged information. Request a new download from Instagram with these selected and choose that file."
    )
    assert d["text"]["translations"]["nl"] == (
        "Je Instagram-bestand bevat geen van de onderdelen die het onderzoek gebruikt: Je Instagram-activiteit, Connecties, "
        "Advertentie-informatie, Gelogde informatie. Vraag bij Instagram een nieuwe download aan waarin deze zijn geselecteerd en kies dat bestand."
    )
    retry = ph.generate_retry_prompt("Instagram").toDict()
    assert d["ok"] == retry["ok"]
    assert d["cancel"] == retry["cancel"]
    assert not _FORMAL.search(d["text"]["translations"]["nl"])
