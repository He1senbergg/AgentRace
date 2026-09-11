"""AgentRace defense; mechanically extracted from frozen V2.2."""
from collections import Counter
from collections import defaultdict
from itertools import product
from .model import (
    DefensePolicy,
    UPGRADES,
    WEAPONS,
    building_ring,
    distance,
    in_bounds,
    inventory,
    level_of,
    max_health,
    neighbors,
    nonnegative_int,
    positive_health
)
from .economy import (
    EconomyPlanner
)


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
        self.all_robots = {i: r for i, r in self.world.robots.items() if positive_health(r.get("health"))}
        self.robots = {i: r for i, r in self.all_robots.items() if r.get("targetTeam") in (None, side)}
        self.remaining = {i: r["health"] for i, r in self.all_robots.items()}
        self.stunned = {i for i, r in self.robots.items() if r.get("abnormalState") == "dizzy"}

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

    def base_reserve(self):
        for base in self.stations:
            level = level_of(base)
            if level is not None and level < 3 and base["health"] < 750 * level:
                return self.v.prices.get(f"StationUpgradeVoucher{level}", 0)
        return 0

    def resume_upgrade(self):
        trip = self.v.memory.upgrade_trip
        if not trip:
            return False
        actor, name, cell = trip
        if actor in self.v.busy:
            return True  # A lifesaving action may pause, but not erase, delivery.
        character = next((c for c in self.characters() if c["id"] == actor), None)
        building = self.v.building_at(cell)
        required = UPGRADES.get(name)
        if (character is None or building is None or required is None
                or building.get("roleType") not in required[0] or level_of(building) != required[1]):
            self.v.memory.upgrade_trip = None
            return False
        if (inventory(character) or Counter())[name]:
            if self.use_at(actor, name, cell):
                self.v.memory.upgrade_trip = None
                return True
            return self.economy.travel(actor, {cell})
        if self.base_reserve() and not name.startswith("Station"):
            self.v.memory.upgrade_trip = None
            return False
        phase = self.v.memory.phase
        route = self.world.path(character["cell"], self.world.adjacent_goals(
            self.world.zones["weaponShop"], character["cell"]), self.v.targets)
        back = self.world.path(route[-1], self.world.adjacent_goals({cell}, route[-1]), self.v.targets) if route else None
        if (not phase or not phase.is_day or not back or len(route) + len(back) + 2 > 71 - phase.round_in_day
                or self.v.prices.get(name, self.v.gold + 1) > self.v.gold):
            self.v.memory.upgrade_trip = None
            return False
        return self.economy.purchase(actor, name)

    def exposure(self, cell):
        """Conservative nearby threat, not a claim about robot target selection."""
        power = {"smallRobot": 5, "middleRobot": 10, "largeRobot": 20, "bossRobot": 40}
        return sum(power.get(r.get("roleType"), 40) for i, r in self.robots.items()
                   if i not in self.stunned and distance(cell, r["cell"]) <= 3)

    def protect(self):
        # Healing must reserve the character before firing reserves its controller.
        for character in self.characters():
            maximum = 220 if character["roleType"] == "worker" else 200
            threat = self.exposure(character["cell"])
            if character["health"] < maximum and (
                    character["health"] <= maximum // 2 or character["health"] <= threat * 2):
                self.use_at(character["id"], "Medicine")

    def provision(self):
        """Carry two heals per controller; only make affordable daylight errands."""
        phase = self.v.memory.phase
        if not phase or not phase.is_day or not self.weapons or "Medicine" not in self.v.prices:
            return
        for character in self.characters():
            bag = inventory(character)
            if bag is None or bag["Medicine"] >= 2:
                continue
            # Nearby shopping is cheap; a dedicated trip needs a built defense.
            goals = self.world.adjacent_goals(self.world.zones["weaponShop"], character["cell"])
            route = self.world.path(character["cell"], goals, self.v.targets)
            if not route or len(self.weapons) < 3 and len(route) > 1:
                continue
            # Healthy pioneers keep their task window; wounded pioneers get a
            # chance to obtain medicine before task movement reserves them.
            if character["roleType"] == "pioneer" and character["health"] > 100 and len(route) > 1:
                continue
            back = self.economy.return_steps(route[-1])
            if back is None or len(route) + back + 3 > 71 - phase.round_in_day:
                continue
            reserve = max(max(0, 3 - len(self.weapons)) * 25, self.base_reserve())
            if self.weapons and not any(level_of(w) >= 2 for w in self.weapons) and character['health'] > 110:
                reserve = max(reserve, self.v.prices.get('WeaponUpgradeVoucher1', 0))
            if self.v.gold - reserve < self.v.prices["Medicine"] * (2 - bag["Medicine"]):
                continue
            self.economy.purchase(character["id"], "Medicine", 2)

    def maintain(self, emergency_only=False):
        if self.v.memory.upgrade_trip:
            return True  # One observed-state delivery at a time; do not switch workers.
        buildings = sorted((r for r in self.world.roles.values()
                            if isinstance(r.get("roleType"), str)
                            and r["roleType"] in WEAPONS | {"station", "wall"}
                            and level_of(r) is not None and positive_health(r.get("health"))),
                           key=lambda r: (0 if r["roleType"] == "station" and r["health"] < 750 * level_of(r) else
                                          1 if r["roleType"] == "rocket" else 2 if r["roleType"] in WEAPONS else 3,
                                          level_of(r), r["health"], r["id"]))
        for building in buildings:
            kind, level = building["roleType"], level_of(building)
            maximum = (1500 * level if kind == "station" else 500 + 500 * level)
            urgent = kind == "station" and building["health"] < maximum // 2
            if emergency_only and not urgent:
                continue
            if kind in WEAPONS and level >= 2 and any(level_of(w) == 1 for w in self.weapons):
                continue  # Breadth first: do not spend on L3 while an L1 can grow.
            if kind == 'wall' and building['health'] >= maximum:
                continue  # Do not spend scarce firepower money upgrading untouched walls.
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
                capacity = sum(max_health(w) or 0 for w in buildings if w.get('roleType') == 'wall')
                growth = capacity < DefensePolicy().capacity_target(phase.day)
                if kind == "wall" and building["health"] < maximum and (level == 3 or not growth):
                    name = "WallFixer"
                errands = []
                for character in self.characters():
                    if character["roleType"] != "worker":
                        continue
                    purchase_name = name
                    if (purchase_name not in self.v.prices or self.v.prices[purchase_name] > self.v.gold):
                        if kind != 'wall' or building['health'] >= maximum:
                            continue
                        purchase_name = 'WallFixer'
                    if purchase_name not in self.v.prices or self.v.prices[purchase_name] > self.v.gold:
                        continue
                    if not urgent and self.v.prices[purchase_name] > self.v.gold - self.base_reserve():
                        continue
                    shop_route = self.world.path(character["cell"], self.world.adjacent_goals(
                        self.world.zones["weaponShop"], character["cell"]), self.v.targets)
                    if not shop_route:
                        continue
                    return_route = self.world.path(shop_route[-1], self.world.adjacent_goals(
                        {building["cell"]}, shop_route[-1]), self.v.targets)
                    if not return_route or len(shop_route) + len(return_route) + 2 > 71 - phase.round_in_day:
                        continue
                    errands.append((len(shop_route) + len(return_route), character["id"], purchase_name))
                for _, actor, name in sorted(errands):
                    if self.economy.purchase(actor, name):
                        if name in UPGRADES:
                            self.v.memory.upgrade_trip = (actor, name, building["cell"])
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
            kind = min(names, key=lambda k: ("rocket", "gatling", "railgun").index(k))
            candidates = [(names[kind], cell) for cell in sorted(building_ring(station, 1))]
        elif nonnegative_int(self.v.rules.wall_stone_cost) and self.v.rules.wall_stone_cost > 0:
            # Build a front screen; leave the back half open for economic routes.
            sx, sy = station
            cells = {p for p in building_ring(station, 2)
                     if (p[0]-sx-.5)*(20-sx-.5)+(p[1]-sy+.5)*(16-sy) > 0}
            candidates = [("wall", cell) for cell in sorted(cells)]
            workers = [r for r in workers if (inventory(r) or Counter())["stone"] >= self.v.rules.wall_stone_cost]
            workers = [r for r in workers if not self.v.memory.wall_builder
                       or r['id'] != self.v.memory.wall_builder['actor']
                       or self.v.memory.wall_builder['building']]
        choices = []
        for name, cell in candidates:
            if cell in self.world.occupied or cell in self.v.targets:
                continue
            for worker in workers:
                route = self.world.path(worker["cell"], self.world.adjacent_goals({cell}, worker["cell"]), self.v.targets)
                if route:
                    # Face the shared map center on either starting side. The
                    # old coordinate/worker-id tie break built both bases alike.
                    cx, cy = station[0] + .5, station[1] - .5
                    frontage = -((cell[0] - cx) * (20 - cx) + (cell[1] - cy) * (15.5 - cy))
                    choices.append((frontage if name == 'wall' else -frontage,
                                    len(route), worker["id"], name, cell))
        for _, _, actor, name, cell in sorted(choices):
            if self.v.add(actor, {"action": "build", "name": name,
                                  "targetPos": [{"x": cell[0], "y": cell[1]}]}):
                return True
            if self.economy.travel(actor, {cell}):
                return True
        return False

    def fortify(self):
        """Bounded nearby stone errands for the existing wall construction plan."""
        phase = self.v.memory.phase
        if (not phase or not phase.is_day or self.v.weapon_count < 3
                or self.v.wall_count >= 8 or self.base_reserve()
                or not nonnegative_int(self.v.rules.wall_stone_cost) or self.v.rules.wall_stone_cost <= 0):
            self.v.memory.wall_builder = None
            return False
        job = self.v.memory.wall_builder
        if job:
            owner = self.world.characters.get(job['actor'])
            bag = inventory(owner) if owner else None
            if bag is None:
                self.v.memory.wall_builder = None
                job = None
            elif job['building']:
                # Called only after construct could not act. Do not strand a
                # stocked builder when all remaining front sites are blocked.
                self.v.memory.wall_builder = None
                if bag['stone'] >= self.v.rules.wall_stone_cost:
                    return False
                job = None
            elif bag['stone'] >= job['goal']:
                job['building'] = True
                return False
        errands = []
        for character in self.characters():
            if character['roleType'] != 'worker':
                continue
            if job and character['id'] != job['actor']:
                continue
            bag = inventory(character)
            if bag is None:
                continue
            if not job and bag['stone'] >= self.v.rules.wall_stone_cost:
                continue
            for cell in self.world.zones['stone']:
                route = self.world.path(character['cell'], self.world.adjacent_goals({cell}, character['cell']), self.v.targets)
                back = self.economy.return_steps(route[-1]) if route else None
                goal = job['goal'] if job else min(8 - self.v.wall_count, 8) * self.v.rules.wall_stone_cost
                needed = max(0, goal - bag['stone'])
                capacity = character.get('backPackCapability', 100)
                if (nonnegative_int(capacity) and sum(bag.values()) + needed <= capacity
                        and route and back is not None
                        and len(route) - 1 + needed + back + 3 <= min(26, 71 - phase.round_in_day)):
                    errands.append((len(route), character['id'], cell, route, goal))
        for _, actor, cell, route, goal in sorted(errands):
            target = cell if len(route) == 1 else route[1]
            if self.v.add(actor, {'action': 'collect' if len(route) == 1 else 'move',
                                 'targetPos': [dict(x=target[0], y=target[1])]}):
                self.v.memory.wall_builder = {'actor': actor, 'goal': goal, 'building': False}
                return True
        if job:
            self.v.memory.wall_builder = None  # Unreachable/refreshed mine or deadline: release the worker.
        return False

    def damage(self, weapon, target):
        origin, kind = weapon["cell"], weapon["roleType"]
        if kind == "rocket":
            return {i: min(self.remaining[i], 20 if r["cell"] == target else 10)
                    for i, r in self.all_robots.items() if distance(r["cell"], target) <= 1 and self.remaining[i] > 0}
        dx, dy = target[0] - origin[0], target[1] - origin[1]
        length = dx * dx + dy * dy
        aligned = []
        for i, robot in self.all_robots.items():
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

    def attack_plan(self, weapon):
        """Evaluate a volley without retaining its speculative damage."""
        kind, level = weapon["roleType"], level_of(weapon)
        radius = weapon.get("attackRange", {"gatling": (3, 5, 7), "railgun": (6, 8, 10), "rocket": (10, 15, 40)}[kind][level-1])
        if not nonnegative_int(radius):
            return [], dict(self.remaining), 0
        cells = {r["cell"] for r in self.robots.values()}
        if kind == "rocket":
            cells |= {p for r in self.robots.values() for p in neighbors(r["cell"])}
        cells = sorted(p for p in cells if 0 < distance(weapon["cell"], p) <= radius)
        selected = []
        total_score = 0
        before = self.remaining
        self.remaining = dict(before)
        for _ in range(1 if kind == "railgun" else level):
            options = []
            for cell in cells:
                if kind == "gatling" and any((cell[0]-weapon["cell"][0])*(p[0]-weapon["cell"][0]) +
                                            (cell[1]-weapon["cell"][1])*(p[1]-weapon["cell"][1]) < 0 for p in selected):
                    continue
                damage = self.damage(weapon, cell)
                score = sum(amount * (3 if any(distance(self.robots[i]["cell"], c["cell"]) <= 3
                                              for c in self.world.characters.values()) else
                                      2 if self.stations and distance(self.robots[i]["cell"], self.stations[0]["cell"]) <= 4 else 1)
                            for i, amount in damage.items() if i in self.robots)
                options.append((score, cell, damage))
            if not options:
                break
            score, cell, damage = max(options, key=lambda x: (x[0], x[1]))
            if score <= 0:
                if selected:
                    selected.append(selected[0])
                    continue
                break
            total_score += score
            selected.append(cell)
            for i, amount in damage.items():
                self.remaining[i] -= amount
        after = self.remaining
        self.remaining = before
        return selected, after, total_score

    def fire(self):
        phase = self.v.memory.phase
        if phase is None or phase.is_day:
            return
        available = {w["id"]: w for w in self.weapons}
        shortage = len(self.characters()) < len(self.weapons)
        while available and self.characters():
            candidates = []
            for weapon in available.values():
                cooldown = weapon.get("cooldown", 0)
                if not nonnegative_int(cooldown):
                    continue
                if cooldown and not shortage:
                    continue
                selected, after, score = self.attack_plan(weapon)
                if not selected or score <= 0:
                    continue
                for character in self.characters():
                    near = self.v.near(character, {weapon["cell"]})
                    if near:
                        if cooldown:
                            continue
                        moves = 0
                    elif shortage:
                        route = self.world.path(character["cell"], self.world.adjacent_goals(
                            {weapon["cell"]}, character["cell"]), self.v.targets)
                        if not route:
                            continue
                        moves = len(route) - 1
                    else:
                        continue
                    alternatives = sum(self.v.near(character, {w["cell"]}) for w in available.values())
                    candidates.append((score / (max(moves, cooldown) + 1), -moves, -alternatives,
                                       weapon["id"], character["id"], selected, after))
            if not candidates:
                break
            _, neg_moves, _, weapon_id, actor, selected, after = max(candidates, key=lambda c: c[:5])
            weapon = available.pop(weapon_id)
            if neg_moves:
                self.economy.travel(actor, {weapon["cell"]})
            elif self.v.add(weapon_id, {"action": "attack", "controllerId": actor,
                                      "targetPos": [{"x": x, "y": y} for x, y in selected]}):
                self.remaining = after

    def position_controllers(self):
        phase = self.v.memory.phase
        if phase is None:
            return
        choices = []
        for weapon in sorted(self.weapons, key=lambda r: (r.get('cooldown', 0) != 0, r['id']))[:3]:
            if weapon['id'] in self.v.busy:
                continue
            options = [None]
            for character in sorted(self.characters(), key=lambda c: distance(c['cell'], weapon['cell']))[:6]:
                goals = {p for p in self.world.adjacent_goals({weapon['cell']}, character['cell'])
                         if in_bounds(p) and p not in self.v.targets}
                if not phase.is_day and self.v.near(character, {weapon['cell']}):
                    goals = {p for p in goals if distance(p, character['cell']) <= 1}
                if not goals:
                    continue
                risk = {p: self.exposure(p) for p in goals}
                goals = {p for p in goals if risk[p] == min(risk.values())}
                route = self.world.path(character['cell'], goals, self.v.targets)
                if not route or phase.is_day and len(route) + 3 < 71 - phase.round_in_day:
                    continue
                # Prefer available guns over waiting guns, with a stable shortest
                # complete assignment rather than reserving actors by weapon ID.
                value = (20 if weapon.get('cooldown', 0) == 0 else 5) / len(route)
                options.append((character['id'], route, value, risk[route[-1]]))
            choices.append(options)
        best = None
        best_key = None
        for assignment in product(*choices):
            selected = [x for x in assignment if x is not None]
            actors = [x[0] for x in selected]
            destinations = [x[1][1] if len(x[1]) > 1 else x[1][0] for x in selected]
            if len(set(actors)) != len(actors) or len(set(destinations)) != len(destinations):
                continue
            key = (sum(x[2] for x in selected), len(selected),
                   -sum(x[3] for x in selected), -sum(len(x[1]) for x in selected))
            if best_key is None or key > best_key:
                best_key, best = key, selected
        for actor, route, _, _ in best or []:
            if len(route) == 1:
                self.v.busy.add(actor)
            else:
                self.v.add(actor, {'action': 'move',
                                  'targetPos': [dict(x=route[1][0], y=route[1][1])]})


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
                               and (name == "Bomb" or i not in self.stunned))
                cell = max(sorted(centers), key=score)
                if score(cell) > 0 and self.use_at(actor, name, cell):
                    if name == "Bomb":
                        for i, robot in self.all_robots.items():
                            if distance(robot["cell"], cell) <= 1:
                                self.remaining[i] = max(0, self.remaining[i] - 100)
                    else:
                        self.stunned.update(i for i, r in self.robots.items() if distance(r["cell"], cell) <= 1)
                    break

    def summon(self):
        phase = self.v.memory.phase
        if phase is None or not phase.is_day:
            return
        for character in self.characters():
            bag = inventory(character) or Counter()
            for size in ("Boss", "Large", "Middle", "Small"):
                name = size + "RobotSummonOrder"
                if bag[name] and self.use_at(character["id"], name):
                    break


class ShadowDefensePlanner(DefensePlanner):
    """Same rocket estimate with a cell index; leaves legacy execution unchanged."""
    def __init__(self, validator):
        super().__init__(validator)
        self.robot_cells = defaultdict(list)
        for actor, robot in self.all_robots.items():
            self.robot_cells[robot['cell']].append(actor)

    def damage(self, weapon, target):
        if weapon['roleType'] != 'rocket':
            return super().damage(weapon, target)
        return {actor: min(self.remaining[actor], 20 if cell == target else 10)
                for cell in [target, *neighbors(target)] for actor in self.robot_cells.get(cell, ())
                if self.remaining[actor] > 0}
