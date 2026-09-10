"""AgentRace HTTP entry and protocol boundary (AI Spec sections 42–63)."""
from collections import Counter, defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
import argparse
import hashlib
import json
import logging
import math
import sys
import threading

from flask import Flask, jsonify, request

LOG = logging.getLogger(__name__)
app = Flask(__name__)
app.json.ensure_ascii = False


def empty_response():
    """Return fresh containers: callers must never share mutable responses."""
    return {"roleCommandMap": {}, "prompt": "", "executeCmd": ""}


def valid_position(pos):
    return (isinstance(pos, dict) and set(pos) == {"x", "y"}
            and type(pos["x"]) is int and type(pos["y"]) is int
            and 0 <= pos["x"] < 41 and 0 <= pos["y"] < 32)


def validate_command_shape(command):
    """Wire format only; world-dependent legality belongs to ActionValidator."""
    if not isinstance(command, dict):
        return False
    action = command.get("action")
    fields = {
        "move": {"targetPos"}, "attack": {"controllerId", "targetPos"},
        "sell": {"name", "num"}, "buy": {"name", "num"},
        "build": {"name", "targetPos"}, "remove": {"targetPos"},
        "acceptTask": set(), "submitAnswer": {"taskAnswer"},
        "summonTreasure": {"targetPos", "item"},
        "use": {"name"}, "drop": {"name"}, "collect": {"targetPos"},
    }
    if not isinstance(action, str) or action not in fields:
        return False
    required = fields[action] | {"action"}
    allowed = required | ({"targetPos"} if action == "use" else set())
    if not required <= command.keys() or not command.keys() <= allowed:
        return False
    for key in ("name", "taskAnswer", "controllerId"):
        if key in command and (not isinstance(command[key], str) or not command[key]):
            return False
    if "controllerId" in command and not command["controllerId"].isascii():
        return False
    if "controllerId" in command and not command["controllerId"].isdigit():
        return False
    if "num" in command and (type(command["num"]) is not int or command["num"] <= 0):
        return False
    if "item" in command and (not isinstance(command["item"], list)
            or not all(isinstance(item, str) and item for item in command["item"])):
        return False
    if action == "use":
        name = command["name"]
        targeted = name in {"WallFixer", "Bomb", "DizzyWeapon"} or name.endswith("UpgradeVoucher1") or name.endswith("UpgradeVoucher2")
        if targeted != ("targetPos" in command):
            return False
    if "targetPos" in command:
        targets = command["targetPos"]
        if not isinstance(targets, list) or not all(valid_position(p) for p in targets):
            return False
        if len(targets) not in ({1, 2, 3} if action == "attack" else {1}):
            return False
    return True


def ensure_valid_response(response):
    if not isinstance(response, dict) or set(response) != {"roleCommandMap", "prompt", "executeCmd"}:
        raise ValueError("invalid response fields")
    if not isinstance(response["prompt"], str) or not isinstance(response["executeCmd"], str):
        raise ValueError("invalid response text")
    commands = response["roleCommandMap"]
    if not isinstance(commands, dict):
        raise ValueError("invalid command map")
    for actor, command in commands.items():
        if not isinstance(actor, str) or not actor.isascii() or not actor.isdigit() or not validate_command_shape(command):
            raise ValueError("invalid command")
    return response


# World geometry: AI Spec sections 3–9, 47–54, 69–70.
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
        for zone in object_list(map_info.get("zones")):
            cell = position(zone.get("pos"))
            kind = zone.get("neutralType")
            if cell is not None:
                self.occupied.add(cell)
                if isinstance(kind, str):
                    self.zones[kind].add(cell)
        self.roles = self._roles(self.our.get("roles"))
        self.enemies = self._roles(enemy.get("roles"))
        # Robot wrapper layout is not specified by the text; accept a list and
        # the conventional roles wrapper without requiring absent optional fields.
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


