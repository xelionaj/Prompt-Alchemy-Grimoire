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

The five captured scenarios cover a fixed-gender theme with section selections, seed-random gender and metatype, Fluid scope and plain output, cross-theme Mayhem and JSON formatting, and slider/skin-tone/Bald interaction. Static contracts above cover discovery, widget keys and visibility, labeled output, and preview/persistence behavior. A live Krea 2 workflow check is recorded below; PNG metadata round-trip coverage remains outstanding.
## Post-4.3 comparison

After adding the catalog boundary, all five captured output hashes, output lengths, and slider states still matched. The refactored catalog exposes 14 packs and 56 categories; the layout payload exposes the same 56 categories and retains the legacy theme list and label-to-pack mapping. This was a focused baseline comparison using the installed Python interpreter, not a ComfyUI UI/PNG round-trip test.

## Live workflow check

The user's ArtForm Krea 2 workflow ran successfully twice before the source extraction in this stage. With only Gender enabled, the selector resolved `gender: a feminine adult`. With Environment temporarily set to random, it resolved a `scene/background` fragment (a holo-development studio and volumetric wireframe model), and one image was generated. The setting was restored to off and the workflow was not saved. This confirms the installed node's execution path and wildcard contribution before the Python module move.

## PromptComposer and renderer extraction

The legacy selection logic now lives in `bkwildcards/composition.py` behind `LegacyPromptComposer`; ordered semantic fragments are formatted by `bkwildcards/rendering.py` through `LegacyTextRenderer`. `nodes.py` constructs a `CompositionRequest` and delegates through both interfaces. `nodes.resolve_prompt` remains as a compatibility facade for the route and existing callers.

The five automated regression tests cover the five original output hashes, renderer parity, repeated and cross-process fixed-seed output, Mayhem seed sensitivity and cross-theme picks, random Environment composition, `build()` integration, and the saved-workflow node/widget contract. The current ComfyUI process was not restarted after the module extraction, so live execution of the newly split modules and PNG metadata round-trip still need a post-restart check.
