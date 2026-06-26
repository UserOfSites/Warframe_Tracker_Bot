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
    wiki_known: bool = False  # true iff a wiki entry was reconciled for this item;
    # disambiguates "wiki has entry but no date log" (staples like Sands of Inaros
    # Blueprint, Fae Path Ephemera) from "no wiki entry at all" (novel or unmapped).
    item_type: str | None = None  # wiki ``Type`` field (e.g. "Weapon", "Primed Mod
    # (Rifle)", "Cosmetic (Armor)"); used by the renderer to decide whether last-
    # appearance metadata is worth showing (weapons/mods/relics) vs noise (cosmetics).


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