# Shared action legality and conservative same-round reservations (§75–76).
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
    wall_stone_cost: object = None
    weapon_build_names: tuple = ()  # Confirmed (wire name, roleType) pairs only.


class ActionValidator:
    def __init__(self, world, memory, rules=None):
        self.world, self.memory = world, memory
        self.rules = rules or Rules()
        self.commands, self.busy, self.targets, self.modified = {}, set(), set(), set()
        gold = world.our.get("goldNum")
        self.gold = gold if nonnegative_int(gold) else 0
        self.prices = shop_prices(world.data.get("weaponShopList"))
        self.vendor = shop_prices(world.data.get("vendorShopList"))
        self.weapon_count = sum(r.get("roleType") in WEAPONS for r in world.roles.values()
                                if isinstance(r.get("roleType"), str))
        self.wall_count = sum(r.get("roleType") == "wall" for r in world.roles.values())
        self.summons = memory.summon_attempts

    def near(self, role, cells):
        return any(distance(role["cell"], p) <= 1 for p in cells)

    def building_at(self, target):
        matches = [r for r in self.world.roles.values()
                   if isinstance(r.get("roleType"), str) and r["roleType"] in WEAPONS | {"station", "wall"}
                   and r["cell"] == target] if target is not None else []
        return matches[0] if len(matches) == 1 else None

    def task_cells(self):
        side = self.world.our.get("type")
        if side not in ("challenger", "defender"):
            return set()
        return self.world.zones[side + "TaskPoint1"] | self.world.zones[side + "TaskPoint2"]

    def add(self, actor, command):
        if (not isinstance(actor, str) or actor not in self.world.roles or actor in self.busy
                or not validate_command_shape(command)):
            return False
        role = self.world.roles[actor]
        kind, action = role.get("roleType"), command["action"]
        health = role.get("health")
        if not isinstance(kind, str) or not positive_health(health):
            return False
        targets = [position(p) for p in command.get("targetPos", [])]
        target = targets[0] if targets else None
        phase = self.memory.phase
        active_task = isinstance(self.world.data.get("phaseTask"), str) and bool(self.world.data["phaseTask"])
        cost, new_weapon, new_wall, summon = 0, 0, 0, 0
        lock_target, lock_building, controller = None, None, None
        bag = inventory(role)
        capacity = role.get("backPackCapability", 100 if kind == "worker" else 40)
        space = capacity - sum(bag.values()) if nonnegative_int(capacity) and bag is not None else -1
        name = command.get("name")
        if action == "attack":
            controller = command["controllerId"]
            character = self.world.characters.get(controller)
            level = level_of(role)
            cooldown = role.get("cooldown", 0)
            controller_health = character.get("health") if character else None
            if not positive_health(controller_health):
                return False
            if (kind not in WEAPONS or phase is None or phase.is_day or level is None
                    or not nonnegative_int(cooldown) or cooldown != 0 or character is None
                    or controller in self.busy or role["cell"] in self.modified
                    or not self.near(character, {role["cell"]})):
                return False
            ranges = {"gatling": (3, 5, 7), "railgun": (6, 8, 10), "rocket": (10, 15, 40)}
            radius = role.get("attackRange", ranges[kind][level - 1])
            if (not nonnegative_int(radius) or len(targets) != (1 if kind == "railgun" else level)
                    or any(not 0 < distance(role["cell"], p) <= radius for p in targets)):
                return False
            vectors = [(p[0] - role["cell"][0], p[1] - role["cell"][1]) for p in targets]
            if kind == "gatling" and any(a[0]*b[0] + a[1]*b[1] < 0 for a in vectors for b in vectors):
                return False
            lock_building = role["cell"]
        elif kind not in CHARACTERS:
            return False
        elif action == "move":
            if (kind == "pioneer" and active_task or distance(role["cell"], target) != 1
                    or target in self.world.occupied or target in self.targets):
                return False
            lock_target = target
        elif action in {"buy", "sell"}:
            if bag is None or not self.near(role, self.world.zones["weaponShop" if action == "buy" else "vendor"]):
                return False
            if action == "buy":
                if name not in self.prices or space < command["num"]:
                    return False
                cost = self.prices[name] * command["num"]
            elif name not in MINERALS or name not in self.vendor or bag[name] < command["num"]:
                return False
        elif action == "collect":
            if (kind != "worker" or space < 1 or not self.near(role, {target})
                    or not any(target in self.world.zones[m] for m in MINERALS)):
                return False
        elif action == "build":
            build_kind = dict(self.rules.weapon_build_names).get(name, "wall" if name == "wall" else None)
            stations = [r for r in self.world.roles.values() if r.get("roleType") == "station"]
            if (kind != "worker" or phase is None or not phase.is_day or build_kind is None
                    or not self.near(role, {target}) or len(stations) != 1
                    or target in self.targets or target in self.modified):
                return False
            old = self.building_at(target)
            if target in self.world.occupied and (old is None or old.get("roleType") not in
                                                  (WEAPONS if build_kind in WEAPONS else {"wall"})):
                return False
            if target not in building_ring(stations[0]["cell"], 2 if build_kind == "wall" else 1):
                return False
            if build_kind == "wall":
                stones = self.rules.wall_stone_cost
                if not nonnegative_int(stones) or stones == 0 or bag is None or bag["stone"] < stones:
                    return False
                new_wall = int(old is None)
            else:
                cost, new_weapon = 25, int(old is None)
            if self.weapon_count + new_weapon > 3 or self.wall_count + new_wall > 20:
                return False
            lock_target = lock_building = target
        elif action == "remove":
            old = self.building_at(target)
            if (kind != "worker" or old is None or old.get("roleType") != "wall"
                    or not self.near(role, {target}) or target in self.modified):
                return False
            lock_building = target
        elif action == "acceptTask":
            if kind != "pioneer" or active_task or not self.near(role, self.task_cells()):
                return False
            eligible = False
            for task in object_list(self.world.our.get("playerTasks")):
                cell = position(task.get("taskPosition"))
                # Expand a two-cell task point using its matching map zone.
                cells = {cell} if cell is not None else set()
                for suffix in ("TaskPoint1", "TaskPoint2"):
                    zone = self.world.zones[self.world.our["type"] + suffix]
                    if cell in zone:
                        cells = zone
                if (task.get("isValid") is True and type(task.get("coldDownRounds")) is int
                        and task["coldDownRounds"] == 0 and cells <= self.task_cells() and self.near(role, cells)):
                    eligible = True
            if not eligible:
                return False
        elif action == "submitAnswer":
            if kind != "pioneer" or not active_task or not self.near(role, self.task_cells()):
                return False
        elif action == "summonTreasure":
            if (kind != "pioneer" or bag is None or not self.near(role, {target})
                    or any(bag[item] < count for item, count in Counter(command["item"]).items())):
                return False
        elif action == "drop":
            if bag is None or bag[name] < 1:
                return False
        elif action == "use":
            if name not in USABLE or bag is None or bag[name] < 1:
                return False
            if name in UPGRADES or name == "WallFixer":
                old = self.building_at(target)
                kinds, required_level = UPGRADES.get(name, ({"wall"}, None))
                if (old is None or old.get("roleType") not in kinds or not self.near(role, {target})
                        or target in self.modified or required_level is not None and level_of(old) != required_level):
                    return False
                lock_building = target
            elif name in SUMMON_ORDERS:
                if not self.memory.summon_day_known or phase is None or self.summons >= 10:
                    return False
                summon = 1
            elif name not in {"Bomb", "DizzyWeapon"} and targets:
                return False
        else:
            return False
        if cost > self.gold:
            return False
        # Everything above is read-only: rejection never consumes reservations.
        self.gold -= cost
        self.weapon_count += new_weapon
        self.wall_count += new_wall
        self.summons += summon
        self.busy.add(actor)
        if controller is not None:
            self.busy.add(controller)
        if lock_target is not None:
            self.targets.add(lock_target)
        if lock_building is not None:
            self.modified.add(lock_building)
        self.commands[actor] = deepcopy(command)
        return True


