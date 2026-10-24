"""Legacy wildcard prompt composition behind the PromptComposer boundary."""

import re

from . import catalog, library, selection, sliders, skintones
from .contracts import CompositionRequest, PromptDocument, PromptFragment
from .rendering import (
    LABEL_LABELED, LABEL_JSON, LABEL_PLAIN, LegacyTextRenderer, _format_picks,
    _label_mode,
)

_CATALOG = catalog.get_default_catalog().load()
_CATEGORIES = list(_CATALOG.legacy_categories)
_THEME_TO_PACK = _CATALOG.legacy_theme_to_pack
_GENDERS = list(_CATALOG.genders)
_SELECTION = selection.get_default_selection_service()

# Extra gender-dropdown options beyond the pack-derived genders (Female/Male),
# formatted to match the section dropdowns' reserved options.
GENDER_OFF = library.SECTION_OFF     # "— off —" — no gender, no gendered categories
GENDER_RANDOM = library.SECTION_ANY  # "— random —" — roll a concrete gender per seed
GENDER_FLUID = "Fluid"               # no gender gate — both genders' categories available

# The subject word each gender injects into the prompt so the render is actually
# directed toward a gender. Emitted at order 5, ahead of everything else.
_GENDER_TEXT = {"Female": "a feminine adult", "Male": "a masculine adult"}
_GENDER_FLUID_TEXT = "an androgynous adult"
_GENDER_ORDER = 5

# The Art Style category leads both the node (second, under the Theme header)
# and the prompt output. Its key is fixed by pack+id (common + art_style); its
# low `order` in _pack.json puts its text first, ahead of the gender word.
ART_STYLE_KEY = "common_art_style"
# A second, optional Art Style dropdown over the same list (0.9.19). Aliases the
# same artstyles.txt (library allows two manifest entries per file). Default off,
# its own prompt_label ("art style 2") and its own rng stream, so two styles can
# be blended. _dedupe_second_art_style drops it when it matches the first.
ART_STYLE_KEY_2 = "common_art_style_2"
_ART_STYLE_KEYS = (ART_STYLE_KEY, ART_STYLE_KEY_2)

# Metatype-driven skin tone: the active metatype section chooses the skin-group
# the coloration is rolled from (see skintones). Map each metatype line back to
# its section once at import so a drawn/rolled metatype resolves to its group.
_METATYPE_CAT = next((c for c in _CATEGORIES if c["id"] == "metatype"), None)
_METATYPE_KEY = _METATYPE_CAT["key"] if _METATYPE_CAT else "common_metatype"
_METATYPE_LINE_SECTION = {}
if _METATYPE_CAT:
    for _sec, _rows in library.read_sections(_METATYPE_CAT["path"]):
        for _ln in _rows:
            _METATYPE_LINE_SECTION.setdefault(_ln, _sec)


def _in_scope(cat, active_pack, active_gender):
    """Theme and gender gate. Enforced here, not in the browser.

    active_gender is already resolved to a concrete gender or GENDER_FLUID by
    the time this runs (resolve_prompt rolls GENDER_RANDOM -> a real gender).
    Under Fluid the gender axis is dropped entirely, so both genders'
    gender-scoped categories pass.
    """
    if not (cat["is_global"] or cat["pack"] == active_pack):
        return False
    if cat["gender"] and active_gender != GENDER_FLUID and cat["gender"] != active_gender:
        return False
    return True


# The Bald toggle (a top-level Hair on/off, key _BALD_KEY) suppresses the Hair
# Type, Style and Colour picks — a bald head has none of them. (Before 0.9.19
# bald was a Hair Type section; it moved to its own toggle so it stops eating
# ~1/5 of a random Hair Type roll — owner request 2026-09-19.)
_BALD_KEY = "hair_bald"
_HAIR_SUPPRESSED_BY_BALD = {"hair_color", "hair_style", "hair_type"}


# "hair", "hairs", "haired", "long-haired" — but not "hairless"/"hairline".
_HAIR_WORD = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]*hair(?:ed|s)?(?![A-Za-z0-9_])", re.IGNORECASE)


