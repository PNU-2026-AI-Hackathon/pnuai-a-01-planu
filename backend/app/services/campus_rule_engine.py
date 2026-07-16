"""Campus-zone and back-to-back class travel validation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import json
import re
from typing import Any


class CampusRuleEngine:
    """Evaluate travel using normalized building zones and minute-based rules.

    Accepted rule data is intentionally modest and JSON-friendly::

        {"building_zones": {"6201": "ENGINEERING"},
         "travel_times": {"ENGINEERING": {"HUMANITIES": 15}},
         "default_travel_minutes": 20}

    ``zone_pairs`` (``{"A:B": 10}``) and a list-shaped ``travel_times`` are
    accepted as well, making the loader tolerant of early MVP data revisions.
    """

    def __init__(self, rules: Mapping[str, Any] | None = None) -> None:
        source = dict(rules or {})
        self.default_travel_minutes = int(source.get("default_travel_minutes", 0))
        self.same_zone_travel_minutes = int(source.get("same_zone_travel_minutes", 0))
        self.building_zones = {
            self._code(key): str(value)
            for key, value in source.get(
                "building_zones", source.get("building_to_zone", {})
            ).items()
        }
        self.travel_times: dict[tuple[str, str], int] = {}
        self._load_travel_times(source.get("travel_times", {}))
        self._load_travel_times(source.get("zone_pairs", {}))

    @classmethod
    def from_json(cls, path: str | Path) -> "CampusRuleEngine":
        with Path(path).open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("campus rules JSON root must be an object")
        return cls(data)

    def get_zone(self, building_code: str | None) -> str | None:
        """Return a configured zone, using longest building-code prefix match."""

        if not building_code:
            return None
        code = self._code(building_code)
        if code in self.building_zones:
            return self.building_zones[code]
        matches = [key for key in self.building_zones if code.startswith(key)]
        return self.building_zones[max(matches, key=len)] if matches else None

    extract_zone = get_zone

    def required_travel_minutes(
        self, from_building: str | None, to_building: str | None
    ) -> int:
        if not from_building or not to_building:
            return self.default_travel_minutes
        if self._code(from_building) == self._code(to_building):
            return 0
        origin, destination = self.get_zone(from_building), self.get_zone(to_building)
        if origin is not None and origin == destination:
            return self.same_zone_travel_minutes
        if origin is None or destination is None:
            return self.default_travel_minutes
        return self.travel_times.get(
            (origin, destination),
            self.travel_times.get(
                (destination, origin), self.default_travel_minutes
            ),
        )

    get_travel_minutes = required_travel_minutes

    def can_travel(
        self,
        from_building: str | None,
        to_building: str | None,
        available_minutes: int,
    ) -> bool:
        if available_minutes < 0:
            return False
        return available_minutes >= self.required_travel_minutes(
            from_building, to_building
        )

    is_move_possible = can_travel

    def can_move(self, previous: Any, following: Any) -> bool:
        """Convenience form accepting two ``ClassTime``-like objects."""

        if previous.day != following.day:
            return True
        gap = following.start_minutes - previous.end_minutes
        return self.can_travel(previous.building_code, following.building_code, gap)

    def _load_travel_times(self, values: Any) -> None:
        if isinstance(values, Mapping):
            for origin, destinations in values.items():
                if isinstance(destinations, Mapping):
                    for destination, minutes in destinations.items():
                        self.travel_times[(str(origin), str(destination))] = int(minutes)
                else:
                    pair = re.split(r"\s*(?::|->|,)\s*", str(origin), maxsplit=1)
                    if len(pair) == 2:
                        self.travel_times[(pair[0], pair[1])] = int(destinations)
        elif isinstance(values, list):
            for item in values:
                origin = item.get("from_zone", item.get("from"))
                destination = item.get("to_zone", item.get("to"))
                minutes = item.get("minutes", item.get("travel_minutes"))
                if origin is not None and destination is not None and minutes is not None:
                    self.travel_times[(str(origin), str(destination))] = int(minutes)

    @staticmethod
    def _code(value: object) -> str:
        return str(value).strip().upper().replace(" ", "")
