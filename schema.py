"""
Canonical schema for the LoL champ-select parser.

This module defines the parser's typed contract before any OCR or CV logic.
It is intentionally conservative: if the parser is not sure, it should return
"unknown" rather than inventing certainty.

Design goals:
- One canonical output shape for all parser modes
- Explicit uncertainty handling
- Typed evidence containers for downstream debugging
- JSON-serializable via `to_dict()` helpers
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Core enums / literals
# ---------------------------------------------------------------------------

TeamSide = Literal["blue", "red"]
PhaseName = Literal["ban_phase", "pick_phase", "loadout", "unknown"]


class SlotState(StrEnum):
    """Per-slot state."""

    PICKED = "picked"
    PICKING = "picking"
    PICKING_NEXT = "picking_next"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class ParserMode(StrEnum):
    """High-level parser mode / strategy used to produce the result."""

    SLOT = "slot"
    COLUMN = "column"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class LayoutName(StrEnum):
    """UI layout / scene classification."""

    BAN_PHASE = "ban_phase"
    PICK_PHASE = "pick_phase"
    LOADOUT = "loadout"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Bounding boxes / geometry
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BBox:
    """
    Pixel-space bounding box.

    Coordinates are inclusive-exclusive by convention:
    - x1, y1 = top-left
    - x2, y2 = bottom-right
    """

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(slots=True)
class RelativeBox:
    """
    Relative bounding box in normalized image coordinates [0, 1].
    """

    x1: float
    y1: float
    x2: float
    y2: float


# ---------------------------------------------------------------------------
# OCR + recognition evidence
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OCRToken:
    """Single OCR token detected within a crop/region."""

    text: str
    normalized: str
    confidence: float
    bbox: BBox | None = None
    source: str | None = None  # e.g. "name_crop", "status_crop", "header"
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OCRLine:
    """OCR tokens grouped into one line of text."""

    text: str
    normalized: str
    confidence: float
    tokens: list[OCRToken] = field(default_factory=list)
    bbox: BBox | None = None
    source: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChampionMatchEvidence:
    """Best-effort champion match plus optional alternatives."""

    raw_text: str = ""
    normalized_text: str = ""
    champion: str | None = None
    score: float = 0.0
    method: str | None = None  # e.g. "exact", "alias", "fuzzy_line", "fuzzy_token"
    alternatives: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class KeywordEvidence:
    """Keyword detection for state phrases like 'Picking...'."""

    picking: float = 0.0
    picking_next: float = 0.0
    raw_text: str = ""
    normalized_text: str = ""
    matched_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PortraitEvidence:
    """
    Evidence derived from the portrait/icon crop.

    The parser should avoid converting this directly into a hard state
    without combining it with other evidence.
    """

    placeholder_score: float = 0.0
    non_placeholder_score: float = 0.0
    bbox: BBox | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RoleEvidence:
    """Role signal detected from text, geometry, or fixed slot mapping."""

    role: str | None = None
    confidence: float = 0.0
    source: str | None = None  # e.g. "fixed_slot", "ocr", "column_label"
    raw_text: str = ""


@dataclass(slots=True)
class LayoutEvidence:
    """Evidence supporting scene/layout classification."""

    detected_text: str = ""
    normalized_text: str = ""
    confidence: float = 0.0
    matched_label: LayoutName = LayoutName.UNKNOWN
    header_bbox: BBox | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Slot-level decision evidence
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SlotDecisionEvidence:
    """
    Aggregated evidence for one slot.

    The parser should fill as much of this as it can, even when the final
    state remains UNKNOWN. This keeps the pipeline debuggable.
    """

    name_tokens: list[OCRToken] = field(default_factory=list)
    status_tokens: list[OCRToken] = field(default_factory=list)
    lines: list[OCRLine] = field(default_factory=list)

    champion: ChampionMatchEvidence = field(default_factory=ChampionMatchEvidence)
    keywords: KeywordEvidence = field(default_factory=KeywordEvidence)
    portrait: PortraitEvidence = field(default_factory=PortraitEvidence)
    role: RoleEvidence = field(default_factory=RoleEvidence)

    state_scores: dict[str, float] = field(
        default_factory=lambda: {
            SlotState.PICKED.value: 0.0,
            SlotState.PICKING.value: 0.0,
            SlotState.PICKING_NEXT.value: 0.0,
            SlotState.EMPTY.value: 0.0,
            SlotState.UNKNOWN.value: 0.0,
        }
    )
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Final parser outputs
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SlotResult:
    """
    Canonical parsed result for a single team slot.
    """

    slot_index: int
    team: TeamSide
    role: str | None
    state: SlotState
    champion: str | None
    confidence: float
    summoner_name: str | None = None
    evidence: SlotDecisionEvidence = field(default_factory=SlotDecisionEvidence)


@dataclass(slots=True)
class TurnCandidate:
    """One slot that appears to be currently picking or next to pick."""

    team: TeamSide
    slot_index: int
    role: str | None = None
    label: Literal["picking", "picking_next"] = "picking"
    confidence: float = 0.0


@dataclass(slots=True)
class TurnResult:
    """
    Final turn inference.

    If multiple candidates conflict, team/slot_index/label may remain None
    while the candidate lists preserve ambiguity.
    """

    team: TeamSide | None
    slot_index: int | None
    label: Literal["picking", "picking_next"] | None
    confidence: float = 0.0
    all_picking: list[TurnCandidate] = field(default_factory=list)
    all_picking_next: list[TurnCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BanSlotResult:
    """Result for one ban icon slot."""

    slot_index: int
    team: TeamSide
    champion: str | None
    confidence: float = 0.0
    bbox: BBox | None = None
    method: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseMeta:
    """Metadata about how the parse was produced."""

    parser_mode: ParserMode = ParserMode.UNKNOWN
    parser_version: str = "0.1.0"
    image_width: int | None = None
    image_height: int | None = None
    debug_enabled: bool = False
    debug_dir: str | None = None
    elapsed_ms: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParseResult:
    """
    Canonical top-level parser output.

    This is the single contract that all parsing strategies should produce.
    """

    layout: LayoutName
    phase: PhaseName
    blue_team: list[SlotResult]
    red_team: list[SlotResult]
    bans_blue: list[BanSlotResult]
    bans_red: list[BanSlotResult]
    turn: TurnResult
    layout_evidence: LayoutEvidence = field(default_factory=LayoutEvidence)
    warnings: list[str] = field(default_factory=list)
    meta: ParseMeta = field(default_factory=ParseMeta)

    def validate(self) -> None:
        """Basic structural validation for parser outputs."""
        if len(self.blue_team) != 5:
            raise ValueError(f"blue_team must have length 5, got {len(self.blue_team)}")
        if len(self.red_team) != 5:
            raise ValueError(f"red_team must have length 5, got {len(self.red_team)}")
        if len(self.bans_blue) != 5:
            raise ValueError(f"bans_blue must have length 5, got {len(self.bans_blue)}")
        if len(self.bans_red) != 5:
            raise ValueError(f"bans_red must have length 5, got {len(self.bans_red)}")

        for expected_idx, slot in enumerate(self.blue_team):
            if slot.slot_index != expected_idx:
                raise ValueError(
                    f"blue_team[{expected_idx}] has slot_index={slot.slot_index}"
                )
            if slot.team != "blue":
                raise ValueError(
                    f"blue_team[{expected_idx}] has team={slot.team!r}, expected 'blue'"
                )

        for expected_idx, slot in enumerate(self.red_team):
            if slot.slot_index != expected_idx:
                raise ValueError(
                    f"red_team[{expected_idx}] has slot_index={slot.slot_index}"
                )
            if slot.team != "red":
                raise ValueError(
                    f"red_team[{expected_idx}] has team={slot.team!r}, expected 'red'"
                )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

BLUE_ROLES_DEFAULT = ["SUPPORT", "BOTTOM", "MID", "TOP", "JUNGLE"]


def make_empty_slot(
    slot_index: int,
    team: TeamSide,
    role: str | None = None,
) -> SlotResult:
    """Create a conservative empty slot result."""
    return SlotResult(
        slot_index=slot_index,
        team=team,
        role=role,
        state=SlotState.UNKNOWN,
        champion=None,
        confidence=0.0,
    )


def make_empty_team(
    team: TeamSide,
    roles: list[str | None] | None = None,
) -> list[SlotResult]:
    """Create a 5-slot placeholder team."""
    if roles is None:
        roles = BLUE_ROLES_DEFAULT if team == "blue" else [None] * 5
    if len(roles) != 5:
        raise ValueError(f"roles must have length 5, got {len(roles)}")

    return [
        make_empty_slot(slot_index=i, team=team, role=roles[i])
        for i in range(5)
    ]


def make_empty_bans(team: TeamSide) -> list[BanSlotResult]:
    """Create a 5-slot placeholder ban list."""
    return [
        BanSlotResult(slot_index=i, team=team, champion=None, confidence=0.0)
        for i in range(5)
    ]


def make_empty_result(
    *,
    layout: LayoutName = LayoutName.UNKNOWN,
    phase: PhaseName = "unknown",
    mode: ParserMode = ParserMode.UNKNOWN,
    image_width: int | None = None,
    image_height: int | None = None,
) -> ParseResult:
    """Create a fully shaped but conservative top-level result."""
    result = ParseResult(
        layout=layout,
        phase=phase,
        blue_team=make_empty_team("blue"),
        red_team=make_empty_team("red"),
        bans_blue=make_empty_bans("blue"),
        bans_red=make_empty_bans("red"),
        turn=TurnResult(team=None, slot_index=None, label=None, confidence=0.0),
        meta=ParseMeta(
            parser_mode=mode,
            image_width=image_width,
            image_height=image_height,
        ),
    )
    result.validate()
    return result