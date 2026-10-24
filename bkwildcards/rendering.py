"""Legacy prompt text rendering, independent from content selection."""

import json

from .contracts import PromptDocument, RendererProfile

# label_output modes (the Settings dropdown). Legacy saved workflows stored this
# as a BOOLEAN; _label_mode() coerces True -> labeled, False -> comma-separated,
# so an old workflow still resolves the same way it always did.
LABEL_PLAIN = "comma-separated"      # the old "plain": comma-joined text only
LABEL_LABELED = "labeled"            # "build: ..., hair: ..." lines (default)
LABEL_JSON = "JSON"                  # the labeled picks as a JSON object
_LABEL_MODES = (LABEL_PLAIN, LABEL_LABELED, LABEL_JSON)


def _label_mode(value):
    """Normalise the label_output widget value (or a legacy boolean) to a mode."""
    if value is True:
        return LABEL_LABELED
    if value is False:
        return LABEL_PLAIN
    if isinstance(value, str) and value in _LABEL_MODES:
        return value
    return LABEL_LABELED


def _format_picks(picks, separator, mode):
    """Join (order, label, text) picks by output mode.

    Stable sort by `order` matches the pre-existing behaviour (`_CATEGORIES` is
    already ordered by (order, pack, id), so equal-order picks keep their place).
    - LABEL_PLAIN: comma-joined text only (uses the separator widget).
    - LABEL_LABELED: 'label: ...' lines; adjacent same-label picks merge (the
      three hair categories -> one 'hair:' line).
    - LABEL_JSON: the SAME labeled picks as a JSON object {label: text}; same
      off-omission, same-label picks merged into one key.
    """
    picks = sorted(picks, key=lambda p: p[0])
    if mode == LABEL_PLAIN:
        return separator.join(text for _, _, text in picks)
    groups = []
    for _, label, text in picks:
        if groups and groups[-1][0] == label:
            groups[-1][1].append(text)
        else:
            groups.append((label, [text]))
    if mode == LABEL_JSON:
        obj = {}
        for label, texts in groups:
            val = ", ".join(texts)
            obj[label] = (obj[label] + ", " + val) if label in obj else val
        return json.dumps(obj, indent=2, ensure_ascii=False)
    return ",\n".join(
        "{}: {}".format(label, ", ".join(texts)) for label, texts in groups
    )


class FragmentTextRenderer:
    """Render ordered semantic fragments using the established text formats."""

    def __init__(self, renderer_id="legacy-text"):
        self.renderer_id = renderer_id

    def render(self, document, options):
        options = dict(document.metadata, **(options or {}))
        picks = [
            (fragment.order, fragment.label or fragment.role or "prompt", fragment.text)
            for fragment in document.fragments
        ]
        return _format_picks(
            picks,
            options.get("separator", ", "),
            _label_mode(options.get("label_mode", LABEL_LABELED)),
        )


class LegacyTextRenderer(FragmentTextRenderer):
    """Serialize legacy ordered picks without changing prompt bytes."""

    def __init__(self):
        super().__init__("legacy-text")


class RendererProfileCatalog:
    """Small immutable registry of stable model-target profile metadata."""

    def __init__(self, profiles):
        self._profiles = {profile.profile_id: profile for profile in profiles}

    def get(self, profile_id=None):
        key = profile_id or "legacy-text"
        try:
            return self._profiles[key]
        except KeyError:
            raise ValueError("Unknown renderer profile: {}".format(key))

    def all(self):
        return tuple(self._profiles.values())


# Profiles share a fragment-preserving serializer for now. This is deliberate:
# model-specific prompt transformations should only be added when backed by
# concrete model guidance and compatibility tests. The profiles still provide
# stable IDs, model-family/variant metadata, and a capability contract for
# future adapters. This selector currently emits a single text output.
_PROFILE_DATA = (
    ("legacy-text", "Legacy text", "generic", (), ()),
    ("krea-2", "Krea 2", "Krea 2", ("Turbo", "Raw"),
     ("https://github.com/krea-ai/krea-2/blob/main/docs/prompting.md",)),
    ("flux", "FLUX", "FLUX", (), ()),
    ("anima", "Anima", "Anima", (), ()),
    ("z-image", "Z-Image", "Z-Image", ("Turbo", "Base", "Omni-Base", "Edit"),
     ("https://github.com/Tongyi-MAI/Z-Image",)),
    ("sdxl", "SDXL", "Stable Diffusion XL", ("Base", "Refiner"), ()),
)

_PROFILES = RendererProfileCatalog(
    RendererProfile(
        profile_id=profile_id,
        label=label,
        model_family=model_family,
        variants=variants,
        renderer_id=profile_id,
        prompt_style="fragment-preserving-text",
        references=references,
    )
    for profile_id, label, model_family, variants, references in _PROFILE_DATA
)


def get_renderer_profiles():
    return _PROFILES


def get_renderer(profile_id=None):
    """Return a renderer for a profile; unknown IDs fail clearly."""
    profile = _PROFILES.get(profile_id)
    if profile.profile_id == "legacy-text":
        return LegacyTextRenderer()
    return FragmentTextRenderer(profile.renderer_id)


def render_for_profile(document, profile_id=None, options=None):
    """Render a document through a registered profile, defaulting to legacy."""
    return get_renderer(profile_id).render(document, options or {})