class EconomyPlanner:
    def __init__(self, validator):
        self.v = validator
        self.world = validator.world

    def travel(self, actor, cells):
        role = self.world.characters[actor]
        route = self.world.path(role["cell"], self.world.adjacent_goals(cells, role["cell"]), self.v.targets)
        return bool(route and len(route) > 1 and self.v.add(actor, {
            "action": "move", "targetPos": [{"x": route[1][0], "y": route[1][1]}]}))

    def purchase(self, actor, name, count=1):
        role = self.world.characters.get(actor)
        bag = inventory(role) if role else None
        price = self.v.prices.get(name)
        if bag is None or price is None or type(count) is not int or count <= 0:
            return False
        missing = count - bag[name]
        capacity = role.get("backPackCapability", 100 if role["roleType"] == "worker" else 40)
        if (missing <= 0 or price * missing > self.v.gold or not nonnegative_int(capacity)
                or sum(bag.values()) + missing > capacity):
            return False
        if self.v.add(actor, {"action": "buy", "name": name, "num": missing}):
            return True
        return self.travel(actor, self.world.zones["weaponShop"])

    def workers(self):
        for actor, role in sorted(self.world.characters.items()):
            if actor in self.v.busy or role["roleType"] != "worker":
                continue
            bag = inventory(role)
            capacity = role.get("backPackCapability", 100)
            if bag is None or not nonnegative_int(capacity):
                continue
            minerals = sorted((m for m in MINERALS if bag[m] and m in self.v.vendor),
                              key=lambda m: (-bag[m] * self.v.vendor[m], m))
            if minerals and (sum(bag.values()) >= min(20, capacity)
                             or self.v.near(role, self.world.zones["vendor"])):
                name = minerals[0]
                if self.v.add(actor, {"action": "sell", "name": name, "num": bag[name]}):
                    continue
                if self.travel(actor, self.world.zones["vendor"]):
                    continue
            if sum(bag.values()) >= capacity:
                continue
            options = []
            for mineral in sorted(MINERALS):
                price = self.v.vendor.get(mineral)
                if price is None or price <= 0:
                    continue
                cells = self.world.zones[mineral]
                route = self.world.path(role["cell"], self.world.adjacent_goals(cells, role["cell"]), self.v.targets)
                if route:
                    options.append((price / (len(route) + 5), mineral, route))
            if not options:
                if minerals:
                    self.travel(actor, self.world.zones["vendor"])
                continue
            _, mineral, route = max(options, key=lambda choice: (choice[0], choice[1]))
            if len(route) == 1:
                for target in sorted(self.world.zones[mineral]):
                    if self.v.add(actor, {"action": "collect", "targetPos": [{"x": target[0], "y": target[1]}]}):
                        break
            else:
                target = route[1]
                self.v.add(actor, {"action": "move", "targetPos": [{"x": target[0], "y": target[1]}]})


