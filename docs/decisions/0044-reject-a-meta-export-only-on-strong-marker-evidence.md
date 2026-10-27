---
status: accepted
date: "2026-10-27"
tags:
    - validation
    - meta
    - recognition
category: Extraction
applies_to:
    - packages/python/port/helpers/meta_recognition.py
    - packages/python/port/platforms/instagram.py
    - packages/python/port/platforms/facebook.py
    - packages/data-collector/src/components/consent_form_viz/serialize.ts
priority: invariant
companions:
    - packages/python/tests/test_meta_recognition.py
    - packages/python/tests/test_instagram_recognition.py
    - packages/python/tests/test_facebook_recognition.py
    - packages/python/tests/test_listings_corpus.py
    - packages/python/tests/test_extractor_inputs.py
    - packages/data-collector/src/components/consent_form_viz/serialize.test.ts
---

# Reject a Meta export only on strong marker evidence

## Decision

Instagram and Facebook recognise an upload through `meta_recognition.validate_meta`, which may reject it as the other product (`<other>_detected`) or as both (`mixed`) only on strong marker evidence. Weak markers and resolved extractor inputs only ever argue for acceptance.

## Guidance

- Only strong evidence may establish `<other>_detected` or `mixed`: never let a weak marker or a resolved input produce either, never count the other product's weak markers against ours, and rest any new wrong-product rejection on strong evidence; the same weak-only archive may validate at either step. The `unknown`, `nested_zip`, `bad_zip` and `no_study_categories` rejections stay as they are.
- `decide()` is the whole table. Strong markers of ours only: accept on the `strong` basis. Strong of the other only: return the other product's name, which `validate_meta` maps to the `<other>_detected` category id. Strong of both: `mixed`, so a combined download holding both product roots is `mixed` by design. No strong marker either way: one weak marker of ours accepts on the `weak` basis whatever the other's weak count; else one resolved input accepts on the `files` basis; else `nested_zip` or `unknown`.
- Admit a strong marker only by structure: a product-named root (`your_<product>_activity`, `apps_and_websites_off_of_<product>`), a pair under one, or a leaf on the short verified list that carries the product's name. Demote a leaf to weak in the same change that finds it in the other product's export.
- Derive weak markers (folder pairs, and Facebook's file-stem markers) from real export listings, and admit a pair only when a listing of that product holds it outside the product's strong roots, wherever it sits: at the export root (`preferences/settings`) or deeper (`your_topics/your_ads_see_more`, under `preferences/`). The Facebook pairs `messages/e2ee_cutover`, `messages/filtered_threads`, `messages/photos`, `messages/stickers_used`, `posts/album`, `posts/media`, `media/stickers_used`, `media/your_posts` and `comments_and_reactions/icons` stay out: Facebook listings hold them only beneath `your_facebook_activity/`, where the strong root already decides, so anywhere else they fire only inside an Instagram export.
- The files tier is the inputs each active extractor declares in its `Table config::` docstring block, carried by the port config as `inputs` and read as `EXTRACTOR_INPUTS`. Count an input present when a member satisfies extraction's matching rule (`member_matches`: exact path or path-boundary suffix at any depth, the apostrophe variant on the request only, `re:` inputs searched), whereas extraction additionally requires a plain name's suffix match to be unique; record the count on every basis. A new read in an extractor is declared in its `Table config::` and reaches the port config in the same change.
- `require_study_categories` rejects a recognised export as `no_study_categories` only when every study-category folder is missing and no input resolved (`files == 0`), keeping the participant pending at the retry prompt instead of completing through the no-data page; on the files basis `missing_study_labels` is `{}`.
- The files tier accepts some single-category uploads at the wrong product's step (ads files Meta writes identically for both products, Instagram's link history at the Facebook step). This is a deliberate trade, pinned by resolution against the local listings corpus in `test_wrong_step_routes_by_resolution`; a change that widens the set goes to the owner, not into a wider pin.
- Accept a marker or input change only on exports held out of its derivation. A skeleton that drives a marker change joins the regression corpus and stops counting as acceptance evidence.
- `dd-script-selector` builds the config it sends to `dd-script-builder` from a fixed key list and `release.sh` does not validate the injected config, so a selector-built Meta study drops `inputs` and ships with the files tier silently off. Confirm a selector-built Meta study's config carries `inputs` before release; drop this rule once the selector forwards every key the generator emits, or the fork's validator requires `inputs` for the Meta platforms and `release.sh` validates the injected config.
- The host milestone (`ig=<strong>+<weak> fb=<strong>+<weak> basis=<basis>`, plus ` files=<n>` on the files basis) and the donation's `validation` record (`category`, `basis`, `ig_strong`, `ig_weak`, `fb_strong`, `fb_weak`, `files`) carry only a category id, a basis word (`strong`, `weak`, `files`, `none`) and integer counts, never a path or member name. `serialize.ts` writes the record as given beside `"deleted row count"` in every table object and omits the key when there is none; readers treat it as optional.
- A Meta platform's `DDP_CATEGORIES` name only the format (json/html); they and `known_files` play no part in recognition.

## Why

The full extent of participant export layouts is unknowable, so a rule that rejects on sample-derived evidence will meet a genuine export on a layout nobody anticipated and turn the participant away: that false rejection loses the donation and is the worst outcome, while a thin, empty or mislabelled wrong-product donation is the lesser one. It happened: `messages/photos` scored for Facebook and turned a real Instagram export into `mixed`. Instagram and Facebook share a layout and file names, so only product-named structure has separated them in every listing seen so far; weakening the strong-only veto, or letting the files tier lag the extractors, refuses exports that extraction would have read.

## Checks

- Confirm `instagram.validate_ddp` and `facebook.validate_ddp` delegate to `validate_meta` with `inputs=EXTRACTOR_INPUTS` and do not read `known_files` for recognition.
- `pnpm test:py -- tests/test_meta_recognition.py tests/test_instagram_recognition.py tests/test_facebook_recognition.py` passes: the decision table, weak-only acceptance at either step, the files basis and `no_study_categories` are pinned there.
- `pnpm test:py -- tests/test_extractor_inputs.py` passes: each config's `inputs` equals the reads reachable from its extractor.
- With the local listings corpus present, `pnpm test:py -- tests/test_listings_corpus.py` passes without skips: every listing validates as its product on the strong basis and as `<product>_detected` at the other step, except the data-logs-only Facebook listing (`unknown` at both steps) and the three-member researcher skeleton (accepted on the `weak` basis at the Instagram step, `unknown` at the Facebook step, `no_study_categories` through `validate_ddp`); no strong marker appears in the other product's listings; and `test_wrong_step_routes_by_resolution` enumerates exactly the pinned wrong-step inputs.
- `pnpm --filter @eyra/data-collector test` passes, including `serialize.test.ts`'s placement and omission of the `validation` key.
