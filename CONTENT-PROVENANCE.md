# Content provenance and licensing

This document records where prompt-library content comes from and which terms apply. The code license and the content license are separate; see [LICENSE](LICENSE) and [LICENSE-CONTENT](LICENSE-CONTENT).

## Inherited library

| Path | Author / source | License | Relationship |
|---|---|---|---|
| `wildcards/**` | BKWILDCARDS by bkidderz | CC BY-SA 4.0 | Inherited content from the fork; covered by `LICENSE-CONTENT`. |

Required attribution for this inherited library:

> Wildcard content from BKWILDCARDS by bkidderz, licensed under CC BY-SA 4.0.

Any redistributed adaptations or extensions of this library must follow CC BY-SA 4.0, including attribution and ShareAlike. The license explicitly says it does not assert ShareAlike over generated images; see `LICENSE-CONTENT` for the author's statement and the incorporated legal code.

## Independently authored Grimoire content

No independently authored Grimoire wildcard library is included yet. New content must be written independently, with its author, source or research references, and chosen license recorded before it is added to a distributable library. Do not copy, adapt, translate, or lightly rewrite entries from `wildcards/` into a differently licensed collection. Avoid third-party characters, settings, and other protected expression unless there is a clear right to use them.

Future independently authored Grimoire content will use **CC BY-SA 4.0**, matching the inherited wildcard content license. This applies to original contributions as a licensing choice; it does not mean those contributions were copied or adapted from the inherited library. Record the author, source or research references, and license with each collection. The software remains MIT licensed.

## Provenance record for future additions

For each new content collection or file, record:

- path or collection identifier;
- author or contributor;
- source and research references, or `original work`;
- license identifier and the file that contains its terms;
- whether the material is original, adapted, or imported;
- any changes from its source and the required attribution.

The current loader only discovers content under `wildcards/`. Keep new content out of that directory until its provenance and license are settled and the content-loading design can preserve the separation at runtime and in packaged distributions.