# Content schema proposal

Status: design proposal for step 3. This defines the target data contract; it does not change the current loader. Existing `_pack.json` manifests and line-based `.txt` files remain the compatibility format during migration.

## Design goals

- Keep content, composition semantics, UI presentation, and model rendering distinct.
- Keep stable IDs as the saved-workflow and deterministic-randomization contract.
- Represent multiple content roots and licenses without conflating them with the software license.
- Let a theme contain multiple packs and a pack contain multiple categories.
- Make sections explicit for new content while continuing to parse existing `#`-headed text files.
- Keep renderer-specific instructions optional and isolated by renderer profile.

## Existing format and compatibility mapping

Today `bkwildcards/library.py` discovers `wildcards/<pack>/_pack.json` and `.txt` files. Each directory is one pack. A non-global pack becomes one theme; `global: true` makes it available across themes; optional `gender` further scopes it. Each `entries[]` item describes one category. `select: "section"` turns `#` headings into options; omission defaults to a Boolean `toggle`. A `.txt` file omitted from `entries[]` is still loaded as a default category. Repeated manifest entries may intentionally point to the same text file, as with the two Art Style selectors.

| Existing field / behavior | Target field |
|---|---|
| directory name or `pack` | `pack.id` |
| `label` on a non-global pack | legacy theme ID is the pack ID; theme label is the pack label |
| `global: true` | `pack.scope.kind: "global"` |
| non-global pack | `pack.scope.kind: "theme"`, `pack.scope.theme_id: <pack id>` |
| `gender` | `pack.scope.gender` |
| `entries[].id` | `categories[].id` |
| `file` | `content.path` |
| `label`, `group`, `display` | `ui.label`, `ui.group`, `ui.order` |
| `prompt_label`, `order` | `semantics.label`, `semantics.order` |
| `select: "section"` | `selection.mode: "section"` |
| missing/`toggle` select | `selection.mode: "toggle"` |
| `default` | `selection.default` |
| `#` headings in `.txt` | compatibility parser; explicit section data for new content |

For legacy manifests, missing `select` remains a toggle, `display` falls back to `order`, and undeclared `.txt` files continue to load. New-format manifests should be explicit and validated. Do not silently reinterpret an existing field during migration.

## Version 1 layout

Each independently licensed content root has a `library.json` index. The index records its source/license boundary, theme labels, and the packs it contains. Each listed pack has a `_pack.json` manifest containing its scope and categories. Pack and category data paths are relative to their containing root or pack directory as documented below; readers must reject paths that escape the content root.

The current inherited `wildcards/` tree remains a legacy root and continues to use its existing manifests. New Grimoire content belongs in a separate root, for example `grimoire_content/`, after a reader supports this layout. Do not add a `library.json` to or move/rewrite the inherited tree as part of this design step.

### Content-root index: `library.json`

```json
{
  "schema_version": 1,
  "source": {
    "id": "pag-original",
    "authors": ["Example contributor name"],
    "origin": "original work",
    "references": [],
    "license": "CC-BY-SA-4.0",
    "notice": "CONTENT-PROVENANCE.md"
  },
  "themes": [
    { "id": "cyberpunk", "label": "Cyberpunk" }
  ],
  "packs": [
    { "id": "cyberpunk-core", "path": "packs/cyberpunk-core" }
  ]
}
```

A source ID is stable and unique across all loaded content roots. The SPDX license and notice apply to the source's contents; pack/category provenance inherits them. If a source includes material under different terms, split it into separate roots rather than hiding a second license in a category.

### Pack manifest: `packs/<pack-id>/_pack.json`

```json
{
  "schema_version": 1,
  "id": "cyberpunk-core",
  "label": "Cyberpunk Core",
  "scope": {
    "kind": "theme",
    "theme_id": "cyberpunk",
    "gender": null
  },
  "categories": [
    {
      "id": "outfit",
      "input_key": "pag_original_cyberpunk_core_outfit",
      "stable_key": "pag-original:cyberpunk-core:outfit",
      "content": {
        "path": "outfits.txt",
        "format": "lines",
        "sections": "legacy-hash-headings"
      },
      "selection": {
        "mode": "section",
        "default": "off"
      },
      "ui": {
        "label": "Outfits",
        "group": "Wardrobe",
        "order": 40
      },
      "semantics": {
        "role": "wardrobe.outfit",
        "label": "outfit",
        "order": 40
      }
    }
  ]
}
```

A pack's `scope.kind` is `theme` or `global`. Theme packs reference an ID in the source root's `themes` list; global packs omit `theme_id`. Optional `gender` scopes either kind. Multiple packs may refer to the same theme.

## Field contract

### Source, themes, and scope

