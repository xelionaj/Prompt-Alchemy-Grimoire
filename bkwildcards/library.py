"""
Legacy wildcard utilities and compatibility facade for Prompt-Alchemy-Grimoire.

Layout
------
`wildcards/<pack>/*.txt` — each subdirectory is a pack, each .txt a category.
`wildcards/<pack>/_pack.json` — optional manifest controlling labels, ordering,
defaults, scope and selection style. Files absent from it still load.

Pack scope
----------
A pack can be scoped on two independent axes:

  "global": true   always active, whatever theme is selected
  "gender": "Female"  only active when that gender is selected

They compose. The `female` pack is global *and* gender-scoped: its categories
apply to every theme, but only when Female is the chosen gender. A theme pack
with no `gender` key is available to every gender.

Orderings
---------
Two, and they are not the same thing:

  display order — the order toggles appear on the node, grouped by pack.
  output order  — the order selections are joined into the prompt, driven by
                  each category's `order` across all packs, so a goth outfit
                  and a cyberpunk outfit land in the same slot of the sentence.

File format
-----------
One entry per line. Blank lines ignored. Lines beginning with '#' are section
headers: ignored for plain categories, but a category declared
`"select": "section"` turns them into a dropdown so you can draw from one
section rather than the whole file.
"""

import os
import re
import zlib

# repo_root/bkwildcards/library.py -> repo_root/wildcards
_HERE = os.path.dirname(os.path.abspath(__file__))
WILDCARD_ROOT = os.path.normpath(os.path.join(_HERE, os.pardir, "wildcards"))

DEFAULT_ORDER = 500
GLOBAL_PACK = "common"

# Reserved options on a section dropdown. Prefixed so a section literally named
# "off" or "any" cannot collide with them.
SECTION_OFF = "— off —"
SECTION_ANY = "— random —"

SELECT_TOGGLE = "toggle"
SELECT_SECTION = "section"


def _prettify(stem):
    """Compatibility wrapper for the catalog label formatter."""
    from .catalog import _prettify as catalog_prettify
    return catalog_prettify(stem)


def read_lines(path):
    """Every usable entry in a file, comments and blanks stripped."""
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                out.append(line)
    except OSError:
        return []
    return out


# Brand/acronym labels kept verbatim rather than title-cased (which would turn
# "BKSTYLE" into "Bkstyle"). Everything else still title-cases as before.
_VERBATIM_LABELS = {"BKSTYLE", "E.T."}


def clean_section_name(header):
    """Turn a raw '#' header into a dropdown-friendly label.

    Strips leading dashes, cuts a trailing parenthetical, and title-cases.
    Returns None for anything that reads as prose rather than a header —
    a rule line, or something still long after cleaning.

    Cleaning happens BEFORE the length test on purpose. A raw header like
    "-- orks, trolls, dwarves (Shadowrun-style - come in every ancestry,
    skin unchanged)" is 80+ characters and would fail a raw length test, but
    cleans down to "Orks, Trolls, Dwarves" — a perfectly good option.
    """
    h = header.strip().lstrip("#").strip()
    if not h or h.startswith("=") or set(h) <= set("-—= "):
        return None
    h = h.lstrip("-—").strip()
    h = re.split(r"\s*[\(\[]", h, maxsplit=1)[0].strip()
    if h in _VERBATIM_LABELS:
        # Check before rstrip so a verbatim label like "E.T." keeps its trailing dot.
        return h
    h = h.rstrip(":,.")
    if not h or len(h) > 40:
        return None
    if h in _VERBATIM_LABELS:
        return h
    if h.isupper() or h.islower():
        h = h.title()
    return h


def read_sections(path):
    """Entries grouped by their preceding '#' header, in file order.

    Returns a list of (section_label, [lines]). Entries before any header are
    grouped under None. Sections with no entries are dropped. Labels that
    collide are suffixed so the dropdown stays unambiguous.
    """
    sections = []
    current = None
    bucket = []

    def flush():
        if bucket:
            sections.append((current, list(bucket)))

    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    header = clean_section_name(line)
                    if header is None:
                        continue
                    flush()
                    bucket = []
                    current = header
                    continue
                bucket.append(line)
        flush()
    except OSError:
        return []

    # De-duplicate labels so the dropdown never has two identical options.
    seen = {}
    unique = []
    for name, rows in sections:
        if name is None:
            unique.append((name, rows))
            continue
        if name in seen:
            seen[name] += 1
            name = "{} ({})".format(name, seen[name])
        else:
            seen[name] = 1
        unique.append((name, rows))
    return unique


def _load_pack(pack_dir, pack_name):
    """Compatibility wrapper for the legacy catalog pack reader."""
    from .catalog import get_default_catalog
    return get_default_catalog()._load_pack(pack_dir, pack_name)


def _walk():
    """Compatibility wrapper for the legacy catalog directory walk."""
    from .catalog import get_default_catalog
    return get_default_catalog()._walk()


def scan():
    """Every category, in output order (legacy compatibility view)."""
    from .catalog import get_default_catalog
    return list(get_default_catalog().load().legacy_categories)


def scan_packs():
    """Every pack, including packs without category files (legacy view)."""
    from .catalog import get_default_catalog
    return list(get_default_catalog().load().legacy_packs)


def themes(packs):
    """Selectable theme labels. Global packs are not themes."""
    from .catalog import themes as catalog_themes
    return catalog_themes(packs)


def theme_to_pack(packs):
    from .catalog import theme_to_pack as catalog_theme_to_pack
    return catalog_theme_to_pack(packs)


def genders(packs):
    """Distinct gender values declared by packs, in pack order."""
    from .catalog import genders as catalog_genders
    return catalog_genders(packs)

def section_options(category):
    """Dropdown options for a section-select category."""
    return [SECTION_OFF, SECTION_ANY] + list(category["sections"])


def draw(category, choice, rng):
    """Pick one entry from a category, honouring its selection style.

    Returns None when the category should not contribute.
    """
    if category["select"] == SELECT_SECTION:
        if not choice or choice == SECTION_OFF:
            return None
        if choice == SECTION_ANY:
            pool = read_lines(category["path"])
        else:
            pool = []
            for name, rows in read_sections(category["path"]):
                if name == choice:
                    pool = rows
                    break
    else:
        if not choice:
            return None
        pool = read_lines(category["path"])

    return rng.choice(pool) if pool else None


def stable_offset(key):
    """Deterministic per-category seed offset, stable across processes.

    Python's built-in hash() is salted per process, so the same seed would
    otherwise produce different picks in different ComfyUI sessions.
    """
    return zlib.crc32(key.encode("utf-8")) & 0x7FFFFFFF
