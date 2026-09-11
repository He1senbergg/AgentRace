"""AgentRace model; mechanically extracted from frozen V2.2."""
from collections import Counter
from collections import defaultdict
from collections import deque
from dataclasses import dataclass
import math


DEFAULT_STRATEGY_MODE = "defense"


SHADOW_WARN_MS = 1500


TOTAL_WARN_MS = 3000


@dataclass(frozen=True)
class ProductionPolicy:
    """V2.3 experiments, separate from legacy DefensePolicy and game rules."""
    day_floors: tuple = (8000, 12000, 15000)
    wall_loss_weight: float = 0.5
    missing_wall_weight: int = 1000
    station_loss_weight: float = 2.0
    missing_controller_weight: int = 1000
    growth_quantum: int = 500

    def capacity_target(self, day, night):
        floor = self.day_floors[min(max(day, 1), len(self.day_floors)) - 1]
        if day <= 3 or not night:
            return floor
        # Missing IDs are risk proxies, not a claim that a kill was observed.
        pressure = (night.get('wall_hp_loss', 0) * self.wall_loss_weight
                    + len(night.get('missing_wall_ids', ())) * self.missing_wall_weight
                    + night.get('station_hp_loss', 0) * self.station_loss_weight
                    + len(night.get('missing_controller_ids', ())) * self.missing_controller_weight)
        growth = math.ceil(pressure / self.growth_quantum) * self.growth_quantum
        return max(floor, (night.get('previous_capacity') or 0) + growth)


def valid_position(pos):
    return (isinstance(pos, dict) and set(pos) == {"x", "y"}
            and type(pos["x"]) is int and type(pos["y"]) is int
            and 0 <= pos["x"] < 41 and 0 <= pos["y"] < 32)


CHARACTERS = {"worker", "pioneer"}


WEAPONS = {"gatling", "railgun", "rocket"}


MINERALS = {"stone", "iron", "copper"}