def _scrub_hair(text):
    """Remove every comma-separated clause that mentions hair; inside a clause
    joined by ' and ', drop only the hair half. Other picks (art styles,
    ancestry, outfits, poses) describe hair in passing — 'layered anime hair',
    'long wavy hair' — and under a bald head those clauses must not reach the
    renderer or it grows hair anyway (owner-reported, 2026-09-01)."""
    if not _HAIR_WORD.search(text):
        return text
    out = []
    for clause in text.split(", "):
        if not _HAIR_WORD.search(clause):
            out.append(clause)
            continue
        keep = [p for p in clause.split(" and ") if not _HAIR_WORD.search(p)]
        if keep:
            out.append(" and ".join(keep))
    return ", ".join(out)


def _drop_if_bald(raw, preserve_keys=False):
    """raw is a list of (order, label, text, key). When the Bald toggle is on
    (a pick with key _BALD_KEY is present), drop the Hair Type/Style/Colour
    picks AND scrub hair clauses out of every other pick's text, then return
    ordered picks ready for PromptDocument conversion. When preserve_keys is
    true, retain category identity for provenance; otherwise return legacy
    (order, label, text) triples. Both normal and Mayhem paths call this.
    """
    bald = any(k == _BALD_KEY for _, _, _t, k in raw)
    if bald:
        raw = [(o, l, t if k == _BALD_KEY else _scrub_hair(t), k)
               for o, l, t, k in raw if k not in _HAIR_SUPPRESSED_BY_BALD]
    return list(raw) if preserve_keys else [(o, l, t) for o, l, t, _k in raw]


def _dedupe_second_art_style(raw):
    """raw is a list of (order, label, text, key). Drop the second Art Style
    pick when its text is identical to the first, so two — random — rolls that
    land on the same style don't emit it twice. Keyed list in, keyed list out —
    runs before _drop_if_bald strips the keys; shared by the normal path and
    Mayhem."""
    first = next((t for _, _, t, k in raw if k == ART_STYLE_KEY), None)
    if first is None:
        return raw
    return [(o, l, t, k) for o, l, t, k in raw
            if not (k == ART_STYLE_KEY_2 and t == first)]


# Cybernetics finish colour: the Cybernetics Color pick replaces the "chrome"
# finish word inside the chosen Cybernetics augment (a cross-category rule, like
# the bald one). The colour never emits on its own, and vanishes if no augment
# is active. Keep exactly one "chrome" per augment line for a clean swap.
_CYBER_KEY = "common_cybernetics"
_CYBER_COLOR_KEY = "common_cyber_color"
_CYBER_FINISH = "chrome"


def _apply_cyber_color(raw):
    """raw is a list of (order, label, text, key). Fold the Cybernetics Color
    pick into the Cybernetics augment by swapping its finish word, then drop the
    colour entry so it is a modifier, not an emitter."""
    color = next((t for _o, _l, t, k in raw if k == _CYBER_COLOR_KEY), None)
    if color is None:
        return raw
    out = []
    for o, l, t, k in raw:
        if k == _CYBER_COLOR_KEY:
            continue
        if k == _CYBER_KEY and _CYBER_FINISH in t:
            t = t.replace(_CYBER_FINISH, color, 1)
        out.append((o, l, t, k))
    return out


# --- Slider Build Control (EXPERIMENTAL, may never ship) --------------------
# A manual body-shaping lane parallel to the Build presets. Master toggle ON ->
# the slider-synthesized build emits under the Build slot and every Build
# preset pick is dropped for that run (one body description, never two).
# OFF -> the sliders are inert. Value->prose rules live in sliders.py; the
# gender->register mapping is here with the rest of the gender logic.
# Register = Gender (the owner's "hard lock", 2026-09-01): Female/Male -> the
# gendered banks; Fluid and Off -> the androgynous bank; Random never reaches
# here (resolve_prompt rolls it to a concrete gender first). A masculine..
# feminine blend slider stood in for this for part of 2026-09-01 and was
# removed the same day.
_SLIDER_REGISTER = {
    "Female": "feminine",
    "Male": "masculine",
    GENDER_FLUID: "androgynous",
    GENDER_OFF: "androgynous",
}
_SLIDER_DEFAULT_REGISTER = "androgynous"
# The Build preset picks the slider build replaces, and the slot it takes over.
_BUILD_KEYS = {c["key"] for c in _CATEGORIES if c["id"] == "build"}
_BUILD_CAT = next((c for c in _CATEGORIES if c["id"] == "build"), None)
_BUILD_ORDER = _BUILD_CAT["order"] if _BUILD_CAT else 15
_BUILD_LABEL = (_BUILD_CAT.get("prompt_label") or _BUILD_CAT["label"]) if _BUILD_CAT else "build"
_SLIDER_KEY = "__body_sliders__"


