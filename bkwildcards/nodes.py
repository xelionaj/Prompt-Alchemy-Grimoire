"""Prompt-Alchemy-Grimoire node definitions."""


from . import library
from . import catalog
from . import sliders
from . import skintones

# Scanned once at import. INPUT_TYPES is called on every /object_info request,
# so the walk is cached here. Adding a wildcard file needs a ComfyUI restart or
# "Refresh Node Definitions" before its toggle appears.
_CATALOG = catalog.get_default_catalog().load()
_PACKS = list(_CATALOG.legacy_packs)
_CATEGORIES = list(_CATALOG.legacy_categories)
_THEMES = sorted(_CATALOG.theme_labels, key=str.lower)  # alphabetical dropdown
_THEME_TO_PACK = _CATALOG.legacy_theme_to_pack
_GENDERS = list(_CATALOG.genders)

# Written into the workflow node's `properties` so the resolved text survives a
# save and, via extra_pnginfo, an embed into a generated PNG.
PROP_PROMPT = "bk_resolved"
PROP_SLIDERS = "bk_sliders"  # slider lane state (mode, values, register) per run


def _stamp_workflow(extra_pnginfo, unique_id, prompt_text, extra_props=None):
    """Write the resolved text into the workflow snapshot bound for the PNG.

    ComfyUI captures the workflow at queue time, before this node runs, so a
    widget written after execution would always be one generation stale in the
    saved image. Mutating the `extra_pnginfo` snapshot here — which SaveImage
    serialises into a PNG text chunk after we return — puts *this* run's text
    into *this* run's file.

    Written to `properties` rather than `widgets_values` because the latter is
    positional and its indices shift whenever a widget is added.
    """
    if not extra_pnginfo or unique_id is None:
        return
    try:
        workflow = extra_pnginfo.get("workflow")
        if not isinstance(workflow, dict):
            return
        for node in workflow.get("nodes", []) or []:
            if str(node.get("id")) != str(unique_id):
                continue
            props = node.get("properties")
            if not isinstance(props, dict):
                props = {}
                node["properties"] = props
            props[PROP_PROMPT] = prompt_text
            for key, value in (extra_props or {}).items():
                props[key] = value
            break
    except Exception as exc:  # never let metadata stamping break a render
        print("[Prompt-Alchemy-Grimoire] could not stamp workflow metadata: {}".format(exc))


# Prompt composition and text serialization live behind explicit contracts.
from . import composition, rendering
from .contracts import CompositionRequest

GENDER_OFF = composition.GENDER_OFF
GENDER_RANDOM = composition.GENDER_RANDOM
GENDER_FLUID = composition.GENDER_FLUID
ART_STYLE_KEY = composition.ART_STYLE_KEY
ART_STYLE_KEY_2 = composition.ART_STYLE_KEY_2
_ART_STYLE_KEYS = composition._ART_STYLE_KEYS
_METATYPE_KEY = composition._METATYPE_KEY
LABEL_PLAIN = rendering.LABEL_PLAIN
LABEL_LABELED = rendering.LABEL_LABELED
LABEL_JSON = rendering.LABEL_JSON
_label_mode = rendering._label_mode
resolve_prompt = composition.resolve_prompt
slider_state = composition.slider_state
mayhem_slider_state = composition.mayhem_slider_state
_PROMPT_COMPOSER = composition.get_default_composer()
_PROMPT_RENDERER = composition.get_default_renderer()


