from dataclasses import dataclass, field, replace

from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType


def _norm(s: str) -> str:
    return s.strip().lower()


@dataclass(frozen=True)
class SubscriptionFilter:
    """Per-(user, topic) allowlist narrowing which matching fissures fire DMs.

    Each field is an *allowlist*. Empty = no restriction (everything passes).
    Across fields the relationship is AND; within a field the relationship is
    OR. So ``nodes={Apollodorus, Sui}`` + ``missions={Capture}`` means "Capture
    on Apollodorus OR Capture on Sui", and an empty ``planets`` does not
    further restrict.
    """

    nodes: frozenset[str] = field(default_factory=frozenset)
    planets: frozenset[str] = field(default_factory=frozenset)
    mission_types: frozenset[MissionType] = field(default_factory=frozenset)

    @property
    def is_unrestricted(self) -> bool:
        return not (self.nodes or self.planets or self.mission_types)

    def matches(self, fissure: Fissure) -> bool:
        if self.nodes:
            allowed = {_norm(n) for n in self.nodes}
            if _norm(fissure.node) not in allowed:
                return False
        if self.planets:
            allowed = {_norm(p) for p in self.planets}
            if _norm(fissure.planet) not in allowed:
                return False
        if self.mission_types:
            if fissure.mission_type not in self.mission_types:
                return False
        return True

    def with_node_added(self, node: str) -> "SubscriptionFilter":
        return replace(self, nodes=self.nodes | {node})

    def with_node_removed(self, node: str) -> "SubscriptionFilter":
        target = _norm(node)
        return replace(self, nodes=frozenset(n for n in self.nodes if _norm(n) != target))

    def with_planet_added(self, planet: str) -> "SubscriptionFilter":
        return replace(self, planets=self.planets | {planet})

    def with_planet_removed(self, planet: str) -> "SubscriptionFilter":
        target = _norm(planet)
        return replace(self, planets=frozenset(p for p in self.planets if _norm(p) != target))

    def with_mission_added(self, mt: MissionType) -> "SubscriptionFilter":
        return replace(self, mission_types=self.mission_types | {mt})

    def with_mission_removed(self, mt: MissionType) -> "SubscriptionFilter":
        return replace(self, mission_types=self.mission_types - {mt})

    def cleared_nodes(self) -> "SubscriptionFilter":
        return replace(self, nodes=frozenset())

    def cleared_planets(self) -> "SubscriptionFilter":
        return replace(self, planets=frozenset())

    def cleared_missions(self) -> "SubscriptionFilter":
        return replace(self, mission_types=frozenset())