def _slider_register(gender):
    return _SLIDER_REGISTER.get(gender, _SLIDER_DEFAULT_REGISTER)


def _resolve_gender(seed, gender):
    """Random -> a concrete gender rolled per seed on its own rng stream (so
    the per-category draws are unchanged). Deterministic, so preview still
    matches execution. Everything else passes through."""
    if gender == GENDER_RANDOM and _GENDERS:
        return _SELECTION.rng_for_legacy_key(seed, "__gender_roll__").choice(_GENDERS)
    return gender


def _preset_pick(seed, gender, choices):
    """(register, section) of the Build preset that will emit this run, or
    None. Mirrors the category loop's draw for the build categories so the
    section of a `— random —` preset is known at preview time."""
    gender = _resolve_gender(seed, gender)
    active = [c for c in _CATEGORIES if c["id"] == "build" and _in_scope(c, None, gender)]
    for cat in active:
        pick = _SELECTION.draw_legacy(cat, choices.get(cat["key"]), seed)
        if not pick:
            continue
        section = next((name for name, rows in library.read_sections(cat["path"]) if pick in rows), None)
        return _SLIDER_REGISTER.get(cat["gender"], _SLIDER_DEFAULT_REGISTER), section
    return None


def slider_state(seed, gender, choices):
    """What the slider lane will do for this run, or None when it is off.

    {"mode", "values": {axis: 0-10} | None, "register", "section"?} — under
    `— random —` the values are rolled from the seed (sliders.roll_values);
    under `on` they are read from the widgets; under `preset` they are the
    emitting preset section's vector (display only — the preset prose is what
    emits). Gender `— off —` -> None: the lane is suppressed like the gendered
    presets are. Shared by resolve_prompt (to build the text), build() (to
    stamp the state into the PNG workflow) and the populate endpoint (to hand
    the values back so the on-node sliders show them). Pure function of its
    arguments, so all three agree.
    """
    choices = choices or {}
    mode = sliders.mode_of(choices.get(sliders.TOGGLE_INPUT))
    if mode == sliders.MODE_OFF or sliders.BANKS is None or gender == GENDER_OFF:
        return None
    register = _slider_register(_resolve_gender(seed, gender))
    if mode == sliders.MODE_PRESET:
        pick = _preset_pick(seed, gender, choices)
        if pick is None:
            return {"mode": mode, "values": None, "register": register, "section": None}
        reg, section = pick
        return {"mode": mode, "values": sliders.preset_vector(reg, section),
                "register": reg, "section": section}
    if mode == sliders.MODE_RANDOM:
        values = sliders.roll_values(seed)
    else:
        values = {axis: sliders.clamp(choices.get(name))
                  for axis, name in sliders.AXIS_INPUTS.items()}
    return {"mode": mode, "values": values, "register": register}


def _apply_body_sliders(raw, seed, gender, choices):
    """raw is a list of (order, label, text, key). The Body Sliders lane governs
    the build slot:
      off      -> no build at all. The Build preset speaks ONLY in preset mode
                  (owner, 2026-10-03), so off drops any Build-preset pick and
                  adds nothing — a preset selected earlier can no longer leak in
                  through the hidden dropdown.
      preset   -> the Build preset pick stands (the presets' turn to speak).
      on/random -> replace the Build-preset pick with the synthesized slider build.
    Fails soft: no banks -> presets untouched (classic Build behavior).
    """
    if sliders.BANKS is None:
        return raw  # fail-soft: slider banks unavailable, leave the presets alone
    mode = sliders.mode_of((choices or {}).get(sliders.TOGGLE_INPUT))
    if mode == sliders.MODE_OFF:
        return [r for r in raw if r[3] not in _BUILD_KEYS]
    state = slider_state(seed, gender, choices)
    if state is None or state["mode"] == sliders.MODE_PRESET:
        return raw  # Gender off (no body), or the preset's turn to speak
    text = sliders.synthesize(state["register"], state["values"])
    raw = [r for r in raw if r[3] not in _BUILD_KEYS]
    if text:
        raw.append((_BUILD_ORDER, _BUILD_LABEL, text, _SLIDER_KEY))
    return raw