class BKWildcardSelector:
    """Pick a gender and a theme, choose categories, emit one prompt string.

    Scoping is enforced in Python. A category belonging to another theme or
    another gender cannot contribute no matter what its widget says. The frontend
    extension only hides those widgets; if it fails to load, behaviour is
    unchanged and the node simply shows everything.
    """

    @classmethod
    def INPUT_TYPES(cls):
        required = {}

        # Emit one category's widget (section dropdown or boolean toggle) into
        # `required`. A closure so the Art Style category can be placed at the
        # top (before gender) while every other category flows through the loop.
        def emit(cat):
            scope_bits = []
            if cat["gender"]:
                scope_bits.append(cat["gender"])
            scope_bits.append("always on" if cat["is_global"] else cat["pack_label"])
            scope = " / ".join(scope_bits)
            if cat["select"] == library.SELECT_SECTION:
                options = library.section_options(cat)
                required[cat["key"]] = (
                    options,
                    {
                        "default": options[0],
                        "tooltip": "{} — {}. Pick a section, or random to draw from all {} entries.".format(
                            scope, cat["label"], cat["count"]
                        ),
                    },
                )
            else:
                required[cat["key"]] = (
                    "BOOLEAN",
                    {
                        "default": cat["default"],
                        "label_on": "yes",
                        "label_off": "no",
                        "tooltip": "{} — {} ({} entries)".format(
                            scope, cat["label"], cat["count"]
                        ),
                    },
                )

        # --- scope selectors, top of the node ---
        # Theme is its own UI section; gender leads the Identity section. The JS
        # assigns their section headers (theme -> "Theme", gender -> "Identity").
        if _THEMES:
            required["theme"] = (
                _THEMES,
                {
                    "default": _THEMES[0],
                    "tooltip": "Only this theme's categories contribute. Others are ignored.",
                },
            )

        # Art Style (and the optional Art Style 2): the options under the Theme
        # header, emitted here right after the theme selector and before gender,
        # and leading the output (their low `order`s in _pack.json). Both are
        # excluded from the general globals loop below so they render here, not
        # in the Identity/Physical block.
        for akey in _ART_STYLE_KEYS:
            art_style_cat = next(
                (c for c in _CATEGORIES if c["key"] == akey), None
            )
            if art_style_cat:
                emit(art_style_cat)

        if _GENDERS:
            required["gender"] = (
                [GENDER_OFF, GENDER_RANDOM] + _GENDERS + [GENDER_FLUID],
                {
                    "default": _GENDERS[0],
                    "tooltip": "The subject's gender, injected into the prompt (a feminine adult / a masculine adult). "
                    "— off —: no gender word and no gendered categories. — random —: roll a gender "
                    "per seed. Fluid: both genders' physical options available and mixable "
                    "(an androgynous adult subject).",
                },
            )

        # --- category selectors ---
        # Global packs first, then each theme's block, each sorted by `display`
        # so a category can be moved on the node without moving it in the
        # prompt. Inputs for every theme and gender always exist, which is what
        # lets settings survive switching away and back.
        def by_display(cats):
            return sorted(cats, key=lambda c: (c["display"], c["pack"], c["id"]))

        # Most globals (Identity, Physical, Hair) render above the theme block.
        # The Camera section is pinned BELOW the theme's Scene, so its globals
        # are emitted after all theme blocks.
        POST_THEME_GROUPS = {"Camera"}
        globals_all = [c for c in _CATEGORIES if c["is_global"] and c["key"] not in _ART_STYLE_KEYS]
        pre_globals = by_display(
            [c for c in globals_all if c.get("group") not in POST_THEME_GROUPS]
        )
        post_globals = by_display(
            [c for c in globals_all if c.get("group") in POST_THEME_GROUPS]
        )

        ordered = list(pre_globals)
        for theme in _THEMES:
            pack = _THEME_TO_PACK[theme]
            ordered += by_display([c for c in _CATEGORIES if c["pack"] == pack])
        ordered += post_globals

        # Slider Build Control (experimental): six fixed inputs emitted directly
        # after the last Build-preset category so they render inside the
        # Physical - Body section: the mode selector, the Build presets under
        # it, then the five body sliders (the JS hides them while the mode is off).
        # Inserting mid-list shifts widgets_values (a one-time node re-add) —
        # the owner's explicit call.
        def emit_body_mode():
            required[sliders.TOGGLE_INPUT] = (
                list(sliders.MODES),
                {
                    "default": sliders.MODE_OFF,
                    "tooltip": "Experimental. on: the five sliders below are synthesized into one "
                    "build phrase (register follows Gender) and the Build preset is ignored. "
                    "— random —: the five values are rolled from the seed each run and shown "
                    "on the sliders. preset: the Build preset dropdown speaks and the sliders "
                    "snap to its section as a starting point. — off —: sliders hidden and "
                    "inert. Gender — off — silences the lane. Mayhem ignores it.",
                },
            )
        def emit_body_axes():
            # No tooltips on the five body sliders: each slider's own label reads
            # out its value and the phrase it selects, live, as it moves (owner,
            # 2026-09-01 — the hover pop-up got in the way of the slider).
            for axis in sliders.AXES:
                required[sliders.AXIS_INPUTS[axis]] = (
                    "INT",
                    {
                        "default": sliders.SLIDER_DEFAULT,
                        "min": sliders.SLIDER_MIN,
                        "max": sliders.SLIDER_MAX,
                        "step": 1,
                        "display": "slider",
                    },
                )

        def emit_skin_tone():
            # Metatype-driven coloration axis (experimental, 0.9.16). Renders in
            # Physical - Body, under the sliders. off / random / family; the roll
            # is kept coherent with the active Metatype's skin group in Python.
            opts = skintones.family_options()
            required[skintones.INPUT] = (
                opts,
                {
                    "default": opts[0],
                    "tooltip": "Experimental. Coloration rolled from a palette that fits the "
                    "current Metatype (human tones for people, reds/violets for tieflings, "
                    "matte/chrome for androids, fur for beast-forms, …). — off —: none. "
                    "— random —: roll within the metatype's group. A family name: roll within "
                    "it. Set Metatype for a fitting roll; with none it defaults to human tones.",
                },
            )

        # Physical - Body order (owner, 2026-09-01): the Body Sliders selector,
        # then the Build preset dropdowns directly under it, then the five
        # sliders. The selector goes out just before the first Physical - Body
        # category and the sliders right after the last.
        body_cats = [c for c in ordered if c.get("group") == sliders.BODY_GROUP]
        body_first = body_cats[0] if body_cats else None
        body_last = body_cats[-1] if body_cats else None
        for cat in ordered:
            if cat is body_first:
                emit_body_mode()
            emit(cat)
            if cat is body_last:
                emit_body_axes()
                emit_skin_tone()
        if not body_cats:  # no Build categories found: still expose the lane
            emit_body_mode()
            emit_body_axes()
            emit_skin_tone()

        # --- run controls, below the selectors ---
        required["separator"] = (
            "STRING",
            {
                "default": ", ",
                "multiline": False,
                "tooltip": "Placed between the selections from each enabled category.",
            },
        )
        required["seed"] = (
            "INT",
            {
                "default": 0,
                "min": 0,
                "max": 0xFFFFFFFFFFFFFFFF,
                "control_after_generate": True,
                "tooltip": "Drives which line is drawn from each enabled category.",
            },
        )
        required["label_output"] = (
            [LABEL_PLAIN, LABEL_LABELED, LABEL_JSON],
            {
                "default": LABEL_LABELED,
                "tooltip": "How the prompt is formatted. comma-separated: one comma-joined "
                "string. labeled: tag each active selection (build:, hair:, …) so the "
                "renderer reads structured attributes. JSON: the same labeled selections "
                "as a JSON object. All three omit categories set to off.",
            },
        )
        required["mayhem"] = (
            "BOOLEAN",
            {
                "default": False,
                "label_on": "MAYHEM",
                "label_off": "off",
                "tooltip": "One-click chaos: ignore every selection and the theme/gender, and "
                "build a fully random CROSS-THEME image seeded by seed. Queue again "
                "(advance the seed) for a new one. Includes all themes and adult content.",
            },
        )

        # Display box, declared LAST so it renders below everything else.
        #
        # NOTE: widget order is positional in a saved workflow's widgets_values
        # array. Moving or inserting an input shifts every value after it.
        # Treat this ordering as frozen once the repo is published.
        required["resolved"] = (
            "STRING",
            {
                "default": "",
                "multiline": True,
                "tooltip": "The prompt this node produced. Filled in automatically; edits are ignored.",
            },
        )

        return {
            "required": required,
            "hidden": {
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "build"
    CATEGORY = "Prompt-Alchemy-Grimoire"
    DESCRIPTION = (
        "Pick a gender and theme, then choose categories. Draws one line from each "
        "and returns them joined as a single prompt string. The resolved text is "
        "shown on the node and saved into generated PNGs."
    )

    def build(
        self,
        seed,
        separator,
        resolved="",
        gender=None,
        theme=None,
        label_output=LABEL_LABELED,
        mayhem=False,
        extra_pnginfo=None,
        unique_id=None,
        **choices
    ):
        request = CompositionRequest(
            seed=int(seed), separator=separator, gender=gender, theme=theme,
            choices=choices, label_mode=_label_mode(label_output), mayhem=bool(mayhem),
        )
        document = _PROMPT_COMPOSER.compose(request, _CATALOG)
        prompt_text = _PROMPT_RENDERER.render(document, {})
        # The slider lane's effective values (rolled under — random —) ride
        # along in `properties` so the saved workflow and the PNG carry them.
        state = (mayhem_slider_state(seed, choices) if mayhem
                 else slider_state(seed, gender, choices))
        _stamp_workflow(extra_pnginfo, unique_id, prompt_text,
                        {PROP_SLIDERS: state} if state else None)

        # Printed to the ComfyUI server log every run. If a new line appears
        # here on each queue while the on-node box stays frozen, the backend is
        # fine and the frontend script is stale.
        print(
            "[Prompt-Alchemy-Grimoire] node {} seed {} -> {} chars: {}".format(
                unique_id, seed, len(prompt_text), prompt_text[:70].replace("\n", " ")
            )
        )

        return {
            "ui": {"bk_resolved": [prompt_text]},
            "result": (prompt_text,),
        }


NODE_CLASS_MAPPINGS = {
    "BKWildcardSelector": BKWildcardSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BKWildcardSelector": "Prompt-Alchemy-Grimoire Selector",
}
