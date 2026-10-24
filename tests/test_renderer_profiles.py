"""Contract tests for model-target renderer profiles."""

import unittest

from bkwildcards import rendering
from bkwildcards.contracts import PromptDocument, PromptFragment


class RendererProfileTests(unittest.TestCase):
    def test_registry_contains_supported_model_families(self):
        profiles = rendering.get_renderer_profiles().all()
        self.assertEqual(
            {profile.profile_id for profile in profiles},
            {"legacy-text", "krea-2", "flux", "anima", "z-image", "sdxl"},
        )
        self.assertEqual(rendering.get_renderer_profiles().get().profile_id,
                         "legacy-text")

    def test_profiles_preserve_text_and_existing_modes(self):
        document = PromptDocument(
            fragments=(
                PromptFragment("oil-painted copper armor", label="wardrobe", order=2),
                PromptFragment("rainy neon street", label="scene", order=10),
            ),
            metadata={"separator": " / ", "label_mode": "comma-separated"},
        )
        expected = "oil-painted copper armor / rainy neon street"
        for profile in rendering.get_renderer_profiles().all():
            with self.subTest(profile=profile.profile_id):
                self.assertEqual(
                    rendering.render_for_profile(document, profile.profile_id),
                    expected,
                )

    def test_resolver_profiles_preserve_legacy_composed_output(self):
        from bkwildcards import nodes

        args = (314159, ", ", "Female", "_ghost.runner", {
            "common_art_style": "Painterly", "common_metatype": "Human",
        })
        legacy = nodes.resolve_prompt(*args, label_mode="labeled", mayhem=True)
        for profile in rendering.get_renderer_profiles().all():
            with self.subTest(profile=profile.profile_id):
                self.assertEqual(
                    nodes.resolve_prompt(*args, label_mode="labeled", mayhem=True,
                                         renderer_id=profile.profile_id),
                    legacy,
                )

    def test_profile_contract_is_adapter_capability_not_model_claim(self):
        profiles = rendering.get_renderer_profiles()
        for profile_id in ("krea-2", "flux", "anima", "z-image", "sdxl"):
            profile = profiles.get(profile_id)
            self.assertEqual(profile.prompt_style, "fragment-preserving-text")
            self.assertTrue(profile.supports_single_text_output)
            self.assertTrue(profile.supports_labeled_output)
            self.assertTrue(profile.supports_json_output)
            self.assertFalse(profile.supports_negative_prompt_output)
            self.assertFalse(profile.supports_secondary_prompt_output)
            self.assertEqual(
                rendering.get_renderer(profile_id).renderer_id, profile_id
            )

    def test_unknown_profile_fails_with_useful_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown renderer profile"):
            rendering.get_renderer("not-a-profile")


if __name__ == "__main__":
    unittest.main()
