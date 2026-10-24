"""Contracts shared by content discovery, selection, composition, and rendering.

The catalog adapter also exposes a legacy mapping view so the existing ComfyUI
widgets remain unchanged during migration.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Tuple


@dataclass(frozen=True)
class ProvenanceRecord:
    """License and attribution data attached to a content source."""

    source_id: str
    authors: Tuple[str, ...]
    origin: str
    license_id: str
    notice: str
    references: Tuple[str, ...] = ()

    def as_dict(self):
        return {
            "source_id": self.source_id,
            "authors": list(self.authors),
            "origin": self.origin,
            "references": list(self.references),
            "license": self.license_id,
            "notice": self.notice,
        }


@dataclass(frozen=True)
class ThemeRecord:
    id: str
    label: str
    source_id: str
    pack_ids: Tuple[str, ...]
    provenance: ProvenanceRecord


@dataclass(frozen=True)
class PackRecord:
    id: str
    label: str
    scope_kind: str
    theme_id: Optional[str]
    gender: Optional[str]
    source_id: str
    provenance: ProvenanceRecord

    def as_legacy_dict(self):
        return {
            "pack": self.id,
            "label": self.label,
            "is_global": self.scope_kind == "global",
            "gender": self.gender,
            "source_id": self.source_id,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class CategoryRecord:
    """Normalized category metadata plus an unchanged legacy widget view."""

    id: str
    input_key: str
    stable_key: str
    pack_id: str
    pack_label: str
    scope_kind: str
    theme_id: Optional[str]
    gender: Optional[str]
    content_path: str
    content_format: str
    entry_count: int
    selection_mode: str
    selection_default: Any
    sections: Tuple[str, ...]
    ui_label: str
    ui_group: Optional[str]
    ui_order: int
    prompt_label: Optional[str]
    semantic_role: Optional[str]
    composition_order: int
    source_id: str
    provenance: ProvenanceRecord
    legacy_default: bool = False

    def as_legacy_dict(self):
        return {
            "key": self.input_key,
            "stable_key": self.stable_key,
            "pack": self.pack_id,
            "pack_label": self.pack_label,
            "is_global": self.scope_kind == "global",
            "gender": self.gender,
            "id": self.id,
            "group": self.ui_group,
            "prompt_label": self.prompt_label,
            "label": self.ui_label,
            "path": self.content_path,
            "order": self.composition_order,
            "display": self.ui_order,
            "default": self.legacy_default,
            "select": self.selection_mode,
            "sections": list(self.sections),
            "count": self.entry_count,
            "source_id": self.source_id,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class CatalogSnapshot:
    """A discovered, normalized catalog view with legacy compatibility data."""

    packs: Tuple[PackRecord, ...]
    categories: Tuple[CategoryRecord, ...]
    themes: Tuple[ThemeRecord, ...]
    sources: Tuple[ProvenanceRecord, ...]

    @property
    def theme_labels(self):
        labels = []
        for theme in self.themes:
            if theme.label not in labels:
                labels.append(theme.label)
        return tuple(labels)

    @property
    def legacy_packs(self):
        return tuple(pack.as_legacy_dict() for pack in self.packs)

    @property
    def legacy_categories(self):
        return tuple(category.as_legacy_dict() for category in self.categories)

    @property
    def legacy_theme_to_pack(self):
        # Old workflows/UI map one displayed label to one pack. Preserve that
        # view for legacy roots; normalized ThemeRecords support many packs.
        return {
            pack.label: pack.id
            for pack in self.packs
            if pack.scope_kind != "global"
        }

    @property
    def genders(self):
        values = []
        for pack in self.packs:
            if pack.gender and pack.gender not in values:
                values.append(pack.gender)
        return tuple(values)


@dataclass(frozen=True)
class CompositionRequest:
    """Normalized inputs required to compose a prompt."""

    seed: int
    separator: str = ", "
    gender: Optional[str] = None
    theme: Optional[str] = None
    choices: Mapping[str, Any] = field(default_factory=dict)
    label_mode: str = "labeled"
    mayhem: bool = False
    renderer_id: Optional[str] = None
    renderer_options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectedEntry:
    """One chosen content value with its catalog identity and section context."""

    text: str
    category_id: str
    input_key: str
    stable_key: str
    source_id: str
    section: Optional[str] = None
    entry_id: Optional[str] = None
    provenance: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class PromptFragment:
    """One selected semantic value before renderer-specific formatting."""

    text: str
    role: Optional[str] = None
    label: Optional[str] = None
    order: int = 500
    input_key: Optional[str] = None
    source_id: Optional[str] = None
    provenance: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class PromptDocument:
    """Composed prompt data, independent of final text serialization."""

    fragments: Tuple[PromptFragment, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ContentCatalog(Protocol):
    """Discovers content and returns normalized records with provenance."""

    def load(self) -> CatalogSnapshot:
        ...


class SelectionService(Protocol):
    """Creates deterministic streams for legacy and source-qualified content."""

    def rng_for_seed(self, seed: int):
        ...

    def rng_for_legacy_key(self, seed: int, key: str):
        ...

    def rng_for_source_key(self, seed: int, source_id: str, stable_key: str):
        ...

    def rng_for_category(self, seed: int, category: CategoryRecord):
        ...

    def rng_for_entry(self, seed: int, source_id: str, category_id: str, entry_id: str):
        ...

    def draw_legacy(self, category, choice, seed: int):
        ...

    def select_legacy(self, category, choice, seed: int) -> Optional[SelectedEntry]:
        ...

    def select_random(self, category, rng) -> Optional[SelectedEntry]:
        ...


class PromptComposer(Protocol):
    """Turns a request and catalog into semantic prompt fragments."""

    def compose(self, request: CompositionRequest, catalog: CatalogSnapshot) -> PromptDocument:
        ...


class PromptRenderer(Protocol):
    """Formats semantic prompt data for a selected model/profile."""

    renderer_id: str

    def render(self, document: PromptDocument, options: Mapping[str, Any]) -> str:
        ...


@dataclass(frozen=True)
class RendererProfile:
    """Descriptive model target plus the renderer strategy used for its text.

    Capabilities describe this node's current text-output adapter, not every
    feature a model family may support. Profiles intentionally do not rewrite
    semantic fragment text unless a later, evidence-backed renderer opts in.
    """

    profile_id: str
    label: str
    model_family: str
    variants: Tuple[str, ...]
    renderer_id: str
    prompt_style: str
    supports_labeled_output: bool = True
    supports_json_output: bool = True
    supports_single_text_output: bool = True
    supports_negative_prompt_output: bool = False
    supports_secondary_prompt_output: bool = False
    references: Tuple[str, ...] = ()


class RendererProfileRegistry(Protocol):
    """Resolves stable profile IDs without coupling composition to a model."""

    def get(self, profile_id: Optional[str] = None) -> RendererProfile:
        ...

    def all(self) -> Tuple[RendererProfile, ...]:
        ...
