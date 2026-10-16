"""Canonical building model primitives.

Relationships are first-class: an Opening is hosted by a Wall (wall_id + offset
along the wall), a Wall belongs to a Level, a Space is bounded by walls, a Stair
connects two Levels. If a wall moves, its openings move with it because their
world position is derived from the host wall — never stored independently.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math

FT2_PER_M2 = 10.7639
M_PER_FT = 0.3048


@dataclass
class Rect:
    x: float
    y: float
    w: float
    d: float  # origin = south-west corner, metres

    @property
    def x2(self):
        return self.x + self.w

    @property
    def y2(self):
        return self.y + self.d

    @property
    def area(self):
        return self.w * self.d

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.d / 2

    def polygon(self):
        return [
            [self.x, self.y],
            [self.x2, self.y],
            [self.x2, self.y2],
            [self.x, self.y2],
        ]

    def overlaps(self, o: "Rect", eps=1e-6):
        return (
            min(self.x2, o.x2) - max(self.x, o.x) > eps
            and min(self.y2, o.y2) - max(self.y, o.y) > eps
        )

    def inside(self, o: "Rect", eps=1e-6):
        return (
            self.x >= o.x - eps
            and self.y >= o.y - eps
            and self.x2 <= o.x2 + eps
            and self.y2 <= o.y2 + eps
        )

    def shared_edge(self, o: "Rect"):
        """Return ('v'|'h', fixed_coord, lo, hi) of a shared edge, else None."""
        if abs(self.x2 - o.x) < 1e-6 or abs(o.x2 - self.x) < 1e-6:
            c = self.x2 if abs(self.x2 - o.x) < 1e-6 else self.x
            lo, hi = max(self.y, o.y), min(self.y2, o.y2)
            if hi - lo > 1e-6:
                return ("v", c, lo, hi)
        if abs(self.y2 - o.y) < 1e-6 or abs(o.y2 - self.y) < 1e-6:
            c = self.y2 if abs(self.y2 - o.y) < 1e-6 else self.y
            lo, hi = max(self.x, o.x), min(self.x2, o.x2)
            if hi - lo > 1e-6:
                return ("h", c, lo, hi)
        return None


@dataclass
class Wall:
    id: str
    level: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float = 0.15
    height: float = 3.0
    kind: str = "interior"
    spaces: list = field(default_factory=lambda: [None, None])  # [side A, side B]

    @property
    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def vertical(self):
        return abs(self.x1 - self.x2) < 1e-9

    def point_at(self, offset: float):
        """World position of a hosted opening — derived from the host wall."""
        t = offset / self.length if self.length else 0
        return (self.x1 + (self.x2 - self.x1) * t, self.y1 + (self.y2 - self.y1) * t)


@dataclass
class Opening:
    id: str
    kind: str
    wall_id: str | None
    offset: float
    width: float = 0.9
    height: float = 2.1
    sill: float = 0.0
    space_id: str | None = None


@dataclass
class StairCalc:
    space_id: str
    from_level: str
    to_level: str
    risers: int
    riser_mm: float
    going_mm: float
    run_length: float

    @staticmethod
    def design(space_id, from_level, to_level, rise_m, going_mm=280):
        risers = max(4, round(rise_m / 0.175 / 2) * 2)
        return StairCalc(
            space_id,
            from_level,
            to_level,
            risers,
            round(rise_m / risers * 1000, 1),
            going_mm,
            round((risers - 2) * going_mm / 1000, 2),
        )


DISCLAIMER = (
    "Concept design only — requires licensed professional review. Not for construction."
)


def model_to_dict(model: dict) -> dict:
    return model


def fmt_area(m2: float) -> str:
    return f"{m2:.1f} m² ({m2 * FT2_PER_M2:,.0f} ft²)"