def _apply_skin_tone(raw, seed, choices, force_random=False):
    """raw is a list of (order, label, text, key). Append a coloration pick
    rolled from the ACTIVE metatype's skin group (skintones). The metatype line
    already emitted is mapped back to its section to pick the group.
    force_random (Mayhem) ignores the widget and always rolls; otherwise the
    skin_tone widget drives it (off/random/family). Fails soft: no bank -> no-op.
    """
    if skintones.GROUPS is None:
        return raw
    choice = skintones.TONE_RANDOM if force_random else choices.get(skintones.INPUT)
    if not choice or choice == skintones.TONE_OFF:
        return raw
    mt_index = next((i for i, (_o, _l, _t, k) in enumerate(raw) if k == _METATYPE_KEY), None)
    pick = raw[mt_index][2] if mt_index is not None else None
    section = _METATYPE_LINE_SECTION.get(pick) if pick else None
    tone = skintones.roll(seed, section, choice)
    if tone:
        entry = (skintones.ORDER, skintones.PROMPT_LABEL, tone, skintones.KEY)
        # Insert right after the metatype line (they tie at order 20, and eyes is
        # 20 too), so the stable sort emits metatype -> coloration -> eyes. No
        # metatype selected -> append (nothing to anchor to).
        if mt_index is not None:
            raw.insert(mt_index + 1, entry)
        else:
            raw.append(entry)
    return raw


# --- Mayhem mode -----------------------------------------------------------
# One-click, no-input, seeded, cross-theme composition. Maps each category id
# to the "slot" it competes in; mayhem picks at most one category per slot from
# a random source theme, so you get wild cross-theme mixing without stacking
# six outfits. Core slots always appear; extras roll in at _MAYHEM_EXTRA_PROB.
# These constants are tuning knobs, safe to adjust.
_MAYHEM_SLOT = {
    "ancestry": "ancestry", "metatype": "metatype", "build": "build",
    "face": "face", "nose": "nose", "lips": "lips",
    "color": "hair_color", "type": "hair_type", "style": "hair_style",
    "outfit": "outfit", "dress": "outfit", "eastern": "outfit", "set": "outfit",
    "tattoo": "tattoos", "weapon": "weapons",
    "accent_palette": "palette", "environment": "environment",
    "pose": "pose", "spell_casting": "pose",
    "spell_effects": "effect",
    "angle": "shot_angle", "framing": "shot_framing",
}
_MAYHEM_CORE = {"ancestry", "build", "hair_color", "hair_type",
                "hair_style", "outfit", "environment", "pose"}
_MAYHEM_EXTRA_PROB = 0.5
# Bald in Mayhem: an uncommon look. Its own low-probability coin (owner: 5%,
# 2026-09-19) on a dedicated rng stream, so it never renders half-bald and never
# disturbs the other rolls. When it lands, _drop_if_bald removes the hair picks.
_MAYHEM_BALD_PROB = 0.05