class DefensePlanner:
    """Observed-state defense; damage estimates are not execution feedback."""
    def __init__(self, validator):
        self.v = validator
        self.world = validator.world
        self.economy = EconomyPlanner(validator)
        self.stations = [r for r in self.world.roles.values() if r.get("roleType") == "station"]
        self.weapons = [r for r in self.world.roles.values()
                        if isinstance(r.get("roleType"), str) and r["roleType"] in WEAPONS
                        and positive_health(r.get("health")) and level_of(r) is not None]
        side = self.world.our.get("type")
        self.robots = {i: r for i, r in self.world.robots.items()
                       if positive_health(r.get("health")) and r.get("targetTeam") in (None, side)}
        self.remaining = {i: r["health"] for i, r in self.robots.items()}

    def characters(self):
        active = bool(self.world.data.get("phaseTask"))
        return [r for i, r in sorted(self.world.characters.items())
                if i not in self.v.busy and positive_health(r.get("health"))
                and not (active and r["roleType"] == "pioneer")]

    def use_at(self, actor, name, cell=None):
        command = {"action": "use", "name": name}
        if cell is not None:
            command["targetPos"] = [{"x": cell[0], "y": cell[1]}]
        return self.v.add(actor, command)

    def maintain(self, emergency_only=False):
        buildings = sorted((r for r in self.world.roles.values()
                            if isinstance(r.get("roleType"), str)
                            and r["roleType"] in WEAPONS | {"station", "wall"}
                            and level_of(r) is not None and positive_health(r.get("health"))),
                           key=lambda r: (r["roleType"] != "station", r["health"], r["id"]))
        for building in buildings:
            kind, level = building["roleType"], level_of(building)
            maximum = (1500 * level if kind == "station" else 500 + 500 * level)
            urgent = kind == "station" and building["health"] < maximum // 2
            if emergency_only and not urgent:
                continue
            if kind == "wall" and building["health"] < maximum:
                for character in sorted(self.characters(), key=lambda r: distance(r["cell"], building["cell"])):
                    bag = inventory(character)
                    if bag and bag["WallFixer"]:
                        if self.use_at(character["id"], "WallFixer", building["cell"]):
                            return True
                        if self.economy.travel(character["id"], {building["cell"]}):
                            return True
            if level < 3:
                prefix = "Station" if kind == "station" else "Wall" if kind == "wall" else "Weapon"
                name = f"{prefix}UpgradeVoucher{level}"
            elif kind == "wall" and building["health"] < maximum:
                name = "WallFixer"
            else:
                continue
            for character in sorted(self.characters(), key=lambda r: distance(r["cell"], building["cell"])):
                actor = character["id"]
                bag = inventory(character)
                if bag and bag[name]:
                    if self.use_at(actor, name, building["cell"]):
                        return True
                    if self.economy.travel(actor, {building["cell"]}):
                        return True
            # Keep construction/upgrade errands to one worker in normal daylight.
            phase = self.v.memory.phase
            if phase and phase.is_day and (urgent or self.v.weapon_count >= 2):
                for character in self.characters():
                    if character["roleType"] == "worker" and self.economy.purchase(character["id"], name):
                        return True
        return False

    def construct(self):
        phase = self.v.memory.phase
        if phase is None or not phase.is_day or len(self.stations) != 1:
            return False
        station = self.stations[0]["cell"]
        names = {kind: wire for wire, kind in self.v.rules.weapon_build_names if kind in WEAPONS}
        workers = [r for r in self.characters() if r["roleType"] == "worker"]
        if not workers:
            return False
        candidates = []
        if self.v.weapon_count < 3 and self.v.gold >= 25 and names:
            existing = Counter(r["roleType"] for r in self.weapons)
            kind = min(names, key=lambda k: (existing[k], ("gatling", "rocket", "railgun").index(k)))
            candidates = [(names[kind], cell) for cell in sorted(building_ring(station, 1))]
        elif nonnegative_int(self.v.rules.wall_stone_cost) and self.v.rules.wall_stone_cost > 0:
            # Leave a cardinal entrance on each side, including its diagonal approach.
            sx, sy = station
            cells = {p for p in building_ring(station, 2)
                     if p[0] not in (sx, sx + 1) and p[1] not in (sy, sy - 1)}
            candidates = [("wall", cell) for cell in sorted(cells)]
            workers = [r for r in workers if (inventory(r) or Counter())["stone"] >= self.v.rules.wall_stone_cost]
        choices = []
        for name, cell in candidates:
            if cell in self.world.occupied or cell in self.v.targets:
                continue
            for worker in workers:
                route = self.world.path(worker["cell"], self.world.adjacent_goals({cell}, worker["cell"]), self.v.targets)
                if route:
                    choices.append((len(route), worker["id"], name, cell))
        for _, actor, name, cell in sorted(choices):
            if self.v.add(actor, {"action": "build", "name": name,
                                  "targetPos": [{"x": cell[0], "y": cell[1]}]}):
                return True
            if self.economy.travel(actor, {cell}):
                return True
        return False

    def damage(self, weapon, target):
        origin, kind = weapon["cell"], weapon["roleType"]
        if kind == "rocket":
            return {i: min(self.remaining[i], 20 if r["cell"] == target else 10)
                    for i, r in self.robots.items() if distance(r["cell"], target) <= 1 and self.remaining[i] > 0}
        dx, dy = target[0] - origin[0], target[1] - origin[1]
        length = dx * dx + dy * dy
        aligned = []
        for i, robot in self.robots.items():
            x, y = robot["cell"][0] - origin[0], robot["cell"][1] - origin[1]
            dot = x * dx + y * dy
            if self.remaining[i] > 0 and x * dy == y * dx and 0 < dot <= length:
                aligned.append((dot, i))
        energy = 10 if kind == "gatling" else 10 * level_of(weapon)
        result = {}
        for _, i in sorted(aligned):
            dealt = min(energy, self.remaining[i])
            result[i] = dealt
            energy -= dealt
            if kind == "gatling" or energy <= 0:
                break
        return result

    def fire(self):
        phase = self.v.memory.phase
        if phase is None or phase.is_day:
            return
        for weapon in sorted(self.weapons, key=lambda r: (r["roleType"] == "rocket", r["id"])):
            controllers = [r for r in self.characters() if self.v.near(r, {weapon["cell"]})]
            if not controllers or weapon.get("cooldown", 0) != 0:
                continue
            # Prefer a controller with fewer other adjacent weapons.
            controller = min(controllers, key=lambda r: (sum(self.v.near(r, {w["cell"]}) for w in self.weapons), r["id"]))
            kind, level = weapon["roleType"], level_of(weapon)
            radius = weapon.get("attackRange", {"gatling": (3, 5, 7), "railgun": (6, 8, 10), "rocket": (10, 15, 40)}[kind][level-1])
            if not nonnegative_int(radius):
                continue
            cells = {r["cell"] for r in self.robots.values()}
            if kind == "rocket":
                cells |= {p for r in self.robots.values() for p in neighbors(r["cell"])}
            cells = sorted(p for p in cells if 0 < distance(weapon["cell"], p) <= radius)
            selected = []
            before = dict(self.remaining)
            for _ in range(1 if kind == "railgun" else level):
                options = []
                for cell in cells:
                    if kind == "gatling" and any((cell[0]-weapon["cell"][0])*(p[0]-weapon["cell"][0]) +
                                                (cell[1]-weapon["cell"][1])*(p[1]-weapon["cell"][1]) < 0 for p in selected):
                        continue
                    damage = self.damage(weapon, cell)
                    score = sum(amount * (2 if self.stations and distance(self.robots[i]["cell"], self.stations[0]["cell"]) <= 4 else 1)
                                for i, amount in damage.items())
                    options.append((score, cell, damage))
                if not options:
                    break
                score, cell, damage = max(options, key=lambda x: (x[0], x[1]))
                if score <= 0:
                    if selected:
                        selected.append(selected[0])
                        continue
                    break
                selected.append(cell)
                for i, amount in damage.items():
                    self.remaining[i] -= amount
            command = {"action": "attack", "controllerId": controller["id"],
                       "targetPos": [{"x": x, "y": y} for x, y in selected]}
            if not self.v.add(weapon["id"], command):
                self.remaining = before

    def position_controllers(self):
        phase = self.v.memory.phase
        if phase is None:
            return
        for weapon in sorted(self.weapons, key=lambda r: r["id"]):
            if weapon["id"] in self.v.busy:
                continue
            routes = []
            for character in self.characters():
                route = self.world.path(character["cell"], self.world.adjacent_goals({weapon["cell"]}, character["cell"]), self.v.targets)
                if route and (not phase.is_day or len(route) + 3 >= 71 - phase.round_in_day):
                    routes.append((len(route), character["id"], route))
            if routes:
                _, actor, route = min(routes)
                if len(route) == 1:
                    self.v.busy.add(actor)  # Hold station, emitting no artificial wait action.
                else:
                    self.economy.travel(actor, {weapon["cell"]})


    def support(self):
        phase = self.v.memory.phase
        for character in self.characters():
            actor = character["id"]
            maximum = 220 if character["roleType"] == "worker" else 200
            if character["health"] < maximum // 2 and self.use_at(actor, "Medicine"):
                continue
            if phase is None or phase.is_day or not self.robots:
                continue
            bag = inventory(character) or Counter()
            for name in ("Bomb", "DizzyWeapon"):
                if not bag[name]:
                    continue
                centers = {p for r in self.robots.values() for p in {r["cell"]} | set(neighbors(r["cell"]))}
                def score(p):
                    return sum(min(100, self.remaining[i]) if name == "Bomb" else 1
                               for i, r in self.robots.items() if self.remaining[i] > 0
                               and distance(r["cell"], p) <= 1
                               and (name == "Bomb" or r.get("abnormalState") != "dizzy"))
                cell = max(sorted(centers), key=score)
                if score(cell) > 0 and self.use_at(actor, name, cell):
                    if name == "Bomb":
                        for i, robot in self.robots.items():
                            if distance(robot["cell"], cell) <= 1:
                                self.remaining[i] = max(0, self.remaining[i] - 100)
                    break