- `schema_version`: required integer on each versioned index and pack manifest.
- `source.id`: required stable source ID; `authors`, `origin`, `references`, `license`, and `notice` record provenance. Use an empty `references` array for original work with no source references. `license` uses an SPDX identifier where possible. New Grimoire-authored content uses `CC-BY-SA-4.0` per `CONTENT-PROVENANCE.md`; inherited content remains identified as BKWILDCARDS by bkidderz under the same license. The software remains MIT licensed.
- `themes[].id`: stable machine ID; `themes[].label`: human-readable name. IDs, rather than labels, are used for scoping.
- `packs[].id`: stable pack ID within the source; `packs[].path` is relative to the source root.
- `pack.id`: must match the pack ID in the root index. `pack.label` is the human-readable pack name, not necessarily the theme name.
- `scope.kind`: `theme` or `global`; `scope.theme_id` is required for a theme pack and must exist in the index; `scope.gender` is optional, with null meaning no gender restriction.

### Categories and content

- `categories[].id`: stable category ID within its pack. `input_key` is the unique ComfyUI widget/input name across all loaded sources; preserve the legacy `<pack>_<id>` input name for existing workflows, and use a stable source-qualified key for new inputs. It is separate from the random-stream key.
- `categories[].stable_key`: immutable random-stream identity. For legacy categories the adapter must preserve the exact current key (`<pack>_<id>`) so seeded picks do not change. New categories use a source-qualified key to avoid collisions. Never derive this key from a label or UI position.
- `content.path`: path relative to the pack directory.
- `content.format`: `lines` for the legacy-compatible form; `jsonl` for structured entries.
- `content.sections`: new data may declare section labels and entry membership explicitly. `legacy-hash-headings` is compatibility-only; do not use the current heading-cleanup heuristics as the new schema.
- `selection.mode`: `toggle`, `section`, or a later declared selection type. Section selection supports off, random-from-all, and a named section. `selection.default` must be valid for the declared mode; `off` is the symbolic default for an unselected category.
- Empty or missing content is a validation issue; report it with source and category context rather than silently creating an unusable selector.

### UI and semantics

- `ui.label`, `ui.group`, `ui.order` control widget naming and placement. They do not define prompt meaning.
- `semantics.role` is a stable vocabulary such as `identity.metatype`, `appearance.hair.color`, `wardrobe.outfit`, `scene.environment`, `action.pose`, or `camera.angle`.
- `semantics.label` is the human-readable output label; `semantics.order` is the default composition order. A renderer may use role-aware ordering rather than relying only on this number.
- New categories should declare a semantic role. Legacy categories can infer a temporary role from stable category IDs and `prompt_label`, with inference recorded in the adapter rather than copied into content.

### Renderer-specific options

Renderer behavior belongs to renderer profiles, not to the legacy wildcard parser. A future category or entry may include an optional `renderer_hints` object keyed by stable renderer IDs (for example `flux`, `sdxl`, or `z_image`). Each adapter owns and validates its hint keys; unknown hints must be preserved or surfaced as validation warnings, never interpreted by another renderer. Use hints for formatting or model-specific weighting. Keep a common semantic value/fallback so all renderers work when no hint exists.

If a model needs genuinely different wording, a structured entry may provide an explicit `renderer_variants` map keyed by renderer ID. Each variant remains content under the source license and must have provenance. Renderers use the common `text` when a variant is missing. Do not make every content file model-specific by default.

### Structured entry format for new content

For explicit section membership and stable per-entry IDs, use JSON Lines (`content.format: "jsonl"`) rather than inferring structure from prose headings:

```jsonl
{ "id": "corporate-executive-01", "section": "Corporate Executive", "text": "a tailored graphite jacket with a high collar" }
{ "id": "street-runner-01", "section": "Street Runner", "text": "a weathered utility coat with luminous seam piping", "renderer_variants": { "sdxl": "weathered utility coat, luminous seam piping" }, "renderer_hints": { "flux": { "emphasis": "wardrobe" } } }
```

Each line is one JSON object. `id`, `text`, and `section` (when the category is sectioned) are stable fields. `renderer_variants` and `renderer_hints` are optional; their values are interpreted only by the named adapter.

## Stable identity and seed compatibility

Current draws create `random.Random(seed + CRC32(category_key))` and choose from a file's current ordered pool. Therefore:

- preserve each legacy category key exactly to retain its independent random stream; for new categories, assign a source-qualified stable key once and keep it;
- changing labels or UI grouping must not change the random key;
- adding, deleting, or reordering entries can change which item a seed selects, even when IDs stay stable;
- section labels are user-facing workflow values and should be migrated or aliased if renamed;
- any new entry-level randomization must use stable entry IDs and a documented deterministic algorithm.

A schema migration should accept both legacy and versioned roots, convert both to one normalized in-memory model, and leave old input names and saved choices usable. The legacy reader should remain the fallback until the normalized model reproduces current theme/gender filtering, section choices, output order, and per-category deterministic draws.

## Out of scope for this step

This proposal does not implement a loader, validator, schema file, renderer, prompt intermediate representation, or workflow migration. Those changes belong to later implementation steps after this contract is reviewed.