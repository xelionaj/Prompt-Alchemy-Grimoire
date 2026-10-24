"""Legacy prompt text rendering, independent from content selection."""

import json

from .contracts import PromptDocument

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


class LegacyTextRenderer:
    """Serialize the existing ordered picks without changing prompt bytes."""

    renderer_id = "legacy-text"

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
