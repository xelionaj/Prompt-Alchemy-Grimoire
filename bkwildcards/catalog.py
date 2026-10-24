"""Content catalog boundary and legacy filesystem adapter.

The legacy adapter preserves the existing wildcard directory and manifest
semantics. Later catalog providers can implement ContentCatalog without changing
prompt selection or composition.
"""

import json
import os
import re

from . import library
from .contracts import CatalogSnapshot, CategoryRecord, PackRecord, ProvenanceRecord, ThemeRecord


LEGACY_PROVENANCE = ProvenanceRecord(
    source_id="bkwildcards",
    authors=("bkidderz",),
    origin="BKWILDCARDS inherited wildcard library",
    license_id="CC-BY-SA-4.0",
    notice="LICENSE-CONTENT",
)


def _prettify(stem):
    s = re.sub(r"^(krea2bk|krea2-bk|bk)[_-]", "", stem)
    s = re.sub(r"[_-]\d+$", "", s)
    s = s.replace("_", " ").replace("-", " ").strip()
    return s.title() if s else stem


class LegacyFilesystemCatalog:
    """Read the inherited `wildcards/<pack>` layout into a catalog snapshot."""

    def __init__(self, root=None):
        self.root = root or library.WILDCARD_ROOT

    def load(self):
        legacy_packs, legacy_categories = self._walk()
        legacy_categories.sort(key=lambda c: (c["order"], c["pack"], c["id"]))

        packs = tuple(
            PackRecord(
                id=row["pack"],
                label=row["label"],
                scope_kind="global" if row["is_global"] else "theme",
                theme_id=None if row["is_global"] else row["pack"],
                gender=row["gender"],
                source_id=row["source_id"],
                provenance=LEGACY_PROVENANCE,
            )
            for row in legacy_packs
        )
        pack_by_id = {pack.id: pack for pack in packs}
        themes = tuple(
            ThemeRecord(
                id=pack.id,
                label=pack.label,
                source_id=pack.source_id,
                pack_ids=(pack.id,),
                provenance=pack.provenance,
            )
            for pack in packs
            if pack.scope_kind != "global"
        )
        categories = []
        for row in legacy_categories:
            pack = pack_by_id[row["pack"]]
            selection_mode = row["select"]
            categories.append(
                CategoryRecord(
                    id=row["id"],
                    input_key=row["key"],
                    stable_key=row["key"],
                    pack_id=pack.id,
                    pack_label=pack.label,
                    scope_kind=pack.scope_kind,
                    theme_id=pack.theme_id,
                    gender=pack.gender,
                    content_path=row["path"],
                    content_format="lines",
                    entry_count=row["count"],
                    selection_mode=selection_mode,
                    selection_default=(
                        library.SECTION_OFF
                        if selection_mode == library.SELECT_SECTION
                        else row["default"]
                    ),
                    sections=tuple(row["sections"]),
                    ui_label=row["label"],
                    ui_group=row["group"],
                    ui_order=row["display"],
                    prompt_label=row["prompt_label"],
                    semantic_role=None,
                    composition_order=row["order"],
                    source_id=row["source_id"],
                    provenance=LEGACY_PROVENANCE,
                    legacy_default=row["default"],
                )
            )
        return CatalogSnapshot(
            packs=packs,
            categories=tuple(categories),
            themes=themes,
            sources=(LEGACY_PROVENANCE,),
        )

    def scan_packs(self):
        """Compatibility convenience method; returns legacy pack mappings."""
        return list(self.load().legacy_packs)

    def scan(self):
        """Compatibility convenience method; returns legacy category mappings."""
        return list(self.load().legacy_categories)
    def _load_pack(self, pack_dir, pack_name):
        manifest = {}
        manifest_path = os.path.join(pack_dir, "_pack.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as fh:
                    manifest = json.load(fh)
            except (OSError, ValueError):
                manifest = {}

        pack = {
            "pack": pack_name,
            "label": manifest.get("label") or _prettify(pack_name),
            "is_global": bool(manifest.get("global", pack_name == library.GLOBAL_PACK)),
            "gender": manifest.get("gender") or None,
        }
        self._attach_provenance(pack)

        declared = {}
        for entry in manifest.get("entries", []) or []:
            fname = entry.get("file")
            if fname:
                declared.setdefault(fname, []).append(entry)

        categories = []
        for fname in sorted(os.listdir(pack_dir)):
            if not fname.lower().endswith(".txt"):
                continue
            path = os.path.join(pack_dir, fname)
            if not os.path.isfile(path):
                continue

            # Multiple manifest entries may intentionally share one file.
            # Undeclared files still create one default category for compatibility.
            entries_for_file = declared.get(fname) or [{}]
            stem = os.path.splitext(fname)[0]
            lines_count = len(library.read_lines(path))
            for entry in entries_for_file:
                cid = entry.get("id") or re.sub(
                    r"[^a-z0-9]+", "_", stem.lower()
                ).strip("_")

                select = entry.get("select", library.SELECT_TOGGLE)
                section_names = []
                if select == library.SELECT_SECTION:
                    section_names = [
                        name for name, rows in library.read_sections(path) if name and rows
                    ]
                    if not section_names:
                        # Keep the established fallback for unusable section manifests.
                        select = library.SELECT_TOGGLE

                category = {
                    "key": "{}_{}".format(pack_name, cid),
                    "pack": pack_name,
                    "pack_label": pack["label"],
                    "is_global": pack["is_global"],
                    "gender": pack["gender"],
                    "id": cid,
                    "group": entry.get("group"),
                    "prompt_label": entry.get("prompt_label"),
                    "label": entry.get("label") or _prettify(stem),
                    "path": path,
                    "order": entry.get("order", library.DEFAULT_ORDER),
                    "display": entry.get(
                        "display", entry.get("order", library.DEFAULT_ORDER)
                    ),
                    "default": bool(entry.get("default", False)),
                    "select": select,
                    "sections": section_names,
                    "count": lines_count,
                }
                self._attach_provenance(category)
                categories.append(category)
        return pack, categories

    @staticmethod
    def _attach_provenance(record):
        record["source_id"] = LEGACY_PROVENANCE.source_id
        record["provenance"] = LEGACY_PROVENANCE.as_dict()

    def _walk(self):
        packs, categories = [], []
        if not os.path.isdir(self.root):
            return packs, categories
        for pack_name in sorted(os.listdir(self.root)):
            pack_dir = os.path.join(self.root, pack_name)
            if not os.path.isdir(pack_dir) or pack_name.startswith((".", "_")):
                continue
            pack, pack_categories = self._load_pack(pack_dir, pack_name)
            packs.append(pack)
            categories.extend(pack_categories)
        return packs, categories


_DEFAULT_CATALOG = None


def get_default_catalog():
    """Return the singleton legacy catalog for the inherited wildcard root."""
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = LegacyFilesystemCatalog()
    return _DEFAULT_CATALOG


def themes(packs):
    """Legacy theme labels in pack order; global packs are excluded."""
    labels = []
    for pack in packs:
        if pack["is_global"]:
            continue
        if pack["label"] not in labels:
            labels.append(pack["label"])
    return labels


def theme_to_pack(packs):
    return {p["label"]: p["pack"] for p in packs if not p["is_global"]}


def genders(packs):
    """Distinct gender values in pack order."""
    values = []
    for pack in packs:
        gender = pack["gender"]
        if gender and gender not in values:
            values.append(gender)
    return values