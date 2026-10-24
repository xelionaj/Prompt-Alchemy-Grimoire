"""Deterministic random streams for wildcard selection.

Legacy category streams deliberately retain the original CRC32 offset formula.
New content should use source-qualified stable keys so it cannot collide with
or perturb the inherited library's streams.
"""

import hashlib
import random

from . import library


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
        return library.draw(category, choice, cls.rng_for_category(seed, category))


def get_default_selection_service():
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = DeterministicSelectionService()
    return _DEFAULT_SERVICE