def distance(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def in_bounds(pos):
    return 0 <= pos[0] < 41 and 0 <= pos[1] < 32


def neighbors(pos):
    x, y = pos
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            candidate = (x + dx, y + dy)
            if (dx or dy) and in_bounds(candidate):
                yield candidate


def station_cells(pos):
    """Left-upper anchor and upward y per specification; platform check pending."""
    x, y = pos
    return {(x, y), (x + 1, y), (x, y - 1), (x + 1, y - 1)}


def building_ring(pos, radius):
    cells = station_cells(pos)
    return {p for x in range(pos[0] - radius, pos[0] + 2 + radius)
            for y in range(pos[1] - 1 - radius, pos[1] + 1 + radius)
            if in_bounds(p := (x, y)) and min(distance(p, c) for c in cells) == radius}


@dataclass(frozen=True)
class Phase:
    day: int
    round_in_day: int

    @property
    def is_day(self):
        return self.round_in_day <= 70

    @classmethod
    def from_round(cls, round_no, origin):
        # No implicit origin: the caller must supply its configured/observed basis.
        if type(origin) is not int or origin not in (0, 1):
            raise ValueError("unknown round origin")
        if type(round_no) is not int or not origin <= round_no < origin + 1300:
            raise ValueError("round outside half")
        index = round_no - origin
        return cls(index // 130 + 1, index % 130 + 1)


def object_list(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def position(value):
    return (value["x"], value["y"]) if valid_position(value) else None


class World:
    """Fresh observed state. Historical observations deliberately stay elsewhere."""
    def __init__(self, data):
        self.data = data if isinstance(data, dict) else {}
        our = self.data.get("teamOur")
        enemy = self.data.get("teamEnemy")
        map_info = self.data.get("mapInfo")
        self.our = our if isinstance(our, dict) else {}
        enemy = enemy if isinstance(enemy, dict) else {}
        map_info = map_info if isinstance(map_info, dict) else {}
        self.zones = defaultdict(set)
        self.occupied = set()
        self.static_occupied, self.transient_occupied = set(), set()
        for zone in object_list(map_info.get("zones")):
            cell = position(zone.get("pos"))
            kind = zone.get("neutralType")
            if cell is not None:
                self.occupied.add(cell)
                self.static_occupied.add(cell)
                if isinstance(kind, str):
                    self.zones[kind].add(cell)
        self.roles = self._roles(self.our.get("roles"))
        self.enemies = self._roles(enemy.get("roles"))
        # Official interface 1.5 specifies the roles wrapper; retain list
        # compatibility without requiring fields absent from older samples.
        robots = self.data.get("robot")
        self.robots = self._roles(robots.get("roles") if isinstance(robots, dict) else robots)
        self.characters = {i: r for i, r in self.roles.items()
                           if isinstance(r.get("roleType"), str) and r["roleType"] in CHARACTERS}

    def _roles(self, values):
        result = {}
        duplicates = set()
        for role in object_list(values):
            cell = position(role.get("pos"))
            health = role.get("health")
            if type(health) in (int, float) and health <= 0:
                continue
            if cell is None:
                continue
            footprint = station_cells(cell) if role.get("roleType") == "station" else {cell}
            self.occupied.update(p for p in footprint if in_bounds(p))
            blockers = (self.static_occupied if isinstance(role.get("roleType"), str)
                        and role["roleType"] in WEAPONS | {"station", "wall"}
                        else self.transient_occupied)
            blockers.update(p for p in footprint if in_bounds(p))
            raw_id = role.get("id")
            if type(raw_id) is int and raw_id >= 0:
                actor = str(raw_id)
            elif isinstance(raw_id, str) and raw_id.isascii() and raw_id.isdigit():
                actor = raw_id.lstrip("0") or "0"
            else:
                continue
            if actor in result:
                duplicates.add(actor)
            else:
                result[actor] = dict(role, id=actor, cell=cell)
        for actor in duplicates:
            result.pop(actor, None)
        return result

    def adjacent_goals(self, target_cells, start=None):
        return {p for target in target_cells for p in neighbors(target)
                if p not in self.occupied or p == start}

    def path(self, start, goals, reserved=()):
        """Shortest 8-neighbor route, including start. None means unreachable."""
        if not in_bounds(start):
            return None
        blocked = self.occupied | set(reserved)
        goals = {p for p in goals if in_bounds(p) and (p not in blocked or p == start)}
        if not goals:
            return None
        queue = deque([start])
        parent = {start: None}
        end = None
        while queue:
            cell = queue.popleft()
            if cell in goals:
                end = cell
                break
            for nxt in neighbors(cell):
                if nxt not in blocked and nxt not in parent:
                    parent[nxt] = cell
                    queue.append(nxt)
        if end is None:
            return None
        route = []
        while end is not None:
            route.append(end)
            end = parent[end]
        return route[::-1]


def render_map(world):
    """Current observation only, fixed-size ASCII; never render external text."""
    grid = [["." for _ in range(41)] for _ in range(32)]
    def put(cell, symbol):
        if in_bounds(cell):
            grid[cell[1]][cell[0]] = symbol
    zones = {"stone": "s", "iron": "i", "copper": "c", "vendor": "V", "weaponShop": "$",
             "challengerTaskPoint1": "T", "challengerTaskPoint2": "T",
             "defenderTaskPoint1": "t", "defenderTaskPoint2": "t"}
    for kind, cells in world.zones.items():
        for cell in cells:
            put(cell, zones.get(kind, "?"))
    for role in world.robots.values():
        put(role["cell"], "R" if role.get("targetTeam") in (None, world.our.get("type")) else "r")
    symbols = {"worker": "W", "pioneer": "P", "station": "B", "gatling": "G",
               "railgun": "L", "rocket": "K", "wall": "#"}
    for roles, ours in ((world.enemies, False), (world.roles, True)):
        for role in roles.values():
            kind = role.get("roleType")
            symbol = symbols.get(kind, "?") if isinstance(kind, str) else "?"
            cells = station_cells(role["cell"]) if kind == "station" else {role["cell"]}
            for cell in cells:
                put(cell, symbol if ours else symbol.lower())
    return "\n".join([
        "    " + "".join(str(x // 10) for x in range(41)),
        "    " + "".join(str(x % 10) for x in range(41)),
        *[f"{y:02d}  {''.join(grid[y])}" for y in range(31, -1, -1)],
        "W/P=our worker/pioneer B=base G/L/K=weapons #=wall; enemy=lowercase",
        "s/i/c=minerals V=vendor $=shop T/t=challenger/defender task R/r=robots targeting us/other",
        ".=no observed object ?=unknown; units overlay zones; x right, y up",
    ])


class MoveReservations:
    """Conservative: never enter another observed unit's current cell."""
    def __init__(self, world):
        self.world = world
        self.targets = set()
        self.actors = set()

    def reserve(self, actor, target):
        role = self.world.characters.get(actor)
        if (role is None or actor in self.actors or not in_bounds(target)
                or distance(role["cell"], target) != 1
                or target in self.world.occupied or target in self.targets):
            return False
        self.targets.add(target)
        self.actors.add(actor)
        return True


UPGRADES = {f"{prefix}UpgradeVoucher{level}": (kinds, level)
            for prefix, kinds in (("Weapon", WEAPONS), ("Wall", {"wall"}),
                                  ("Station", {"station"})) for level in (1, 2)}


SUMMON_ORDERS = {f"{size}RobotSummonOrder" for size in ("Small", "Middle", "Large", "Boss")}


USABLE = set(UPGRADES) | SUMMON_ORDERS | {"Medicine", "WallFixer", "Bomb", "DizzyWeapon"}


def nonnegative_int(value):
    return type(value) is int and value >= 0


def positive_health(value):
    # Integers are finite without conversion to float (which can overflow).
    return (type(value) is int and value > 0 or
            type(value) is float and math.isfinite(value) and value > 0)


def level_of(role):
    value = role.get("level")
    if type(value) is int and value in (1, 2, 3):
        return value
    return {"level1": 1, "level2": 2, "level3": 3}.get(value) if isinstance(value, str) else None


def shop_prices(value):
    prices, seen = {}, set()
    for entry in object_list(value):
        name, price = entry.get("name"), entry.get("price")
        if not isinstance(name, str) or not name:
            continue
        if name in seen:
            prices.pop(name, None)
        elif nonnegative_int(price):
            prices[name] = price
        seen.add(name)
    return prices


def inventory(role):
    items = role.get("backpack")
    if not isinstance(items, list) or not all(isinstance(v, str) and v for v in items):
        return None
    # Only normalize known consumables; dynamic task item names remain exact.
    aliases = {name.lower(): name for name in USABLE}
    return Counter(aliases.get(item.lower(), item) for item in items)


@dataclass(frozen=True)
class Rules:
    wall_stone_cost: object = 1
    weapon_build_names: tuple = (("gatling", "gatling"), ("railgun", "railgun"), ("rocket", "rocket"))


@dataclass(frozen=True)
class DefensePolicy:
    """Experimental policy parameters, not platform rules."""
    controller_health_ratio: float = 0.8
    station_emergency_ratio: float = 0.7
    night3_capacity: int = 10000
    night3_stretch: int = 12000

    def __post_init__(self):
        if not 0 < self.controller_health_ratio <= 1 or not 0 < self.station_emergency_ratio <= 1:
            raise ValueError('invalid experimental health threshold')

    def capacity_target(self, day):
        return 8000 if day == 1 else 9000 if day == 2 else self.night3_capacity


def max_health(role):
    kind = role.get('roleType')
    if isinstance(kind, str) and kind in CHARACTERS:
        return 220 if kind == 'worker' else 200
    level = level_of(role)
    return (1500 * level if kind == 'station' else 500 + 500 * level) if level else None


@dataclass
class CanonicalLayout:
    footprint: frozenset
    front: tuple
    weapon_slots: tuple
    wall_slots: tuple
    static_blockers: frozenset
    transient_occupancy: frozenset

    @classmethod
    def from_world(cls, world):
        bases = [r for r in world.roles.values() if r.get("roleType") == "station"]
        if len(bases) != 1:
            return cls(frozenset(), (0, 0), (), (), frozenset(world.static_occupied),
                       frozenset(world.transient_occupied))
        anchor = bases[0]["cell"]
        center2 = (2 * anchor[0] + 1, 2 * anchor[1] - 1)
        sign = 1 if center2[0] < 40 else -1
        def transform(offset):
            return ((center2[0] + sign * offset[0]) // 2,
                    (center2[1] + sign * offset[1]) // 2)
        def ranked(offsets, radius):
            canonical = [transform(p) for p in offsets]
            ring = building_ring(anchor, radius)
            fallback = sorted(ring - set(canonical), key=lambda p: (
                min(distance(p, c) for c in canonical), sign * p[0], sign * p[1]))
            return tuple(p for p in canonical + fallback if p in ring and p not in world.static_occupied)
        weapons = ranked(((-1, -3), (-3, 1), (-3, 3)), 1)
        walls = ranked(((5, 1), (5, 3), (5, -1), (5, 5), (5, -3), (5, -5), (3, 5), (3, -5)), 2)
        return cls(frozenset(station_cells(anchor)), (sign, -sign), weapons, walls,
                   frozenset(world.static_occupied), frozenset(world.transient_occupied))

    def connected(self, world, cell, weapons):
        """Static egress test, independently of today's units/robots."""
        geometry = object.__new__(World)
        geometry.occupied = set(self.static_blockers) | {cell}
        outside = {p for f in self.footprint for p in building_ring(f, 3)
                   if p not in geometry.occupied}
        for weapon in weapons:
            starts = geometry.adjacent_goals({weapon})
            if not any(geometry.path(start, outside) for start in starts):
                return False
        return True
