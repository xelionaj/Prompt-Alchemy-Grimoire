"""Composition consumes normalized catalog records and selected entries."""

import unittest

from bkwildcards.composition import LegacyPromptComposer
from bkwildcards.contracts import (
    CatalogSnapshot,
    CategoryRecord,
    CompositionRequest,
    PackRecord,
    ProvenanceRecord,
    SelectedEntry,
    ThemeRecord,
)
from bkwildcards.rendering import LegacyTextRenderer


class StubSelectionService:
    def __init__(self):
        self.calls = []

    def select_legacy(self, category, choice, seed):
        self.calls.append((category, choice, seed))
        return SelectedEntry(
            text="a moonlit glass observatory",
            category_id=category.id,
            input_key=category.input_key,
            stable_key=category.stable_key,
            source_id=category.source_id,
            section="Night",
            entry_id="observatory-01",
            provenance=category.provenance.as_dict(),
        )


class CompositionCatalogBoundaryTests(unittest.TestCase):
    def test_composer_uses_supplied_records_and_selection_result(self):
        provenance = ProvenanceRecord(
            source_id="fixture-source",
            authors=("Prompt-Alchemy-Grimoire contributors",),
            origin="independent test fixture",
            license_id="CC-BY-SA-4.0",
            notice="fixture notice",
        )
        pack = PackRecord(
            id="fixture-pack", label="Fixture", scope_kind="theme",
            theme_id="fixture-theme", gender=None, source_id="fixture-source",
            provenance=provenance,
        )
        theme = ThemeRecord(
            id="fixture-theme", label="Fixture Theme", source_id="fixture-source",
            pack_ids=(pack.id,), provenance=provenance,
        )
        category = CategoryRecord(
            id="scene", input_key="fixture_scene",
            stable_key="fixture-source:fixture-pack:scene",
            pack_id=pack.id, pack_label=pack.label, scope_kind="theme",
            theme_id=theme.id, gender=None,
            content_path="path-that-must-not-be-read.txt", content_format="lines",
            entry_count=1, selection_mode="toggle", selection_default=False,
            sections=("Night",), ui_label="Scene", ui_group="scene",
            ui_order=10, prompt_label="scene/background", semantic_role="environment",
            composition_order=30, source_id=provenance.source_id,
            provenance=provenance,
        )
        snapshot = CatalogSnapshot(
            packs=(pack,), categories=(category,), themes=(theme,),
            sources=(provenance,),
        )
        selector = StubSelectionService()
        composer = LegacyPromptComposer(selector)
        request = CompositionRequest(
            seed=2468, theme=theme.label, choices={category.input_key: True},
            label_mode="labeled",
        )

        document = composer.compose(request, snapshot)
        rendered = LegacyTextRenderer().render(document, {})

        self.assertEqual(len(selector.calls), 1)
        self.assertIs(selector.calls[0][0], category)
        self.assertEqual(selector.calls[0][1:], (True, request.seed))
        self.assertEqual(rendered, "scene/background: a moonlit glass observatory")
        self.assertEqual(document.fragments[0].role, "environment")
        self.assertEqual(document.fragments[0].source_id, provenance.source_id)
        self.assertEqual(document.fragments[0].provenance, provenance.as_dict())


if __name__ == "__main__":
    unittest.main()
