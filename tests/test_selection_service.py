"""Compatibility and identity tests for deterministic selection streams."""

import os
import random
import subprocess
import sys
import unittest
from pathlib import Path

from bkwildcards import catalog, library, selection

ROOT = Path(__file__).resolve().parents[1]


class DeterministicSelectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = selection.DeterministicSelectionService()

    def test_legacy_key_stream_matches_original_formula(self):
        seed = 271828
        key = "common_art_style"
        expected = random.Random(seed + library.stable_offset(key))
        actual = self.service.rng_for_legacy_key(seed, key)
        self.assertEqual([expected.random() for _ in range(8)],
                         [actual.random() for _ in range(8)])

    def test_legacy_category_draw_matches_library_draw(self):
        category = next(
            row for row in catalog.get_default_catalog().load().legacy_categories
            if row["key"] == "common_art_style"
        )
        seed = 161803
        choice = library.SECTION_ANY
        expected = library.draw(
            category, choice,
            random.Random(seed + library.stable_offset(category["key"])),
        )
        self.assertEqual(self.service.draw_legacy(category, choice, seed), expected)

    def test_legacy_and_source_qualified_keys_use_their_declared_paths(self):
        legacy = {"key": "common_art_style", "stable_key": "common_art_style"}
        qualified = {
            "key": "outfit-widget",
            "stable_key": "outfit-widget",
            "source_id": "pag-original",
        }
        seed = 57721
        old_expected = random.Random(seed + library.stable_offset(legacy["key"]))
        old_actual = self.service.rng_for_category(seed, legacy)
        self.assertEqual(old_expected.random(), old_actual.random())
        qualified_a = self.service.rng_for_category(seed, qualified)
        qualified_b = self.service.rng_for_source_key(
            seed, "pag-original", "outfit-widget"
        )
        self.assertEqual([qualified_a.random() for _ in range(5)],
                         [qualified_b.random() for _ in range(5)])

    def test_stable_entry_ids_define_independent_repeatable_streams(self):
        first = self.service.rng_for_entry(1234, "pag-original", "outfit", "coat-01")
        repeated = self.service.rng_for_entry(1234, "pag-original", "outfit", "coat-01")
        other_entry = self.service.rng_for_entry(1234, "pag-original", "outfit", "coat-02")
        first_values = [first.random() for _ in range(8)]
        self.assertEqual(first_values, [repeated.random() for _ in range(8)])
        self.assertNotEqual(first_values, [other_entry.random() for _ in range(8)])

    def test_source_stream_is_process_independent(self):
        script = """from bkwildcards.selection import DeterministicSelectionService
rng = DeterministicSelectionService.rng_for_source_key(8675309, 'source-a', 'source-a:pack:category')
print([rng.randrange(1000000) for _ in range(8)])
"""
        outputs = []
        for _ in range(2):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = "random"
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=str(ROOT), env=environment,
                check=True, capture_output=True, text=True,
            )
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
