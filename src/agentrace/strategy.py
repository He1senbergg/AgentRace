"""AgentRace strategy; mechanically extracted from frozen V2.2."""
from collections import Counter
from copy import deepcopy
from .model import (
    CanonicalLayout,
    DefensePolicy,
    MINERALS,
    USABLE,
    WEAPONS,
    World,
    distance,
    inventory,
    level_of,
    max_health,
    neighbors,
    nonnegative_int,
    positive_health
)
from .memory import (
    ControllerAssignment,
    Day1Plan,
    RoleJob
)
from .actions import (
    ActionArbiter,
    ActionProposal,
    ActionValidator,
    BudgetReserve,
    JobAuthorization,
    empty_response
)
from .economy import (
    EconomyPlanner
)
from .defense import (
    DefensePlanner,
    ShadowDefensePlanner
)
from .task_news import (
    NewsPlanner,
    TaskPlanner,
    TreasurePlanner,
    task_options
)


def plan_turn(world, memory, rules=None):
    validator = ActionValidator(world, memory, rules)
    response = empty_response()
    defense = DefensePlanner(validator)
    defense.protect()
    defense.resume_upgrade()
    maintained = defense.maintain(emergency_only=True)
    NewsPlanner(validator).run(response)
    defense.fire()
    defense.support()
    EconomyPlanner(validator).liquidate()
    if not maintained:
        maintained = defense.maintain()  # Budgeted upgrades precede optional shopping and early return.
    defense.position_controllers()
    if not maintained or validator.weapon_count >= 3:
        if not defense.construct():
            defense.fortify()
    TreasurePlanner(validator).run()
    defense.provision()
    TaskPlanner(validator).run(response)
    defense.summon()
    EconomyPlanner(validator).workers()
    response["roleCommandMap"] = validator.commands
    return response


