# Compatibility baseline

This is the pre-refactor baseline for stages 4.1–4.3. Resolver hashes were captured at source commit `f0366d5` by direct calls to `bkwildcards.nodes.resolve_prompt` using Python 3.14.6 at `C:/Python314/python.exe`. ComfyUI itself was not launched, so these captures cover resolver output and slider state, not live widget rendering, HTTP preview, execution events, or PNG writing. Scenario inputs, lengths, SHA-256 digests, and slider state are in [COMPATIBILITY-BASELINE.json](COMPATIBILITY-BASELINE.json). Hashes are over UTF-8 output bytes.

## Behavior contracts from the current source

- **Discovery:** `nodes.py` scans on import. Pack folders and `.txt` files are sorted; category outputs are ordered by `(order, pack, id)`. The node UI orders global categories and each theme's categories separately by `display`, with Camera globals after theme packs.
- **Widget identity:** category widget keys are `<pack>_<id>`. All theme/gender category widgets are registered so values persist when hidden. The frontend hides widgets by scope; Python enforces scope independently.
- **Scope:** global categories apply across themes; a non-global pack is enabled only for its selected theme. Gender-specific packs require that gender; Fluid admits both gender-specific sets; Off excludes gender-specific packs; Random resolves to one gender from the seed.
- **Selection:** section dropdowns expose Off, Random, and cleaned `#` headings. Off omits a pick; Random draws from the whole file; a named heading draws from its section. Toggle categories draw from the whole file when enabled. Empty pools produce no pick.
- **Random streams:** each category uses `random.Random(seed + (crc32(category_key) & 0x7fffffff))`; category streams are independent. Section/file order is part of the deterministic input. Stable keys, IDs, and order must not be changed casually.
- **Prompt format:** picks sort by `order`. Plain mode joins selected text with the configured separator. Labeled mode groups adjacent equal labels and joins groups with `,\n`. JSON mode emits the same grouped labels as an indented JSON object. Missing choices are omitted.
- **Special behavior:** body slider modes can replace build presets; skin-tone selection follows metatype; Bald suppresses hair type/style/color; duplicate second art style is removed; cybernetic color can be harmonized. Mayhem uses a separate cross-theme composition with its fixed slot mapping, seeded optional slots, honored art style/metatype choices, and seeded slider lane.
- **Preview and persistence:** queue-time preview calls the same resolver as execution; execution returns the prompt string, updates the node's resolved box, and stamps prompt/slider properties into workflow metadata for PNG embedding.

## Substep 4.1 coverage

The five captured scenarios cover a fixed-gender theme with section selections, seed-random gender and metatype, Fluid scope and plain output, cross-theme Mayhem and JSON formatting, and slider/skin-tone/Bald interaction. Static contracts above cover discovery, widget keys and visibility, labeled output, and preview/persistence behavior. Live Krea 2 workflow and PNG metadata round-trip checks are recorded below.
## Post-4.3 comparison

After adding the catalog boundary, all five captured output hashes, output lengths, and slider states still matched. The refactored catalog exposes 14 packs and 56 categories; the layout payload exposes the same 56 categories and retains the legacy theme list and label-to-pack mapping. This was a focused baseline comparison using the installed Python interpreter, not a ComfyUI UI/PNG round-trip test.

## Live workflow check

The user's ArtForm Krea 2 workflow ran successfully twice before the source extraction and once after ComfyUI restarted with the split modules. The post-restart run resolved a seeded art-style fragment plus `gender: a feminine adult` and generated one image. The workflow's output folder was configured by the user.

## PromptComposer and renderer extraction

The legacy selection logic now lives in `bkwildcards/composition.py` behind `LegacyPromptComposer`; ordered semantic fragments are formatted by `bkwildcards/rendering.py` through `LegacyTextRenderer`. `nodes.py` constructs a `CompositionRequest` and delegates through both interfaces. `nodes.resolve_prompt` remains as a compatibility facade for the route and existing callers.

The automated regression tests cover the five original output hashes, renderer parity, repeated and cross-process fixed-seed output, Mayhem seed sensitivity and cross-theme picks, random Environment composition, `build()` integration, the saved-workflow node/widget contract, and deterministic stream compatibility. PNG metadata replay findings are recorded in substep 4.6 below.

## Stage 5 — renderer profile contract