def _mayhem_compose(seed, choices=None):
    """Seeded cross-theme random composition, ignoring every input EXCEPT the
    Art Style selection. Returns (raw picks, slider-lane state).

    Rolls a gender, then for each slot picks one category from a random source
    theme and a random line from it. Fully determined by `seed`, so the
    queue-time preview still matches the render and a mayhem PNG reproduces.
    Core slots (via `or` short-circuit) never consume an extra-roll, keeping the
    rng sequence identical between preview and execution.

    Art Style is exempt from the randomisation: mayhem honours the user's Art
    Style pick on its own seeded rng stream (independent of the mayhem rolls), so
    the look stays consistent while everything else goes wild. Off contributes
    nothing; a specific style stays put; — random — still rolls per seed.
    """
    choices = choices or {}
    rng = _SELECTION.rng_for_seed(seed)
    gender = rng.choice([None] + list(_GENDERS))
    # A user-SELECTED specific metatype is honoured (kept), like Art Style, so its
    # skin stays within that metatype's group; — off — / — random — let mayhem roll it.
    mt_choice = choices.get(_METATYPE_KEY)
    honour_metatype = mt_choice not in (None, library.SECTION_OFF, library.SECTION_ANY)
    slots = {}
    for cat in _CATEGORIES:
        if cat["gender"] and cat["gender"] != gender:
            continue
        slot = _MAYHEM_SLOT.get(cat["id"])
        if slot == "metatype" and honour_metatype:
            continue  # honoured below, not randomised
        if slot:
            slots.setdefault(slot, []).append(cat)
    raw = []  # (order, label, text, key)
    # Both Art Style dropdowns are honoured from the user's selection, not
    # randomised by mayhem — each on its own rng stream so the look stays put
    # while everything else goes wild. Off contributes nothing; a specific style
    # stays; — random — rolls per seed. _dedupe_second_art_style (in
    # _resolve_mayhem) drops the second if it lands on the first's style.
    for akey in _ART_STYLE_KEYS:
        art_cat = next((c for c in _CATEGORIES if c["key"] == akey), None)
        if not art_cat:
            continue
        pick = _SELECTION.draw_legacy(
            art_cat, choices.get(art_cat["key"]), seed
        )
        if pick:
            raw.append((art_cat["order"],
                        art_cat.get("prompt_label") or art_cat["label"],
                        pick, art_cat["key"]))
    gtext = _GENDER_TEXT.get(gender)
    if gtext:
        raw.append((_GENDER_ORDER, "gender", gtext, None))
    # Honoured metatype: drawn on its own rng stream (like Art Style) so it does
    # not disturb the other mayhem rolls; the skin injection below then keeps the
    # coloration inside this metatype's group.
    if honour_metatype and _METATYPE_CAT:
        mt_pick = _SELECTION.draw_legacy(_METATYPE_CAT, mt_choice, seed)
        if mt_pick:
            raw.append((_METATYPE_CAT["order"],
                        _METATYPE_CAT.get("prompt_label") or _METATYPE_CAT["label"],
                        mt_pick, _METATYPE_CAT["key"]))
    for slot, cats in slots.items():
        if slot not in _MAYHEM_CORE and rng.random() >= _MAYHEM_EXTRA_PROB:
            continue
        cat = rng.choice(cats)
        pool = library.read_lines(cat["path"])
        if not pool:
            continue
        raw.append((cat["order"], cat.get("prompt_label") or cat["label"],
                    rng.choice(pool), cat["key"]))
    # Bald: an independent low-probability roll on its own rng stream, so it does
    # not disturb the other mayhem rolls (the queue preview stays == execution).
    # When it hits, the shared _drop_if_bald (in _resolve_mayhem) removes the
    # rolled hair type/style/colour, so Mayhem never renders a half-bald head.
    bald_cat = next((c for c in _CATEGORIES if c["key"] == _BALD_KEY), None)
    if bald_cat:
        bald_rng = _SELECTION.rng_for_legacy_key(seed, _BALD_KEY)
        if bald_rng.random() < _MAYHEM_BALD_PROB:
            pool = library.read_lines(bald_cat["path"])
            if pool:
                raw.append((bald_cat["order"],
                            bald_cat.get("prompt_label") or bald_cat["label"],
                            bald_rng.choice(pool), _BALD_KEY))
    raw = _apply_skin_tone(raw, seed, choices, force_random=True)
    return _mayhem_slider_lane(seed, gender, raw)


# Mayhem's build slot: a preset line (as always) or a rolled slider body, on a
# seeded coin. Its own rng stream, so every other Mayhem pick for a seed is
# unchanged by this feature. Tuning knob (owner: 50/50, 2026-09-01).
_MAYHEM_SLIDER_PROB = 0.5


def _mayhem_slider_lane(seed, gender, raw):
    """raw is a list of (order, label, text, key). With a preset build in the
    composition, flip the coin: heads -> replace it with a slider body rolled
    from the seed in the rolled gender's register; tails -> keep the preset and
    report its section's vector. Returns (raw, state) where state is what the
    sliders mirror ({"mode": "mayhem", "values", "register", "section"?}) or
    None when Mayhem rolled no gender (no body, as with Gender off)."""
    build = next((r for r in raw if r[3] in _BUILD_KEYS), None)
    if gender is None or build is None or sliders.BANKS is None:
        return raw, None
    rng = _SELECTION.rng_for_legacy_key(seed, "__mayhem_sliders__")
    register = _SLIDER_REGISTER.get(gender, _SLIDER_DEFAULT_REGISTER)
    if rng.random() < _MAYHEM_SLIDER_PROB:
        values = {axis: rng.randint(sliders.SLIDER_MIN, sliders.SLIDER_MAX)
                  for axis in sliders.AXES}
        text = sliders.synthesize(register, values)
        if text:
            raw = [r for r in raw if r[3] not in _BUILD_KEYS]
            raw.append((_BUILD_ORDER, _BUILD_LABEL, text, _SLIDER_KEY))
            return raw, {"mode": sliders.MODE_MAYHEM, "values": values, "register": register}
    cat = next((c for c in _CATEGORIES if c["key"] == build[3]), None)
    section = None
    if cat:
        section = next((name for name, rows in library.read_sections(cat["path"])
                        if build[2] in rows), None)
    return raw, {"mode": sliders.MODE_MAYHEM, "values": sliders.preset_vector(register, section),
                 "register": register, "section": section}