def plan_turn(world, memory, rules=None):
    validator = ActionValidator(world, memory, rules)
    defense = DefensePlanner(validator)
    defense.maintain(emergency_only=True)
    defense.fire()
    defense.support()
    defense.position_controllers()
    if not defense.maintain():
        defense.construct()
    EconomyPlanner(validator).workers()
    response = empty_response()
    response["roleCommandMap"] = validator.commands
    return response


@dataclass
class GameMemory:
    identity: tuple
    origin: object = None
    last_round: object = None
    phase: object = None
    news: list = field(default_factory=list)
    enemy_history: dict = field(default_factory=dict)
    previous_actions: dict = field(default_factory=dict)
    feedback: dict = field(default_factory=dict)

    summon_attempts: int = 0
    summon_day_known: bool = False

    def observe(self, world, round_no):
        if round_no == 0:
            self.origin = 0
        self.phase = Phase.from_round(round_no, self.origin) if self.origin is not None else None
        if self.phase is not None and self.phase.round_in_day == 1:
            self.summon_attempts = 0
            self.summon_day_known = True
        elif self.last_round is not None and round_no != self.last_round + 1:
            self.summon_day_known = False
        # These fields describe the previous platform round, not necessarily
        # the last request seen by this process. Never associate across a gap.
        continuous = self.last_round is not None and round_no == self.last_round + 1
        raw_results = world.data.get("lastRoundRoleActionResults")
        results = raw_results if isinstance(raw_results, dict) else {}
        self.feedback = {
            "source_round": round_no - 1,
            "associated": continuous,
            "actions": deepcopy(self.previous_actions) if continuous else {},
            "results": {actor: value for actor, value in results.items()
                        if isinstance(actor, str) and type(value) is bool},
            **{key: deepcopy(world.data.get(key)) for key in
               ("errors", "lastSummonTreasureResult", "llmResp", "lastCmdResult")},
        }
        raw_news = world.data.get("worldNews")
        if isinstance(raw_news, dict):
            news = {key: value for key in ("officialNews", "folkLegends")
                    if isinstance(value := raw_news.get(key), str) and value}
            if news and (not self.news or self.news[-1]["text"] != news
                         or self.news[-1]["day"] != (self.phase.day if self.phase else None)):
                self.news.append({"round": round_no, "day": self.phase.day if self.phase else None,
                                  "text": news})
        for actor, role in world.enemies.items():
            self.enemy_history[actor] = {"round": round_no, "cell": role["cell"],
                                         "roleType": role.get("roleType"), "health": role.get("health")}
        self.last_round = round_no


