from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class BaroInventoryItem:
    """One line of Baro's inventory as warframestat returns it."""

    name: str
    ducats: int | None
    credits: int | None


@dataclass(frozen=True)
class EnrichedBaroItem:
    """Inventory line + historical context from the wiki."""

    name: str
    ducats: int | None
    credits: int | None
    last_appearance: date | None  # most recent visit *before* the current one
    total_appearances: int  # full historical count
    image_name: str | None = None  # warframestat CDN filename for the item icon


@dataclass(frozen=True)
class VoidTraderState:
    character: str
    location: str
    activation: datetime  # when the current/next visit starts
    expiry: datetime  # when the current/next visit ends
    inventory: tuple[BaroInventoryItem, ...]

    @property
    def is_present(self) -> bool:
        return len(self.inventory) > 0


@dataclass(frozen=True)
class BaroBoard:
    state: VoidTraderState
    enriched_inventory: tuple[EnrichedBaroItem, ...]  # empty when state.is_present is False
    generated_at: datetime