def _resolve_mayhem(seed, choices=None):
    raw, _state = _mayhem_compose(seed, choices)
    return _drop_if_bald(
        _dedupe_second_art_style(_apply_cyber_color(raw)), preserve_keys=True
    )


def mayhem_slider_state(seed, choices=None):
    """The slider-lane state of a Mayhem run (for the populate endpoint and the
    PNG stamp), from the same seeded composition build() emits."""
    return _mayhem_compose(seed, choices)[1]


def _compose_picks(seed, gender=None, theme=None, choices=None, mayhem=False):
    """Resolve ordered legacy picks before any renderer formats their text."""
    if mayhem:
        return _resolve_mayhem(seed, choices)
    choices = choices or {}
    gender = _resolve_gender(seed, gender)
    active_pack = _THEME_TO_PACK.get(theme)
    raw = []
    gtext = _GENDER_TEXT.get(gender) or (
        _GENDER_FLUID_TEXT if gender == GENDER_FLUID else None
    )
    if gtext:
        raw.append((_GENDER_ORDER, "gender", gtext, None))
    for cat in _CATEGORIES:
        if not _in_scope(cat, active_pack, gender):
            continue
        pick = _SELECTION.draw_legacy(cat, choices.get(cat["key"]), seed)
        if pick:
            raw.append((cat["order"], cat.get("prompt_label") or cat["label"],
                        pick, cat["key"]))
    raw = _apply_body_sliders(raw, seed, gender, choices)
    raw = _apply_skin_tone(raw, seed, choices)
    return _drop_if_bald(
        _dedupe_second_art_style(_apply_cyber_color(raw)), preserve_keys=True
    )


class LegacyPromptComposer:
    """Compose legacy wildcard picks into renderer-neutral fragments.

    This adapter preserves the existing seeded draws and special rules. It is
    bound to the legacy filesystem catalog; future catalog providers can supply
    their own PromptComposer implementation.
    """

    def compose(self, request, catalog_snapshot):
        if catalog_snapshot != _CATALOG:
            raise ValueError("LegacyPromptComposer requires the legacy filesystem catalog")
        picks = _compose_picks(
            request.seed, request.gender, request.theme,
            request.choices, request.mayhem,
        )
        by_key = {category.input_key: category for category in catalog_snapshot.categories}
        fragments = []
        for order, label, text, key in picks:
            category = by_key.get(key) if key else None
            fragments.append(PromptFragment(
                text=text,
                role=(category.semantic_role if category and category.semantic_role else label),
                label=label,
                order=order,
                input_key=key,
                source_id=category.source_id if category else None,
                provenance=category.provenance.as_dict() if category else None,
            ))
        return PromptDocument(
            fragments=tuple(fragments),
            metadata={
                "seed": request.seed,
                "separator": request.separator,
                "label_mode": request.label_mode,
                "mayhem": request.mayhem,
                "renderer_id": request.renderer_id or "legacy-text",
            },
        )


def resolve_prompt(seed, separator, gender=None, theme=None, choices=None,
                   label_mode=LABEL_LABELED, mayhem=False):
    """Compatibility facade used by routes and older callers."""
    request = CompositionRequest(
        seed=int(seed), separator=separator, gender=gender, theme=theme,
        choices=choices or {}, label_mode=_label_mode(label_mode), mayhem=bool(mayhem),
    )
    document = _DEFAULT_COMPOSER.compose(request, _CATALOG)
    return _DEFAULT_RENDERER.render(document, {})


_DEFAULT_COMPOSER = LegacyPromptComposer()
_DEFAULT_RENDERER = LegacyTextRenderer()


def get_default_composer():
    return _DEFAULT_COMPOSER


def get_default_renderer():
    return _DEFAULT_RENDERER