class GameSession:
    """Atomic in-process planning; transport delivery is not an execution ack."""
    def __init__(self, planner=None, origin=None, rules=None):
        if origin is not None and (type(origin) is not int or origin not in (0, 1)):
            raise ValueError("invalid round origin")
        self.origin = origin
        self.rules = rules or Rules()
        self.planner = planner if planner is not None else lambda w, m: plan_turn(w, m, self.rules)
        self.memory = None
        self.fingerprint = None
        self.response = None
        self.lock = threading.Lock()

    def handle(self, data):
        if not isinstance(data, dict):
            return empty_response()
        round_no = data.get("roundNo")
        our = data.get("teamOur")
        if type(round_no) is not int or not 0 <= round_no <= 1300 or not isinstance(our, dict):
            return empty_response()
        team_id, side = our.get("teamId"), our.get("type")
        if (type(team_id) not in (str, int) or team_id == ""
                or not isinstance(side, str) or side not in {"challenger", "defender"}):
            return empty_response()
        identity = (team_id, side)
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                               allow_nan=False, separators=(",", ":")).encode("utf-8")).digest()
        with self.lock:
            current = self.memory
            same_round = current is not None and current.identity == identity and current.last_round == round_no
            if same_round:
                if fingerprint != self.fingerprint:
                    raise ValueError("conflicting request for committed round")
                return deepcopy(self.response)
            reset = current is None or current.identity != identity or round_no < current.last_round
            candidate = GameMemory(identity, self.origin) if reset else deepcopy(current)
            if candidate.origin == 1 and round_no == 0:
                raise ValueError("round contradicts configured origin")
            world = World(data)
            candidate.observe(world, round_no)
            response = ensure_valid_response(self.planner(world, candidate))
            gate = ActionValidator(world, candidate, self.rules)
            for actor, command in response["roleCommandMap"].items():
                if not gate.add(actor, command):
                    raise ValueError("planner produced illegal action")
            candidate.summon_attempts = gate.summons
            # Serialization and copies can fail; finish them before committing.
            json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")
            cached_response = deepcopy(response)
            outgoing = deepcopy(response)
            candidate.previous_actions = deepcopy(response["roleCommandMap"])
            self.memory, self.fingerprint, self.response = candidate, fingerprint, cached_response
            return outgoing