`bkwildcards/contracts.py` defines immutable `RendererProfile` metadata and the `RendererProfileRegistry` protocol. `bkwildcards/rendering.py` registers stable IDs for `legacy-text`, `krea-2`, `flux`, `anima`, `z-image`, and `sdxl`. Each profile records its model family, known variants where explicitly listed, the fragment-preserving text strategy, current adapter output capabilities, and optional source references. `rendering.get_renderer()` and `rendering.render_for_profile()` resolve those IDs; unknown IDs fail explicitly.

The current profiles intentionally share the byte-compatible fragment text renderer. They preserve all fragment text and the existing comma-separated, labeled, and JSON formats. The profile capability fields describe this selector adapter's single-string output; they do not claim that the underlying models lack negative or secondary prompt inputs. Model-specific transformations remain unimplemented until supported by primary model documentation and dedicated compatibility evidence. The profile dropdown is appended after all legacy widgets, and is optional at the API schema level with a `legacy-text` Python default so pre-profile saved/API workflows can omit it. Both `resolve_prompt()` and the node's queue-time preview and execution paths route through the selected profile.

Official references currently recorded: [Krea 2 prompting guide](https://github.com/krea-ai/krea-2/blob/main/docs/prompting.md) and [Z-Image repository](https://github.com/Tongyi-MAI/Z-Image). Flux, Anima, and SDXL profiles currently make no model-specific prompt-format claims.

## Substep 4.4 — Deterministic selection service

`bkwildcards/selection.py` owns random-stream construction and legacy category draws. Existing category streams still use the exact `seed + (CRC32(key) & 0x7fffffff)` formula; gender, Mayhem, slider, skin-tone, and special category streams retain their previous seeds and key strings. Legacy section/file choice behavior remains delegated to the existing draw helper. New sources use the versioned SHA-256 source-key rule documented in `CONTENT-SCHEMA.md`, with a separate stable-entry-ID stream API. Selection tests compare the legacy formula and draw behavior directly, and verify qualified streams are repeatable across processes.

## Substep 4.5 — Composition policies and selected entries

`LegacyPromptComposer` now composes against the `CatalogSnapshot` supplied with each request. It passes normalized `CategoryRecord` values to the selection service and receives `SelectedEntry` values carrying the chosen text, category/source identity, section, and provenance. Composition has no direct content-file reads; the legacy file/section adapter stays inside `selection.py`. A fixture with an intentionally nonexistent content path verifies that the composer can use an injected catalog and selection service without opening that path.

Theme/gender scope, body slider/build substitution, skin-tone coherence, cybernetic color handling, duplicate art-style removal, Bald hair suppression, and Mayhem slot composition are named policy boundaries. They preserve the legacy ordering and deterministic selection streams. `PromptDocument` remains renderer-independent; prompt labels and final plain/labeled/JSON formatting stay in the renderer. Full resolver hash regression and selection tests are the compatibility gate; direct UI graph reimport is tracked in substep 4.6.

## Substep 4.6 — PNG metadata and replay checkpoint

After the ComfyUI restart, the live ArtForm Krea 2 graph completed and saved `image_2026-10-25_058.png` (1920 × 1088). The PNG contains both standard ComfyUI metadata fields, `workflow` and `prompt`. The decoded UI workflow is valid JSON with graph ID `3115e113-0ba0-41f1-b2f8-8748c42a06cd`, 22 nodes, and the `BKWildcardSelector` node. The decoded API prompt has 16 nodes, including `BKWildcardSelector` and the `PixaromaResolution` node's `ResolutionState` input.

The PNG was opened directly in ComfyUI through **File → Open**. ComfyUI created a new `image_2026-10-25_058` workflow tab; the imported graph retained the custom selector and its resolved prompt. This confirms full workflow metadata can be reimported from the saved PNG. The embedded API prompt was also extracted and submitted to the running ComfyUI; it completed and generated `image_2026-10-25_059.png`, confirming that the prompt payload can be replayed with the custom node after restart. That API-format replay output contains a `prompt` field but no `workflow` field, as expected for an API prompt submission.

Submitting the extracted UI workflow JSON through the `run_workflow` adapter failed at third-party node `PixaromaResolution`: `get_resolution()` was called without its required `ResolutionState` argument. The PNG's embedded API prompt contains that state, the original UI graph run succeeded, and direct PNG import in ComfyUI succeeded. The failure is specific to the adapter's UI-graph-to-API conversion path, not the PNG save or ComfyUI UI importer. **Status:** PNG metadata save, direct UI graph import, and embedded-prompt replay are verified. The separate adapter conversion failure is documented for future tooling investigation.
