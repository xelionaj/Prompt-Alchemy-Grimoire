"""Regression checks for the staged prompt composition boundary."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from bkwildcards import catalog, composition, nodes, rendering
from bkwildcards.contracts import CompositionRequest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "COMPATIBILITY-BASELINE.json").read_text(encoding="utf-8"))


class PromptCompositionCompatibilityTests(unittest.TestCase):
    def test_five_legacy_outputs_and_seeded_slider_state_match_baseline(self):
        for scenario in BASELINE["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                output = nodes.resolve_prompt(
                    scenario["seed"], ", ", scenario["gender"], scenario["theme"],
                    scenario["choices"], label_mode=scenario["label_mode"],
                    mayhem=scenario["mayhem"],
                )
                self.assertEqual(len(output), scenario["output_chars"])
                self.assertEqual(
                    hashlib.sha256(output.encode("utf-8")).hexdigest(),
                    scenario["sha256_utf8"],
                )
                expected_state = scenario.get("slider_state")
                if expected_state is not None:
                    actual_state = nodes.slider_state(
                        scenario["seed"], scenario["gender"], scenario["choices"]
                    )
                    self.assertEqual(actual_state, expected_state)

    def test_composer_document_and_renderer_match_compatibility_facade(self):
        snapshot = catalog.get_default_catalog().load()
        composer = composition.get_default_composer()
        renderer = rendering.LegacyTextRenderer()
        for scenario in BASELINE["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                request = CompositionRequest(
                    seed=scenario["seed"],
                    separator=", ",
                    gender=scenario["gender"],
                    theme=scenario["theme"],
                    choices=scenario["choices"],
                    label_mode=scenario["label_mode"],
                    mayhem=scenario["mayhem"],
                )
                document = composer.compose(request, snapshot)
                output = renderer.render(document, {})
                self.assertEqual(output, nodes.resolve_prompt(
                    scenario["seed"], ", ", scenario["gender"], scenario["theme"],
                    scenario["choices"], label_mode=scenario["label_mode"],
                    mayhem=scenario["mayhem"],
                ))
                self.assertTrue(all(fragment.text for fragment in document.fragments))

    def test_fixed_seed_and_mayhem_are_repeatable_and_seed_sensitive(self):
        args = (314159, ", ", "Female", "_ghost.runner", {
            "common_art_style": "Painterly", "common_metatype": "Human",
        })
        first = nodes.resolve_prompt(*args, label_mode="JSON", mayhem=True)
        repeated = nodes.resolve_prompt(*args, label_mode="JSON", mayhem=True)
        changed_seed = nodes.resolve_prompt(
            314160, *args[1:], label_mode="JSON", mayhem=True
        )
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, changed_seed)

    def test_seeded_prompt_is_stable_across_processes(self):
        script = """from bkwildcards.nodes import resolve_prompt
print(resolve_prompt(314159, ', ', 'Female', '_ghost.runner', {'common_art_style': 'Painterly', 'common_metatype': 'Human'}, label_mode='JSON', mayhem=True))
"""
        outputs = []
        for _ in range(2):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = "random"
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=str(ROOT),
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_mayhem_document_mixes_theme_packs(self):
        snapshot = catalog.get_default_catalog().load()
        request = CompositionRequest(
            seed=314159,
            gender="Female",
            theme="_ghost.runner",
            choices={"common_art_style": "Painterly", "common_metatype": "Human"},
            label_mode="labeled",
            mayhem=True,
        )
        document = composition.get_default_composer().compose(request, snapshot)
        categories = {item.input_key: item for item in snapshot.categories}
        theme_packs = {
            categories[fragment.input_key].pack_id
            for fragment in document.fragments
            if fragment.input_key in categories
            and categories[fragment.input_key].scope_kind == "theme"
        }
        self.assertGreaterEqual(len(theme_packs), 2)

    def test_node_build_uses_composer_and_renderer(self):
        scenario = BASELINE["scenarios"][0]
        result = nodes.BKWildcardSelector().build(
            scenario["seed"], ", ",
            gender=scenario["gender"],
            theme=scenario["theme"],
            label_output=scenario["label_mode"],
            mayhem=scenario["mayhem"],
            **scenario["choices"],
        )
        expected = nodes.resolve_prompt(
            scenario["seed"], ", ", scenario["gender"], scenario["theme"],
            scenario["choices"], label_mode=scenario["label_mode"],
            mayhem=scenario["mayhem"],
        )
        self.assertEqual(result["result"][0], expected)
        self.assertEqual(result["ui"]["bk_resolved"][0], expected)

    def test_random_environment_composes_a_scene_fragment(self):
        scenario = BASELINE["scenarios"][0]
        choices = dict(scenario["choices"])
        environment = next(
            item for item in nodes._CATEGORIES
            if item["id"] == "environment" and item["select"] == "section"
        )
        choices[environment["key"]] = catalog.library.SECTION_ANY
        output = nodes.resolve_prompt(
            scenario["seed"], ", ", scenario["gender"], scenario["theme"],
            choices, label_mode="labeled",
        )
        self.assertIn("scene/background:", output)
        self.assertNotEqual(output, "gender: a feminine adult")

    def test_saved_workflow_node_and_widget_contract_is_unchanged(self):
        contract = BASELINE["workflow_contract"]
        node = nodes.BKWildcardSelector
        self.assertIn(contract["node_class"], nodes.NODE_CLASS_MAPPINGS)
        self.assertEqual(
            nodes.NODE_DISPLAY_NAME_MAPPINGS[contract["node_class"]],
            contract["display_name"],
        )
        self.assertEqual(node.CATEGORY, contract["category"])
        self.assertEqual(list(node.RETURN_TYPES), contract["return_types"])
        self.assertEqual(list(node.RETURN_NAMES), contract["return_names"])
        input_types = node.INPUT_TYPES()
        # Preserve the old required widget ordering. Optional widgets still
        # appear in the UI but old API prompts can omit this new field.
        self.assertEqual(list(input_types["required"].keys()),
                         contract["required_input_keys"])
        profile_widget = input_types["optional"]["renderer_profile"]
        self.assertEqual(profile_widget[1]["default"], "legacy-text")

    def test_node_build_selects_profile_and_keeps_default_compatible(self):
        scenario = BASELINE["scenarios"][0]
        node = nodes.BKWildcardSelector()
        kwargs = dict(scenario["choices"])
        common = dict(
            seed=scenario["seed"], separator=", ", gender=scenario["gender"],
            theme=scenario["theme"], label_output=scenario["label_mode"],
            mayhem=scenario["mayhem"], **kwargs,
        )
        default = node.build(**common)["result"][0]
        selected = node.build(**common, renderer_profile="krea-2")["result"][0]
        expected = nodes.resolve_prompt(
            scenario["seed"], ", ", scenario["gender"], scenario["theme"],
            scenario["choices"], label_mode=scenario["label_mode"],
            mayhem=scenario["mayhem"],
        )
        self.assertEqual(default, expected)
        self.assertEqual(selected, expected)


if __name__ == "__main__":
    unittest.main()
