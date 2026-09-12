"""AgentRace strategy; mechanically extracted from frozen V2.2."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from .model import (
    CanonicalLayout,
    DefensePolicy,
    ProductionPolicy,
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
    BlockReason,
    CapitalState,
    CapitalGoal,
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
        # Experiments run in defense and shadow intentions; legacy output stays frozen.
        self.defense = ShadowDefensePlanner(self.v, capacity_target=lambda day: self.capacity_target(),
                                            growth_mode=True)
        self.return_diagnostics = {}
        self.coverage_relocations = set()
        self.policy = policy or DefensePolicy()
        self.production = ProductionPolicy()
        self.authority = authority
        self.intended_response = empty_response()

    def capacity_target(self):
        return self.production.capacity_target(self.plan.day, self.state.growth_basis)

    def observe_growth(self):
        """Consume normalized phase/continuity and observed assets, never raw feedback."""
        phase = self.delta.phase
        if not phase:
            return
        walls = {w['id']: w['health'] for w in self.world.roles.values() if w.get('roleType') == 'wall'}
        stations = {w['id']: w['health'] for w in self.defense.stations}
        actors = set(self.world.characters)
        previous = self.state.night_growth
        if phase.is_day:
            if previous and previous['day'] < phase.day and self.state.growth_basis.get('day') != previous['day']:
                previous['complete'] = bool(previous['complete'] and self.delta.continuous
                                            and phase.round_in_day == 1 and previous.get('last_round_in_day') == 130)
                if self.delta.continuous and phase.round_in_day == 1:
                    previous['wall_hp_loss'] += sum(max(0, hp - walls.get(a, 0)) for a, hp in previous['last_walls'].items())
                    previous['station_hp_loss'] += sum(max(0, hp - stations.get(a, 0)) for a, hp in previous['last_stations'].items())
                    previous['missing_wall_ids'] = sorted(set(previous['missing_wall_ids']) | (set(previous['last_walls']) - set(walls)))
                    previous['missing_controller_ids'] = sorted(set(previous['missing_controller_ids']) | (set(previous['last_actors']) - actors))
                self.state.growth_basis = dict(previous)
            return
        if not previous or previous['day'] != phase.day:
            previous = dict(day=phase.day, previous_capacity=self.wall_totals()[1], wall_hp_loss=0,
                            station_hp_loss=0, missing_wall_ids=[], missing_controller_ids=[],
                            complete=phase.round_in_day == 71, last_walls=walls, last_stations=stations,
                            last_actors=sorted(actors))
            self.state.night_growth = previous
        elif self.delta.continuous:
            previous['wall_hp_loss'] += sum(max(0, hp - walls.get(a, 0)) for a, hp in previous['last_walls'].items())
            previous['station_hp_loss'] += sum(max(0, hp - stations.get(a, 0)) for a, hp in previous['last_stations'].items())
            previous['missing_wall_ids'] = sorted(set(previous['missing_wall_ids']) | (set(previous['last_walls']) - set(walls)))
            previous['missing_controller_ids'] = sorted(set(previous['missing_controller_ids']) | (set(previous['last_actors']) - actors))
        else:
            previous['complete'] = False
        previous.update(last_walls=walls, last_stations=stations, last_actors=sorted(actors),
                        last_round_in_day=phase.round_in_day)

    def wall_slot(self, job):
        reserved = {j.target for a, j in self.plan.jobs.items() if a != job.owner and j.job_type == 'BUILD_WALL'
                    and isinstance(j.target, tuple)}
        forbidden = set(self.world.static_occupied) | reserved | {a.safe_slot for a in self.plan.controllers.values()}
        geometry = object.__new__(World)
        geometry.occupied = set(self.world.static_occupied) | reserved
        planned_layout = replace(self.layout, static_blockers=self.layout.static_blockers | reserved)
        start = self.world.characters[job.owner]['cell']
        choices = []
        # Keep a valid reservation, then prefer canonical front slots over worker distance.
        for priority, cell in enumerate(self.layout.wall_slots):
            if cell in forbidden or not planned_layout.connected(self.world, cell, [w['cell'] for w in self.defense.weapons]):
                continue
            route = geometry.path(start, geometry.adjacent_goals({cell}, start))
            if route:
                choices.append((cell != job.target, priority, len(route), cell))
        if choices:
            job.target = min(choices)[-1]
            return job.target
        return None

    def task_feasible(self, actor):
        assignment = self.plan.controllers.get(actor)
        slot = assignment.safe_slot if assignment else self.world.characters[actor]['cell']
        trip = self.completion_trip(RoleJob(actor, 'TASK', None, 'START', 50, self.delta.round_no, self.delta.round_no), slot)
        return bool(trip and self.delta.phase and self.delta.phase.is_day
                    and sum(trip) + 5 <= 71 - self.delta.phase.round_in_day and any(task_options(self.v)))

    def goal_complete(self, goal):
        target = self.world.roles.get(goal.target)
        if target is None:
            return False
        value = target.get('health', 0) if goal.item in {'Medicine', 'WallFixer'} else level_of(target)
        return value is not None and value >= goal.target_value

    def purchase_goals(self):
        goals = self.plan.capital_goals
        for goal in goals.values():
            if self.goal_complete(goal):
                goal.state, goal.block_reason = 'DONE', None
            elif goal.target not in self.world.roles:
                goal.state, goal.block_reason = 'BLOCKED', 'TARGET_MISSING'
        def add(kind, target, item, bucket, value):
            key = f'{kind}:{target["id"]}:{value}'
            if key not in goals:
                goals[key] = CapitalGoal(key, kind, target['id'], item, bucket, value)
            elif goals[key].state == 'DONE' and not self.goal_complete(goals[key]):
                goals[key].state = 'DEFICIT'  # A new observed damage episode, not an assumed failed use.
                goals[key].last_action = goals[key].last_action_round = None
            return goals[key]
        for actor, job in self.plan.jobs.items():
            if job.job_type == 'HEAL':
                char = self.world.characters[actor]
                goal = add('HEAL', char, 'Medicine', 'health', self.policy.controller_health_ratio * max_health(char))
                goal.assigned_actor = actor
        if self.station_service:
            actor, base = self.station_service
            add('STATION_SERVICE', base, 'StationUpgradeVoucher1', 'station', 2).assigned_actor = actor
        wall = self.hot_wall()
        if wall:
            item = self.wall_item(wall)
            if item:
                add('WALL_SERVICE', wall, item, 'wall', max_health(wall) if item == 'WallFixer' else level_of(wall) + 1)
        needed = max(0, sum(n >= 2 for n in self.plan.weapon_level_target)
                     - sum((level_of(w) or 0) >= 2 for w in self.defense.weapons))
        required = set()
        for weapon in sorted((w for w in self.defense.weapons if level_of(w) == 1), key=lambda w: w['id'])[:needed]:
            goal = add('UPGRADE', weapon, 'WeaponUpgradeVoucher1', 'upgrade', 2)
            required.add(goal.goal_id)
            if goal.block_reason == 'SUPERSEDED':
                goal.state, goal.block_reason = 'DEFICIT', None
        for goal in goals.values():
            if goal.goal_type == 'UPGRADE' and goal.state != 'DONE' and goal.goal_id not in required:
                goal.state, goal.block_reason, goal.assigned_actor = 'BLOCKED', 'SUPERSEDED', None
        return [g for g in goals.values() if g.state != 'DONE' and g.block_reason != 'SUPERSEDED' and g.target in self.world.roles]

    def schedule_production(self, end):
        """Day-only allocation. Purchase ownership persists; RETURN is re-evaluated daily."""
        old = self.plan.jobs
        jobs = {}
        for actor, char in sorted(self.world.characters.items()):
            if char.get('roleType') == 'pioneer':
                kind = 'TASK_LOCK' if self.delta.task_active else 'TASK' if self.task_feasible(actor) else 'LOGISTICS'
                jobs[actor] = old[actor] if not self.delta.task_active and actor in old and old[actor].job_type == 'HEAL' else RoleJob(actor, kind, None, 'START', 50, self.delta.round_no, end)
            elif actor in old and old[actor].job_type in {'HEAL', 'STATION_SERVICE'}:
                jobs[actor] = old[actor]
        # Retain healthy-controller healing goals and existing target observations.
        self.plan.jobs = {**old, **jobs}
        goals = self.purchase_goals()
        self.plan.jobs = jobs
        missing = max(0, 3 - len(self.defense.weapons))
        workers = [a for a, c in sorted(self.world.characters.items()) if c.get('roleType') == 'worker']
        if missing:
            for actor in workers:
                if actor not in jobs and missing:
                    jobs[actor] = RoleJob(actor, 'BUILD_WEAPON', None, 'START', 85, self.delta.round_no, end)
                    missing -= 1
        assigned = set(a for a, j in jobs.items() if j.job_type not in {'LOGISTICS', 'HEAL', 'STATION_SERVICE'})
        priority = {'HEAL': 95, 'STATION_SERVICE': 90, 'WALL_SERVICE': 80, 'UPGRADE': 60}
        for goal in sorted(goals, key=lambda g: (-priority[g.goal_type], g.goal_id)):
            candidates = []
            for actor, char in sorted(self.world.characters.items()):
                if actor in assigned or goal.goal_type == 'HEAL' and actor != goal.target:
                    continue
                if actor in jobs and jobs[actor].job_type in {'HEAL', 'STATION_SERVICE'} and jobs[actor].job_type != goal.goal_type:
                    continue
                building = None if goal.item == 'Medicine' else self.world.roles[goal.target]
                bag = inventory(char) or Counter()
                sellable = sum(bag[m] * self.v.vendor.get(m, 0) for m in MINERALS)
                gap = max(0, self.v.prices.get(goal.item, 0) - self.delta.gold)
                # Pioneers cannot mine; require an item or a gap covered by current inventory.
                if (char.get('roleType') == 'pioneer' and not bag[goal.item]
                        and gap and sellable < gap):
                    continue
                capacity = char.get('backPackCapability', 100 if char.get('roleType') == 'worker' else 40)
                full = not nonnegative_int(capacity) or sum(bag.values()) >= capacity
                liquidation = not bag[goal.item] and bool(gap and sellable >= gap or full and sellable > 0)
                route, deadline, duration, back, reason = self.service_route_status(actor, building, goal.item, liquidation)
                if not route or not deadline:
                    continue
                candidates.append((not bool(bag[goal.item]), self.delta.gold + sellable < self.v.prices.get(goal.item, float('inf')),
                                   actor != goal.assigned_actor, duration, char.get('roleType') != 'pioneer', actor))
            if not candidates:
                goal.assigned_actor = None
                continue
            actor = min(candidates)[-1]
            assigned.add(actor)
            goal.assigned_actor = actor
            kind = 'LOGISTICS' if self.world.characters[actor].get('roleType') == 'pioneer' else goal.goal_type
            previous = old.get(actor)
            created = previous.created_round if previous and previous.target == goal.target else self.delta.round_no
            jobs[actor] = RoleJob(actor, kind, goal.target, goal.state, priority[goal.goal_type], created, end)
        for actor in workers:
            if actor in jobs:
                continue
            previous = old.get(actor)
            if self.v.wall_count < self.plan.execution_wall_target:
                job = previous if previous and previous.job_type == 'BUILD_WALL' else RoleJob(actor, 'BUILD_WALL', None, 'START', 70, self.delta.round_no, end)
                jobs[actor] = job
                if self.wall_slot(job) is None:
                    job.phase = 'PAUSED'
            else:
                jobs[actor] = RoleJob(actor, 'ECONOMY', None, 'START', 20, self.delta.round_no, end)

    def forced_cash_in(self, job):
        scratch = ActionValidator(self.world, deepcopy(self.memory), self.rules)
        scratch.busy = set(self.world.characters) - {job.owner}
        scratch.targets = set(self.v.targets)
        if EconomyPlanner(scratch).cash_in(self.world.characters[job.owner], force=True):
            command = scratch.commands.get(job.owner)
            return bool(command and self.propose(job, command))
        return False

    def execute_capital(self, job, goal, response):
        building = None if goal.item == 'Medicine' else self.world.roles.get(goal.target)
        row = self.capital_status(goal.goal_id, goal.goal_type, building, goal.item, job.owner, goal.bucket, {job.job_type})
        goal.block_reason = row['block_reason']
        bag = inventory(self.world.characters[job.owner]) or Counter()
        if self.goal_complete(goal):
            goal.state, goal.block_reason = 'DONE', None
            return
        if goal.last_action_round == self.delta.round_no:
            return
        if goal.last_action == 'use' and not bag[goal.item]:
            goal.state, goal.block_reason = 'VERIFY', 'VERIFICATION_PENDING'
            return  # Consumed item with unchanged target is not permission to buy another.
        if not row['route_feasible'] or not row['deadline_feasible']:
            goal.state = 'BLOCKED'
            # Existing V2.2 immediate repair fallback, preserving the growth goal.
            if goal.goal_type == 'WALL_SERVICE' and building and building['health'] < max_health(building) and self.can_service(job.owner, building, 'WallFixer', self.plan.budget.available('wall')):
                self.execute_service(job, building, 'WallFixer', 'wall')
            return
        if bag[goal.item]:
            goal.state = 'APPLY' if building is None or self.v.near(self.world.characters[job.owner], {building['cell']}) else 'DELIVER'
            accepted = self.execute_service(job, building, goal.item, goal.bucket)
        elif row['funding_gap'] and row['sellable_inventory_value'] >= row['funding_gap']:
            goal.state = 'LIQUIDATE'
            accepted = self.forced_cash_in(job)
        elif row['funding_gap']:
            goal.state = 'FUNDING'
            self.worker_income(job, response)
            if job.owner in self.v.commands:
                goal.last_action, goal.last_action_round = self.v.commands[job.owner]['action'], self.delta.round_no
            return
        elif row['block_reason'] == 'INVENTORY_FULL':
            if not row['sellable_inventory_value']:
                goal.state = 'BLOCKED'
                return
            goal.state = 'LIQUIDATE'
            accepted = self.forced_cash_in(job)
        elif row['block_reason']:
            goal.state = 'BLOCKED'
            return
        else:
            goal.state = 'PROCURE'
            accepted = self.execute_service(job, building, goal.item, goal.bucket)
        if accepted:
            command = self.v.commands[job.owner]
            goal.last_action, goal.last_action_round = command['action'], self.delta.round_no
            if command['action'] == 'use':
                goal.state = 'VERIFY'
                goal.block_reason = 'VERIFICATION_PENDING'
            elif command['action'] == 'buy':
                goal.state = 'PROCURE'  # Inventory in the next observation is the acknowledgment.
        else:
            goal.state, goal.block_reason = 'BLOCKED', 'ACTION_REJECTED'
        job.phase = goal.state

    def service_route_status(self, actor, building, name, liquidation=False):
        """Separate geometry from money/deadline; static forecasts are not execution evidence."""
        char = self.world.characters[actor]
        bag = inventory(char) or Counter()
        geometry = object.__new__(World)
        geometry.occupied = set(self.world.static_occupied)
        cursor, cost = char['cell'], 0
        visits = []
        if liquidation:
            visits.append((self.world.zones['vendor'], sum(bag[m] > 0 and self.v.vendor.get(m, 0) > 0 for m in MINERALS), BlockReason.VENDOR_UNREACHABLE))
        if not bag[name]:
            visits.append((self.world.zones['weaponShop'], 1, BlockReason.SHOP_UNREACHABLE))
        if building:
            visits.append(({building['cell']}, 0, BlockReason.TARGET_UNREACHABLE))
        for cells, actions, reason in visits:
            path = geometry.path(cursor, geometry.adjacent_goals(cells, cursor))
            if not path:
                return False, False, None, None, reason
            cursor, cost = path[-1], cost + len(path) - 1 + actions
        cost += 1
        assignment = self.plan.controllers.get(actor)
        goals = {assignment.safe_slot} if assignment else geometry.adjacent_goals({w['cell'] for w in self.defense.weapons}, cursor)
        back = geometry.path(cursor, goals) if goals else [cursor]
        if not back:
            return False, False, cost, None, BlockReason.RETURN_UNREACHABLE
        phase = self.delta.phase
        feasible = bool(phase and phase.is_day and cost + len(back) - 1 + 5 <= 71 - phase.round_in_day)
        return True, feasible, cost, len(back) - 1, None if feasible else BlockReason.DEADLINE

    def capital_status(self, goal_id, goal_type, building, name, actor, bucket, allowed_jobs):
        cost = self.v.prices.get(name)
        char = self.world.characters.get(actor)
        bag = (inventory(char) or Counter()) if char else Counter()
        held = bool(bag[name])
        gold = self.delta.gold
        gap = max(0, (cost or 0) - gold) if not held else 0
        sellable = sum(bag[m] * self.v.vendor.get(m, 0) for m in MINERALS)
        blockers = []
        route, deadline, duration, back = None, None, None, None
        if char is None:
            blockers.append(BlockReason.NO_ACTOR)
        else:
            job = self.plan.jobs.get(actor)
            if actor in self.v.busy or self.delta.task_active and char.get('roleType') == 'pioneer':
                blockers.append(BlockReason.ACTOR_BUSY)
            elif job is None or job.job_type not in allowed_jobs:
                blockers.append(BlockReason.WRONG_JOB_STATE)
            capacity = char.get('backPackCapability', 100 if char.get('roleType') == 'worker' else 40)
            full = not nonnegative_int(capacity) or sum(bag.values()) >= capacity
            route, deadline, duration, back, why = self.service_route_status(
                actor, building, name, not held and bool(gap and sellable >= gap or full and sellable > 0))
            if why:
                blockers.append(why)
            if not held and full:
                blockers.append(BlockReason.INVENTORY_FULL)
        if not held:
            if cost is None:
                blockers.append(BlockReason.ITEM_UNAVAILABLE)
            elif gap:
                blockers.append(BlockReason.NEED_LIQUIDATION if sellable >= gap else BlockReason.FUNDING_GAP)
            elif self.plan.budget and cost > self.plan.budget.available(bucket):
                blockers.append(BlockReason.BUDGET_BLOCKED)
        stage = CapitalState.DELIVER if held else CapitalState.FUNDED if cost is not None and not gap else CapitalState.DEFICIT
        if blockers:
            stage = CapitalState.LIQUIDATE if blockers == [BlockReason.NEED_LIQUIDATION] else CapitalState.BLOCKED
        return dict(goal_id=goal_id, goal_type=goal_type, target=building['id'] if building else actor,
                    item=name, cost=cost, observed_gold=gold, sellable_inventory_value=sellable,
                    funded_cash=held or cost is not None and gold >= cost, funding_gap=gap,
                    assigned_actor=actor, actor_role=char.get('roleType') if char else None,
                    route_feasible=route, deadline_feasible=deadline, executable_now=not blockers,
                    state=stage.value, block_reason=blockers[0].value if blockers else None,
                    block_reasons=[b.value for b in blockers], remaining_cost=duration, return_cost=back)

    def capital_diagnostics(self):
        rows = []
        for goal in self.plan.capital_goals.values():
            actor = goal.assigned_actor
            job = self.plan.jobs.get(actor)
            building = None if goal.item == 'Medicine' else self.world.roles.get(goal.target)
            row = self.capital_status(goal.goal_id, goal.goal_type, building, goal.item, actor, goal.bucket,
                                      {goal.goal_type, 'LOGISTICS'})
            row['target'] = goal.target
            if goal.state == 'DONE':
                row.update(state='DONE', block_reason=None, block_reasons=[], executable_now=False)
            elif building is None and goal.item != 'Medicine':
                row.update(state='BLOCKED', block_reason='TARGET_MISSING', executable_now=False)
            rows.append(row)
        # Construction goals remain visible even when no owner or route is available.
        for kind, target, count, cost in [('BUILD_WEAPON', 3, len(self.defense.weapons), 25),
                                          ('BUILD_WALL', self.plan.benchmark_wall_target, self.v.wall_count, 0)]:
            if count >= target:
                continue
            owners = [j for j in self.plan.jobs.values() if j.job_type == kind] or [None]
            for job in owners:
                actor = job.owner if job else None
                char = self.world.characters.get(actor)
                assignment = self.plan.controllers.get(actor)
                trip = self.completion_trip(job, assignment.safe_slot if assignment else char['cell']) if char else None
                deadline = bool(trip and self.delta.phase and self.delta.phase.is_day and sum(trip) + 5 <= 71 - self.delta.phase.round_in_day)
                reason = 'NO_ACTOR' if not job else 'TARGET_UNREACHABLE' if trip is None else 'DEADLINE' if not deadline else 'FUNDING_GAP' if self.delta.gold < cost else None
                rows.append(dict(goal_id=f'{kind}:{actor}', goal_type=kind, target=target, cost=cost,
                                 observed_gold=self.delta.gold, sellable_inventory_value=0, funded_cash=self.delta.gold >= cost,
                                 funding_gap=max(0, cost-self.delta.gold), assigned_actor=actor,
                                 actor_role=char.get('roleType') if char else None, route_feasible=trip is not None,
                                 deadline_feasible=deadline, executable_now=reason is None,
                                 state='BLOCKED' if reason else 'FUNDED', block_reason=reason,
                                 stone_cost=self.rules.wall_stone_cost if kind == 'BUILD_WALL' else None))
        return rows

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
        geometry.occupied.update(j.target for a, j in self.plan.jobs.items() if a != job.owner
                                 and j.job_type == 'BUILD_WALL' and isinstance(j.target, tuple))
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
            bag = inventory(self.world.characters[job.owner]) or Counter()
            stones = self.rules.wall_stone_cost
            if not nonnegative_int(stones) or stones == 0:
                return None
            collect = max(0, stones - bag['stone'])
            if collect and not visit(self.world.zones['stone'], collect):
                return None
            cell = self.wall_slot(job)
            if cell is None or not visit({cell}):
                return None
            geometry.occupied.add(cell)
        elif job.job_type == "BUILD_WEAPON":
            cells = {job.target} if job.target in self.layout.weapon_slots else set(self.layout.weapon_slots)
            if not visit(cells):
                return None
        elif job.job_type in {'WALL_SERVICE', 'HEAL', 'STATION_SERVICE', 'UPGRADE', 'LOGISTICS'}:
            goal = next((g for g in self.plan.capital_goals.values() if g.assigned_actor == job.owner and g.state != 'DONE'), None)
            if goal:
                building = None if goal.item == 'Medicine' else self.world.roles.get(goal.target)
                bag = inventory(self.world.characters[job.owner]) or Counter()
                gap = max(0, self.v.prices.get(goal.item, 0) - self.delta.gold)
                sellable = sum(bag[m] * self.v.vendor.get(m, 0) for m in MINERALS)
                route, deadline, duration, back, reason = self.service_route_status(job.owner, building, goal.item, bool(gap and sellable >= gap))
                return (duration, back) if route else None
            cost += 1
        elif job.job_type == "TASK":
            trips = []
            for task, cells in task_options(self.v):
                timeout = task.get('timeoutRounds')
                route = geometry.path(cursor, geometry.adjacent_goals(cells, cursor))
                back = geometry.path(route[-1], {slot}) if route else None
                if nonnegative_int(timeout) and route and back:
                    trips.append((len(route) + timeout, len(back) - 1))
            if trips:
                return min(trips, key=lambda t: sum(t))
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
        if sum(w['health'] for w in walls) < self.plan.wall_hp_target or sum(max_health(w) for w in walls) < self.capacity_target():
            return next((w for w in sorted(walls, key=lambda w: (-self.state.wall_damage.get(w['id'], 0), w['id']))
                         if level_of(w) < 3), None)
        return None

    def wall_item(self, wall, actor=None):
        current, capacity = self.wall_totals()
        growth = capacity is not None and (capacity < self.capacity_target() or current < self.plan.wall_hp_target)
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
        self.plan.reasons.append('WALL_SERVICE_BLOCKED')
        return None

    def reconcile(self):
        self.observe_growth()
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
        plan.wall_hp_target = self.capacity_target()
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
                   (capacity < self.capacity_target() or current_hp < plan.wall_hp_target))
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
                plan.jobs[actor] = RoleJob(actor, 'HEAL', actor, 'RECOVER', 95, d.round_no, end)
            if self.station_service:
                actor, base = self.station_service
                if actor not in healers:
                    plan.jobs[actor] = RoleJob(actor, 'STATION_SERVICE', base['id'], 'RECOVER', 90, d.round_no, end)
            self.schedule_production(end)
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
                job.phase = 'PAUSED'
                plan.reasons.append('DEADLINE_INFEASIBLE')
                trip = (0, len(route) - 1)
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
)
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
            "UPGRADE": {"move", "buy", "use", "sell", "collect"}, "TASK": {"move", "acceptTask", "submitAnswer", "use"},
            "WALL_SERVICE": {"move", "buy", "use", "sell", "collect"},
            "LOGISTICS": {"move", "buy", "use", "sell"}, "TASK_LOCK": set(),
            "HEAL": {"move", "buy", "use", "sell"}, "STATION_SERVICE": {"move", "buy", "use", "sell"},
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
        if job.job_type == 'TASK_LOCK':
            return
        goal = next((g for g in self.plan.capital_goals.values() if g.assigned_actor == actor
                     and g.target == job.target and g.state != 'DONE'), None)
        if goal and job.job_type in {'UPGRADE', 'WALL_SERVICE', 'HEAL', 'STATION_SERVICE', 'LOGISTICS'}:
            self.execute_capital(job, goal, response)
            return
        if job.job_type == 'LOGISTICS':
            self.forced_cash_in(job)
            return
        if job.job_type in {'HEAL', 'STATION_SERVICE'}:
            building = self.world.roles.get(job.target) if job.job_type == 'STATION_SERVICE' else None
            name = 'StationUpgradeVoucher1' if building else 'Medicine'
            bucket = 'station' if building else 'health'
            if self.can_service(actor, building, name, self.plan.budget.available(bucket)):
                self.execute_service(job, building, name, bucket)
            else:
                self.plan.reasons.append('RECOVERY_BLOCKED')
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
            needed = stones if wall else 0
            if wall:
                if self.v.wall_count >= self.plan.execution_wall_target:
                    return
                assignment = self.plan.controllers.get(actor)
                slot = assignment.safe_slot if assignment else char['cell']
                trip = self.completion_trip(job, slot)
                if trip is None or sum(trip) + 5 > 71 - phase.round_in_day:
                    job.phase = 'PAUSED'
                    self.plan.reasons.append('DEADLINE' if trip else 'TARGET_UNREACHABLE')
                    return
            if wall and bag['stone'] < needed:
                routes = [(len(r), cell) for cell in sorted(self.world.zones['stone']) if (r := self.route(actor, {cell}))]
                if not routes:
                    self.plan.reasons.append('TARGET_UNREACHABLE')
                    return
                length, cell = min(routes)
                job.phase = 'COLLECT'  # target remains the reserved construction slot.
                if length == 1:
                    self.propose(job, {'action': 'collect', 'targetPos': [dict(x=cell[0], y=cell[1])]})
                else:
                    self.move(job, {cell})
                return
            names = {kind: wire for wire, kind in self.rules.weapon_build_names}
            if wall:
                name = "wall"
            else:
                order = ("rocket", "rocket", "railgun")
                preferred = order[min(self.v.weapon_count, len(order) - 1)]
                name = names.get(preferred) or names.get("rocket")
            if name is None:
                return
            choices = [job.target] if job.target in slots else []
            if not wall:
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
                self.plan.reasons.append('WEAPON_UPGRADE_BLOCKED')
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
        capital_diagnostics = self.capital_diagnostics()
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
            if self.authority and job.job_type in {'TASK', 'TASK_LOCK'}:
                continue
            self.execute_job(job, intended)
        for goal in self.plan.capital_goals.values():
            job = self.plan.jobs.get(goal.assigned_actor)
            command = self.v.commands.get(goal.assigned_actor, {})
            if command.get('action') == 'use' and command.get('name') == goal.item and goal.goal_type == 'HEAL':
                goal.state, goal.block_reason = 'VERIFY', 'VERIFICATION_PENDING'
                goal.last_action, goal.last_action_round = 'use', self.delta.round_no
            if job and job.job_type in {'UPGRADE', 'WALL_SERVICE', 'HEAL', 'STATION_SERVICE', 'LOGISTICS'}:
                job.phase = goal.state
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
            Counter(w.get("roleType") for w in self.defense.weapons) == Counter(rocket=2, railgun=1)
            and len(levels) == 3 and levels >= [2, 1, 1]
            and self.state.metrics["walls"] >= 8 and len(self.world.characters) == 3 and ready == 3)
        def safe(commands):
            return {a: {k: v for k, v in c.items() if k in {"action", "controllerId", "targetPos", "num"}
                        or k == "name" and v in USABLE | MINERALS | WEAPONS | {"wall"}
                        | {wire for wire, _ in self.rules.weapon_build_names}}
                    for a, c in commands.items()}
        actual_commands = actual["roleCommandMap"]
        report = {"round": self.delta.round_no, "mode": self.plan.mode,
                  "scope": "v24_e2_e5_experiments",
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
        for row in capital_diagnostics:
            goal = self.plan.capital_goals.get(row['goal_id'])
            if goal:
                command = self.v.commands.get(goal.assigned_actor)
                accepted = (command if command and goal.last_action_round == self.delta.round_no
                            and goal.last_action == command['action'] and goal.state != 'DONE' else None)
                if accepted or goal.state in {'DONE', 'VERIFY'}:
                    row['state'] = goal.state
                    row['block_reason'] = goal.block_reason
                elif goal.block_reason == 'SUPERSEDED':
                    row.update(state='BLOCKED', block_reason='SUPERSEDED')
                if row['state'] in {'DONE', 'VERIFY'} or row['block_reason'] == 'SUPERSEDED' or not row['block_reason']:
                    row['block_reasons'] = [row['block_reason']] if row['block_reason'] else []
                elif row['block_reason'] not in row['block_reasons']:
                    row['block_reasons'].insert(0, row['block_reason'])
                row['executable_now'] = bool(accepted) and row['state'] not in {'DONE', 'VERIFY', 'BLOCKED'}
                row['accepted_action'] = accepted
        report['capital_deployment'] = capital_diagnostics
        report['growth_basis'] = self.state.growth_basis
        report['defense_target'].update(wall_max_hp_target=self.capacity_target(),
                                        wall_max_hp_stretch=self.policy.night3_stretch if self.plan.day >= 3 else None,
                                        controller_health_ratio=self.policy.controller_health_ratio)
        report['defense_growth'] = ({**{k + '_start': self.state.day_start.get(k) for k in snapshot},
                                    **{k + '_end': v for k, v in snapshot.items()},
                                    'station_hp': self.state.metrics['station_hp'],
                                    'controller_hp': self.state.metrics['controller_health']}
                                   if phase and phase.round_in_day == 70 else None)
        report['readiness_unmet'] = [name for name, unmet in (
            ('WALL_CURRENT_HP', sum(wall_hp.values()) < self.plan.wall_hp_target),
            ('WALL_MAX_HP', self.wall_totals()[1] is None or self.wall_totals()[1] < self.capacity_target()),
            ('WEAPON_LEVELS', len(levels) < 3 or levels < list(self.plan.weapon_level_target)),
            ('CONTROLLER_HEALTH', len(self.plan.controllers) < 3 or not all(self.state.metrics['controller_health_ready'].values()))) if unmet]
        return self.state, report