class StrategicPlanner:
    """Gate1 shadow policy. Intended commands are never execution evidence."""
    def __init__(self, world, memory, delta, rules, policy=None, authority=False):
        self.world, self.memory, self.delta, self.rules = world, memory, delta, rules
        self.state = deepcopy(memory.strategic)
        self.plan = self.state.plan
        self.layout = CanonicalLayout.from_world(world)
        self.v = ActionValidator(world, memory, rules)
        self.defense = ShadowDefensePlanner(self.v)
        self.return_diagnostics = {}
        self.coverage_relocations = set()
        self.policy = policy or DefensePolicy()
        self.authority = authority
        self.intended_response = empty_response()

    def service_trip(self, actor, building, name):
        """Current static routes for buy/use/return, with no predicted income."""
        phase = self.delta.phase
        if not phase or not phase.is_day:
            return None
        character = self.world.characters[actor]
        bag = inventory(character)
        if bag is None:
            return None
        geometry = object.__new__(World)
        geometry.occupied = set(self.world.static_occupied)
        cursor, cost = character['cell'], 0
        if not bag[name]:
            route = geometry.path(cursor, geometry.adjacent_goals(self.world.zones['weaponShop'], cursor))
            if not route:
                return None
            cursor, cost = route[-1], len(route)  # travel + one purchase
        if building:
            route = geometry.path(cursor, geometry.adjacent_goals({building['cell']}, cursor))
            if not route:
                return None
            cursor, cost = route[-1], cost + len(route) - 1
        cost += 1  # use
        assignment = self.plan.controllers.get(actor)
        goals = {assignment.safe_slot} if assignment else geometry.adjacent_goals(
            {w['cell'] for w in self.defense.weapons}, cursor)
        back = geometry.path(cursor, goals) if goals else [cursor]
        if not back or cost + len(back) - 1 + 5 > 71 - phase.round_in_day:
            return None
        return cost, len(back) - 1

    def can_service(self, actor, building, name, funds):
        char = self.world.characters[actor]
        bag = inventory(char)
        if bag is None:
            return False
        capacity = char.get('backPackCapability', 100)
        can_buy = (name in self.v.prices and self.v.prices[name] <= funds
                   and nonnegative_int(capacity) and sum(bag.values()) < capacity)
        return (bag[name] > 0 or can_buy) and self.service_trip(actor, building, name) is not None

    def wall_totals(self):
        walls = [w for w in self.world.roles.values() if w.get('roleType') == 'wall']
        maxima = [max_health(w) for w in walls]
        return sum(w['health'] for w in walls), sum(maxima) if all(x is not None for x in maxima) else None

    def health_ready(self, char):
        return positive_health(char.get('health')) and char['health'] >= self.policy.controller_health_ratio * max_health(char)

    def execute_service(self, job, building, name, bucket):
        bag = inventory(self.world.characters[job.owner]) or Counter()
        if bag[name]:
            if building and not self.v.near(self.world.characters[job.owner], {building['cell']}):
                return self.move(job, {building['cell']})
            command = {'action': 'use', 'name': name}
            if building:
                command['targetPos'] = [dict(x=building['cell'][0], y=building['cell'][1])]
            return self.propose(job, command)
        if self.v.near(self.world.characters[job.owner], self.world.zones['weaponShop']):
            return self.propose(job, {'action': 'buy', 'name': name, 'num': 1}, bucket=bucket)
        return self.move(job, self.world.zones['weaponShop'])

    def route(self, actor, cells, adjacent=True):
        start = self.world.characters[actor]["cell"]
        goals = self.world.adjacent_goals(cells, start) if adjacent else cells
        return self.world.path(start, goals, self.v.targets)

    def completion_trip(self, job, slot):
        """Observed-map route/action estimate to finish this job, then take station.

        Unknown/unreachable means return now. Future occupancy is never guaranteed.
        """
        start = self.world.characters[job.owner]["cell"]
        cursor, cost = start, 0
        geometry = object.__new__(World)
        geometry.occupied = set(self.world.static_occupied)
        geometry.occupied.discard(start)  # This actor leaves its observed cell in the estimate.
        def visit(cells, actions=1):
            nonlocal cursor, cost
            route = geometry.path(cursor, geometry.adjacent_goals(cells, cursor))
            if route is None:
                return False
            cost += len(route) - 1 + actions
            cursor = route[-1]
            return True
        if job.job_type == "BUILD_WALL":
            missing = max(0, self.plan.execution_wall_target - self.v.wall_count)
            bag = inventory(self.world.characters[job.owner]) or Counter()
            stones = self.rules.wall_stone_cost
            if not nonnegative_int(stones) or stones == 0:
                return None
            collect = max(0, missing * stones - bag['stone'])
            if collect and not visit(self.world.zones['stone'], collect):
                return None
            remaining_slots = list(self.layout.wall_slots)
            for _ in range(missing):
                choices = [(len(r), cell) for cell in remaining_slots
                           if cell not in geometry.occupied
                           and (r := geometry.path(cursor, geometry.adjacent_goals({cell}, cursor)))]
                if not choices:
                    return None
                _, cell = min(choices)
                if not visit({cell}):
                    return None
                geometry.occupied.add(cell)
                remaining_slots.remove(cell)
        elif job.job_type == "BUILD_WEAPON":
            cells = {job.target} if job.target in self.layout.weapon_slots else set(self.layout.weapon_slots)
            if not visit(cells):
                return None
        elif job.job_type == 'WALL_SERVICE':
            wall = self.hot_wall()
            if wall:
                name = self.wall_item(wall, job.owner)
                return self.service_trip(job.owner, wall, name) if name else None
        elif job.job_type in {'HEAL', 'STATION_SERVICE'}:
            building = self.world.roles.get(job.target) if job.job_type == 'STATION_SERVICE' else None
            return self.service_trip(job.owner, building, 'StationUpgradeVoucher1' if building else 'Medicine')
        elif job.job_type == "UPGRADE":
            weapons = {w['cell'] for w in self.defense.weapons if level_of(w) == 1}
            bag = inventory(self.world.characters[job.owner]) or Counter()
            if not bag['WeaponUpgradeVoucher1'] and not visit(self.world.zones['weaponShop']):
                return None
            if not visit(weapons):
                return None
        elif job.job_type == "TASK":
            trips = []
            for task, cells in task_options(self.v):
                timeout = task.get('timeoutRounds')
                route = geometry.path(cursor, geometry.adjacent_goals(cells, cursor))
                back = geometry.path(route[-1], {slot}) if route else None
                if nonnegative_int(timeout) and route and back:
                    trips.append((len(route) + timeout, len(back) - 1))
            if trips:
                return max(trips, key=lambda t: sum(t))
            cost += 1
        elif job.job_type == "ECONOMY":
            cost += 1  # Economy is interruptible after each action, never a batch lock.
        route = geometry.path(cursor, {slot})
        return (cost, len(route) - 1) if route else None

    def assign_controllers(self):
        assignments, chars = self.plan.controllers, self.world.characters
        goals = {p for w in self.defense.weapons for p in neighbors(w['cell'])
                 if p not in self.layout.static_blockers}
        for actor, assignment in list(assignments.items()):
            if actor not in chars or assignment.safe_slot not in goals:
                del assignments[actor]
        # Physical coverage is persistent; no weapon owns a particular character.
        for actor, char in sorted(chars.items()):
            if char['cell'] in goals:
                assignments[actor] = ControllerAssignment(actor, char['cell'])
        used = {a.safe_slot for a in assignments.values()}
        for actor, char in sorted(chars.items()):
            if actor in assignments:
                continue
            choices = []
            for goal in sorted(goals - used):
                route = self.route(actor, {goal}, adjacent=False)
                if route:
                    choices.append((self.defense.exposure(goal), len(route), goal))
            if choices:
                _, _, goal = min(choices)
                assignments[actor] = ControllerAssignment(actor, goal)
                used.add(goal)
        physical = self.adjacent_matching(ready_only=False)
        uncovered = [w for w in self.defense.weapons if w['id'] not in physical]
        # Move only redundant characters toward uncovered weapons. Cooldown does
        # not affect this physical-coverage decision or ownership of positions.
        for actor in sorted(set(chars) - set(physical.values())):
            if self.delta.task_active and chars[actor].get('roleType') == 'pioneer':
                continue
            choices = []
            other_slots = {a.safe_slot for key, a in assignments.items() if key != actor}
            for weapon in uncovered:
                for goal in set(neighbors(weapon['cell'])) - self.layout.static_blockers - other_slots:
                    route = self.route(actor, {goal}, adjacent=False)
                    if route:
                        choices.append((len(route), self.defense.exposure(goal), weapon['id'], goal))
            if choices:
                _, _, weapon_id, goal = min(choices)
                assignments[actor] = ControllerAssignment(actor, goal)
                self.coverage_relocations.add(actor)
                uncovered = [w for w in uncovered if w['id'] != weapon_id]

    def adjacent_matching(self, ready_only=True, weapons=None, excluded=()):
        """Maximum cardinality matching on current geometry, not saved slots."""
        candidates = sorted(self.defense.weapons if weapons is None else weapons, key=lambda w: w['id'])
        actors = {a: c for a, c in self.world.characters.items() if a not in excluded
                  and positive_health(c.get('health'))
                  and not (self.delta.task_active and c.get('roleType') == 'pioneer')}
        by_actor = {}
        def augment(weapon, seen):
            for actor, char in sorted(actors.items()):
                if actor in seen or distance(char['cell'], weapon['cell']) > 1:
                    continue
                seen.add(actor)
                if actor not in by_actor or augment(by_actor[actor], seen):
                    by_actor[actor] = weapon
                    return True
            return False
        for weapon in candidates:
            if not ready_only or weapon.get('cooldown', 0) == 0:
                augment(weapon, set())
        return {weapon['id']: actor for actor, weapon in by_actor.items()}

    def hot_wall(self):
        if self.plan.day < 2:
            return None
        walls = [w for w in self.world.roles.values() if w.get('roleType') == 'wall' and level_of(w)]
        damaged = [w for w in walls if w['health'] < 500 + 500 * level_of(w)]
        if damaged:
            return max(damaged, key=lambda w: (self.state.wall_damage.get(w['id'], 0),
                                               500 + 500 * level_of(w) - w['health'], w['id']))
        if sum(w['health'] for w in walls) < self.plan.wall_hp_target or sum(max_health(w) for w in walls) < self.policy.capacity_target(self.plan.day):
            return next((w for w in sorted(walls, key=lambda w: (-self.state.wall_damage.get(w['id'], 0), w['id']))
                         if level_of(w) < 3), None)
        return None

    def wall_item(self, wall, actor=None):
        current, capacity = self.wall_totals()
        growth = capacity is not None and (capacity < self.policy.capacity_target(self.plan.day) or current < self.plan.wall_hp_target)
        choices = []
        if level_of(wall) < 3 and growth:
            choices.append(f'WallUpgradeVoucher{level_of(wall)}')
        if wall['health'] < max_health(wall):
            choices.append('WallFixer')
        if actor is None:
            return choices[0] if choices else None
        funds = self.plan.budget.available('wall') if self.plan.budget else self.v.gold
        for name in choices:
            if self.can_service(actor, wall, name, funds):
                return name
        self.plan.reasons.append('WALL_SERVICE_FUNDS_OR_DEADLINE')
        return None

    def reconcile(self):
        d, plan = self.delta, self.plan
        plan.reasons = []
        if d.phase and d.phase.day != plan.day:
            # New day, even after an observation gap: old jobs never become dawn RETURNs.
            day = d.phase.day
            self.state.previous_night_walls = {
                'last_hp': dict(self.state.last_wall_hp), 'observed_hp_decreases': dict(self.state.wall_damage),
                'missing_ids': sorted(self.state.night_start_walls - set(self.state.last_wall_hp))
                if self.state.night_start_walls is not None else None,
            }
            count = (8, 9, 10)[min(day, 3) - 1]
            self.plan = plan = Day1Plan(day=day, controllers=plan.controllers,
                                       benchmark_wall_target=count, execution_wall_target=count,
                                       wall_hp_target=10000 if day >= 3 else 8000,
                                       weapon_level_target=(2, 2, 1) if day >= 3 else (2, 1, 1))
            self.state.plan = plan
            plan.reasons.append('NEW_DAY')
        if self.state.last_round is not None and not d.continuous:
            plan.reasons.append("observation_gap")
        self.state.last_round = d.round_no
        weapons = self.defense.weapons
        walls = [r for r in self.world.roles.values() if r.get("roleType") == "wall"]
        plan.execution_wall_target = max(plan.execution_wall_target, min(plan.benchmark_wall_target, len(walls)))
        wall_hp = {w['id']: w['health'] for w in walls}
        if d.continuous:
            for actor, hp in wall_hp.items():
                self.state.wall_damage[actor] = self.state.wall_damage.get(actor, 0) + max(
                    0, self.state.last_wall_hp.get(actor, hp) - hp)
        self.state.last_wall_hp = wall_hp
        if d.phase and not d.phase.is_day and self.state.night_key != d.phase.day:
            self.state.night_key = d.phase.day
            self.state.night_start_walls = set(wall_hp) if d.phase.round_in_day == 71 else None
            self.state.wall_damage = {}  # Attribute observed damage within this night, not lifetime.
        self.state.wall_damage = {a: v for a, v in self.state.wall_damage.items() if a in wall_hp}
        missing = max(0, 3 - len(weapons))
        upgrade_needed = sum((level_of(w) or 0) >= 2 for w in weapons) < sum(n >= 2 for n in plan.weapon_level_target)
        held = any((inventory(c) or Counter())["WeaponUpgradeVoucher1"] for c in self.world.characters.values())
        # Observed task income enters this reserve automatically. No predicted rewards.
        build_reserve = min(d.gold, missing * 25)
        wall = self.hot_wall()
        wall_needs = [w for w in walls if level_of(w) and w['health'] < 500 + 500 * level_of(w)] if plan.day >= 2 else []
        wall_cost = self.v.prices.get(self.wall_item(wall), 0) if wall else 0
        self.assign_controllers()
        healers = [a for a in plan.controllers if not self.health_ready(self.world.characters[a])
                   and not (d.task_active and self.world.characters[a].get('roleType') == 'pioneer')
                   and self.can_service(a, None, 'Medicine', d.gold)]
        health_reserve = min(d.gold - build_reserve, sum(
            0 if (inventory(self.world.characters[a]) or Counter())['Medicine'] else self.v.prices.get('Medicine', 0)
            for a in healers))
        base = next((b for b in self.defense.stations if level_of(b) == 1), None)
        self.station_service = None
        if base:
            growth_possible = any(self.can_service(a, wall, self.wall_item(wall), d.gold)
                                  for a, c in self.world.characters.items() if c.get('roleType') == 'worker') if wall else False
            # A fallback never displaces a reachable, affordable structural upgrade.
            growth_possible |= any(self.can_service(a, w, 'WeaponUpgradeVoucher1', d.gold)
                                   for a, c in self.world.characters.items() if c.get('roleType') == 'worker'
                                   for w in weapons if upgrade_needed and level_of(w) == 1)
            if len(walls) < plan.execution_wall_target:
                saved_target = plan.execution_wall_target
                try:
                    plan.execution_wall_target = len(walls) + 1
                    for actor, char in self.world.characters.items():
                        if char.get('roleType') != 'worker':
                            continue
                        slot = plan.controllers[actor].safe_slot if actor in plan.controllers else char['cell']
                        trip = self.completion_trip(RoleJob(actor, 'BUILD_WALL', None, 'START', 70, d.round_no, d.round_no), slot)
                        if trip is not None and d.phase and sum(trip) + 5 <= 71 - d.phase.round_in_day:
                            growth_possible = True
                finally:
                    plan.execution_wall_target = saved_target
            current_hp, capacity = self.wall_totals()
            emergency = base['health'] < self.policy.station_emergency_ratio * 1500
            gap = (plan.day >= 3 and capacity is not None and
                   (capacity < self.policy.capacity_target(plan.day) or current_hp < plan.wall_hp_target))
            if emergency or gap and not growth_possible:
                candidates = [(self.service_trip(a, base, 'StationUpgradeVoucher1'), a)
                              for a, c in self.world.characters.items() if c.get('roleType') == 'worker'
                              and self.can_service(a, base, 'StationUpgradeVoucher1', d.gold - build_reserve - health_reserve)]
                if candidates:
                    self.station_service = (min(candidates)[1], base)
                    plan.reasons.append('STATION_EMERGENCY' if emergency else 'STATION_GAP_FALLBACK')
        station_reserve = (0 if not self.station_service or
                           (inventory(self.world.characters[self.station_service[0]]) or Counter())['StationUpgradeVoucher1']
                           else self.v.prices.get('StationUpgradeVoucher1', 100))
        available = max(0, d.gold - build_reserve - health_reserve - station_reserve)
        wall_reserve = min(available, wall_cost)
        reserve = {"build": build_reserve, "wall": wall_reserve,
                   "health": health_reserve, "station": station_reserve,
                   "upgrade": min(available - wall_reserve, self.v.prices.get("WeaponUpgradeVoucher1", 100))
                   if upgrade_needed and not held else 0}
        plan.budget = BudgetReserve(d.gold, d.gold, reserve)
        self.arbiter = ActionArbiter(self.v, plan.budget)
        self.assign_controllers()
        phase = d.phase
        end = d.round_no + 70 - phase.round_in_day if phase else d.round_no
        plan.mode = "NIGHT" if phase and not phase.is_day else "DAY_NORMAL"
        if not phase or not self.layout.footprint or len(self.world.characters) < 3:
            plan.mode = "RECOVERY" if not phase or phase.is_day else "NIGHT"
        for actor, job in list(plan.jobs.items()):
            assignment = plan.controllers.get(actor) if job.job_type in {"RETURN", "CONTROL"} else None
            orphan = job.job_type in {"RETURN", "CONTROL"} and (assignment is None or assignment.controller != actor)
            complete = (job.job_type == "BUILD_WEAPON" and len(weapons) >= 3
                        or job.job_type == "BUILD_WALL" and len(walls) >= plan.execution_wall_target
                        or job.job_type == "UPGRADE" and not upgrade_needed
                        or job.job_type == 'WALL_SERVICE' and wall is None
                        or job.job_type == 'HEAL' and actor not in healers
                        or job.job_type == 'STATION_SERVICE' and self.station_service is None)
            if actor not in self.world.characters or orphan or complete or d.round_no > job.deadline:
                del plan.jobs[actor]
        if phase and phase.is_day:
            for actor in healers:
                if actor not in plan.jobs or plan.jobs[actor].job_type != 'HEAL':
                    plan.jobs[actor] = RoleJob(actor, 'HEAL', None, 'RECOVER', 95, d.round_no, end)
            if self.station_service:
                actor, base = self.station_service
                if actor not in healers and (actor not in plan.jobs or plan.jobs[actor].job_type != 'STATION_SERVICE'):
                    plan.jobs[actor] = RoleJob(actor, 'STATION_SERVICE', base['id'], 'RECOVER', 90, d.round_no, end)
            # Wall service can preempt optional economy/weapon upgrades, never an active task.
            if wall and not any(j.job_type == 'WALL_SERVICE' for j in plan.jobs.values()):
                for actor, job in sorted(plan.jobs.items()):
                    if self.world.characters[actor].get('roleType') == 'worker' and job.job_type in {'ECONOMY', 'UPGRADE'}:
                        del plan.jobs[actor]
                        break
            for actor, char in sorted(self.world.characters.items()):
                if actor in plan.jobs:
                    continue
                types = {j.job_type for j in plan.jobs.values()}
                kind = ("TASK" if char.get("roleType") == "pioneer" else
                        "BUILD_WEAPON" if missing and "BUILD_WEAPON" not in types else
                        "WALL_SERVICE" if wall and "WALL_SERVICE" not in types else
                        "BUILD_WALL" if len(walls) < plan.execution_wall_target and "BUILD_WALL" not in types else
                        "UPGRADE" if upgrade_needed and "UPGRADE" not in types else "ECONOMY")
                priority = {'WALL_SERVICE': 80, 'BUILD_WALL': 70, 'UPGRADE': 60, 'ECONOMY': 20}.get(kind, 50)
                plan.jobs[actor] = RoleJob(actor, kind, None, "START", priority, d.round_no, end)
        # Recompute completion/return routes from this observation; an estimate is
        # not a guarantee about future blockers or remote task success.
        for assignment in plan.controllers.values():
            actor = assignment.controller
            if d.task_active and self.world.characters[actor].get("roleType") == "pioneer":
                plan.reasons.append("active_task_controller_unavailable")
                continue
            geometry = object.__new__(World)
            geometry.occupied = set(self.world.static_occupied)
            route = geometry.path(self.world.characters[actor]['cell'], {assignment.safe_slot})
            job = plan.jobs.get(actor)
            trip = self.completion_trip(job, assignment.safe_slot) if job else (0, len(route) - 1) if route else None
            if (phase and phase.is_day and job and job.job_type == "BUILD_WALL" and route
                    and (trip is None or sum(trip) + 5 > end - d.round_no + 1)):
                # Missing the full benchmark is not itself a reason to abandon the day.
                while plan.execution_wall_target > self.v.wall_count:
                    plan.execution_wall_target -= 1
                    trip = self.completion_trip(job, assignment.safe_slot)
                    if trip is not None and sum(trip) + 5 <= end - d.round_no + 1:
                        break
                plan.reasons.append("DEADLINE_INFEASIBLE")
                if plan.execution_wall_target <= self.v.wall_count:
                    job.job_type, job.target, job.phase = "ECONOMY", None, "START"
                    trip = (1, len(route) - 1)
            remaining, back = trip if trip else (0, 0)
            self.return_diagnostics[actor] = {
                "job_type": job.job_type if job else None,
                "return_deadline": end - 5 - back + 1 if phase and trip else None,
                "estimated_finish": d.round_no + remaining - 1 if trip else None,
                "direct_return_cost": len(route) - 1 if route else None,
                "after_job_return_cost": back if trip else None,
                "remaining_job_cost": remaining if trip else None,
            }
            # An impossible errand is not evidence that immediate return is necessary.
            direct_due = route is None or d.round_no > end - 5 - (len(route) - 1) + 1
            due = (not phase or not phase.is_day or direct_due
                   or trip is not None and d.round_no + remaining > end - 5 - back + 1)
            if due:
                kind = "CONTROL" if phase and not phase.is_day else "RETURN"
                plan.jobs[actor] = RoleJob(actor, kind, None, "HOLD" if route and len(route) == 1 else "TRAVEL",
                                          100, job.created_round if job else d.round_no, end + 60)
                if phase and phase.is_day:
                    plan.mode = "PRE_NIGHT"

    def propose(self, job, command, actor=None, bucket="optional"):
        actor = actor or job.owner
        resources = frozenset({actor, command["controllerId"]} if command["action"] == "attack" else {actor})
        allowed = {job.owner}
        if job.job_type == "CONTROL" and job.target:
            allowed.add(job.target)
        actions = {
            "BUILD_WEAPON": {"move", "build", "use"}, "BUILD_WALL": {"move", "collect", "build", "use"},
            "UPGRADE": {"move", "buy", "use"}, "TASK": {"move", "acceptTask", "submitAnswer", "use"},
            "WALL_SERVICE": {"move", "buy", "use"},
            "HEAL": {"move", "buy", "use"}, "STATION_SERVICE": {"move", "buy", "use"},
            "ECONOMY": {"move", "collect", "sell", "use"}, "RETURN": {"move", "use"},
            "CONTROL": {"move", "attack", "use"},
        }
        return self.arbiter.accept(ActionProposal(actor, command, resources),
                                   JobAuthorization(frozenset(allowed), frozenset(actions.get(job.job_type, ())), bucket))

    def move(self, job, cells, adjacent=True):
        route = self.route(job.owner, cells, adjacent)
        if route and len(route) > 1:
            return self.propose(job, {"action": "move", "targetPos": [dict(x=route[1][0], y=route[1][1])]})
        return False

    def execute_job(self, job, response):
        actor = job.owner
        char = self.world.characters[actor]
        bag = inventory(char) or Counter()
        phase = self.delta.phase
        if self.authority and actor in self.v.busy:
            return
        if bag["Medicine"] and not self.health_ready(char):
            self.propose(job, {"action": "use", "name": "Medicine"})
            return  # Lifesaving action pauses rather than deletes the persistent job.
        if job.job_type in {"RETURN", "CONTROL"}:
            assignment = self.plan.controllers.get(actor)
            if not assignment:
                return
            weapon = self.world.roles.get(job.target)
            if (job.job_type == "CONTROL" and weapon and weapon.get("cooldown", 0) == 0
                    and distance(char["cell"], weapon["cell"]) <= 1):
                targets, after, score = self.defense.attack_plan(weapon)
                if score > 0 and self.propose(job, {"action": "attack", "controllerId": actor,
                                                   "targetPos": [dict(x=x, y=y) for x, y in targets]}, weapon["id"]):
                    self.defense.remaining = after
                    return
            if actor not in self.coverage_relocations and any(distance(char['cell'], w['cell']) <= 1 for w in self.defense.weapons):
                return  # Already covers a weapon: changing controllerId is not moving station.
            self.move(job, {assignment.safe_slot}, adjacent=False)
            return  # Cooldown does not release the job for mining/shopping.
        if not phase or not phase.is_day:
            return
        if job.job_type in {'HEAL', 'STATION_SERVICE'}:
            building = self.world.roles.get(job.target) if job.job_type == 'STATION_SERVICE' else None
            name = 'StationUpgradeVoucher1' if building else 'Medicine'
            bucket = 'station' if building else 'health'
            if self.can_service(actor, building, name, self.plan.budget.available(bucket)):
                self.execute_service(job, building, name, bucket)
            else:
                self.plan.reasons.append('RECOVERY_FUNDS_OR_DEADLINE')
            return
        if job.job_type == 'WALL_SERVICE':
            wall = self.hot_wall()
            if wall is None:
                return
            name = self.wall_item(wall, actor)
            job.target = wall['id']
            if name:
                self.execute_service(job, wall, name, 'wall')
            else:
                self.worker_income(job, response)
            return
        if job.job_type in {"BUILD_WEAPON", "BUILD_WALL"}:
            wall = job.job_type == "BUILD_WALL"
            slots = self.layout.wall_slots if wall else self.layout.weapon_slots
            stones = self.rules.wall_stone_cost
            if wall and (not nonnegative_int(stones) or stones == 0):
                return
            needed = max(0, self.plan.execution_wall_target - self.v.wall_count) * stones if wall else 0
            if wall and (bag["stone"] < stones or job.phase in {"START", "COLLECT"} and bag["stone"] < needed):
                routes = [(len(r), cell, r) for cell in sorted(self.world.zones["stone"])
                          if (r := self.route(actor, {cell}))]
                if not routes:
                    self.plan.reasons.append("stone_unreachable")
                    return
                _, cell, route = min(routes)
                # Optimistic lower bound is enough to prove impossibility, not feasibility.
                geometry = object.__new__(World)
                geometry.occupied = set(self.world.static_occupied)
                long_route = geometry.path(char['cell'], geometry.adjacent_goals({cell}, char['cell']))
                minimum = (len(long_route) - 1 if long_route else 0) + max(0, needed - bag["stone"]) + max(0, self.plan.execution_wall_target - self.v.wall_count)
                while minimum + 5 > 71 - phase.round_in_day and self.plan.execution_wall_target > self.v.wall_count:
                    self.plan.reasons.append("DEADLINE_INFEASIBLE")
                    self.plan.execution_wall_target -= 1
                    needed = max(0, self.plan.execution_wall_target - self.v.wall_count) * stones
                    minimum = (len(long_route) - 1 if long_route else 0) + max(0, needed - bag['stone']) + max(0, self.plan.execution_wall_target - self.v.wall_count)
                if needed == 0:
                    return
                if bag['stone'] >= needed:
                    job.phase = 'BUILD'
                    self.execute_job(job, response)
                    return
                job.target, job.phase = cell, "COLLECT"
                if len(route) == 1:
                    self.propose(job, {"action": "collect", "targetPos": [dict(x=cell[0], y=cell[1])]})
                else:
                    self.move(job, {cell})
                return
            names = {kind: wire for wire, kind in self.rules.weapon_build_names}
            name = "wall" if wall else names.get("rocket")
            if name is None:
                return
            choices = [job.target] if job.target in slots and job.phase == "BUILD" else []
            choices += [cell for cell in slots if cell not in choices]
            for cell in choices:
                if cell in self.world.occupied or cell in self.v.targets:
                    continue
                if wall and cell in {a.safe_slot for a in self.plan.controllers.values()}:
                    continue
                if not self.layout.connected(self.world, cell, [w["cell"] for w in self.defense.weapons]
                                              + ([] if wall else [cell])):
                    continue
                route = self.route(actor, {cell})
                if not route:
                    continue
                job.target, job.phase = cell, "BUILD"
                if len(route) == 1:
                    self.propose(job, {"action": "build", "name": name,
                                       "targetPos": [dict(x=cell[0], y=cell[1])]}, bucket="optional" if wall else "build")
                else:
                    self.move(job, {cell})
                return
            self.plan.reasons.append("build_slots_blocked")
        elif job.job_type == "UPGRADE":
            weapon = next((w for w in self.defense.weapons if level_of(w) == 1), None)
            if not weapon:
                return
            name = "WeaponUpgradeVoucher1"
            job.target = weapon["id"]
            if self.can_service(actor, weapon, name, self.plan.budget.available('upgrade')):
                self.execute_service(job, weapon, name, 'upgrade')
            else:
                self.plan.reasons.append('WEAPON_UPGRADE_FUNDS_OR_DEADLINE')
                self.worker_income(job, response)
        else:
            # Reuse task protocol and economic route logic on an isolated memory.
            # Restrict helper output to this job; re-submit through the arbiter.
            scratch = ActionValidator(self.world, deepcopy(self.memory), self.rules)
            scratch.busy = set(self.world.characters) - {actor}
            scratch.gold = self.plan.budget.free_gold
            scratch_response = empty_response()
            if job.job_type == "TASK":
                TaskPlanner(scratch).run(scratch_response)
            elif job.job_type == "ECONOMY":
                scratch.memory.wall_builder = None  # RoleJob owns this worker's defense reservation.
                scratch.memory.upgrade_trip = None
                EconomyPlanner(scratch).workers()
            for owner, command in scratch.commands.items():
                if self.propose(job, command, owner) and self.authority and job.job_type == 'ECONOMY':
                    self.memory.worker_mines = deepcopy(scratch.memory.worker_mines)
            if job.job_type == "TASK":
                response["prompt"] = scratch_response["prompt"]
                response["executeCmd"] = scratch_response["executeCmd"]

    def worker_income(self, job, response):
        """Only an infeasible service may yield to interruptible income work."""
        if self.world.characters[job.owner].get('roleType') == 'worker':
            paused = RoleJob(job.owner, 'ECONOMY', None, 'FUNDS', 20, job.created_round, job.deadline)
            self.execute_job(paused, response)

    def run(self, actual):
        old_wall_target = self.plan.execution_wall_target
        self.reconcile()
        intended = empty_response()
        if self.authority and (self.delta.task_active or any(j.job_type == 'TASK' for j in self.plan.jobs.values())):
            # One legacy TaskPlanner owns both task state and task channels.
            TaskPlanner(self.v).run(intended)
            if self.delta.task_active:
                self.v.busy.update(a for a, c in self.world.characters.items() if c.get('roleType') == 'pioneer')
        if self.delta.phase and not self.delta.phase.is_day:
            # Keep the existing target scorer. Only controller assignment changes.
            fireable = [w for w in self.defense.weapons if w.get('cooldown', 0) == 0
                        and self.defense.attack_plan(w)[2] > 0]
            healing = {a for a, c in self.world.characters.items()
                       if (inventory(c) or Counter())['Medicine'] and not self.health_ready(c)}
            healing.update(self.v.busy)
            for weapon, actor in self.adjacent_matching(weapons=fireable, excluded=healing).items():
                job = self.plan.jobs.get(actor)
                if job and job.job_type == 'CONTROL':
                    job.target = weapon
        for job in sorted(self.plan.jobs.values(), key=lambda j: (-j.priority, j.owner)):
            if self.authority and job.job_type == 'TASK':
                continue
            self.execute_job(job, intended)
        intended["roleCommandMap"] = self.v.commands
        self.intended_response = intended
        if self.authority:
            actual = intended
        matching = self.adjacent_matching()
        physical_matching = self.adjacent_matching(ready_only=False)
        ready = len(physical_matching)
        wall_hp = {r['id']: r['health'] for r in self.world.roles.values() if r.get('roleType') == 'wall'}
        self.state.metrics = {
            "round": self.delta.round_no, "gold": self.delta.gold,
            "station_hp": [b.get("health") for b in self.defense.stations],
            "actors_alive": len(self.world.characters), "weapons_alive": len(self.defense.weapons),
            "weapon_levels": sorted((level_of(w) or 0 for w in self.defense.weapons), reverse=True),
            "walls": sum(r.get("roleType") == "wall" for r in self.world.roles.values()),
            "wall_hp": [r.get("health") for r in self.world.roles.values() if r.get("roleType") == "wall"],
            "wall_count": len(wall_hp), "wall_total_hp": sum(wall_hp.values()), "wall_hp_by_id": wall_hp,
            "wall_current_hp_total": sum(wall_hp.values()), "wall_max_hp_total": self.wall_totals()[1],
            "wall_level_counts": dict(Counter(level_of(self.world.roles[a]) for a in wall_hp)),
            "controller_health": {a: {'hp': self.world.characters[a]['health'], 'max_hp': max_health(self.world.characters[a])}
                                  for a in self.plan.controllers},
            "controller_health_ready": {a: self.health_ready(self.world.characters[a]) for a in self.plan.controllers},
            "wall_destroyed_since_night_start": None,  # Missing IDs do not identify cause of disappearance.
            "wall_ids_missing_since_night_start": sorted(self.state.night_start_walls - set(wall_hp))
            if self.delta.phase and not self.delta.phase.is_day and self.state.night_start_walls is not None else None,
            "actors_hp": {a: c.get('health') for a, c in self.world.characters.items()},
            "ready_weapon_count": sum(w.get('cooldown', 0) == 0 for w in self.defense.weapons),
            "adjacent_controller_matching_size": ready,
            "ready_weapon_matching_size": len(matching),
            "controllers_available": ready,
            "actual_fire_commands": sum(c["action"] == "attack" for c in actual["roleCommandMap"].values()),
            "associated_failures": sum(v is False for v in self.delta.feedback["results"].values()) if self.delta.continuous else None,
        }
        levels = self.state.metrics["weapon_levels"]
        snapshot = {'wall_current_hp': sum(wall_hp.values()), 'wall_max_hp': self.wall_totals()[1],
                    'weapon_level': levels}
        phase = self.delta.phase
        if phase and self.state.day_start.get('day') != phase.day:
            self.state.day_start = dict(day=phase.day, **{k: v if phase.round_in_day == 1 else None for k, v in snapshot.items()})
        self.state.metrics["day1_benchmark_met"] = (self.delta.phase is not None and self.delta.phase.day == 1 and
            sum(w.get("roleType") == "rocket" for w in self.defense.weapons) == 3
            and len(levels) == 3 and levels >= [2, 1, 1]
            and self.state.metrics["walls"] >= 8 and len(self.world.characters) == 3 and ready == 3)
        def safe(commands):
            return {a: {k: v for k, v in c.items() if k in {"action", "controllerId", "targetPos", "num"}
                        or k == "name" and v in USABLE | MINERALS | WEAPONS | {"wall"}
                        | {wire for wire, _ in self.rules.weapon_build_names}}
                    for a, c in commands.items()}
        actual_commands = actual["roleCommandMap"]
        report = {"round": self.delta.round_no, "mode": self.plan.mode,
                  "scope": "day1_to_day3_policy_then_hold_day3_targets",
                  "strategy_mode": "defense" if self.authority else "shadow",
                  "authority": "defense_with_legacy_task" if self.authority else "legacy",
                  "defense_target": {"weapon_target": 3, "weapon_level_target": self.plan.weapon_level_target,
                                     "wall_target": self.plan.execution_wall_target, "controllers_target": 3,
                                     "benchmark_wall_target": self.plan.benchmark_wall_target,
                                     "execution_wall_target": self.plan.execution_wall_target,
                                     "unmet_wall_target": self.plan.unmet_wall_target,
                                     "wall_total_hp_experimental_target": self.plan.wall_hp_target},
                  "jobs": {a: {"owner": j.owner, "job_type": j.job_type, "phase": j.phase,
                               "target": j.target, "deadline": j.deadline}
                           for a, j in self.plan.jobs.items()},
                  "controllers": [{"weapon_id": next((w for w, c in matching.items() if c == a.controller), None), "controller_id": a.controller,
                                   "safe_slot": a.safe_slot,
                                   "assignment_status": (
                                       "task_unavailable" if self.delta.task_active and
                                       self.world.characters[a.controller].get("roleType") == "pioneer" else
                                       "at_slot" if self.world.characters[a.controller]["cell"] == a.safe_slot else
                                       "adjacent" if any(distance(self.world.characters[a.controller]["cell"], w['cell']) <= 1
                                                          for w in self.defense.weapons) else "return_required")}
                                  for a in self.plan.controllers.values()],
                  "budget": {"observed_gold": self.plan.budget.observed_gold,
                             "staged_gold": self.plan.budget.staged_gold,
                             "reserved_gold": dict(self.plan.budget.reserved_gold),
                             "free_gold": self.plan.budget.free_gold},
                  "intended": safe(self.v.commands), "actual": safe(actual_commands),
                  "divergence": sorted(a for a in set(self.v.commands) | set(actual_commands)
                                       if self.v.commands.get(a) != actual_commands.get(a)),
                  "channels": {k: {"intended": bool(intended[k]), "actual": bool(actual[k]),
                                    "different": intended[k] != actual[k]} for k in ("prompt", "executeCmd")},
                  "reasons": sorted(set(self.plan.reasons)), "metrics": self.state.metrics}
        report["divergence"] = {"intended": report["intended"], "actual": report["actual"],
                                "divergent_actor_ids": report["divergence"]}
        report["wall_target_changed"] = {
            "old": old_wall_target, "new": self.plan.execution_wall_target,
            "reason": [r for r in report["reasons"] if r in {
                "DEADLINE_INFEASIBLE", "NEW_DAY"}]
            if old_wall_target != self.plan.execution_wall_target else [],
        }
        report["pre_night"] = {
            "active": self.plan.mode == "PRE_NIGHT",
            "return_deadlines": {a: row["return_deadline"] for a, row in self.return_diagnostics.items()},
            "estimated_return_costs": self.return_diagnostics,
        }
        pioneers = [a for a, c in self.world.characters.items() if c.get("roleType") == "pioneer"]
        pioneer = pioneers[0] if len(pioneers) == 1 else None
        task_estimate = self.return_diagnostics.get(pioneer, {})
        report["task"] = {"pioneer_job": report["jobs"].get(pioneer),
                          "estimated_finish": task_estimate.get("estimated_finish")
                          if task_estimate.get("job_type") == "TASK" else None,
                          "return_deadline": task_estimate.get("return_deadline")}
        report['task'].update(self.memory.task_diagnostics)
        report['defense_target'].update(wall_max_hp_target=self.policy.capacity_target(self.plan.day),
                                        wall_max_hp_stretch=self.policy.night3_stretch if self.plan.day >= 3 else None,
                                        controller_health_ratio=self.policy.controller_health_ratio)
        report['defense_growth'] = ({**{k + '_start': self.state.day_start.get(k) for k in snapshot},
                                    **{k + '_end': v for k, v in snapshot.items()},
                                    'station_hp': self.state.metrics['station_hp'],
                                    'controller_hp': self.state.metrics['controller_health']}
                                   if phase and phase.round_in_day == 70 else None)
        report['readiness_unmet'] = [name for name, unmet in (
            ('WALL_CURRENT_HP', sum(wall_hp.values()) < self.plan.wall_hp_target),
            ('WALL_MAX_HP', self.wall_totals()[1] is None or self.wall_totals()[1] < self.policy.capacity_target(self.plan.day)),
            ('WEAPON_LEVELS', len(levels) < 3 or levels < list(self.plan.weapon_level_target)),
            ('CONTROLLER_HEALTH', len(self.plan.controllers) < 3 or not all(self.state.metrics['controller_health_ready'].values()))) if unmet]
        return self.state, report
