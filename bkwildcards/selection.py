"""Deterministic random streams for wildcard selection.

Legacy category streams deliberately retain the original CRC32 offset formula.
New content should use source-qualified stable keys so it cannot collide with
or perturb the inherited library's streams.
"""

import hashlib
import random

from . import library
from .contracts import SelectedEntry


_STABLE_STREAM_PREFIX = "prompt-alchemy-grimoire-selection-v1"
_LEGACY_SOURCE_ID = "bkwildcards"
_DEFAULT_SERVICE = None


def _record_value(record, normalized_name, legacy_name=None):
    if isinstance(record, dict):
        if normalized_name in record:
            return record[normalized_name]
        return record.get(legacy_name) if legacy_name else None
    if hasattr(record, normalized_name):
        return getattr(record, normalized_name)
    return getattr(record, legacy_name, None) if legacy_name else None


class DeterministicSelectionService:
    """Creates stable random streams and performs legacy category draws."""

    @staticmethod
    def rng_for_seed(seed):
        """Return the legacy sequential stream used by Mayhem."""
        return random.Random(int(seed))

    @staticmethod
    def rng_for_legacy_key(seed, key):
        """Return the exact legacy stream: ``Random(seed + CRC32(key))``."""
        return random.Random(int(seed) + library.stable_offset(str(key)))

    @staticmethod
    def rng_for_source_key(seed, source_id, stable_key):
        """Return a versioned stream for a new source-qualified stable key."""
        if not source_id or not stable_key:
            raise ValueError("source_id and stable_key are required")
        identity = "\0".join(
            (_STABLE_STREAM_PREFIX, str(source_id), str(stable_key))
        ).encode("utf-8")
        offset = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big")
        return random.Random(int(seed) + offset)

    @classmethod
    def rng_for_category(cls, seed, category):
        """Use the legacy stream for legacy keys, a qualified stream otherwise."""
        input_key = _record_value(category, "input_key", "key")
        if not input_key:
            raise ValueError("category must provide an input_key or legacy key")
        stable_key = _record_value(category, "stable_key")
        source_id = _record_value(category, "source_id")
        if not stable_key or (
            stable_key == input_key and source_id in (None, _LEGACY_SOURCE_ID)
        ):
            return cls.rng_for_legacy_key(seed, input_key)
        return cls.rng_for_source_key(seed, source_id, stable_key)

    @staticmethod
    def _category_value(category, normalized_name, legacy_name=None, default=None):
        value = _record_value(category, normalized_name, legacy_name)
        return default if value is None else value

    @classmethod
    def _legacy_view(cls, category):
        """Adapt a normalized category to the legacy line/section reader."""
        return {
            "key": cls._category_value(category, "input_key", "key"),
            "id": cls._category_value(category, "id", default=""),
            "path": cls._category_value(category, "content_path", "path"),
            "select": cls._category_value(category, "selection_mode", "select"),
        }

    @classmethod
    def _selected_entry(cls, category, text):
        view = cls._legacy_view(category)
        section = next(
            (name for name, rows in library.read_sections(view["path"])
             if text in rows),
            None,
        )
        provenance = cls._category_value(category, "provenance")
        if hasattr(provenance, "as_dict"):
            provenance = provenance.as_dict()
        return SelectedEntry(
            text=text,
            category_id=cls._category_value(category, "id", default=""),
            input_key=cls._category_value(category, "input_key", "key"),
            stable_key=cls._category_value(category, "stable_key")
                or cls._category_value(category, "input_key", "key"),
            source_id=cls._category_value(category, "source_id", default=""),
            section=section,
            provenance=provenance,
        )

    @classmethod
    def select_legacy(cls, category, choice, seed):
        """Return the selected legacy entry and its section without exposing I/O."""
        view = cls._legacy_view(category)
        text = library.draw(view, choice, cls.rng_for_category(seed, category))
        return cls._selected_entry(category, text) if text else None

    @classmethod
    def select_random(cls, category, rng):
        """Draw from a category with a caller-owned stream (used by Mayhem)."""
        view = cls._legacy_view(category)
        pool = library.read_lines(view["path"])
        text = rng.choice(pool) if pool else None
        return cls._selected_entry(category, text) if text else None

    @classmethod
    def rng_for_entry(cls, seed, source_id, category_id, entry_id):
        """Return a stream tied to an explicit, stable content-entry identity."""
        if not category_id or not entry_id:
            raise ValueError("category_id and entry_id are required")
        stable_key = "entry:{}:{}".format(category_id, entry_id)
        return cls.rng_for_source_key(seed, source_id, stable_key)

    @classmethod
    def draw_legacy(cls, category, choice, seed):
        """Apply the current line/section selection rules on the keyed stream."""
        selected = cls.select_legacy(category, choice, seed)
        return selected.text if selected else None


def get_default_selection_service():
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = DeterministicSelectionService()
    return _DEFAULT_SERVICE