SESSION = GameSession()


def callback(json_data):
    return SESSION.handle(json_data)


@app.route("/", methods=["POST"])
def process_request():
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("request must be an object")
        return jsonify(ensure_valid_response(callback(data)))
    except Exception as exc:
        # Exception messages may contain untrusted request data or credentials.
        LOG.error("[process_request] 请求处理失败: %s", type(exc).__name__)
        return jsonify(empty_response())


def main():
    parser = argparse.ArgumentParser(description="AgentRace HTTP player")
    parser.add_argument("port", type=int)
    parser.add_argument("--round-origin", type=int, choices=(0, 1), default=None,
                        help="confirmed platform round origin; otherwise only observed zero is inferred")
    parser.add_argument("--wall-stone-cost", type=int, default=None,
                        help="confirmed positive stone cost of one wall")
    parser.add_argument("--weapon-build-name", action="append", default=[], metavar="TYPE=NAME",
                        help="confirmed build name, e.g. gatling=gatling; repeat for other types")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.wall_stone_cost is not None and args.wall_stone_cost <= 0:
        parser.error("wall stone cost must be positive")
    names, kinds = {}, set()
    for entry in args.weapon_build_name:
        kind, separator, name = entry.partition("=")
        if not separator or kind not in WEAPONS or not name or name == "wall" or name in names or kind in kinds:
            parser.error("weapon build names must be unique TYPE=NAME mappings")
        names[name] = kind
        kinds.add(kind)
    global SESSION
    SESSION = GameSession(origin=args.round_origin,
                          rules=Rules(args.wall_stone_cost, tuple(names.items())))
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
