"""AgentRace actions; mechanically extracted from frozen V2.2."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
import json
from .model import (
    CHARACTERS,
    MINERALS,
    Rules,
    SUMMON_ORDERS,
    UPGRADES,
    USABLE,
    WEAPONS,
    building_ring,
    distance,
    inventory,
    level_of,
    nonnegative_int,
    object_list,
    position,
    positive_health,
    shop_prices,
    valid_position
)


def empty_response():
    """Return fresh containers: callers must never share mutable responses."""
    return {"roleCommandMap": {}, "prompt": "", "executeCmd": ""}


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


def strict_json(text):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("nonfinite JSON number")

    if not isinstance(text, str):
        return None
    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return result
    except (ValueError, RecursionError, UnicodeEncodeError):
        return None


@dataclass
class BudgetReserve:
    observed_gold: int
    staged_gold: int
    reserved_gold: dict = field(default_factory=dict)
    committed_gold: int = 0
    committed_items: Counter = field(default_factory=Counter)

    def available(self, bucket):
        return max(0, self.staged_gold - sum(v for k, v in self.reserved_gold.items() if k != bucket))

    @property
    def free_gold(self):
        return self.available("optional")

    def accept(self, bucket, cost, items):
        # Called only after all legality/resource checks succeed. Never credit sales.
        self.staged_gold -= cost
        self.committed_gold += cost
        self.reserved_gold[bucket] = max(0, self.reserved_gold.get(bucket, 0) - cost)
        self.committed_items.update(items)


@dataclass(frozen=True)
class JobAuthorization:
    resources: frozenset
    actions: frozenset
    bucket: str


@dataclass(frozen=True)
class ActionProposal:
    actor: str
    command: dict
    resources: frozenset


class ActionArbiter:
    """Validate a trial atomically, then publish both resource and money changes."""
    def __init__(self, validator, budget):
        self.validator, self.budget = validator, budget

    def accept(self, proposal, authorization):
        command, actor = proposal.command, proposal.actor
        resources = {actor}
        if command.get("action") == "attack":
            resources.add(command.get("controllerId"))
        if (proposal.resources != frozenset(resources) or not resources <= authorization.resources
                or command.get("action") not in authorization.actions):
            return False
        # Share read-only world/memory; copy just the small candidate ledger.
        trial = object.__new__(ActionValidator)
        trial.__dict__ = dict(self.validator.__dict__)
        for key in ("commands", "busy", "targets", "modified"):
            setattr(trial, key, deepcopy(getattr(trial, key)))
        if not trial.add(actor, command):
            return False
        cost = self.validator.gold - trial.gold
        if cost > self.budget.available(authorization.bucket):
            return False
        items = Counter()
        if command["action"] == "build" and command.get("name") == "wall":
            items[(actor, "stone")] = trial.rules.wall_stone_cost
        elif command["action"] in {"use", "drop"}:
            items[(actor, command["name"])] = 1
        elif command["action"] == "sell":
            items[(actor, command["name"])] = command["num"]
        self.validator.__dict__.update(trial.__dict__)
        self.budget.accept(authorization.bucket, cost, items)
        return True
