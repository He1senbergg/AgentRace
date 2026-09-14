"""V3 survival policy: observed inventory, persistent trips and batch construction.

The HTTP/transaction/legality/task protocol layers are deliberately reused.
Policy thresholds are experiments, not additional game rules. This module does
not pretend to simulate the private judger's robot AI or task grading.
"""
from collections import Counter, deque
from itertools import product
from .actions import ActionValidator, empty_response
from .defense import ShadowDefensePlanner
from .model import MINERALS, UPGRADES, WEAPONS, World, building_ring, distance, inventory, level_of, max_health, neighbors, nonnegative_int, station_cells, positive_health
from .task_news import TaskPlanner, task_options

class SurvivalPlanner:
    """One mutable observation transaction, with small jobs carried in memory."""

    revision = "v3.1-reviewed-fix"

    def __init__(self, world, memory, delta, rules):
        self.world, self.memory, self.delta, self.rules = (world, memory, delta, rules)
        self.characters = {a: c for a, c in world.characters.items() if positive_health(c.get('health'))}
        self.v = ActionValidator(world, memory, rules)
        self.defense = ShadowDefensePlanner(self.v)
        self.phase = delta.phase
        self.state = getattr(memory, 'survival', None)
        if self.state is None:
            self.state = dict(jobs={}, slots={}, samples={}, stalled={}, last_round=None, last_spend=None, last_asset_change=None, assets=None)
            memory.survival = self.state
        self.jobs = self.state['jobs']
        # Material ownership survives temporary courier/medicine job changes.
        self.wall_reservations = self.state.setdefault('wall_reservations', {})
        self.decisions = {}
        self.events = []
        self.claimed = set()
        self.return_slots = {}
        bases = [b for b in self.defense.stations if positive_health(b.get('health')) and level_of(b)]
        self.base = bases[0] if len(bases) == 1 else None
        self.walls = [r for r in world.roles.values() if r.get('roleType') == 'wall' and positive_health(r.get('health')) and level_of(r)]
        self.weapons = self.defense.weapons
        self.wall_target = min(18, (8, 12, 16, 18)[min(self.phase.day, 4) - 1]) if self.phase else 8
        self.static = object.__new__(World)
        self.static.occupied = set(world.static_occupied)
        self._paths = {}
        self._connected = {}
        self.weapon_slots, self.wall_slots = self.layout()
        self.observe()

    def note(self, actor, reason):
        self.decisions[actor] = reason

    def observe(self):
        """Only changes in the next observation count as progress/verification."""
        alive = set(self.characters)
        for actor in list(self.wall_reservations):
            if actor not in alive or self.v.wall_count >= self.wall_target:
                self.wall_reservations.pop(actor, None)
        for actor in list(self.jobs):
            if actor not in alive:
                del self.jobs[actor]
                self.events.append(dict(event='owner_missing', actor=actor))
        for actor, char in self.characters.items():
            bag = inventory(char)
            sample = (char['cell'], tuple(sorted((bag or Counter()).items())))
            previous = self.state['samples'].get(actor)
            action = self.delta.feedback.get('actions', {}).get(actor, {})
            same = self.delta.continuous and previous == sample and (action.get('action') == 'move')
            self.state['stalled'][actor] = self.state['stalled'].get(actor, 0) + 1 if same else 0
            self.state['samples'][actor] = sample
            if self.state['stalled'][actor] >= 3:
                self.jobs.pop(actor, None)
                self.state['slots'].pop(actor, None)
                self.events.append(dict(event='stalled_trip_released', actor=actor))
        self.state['samples'] = {a: s for a, s in self.state['samples'].items() if a in alive}
        self.state['slots'] = {a: s for a, s in self.state['slots'].items() if a in alive}
        assets = tuple(sorted(((r['id'], level_of(r), r.get('health')) for r in self.world.roles.values() if r.get('roleType') in WEAPONS | {'wall', 'station'})))
        if assets != self.state.get('assets'):
            self.state['last_asset_change'] = self.delta.round_no
        self.state['assets'] = assets
        if self.delta.continuous:
            for actor, c in self.delta.feedback.get('actions', {}).items():
                if c.get('action') == 'buy' or (c.get('action') == 'build' and c.get('name') != 'wall'):
                    if self.delta.feedback.get('results', {}).get(actor) is True:
                        self.state['last_spend'] = self.delta.round_no - 1
        self.state['last_round'] = self.delta.round_no

    def layout(self):
        if not self.base:
            return ((), ())
        anchor = self.base['cell']
        center = (2 * anchor[0] + 1, 2 * anchor[1] - 1)
        sign = 1 if center[0] < 40 else -1

        def transform(offset):
            return ((center[0] + sign * offset[0]) // 2, (center[1] + sign * offset[1]) // 2)
        ring = building_ring(anchor, 1)
        # Rear, compact battery. Left/right deployment is an exact 180-degree mirror.
        primary = [transform(p) for p in ((-3, 1), (-1, 3), (1, 3))]
        weapons = tuple((p for p in primary if p in ring)) + tuple(sorted(ring - set(primary)))
        walls = building_ring(anchor, 2)
        # Two rear exits stay open permanently; transit cells are never sold as wall capacity.
        gates = {transform((-5, 1)), transform((-1, 5))}
        ranked = sorted(walls - gates, key=lambda p: (-sign * (2 * p[0] - center[0] - (2 * p[1] - center[1])), abs(2 * p[0] - center[0]) + abs(2 * p[1] - center[1]), p))
        return (weapons, tuple(ranked))

    def path(self, start, cells, adjacent=True, static=False):
        cells = frozenset(cells)
        geometry = self.static if static else self.world
        reserved = frozenset() if static else frozenset(self.v.targets)
        key = (start, cells, adjacent, static, reserved)
        if key not in self._paths:
            goals = geometry.adjacent_goals(cells, start) if adjacent else set(cells)
            self._paths[key] = geometry.path(start, goals, reserved)
        return self._paths[key]

    def route(self, actor, cells, adjacent=True, static=False):
        return self.path(self.characters[actor]['cell'], cells, adjacent, static)

    def send(self, actor, command, reason):
        if self.v.add(actor, command):
            self.note(actor, reason)
            return True
        self.note(actor, 'action_rejected:' + reason)
        # A later return-home note must not erase evidence of a rejected plan.
        self.events.append(dict(event='action_rejected', actor=actor, reason=reason, command=dict(command)))
        return False

    def move(self, actor, cells, reason, adjacent=True):
        route = self.route(actor, cells, adjacent)
        if route and len(route) > 1:
            return self.send(actor, dict(action='move', targetPos=[dict(x=route[1][0], y=route[1][1])]), reason)
        self.note(actor, 'at_destination:' + reason if route else 'route_blocked:' + reason)
        return False

    def matching(self, weapons=None, actors=None):
        """Maximum-cardinality current-position matching, independent of cooldown."""
        weapons = self.weapons if weapons is None else weapons
        actors = list(self.characters) if actors is None else list(actors)
        by_actor = {}

        def augment(w, seen):
            for a in sorted(actors):
                if a in seen or distance(self.characters[a]['cell'], w['cell']) > 1:
                    continue
                seen.add(a)
                if a not in by_actor or augment(by_actor[a], seen):
                    by_actor[a] = w
                    return True
            return False
        for w in sorted(weapons, key=lambda w: w['id']):
            augment(w, set())
        return {w['id']: a for a, w in by_actor.items()}

    def assign_return_slots(self):
        """Joint distinct weapon, character AND cell assignment; no greedy collisions."""
        chars = sorted(self.characters)
        active = self.delta.task_active
        chars = [a for a in chars if not (active and self.characters[a]['roleType'] == 'pioneer')]
        choices = []
        for w in sorted(self.weapons, key=lambda w: w['id']):
            options = [None]
            for actor in chars:
                candidates = []
                for cell in neighbors(w['cell']):
                    route = self.path(self.characters[actor]['cell'], {cell}, False, True)
                    if not route:
                        continue
                    # Forecast a return through static geometry, execute against dynamic occupancy later.
                    risk = self.defense.exposure(cell)
                    rear = 0
                    if self.base:
                        sign = 1 if self.base['cell'][0] < 20 else -1
                        rear = sign * (cell[0] - cell[1])
                    kept = self.state['slots'].get(actor) == cell
                    candidates.append((risk, len(route) - 1, not kept, rear, cell))
                for risk, steps, changed, rear, cell in sorted(candidates)[:3]:
                    options.append((actor, cell, steps, risk, changed, rear, w['id']))
            choices.append(options)
        best_key, best = (None, [])
        for combo in product(*choices):
            selected = [x for x in combo if x]
            if len({x[0] for x in selected}) != len(selected) or len({x[1] for x in selected}) != len(selected):
                continue
            key = (-len(selected), sum((x[3] for x in selected)), max((x[2] for x in selected), default=0), sum((x[2] for x in selected)), sum((x[4] for x in selected)), sum((x[5] for x in selected)))
            if best_key is None or key < best_key:
                best_key, best = (key, selected)
        self.return_slots = {x[0]: x[1] for x in best}
        self.state['slots'].update(self.return_slots)

    def return_cost(self, actor, start=None):
        start = start or self.characters[actor]['cell']
        if actor in self.return_slots:
            route = self.path(start, {self.return_slots[actor]}, False, True)
        elif self.weapons:
            route = self.path(start, {w['cell'] for w in self.weapons}, True, True)
        elif self.base:
            route = self.path(start, station_cells(self.base['cell']), True, True)
        else:
            return 0
        return len(route) - 1 if route else None

    def fits(self, actor, visits, margin=4):
        """Trips include EVERY action, travel and an assigned return; no expected income."""
        if not self.phase or not self.phase.is_day:
            return False
        cursor = self.characters[actor]['cell']
        cost = 0
        for cells, actions in visits:
            route = self.path(cursor, cells, True, True)
            if not route:
                return False
            cursor, cost = (route[-1], cost + len(route) - 1 + actions)
        back = self.return_cost(actor, cursor)
        return back is not None and cost + back + margin <= 71 - self.phase.round_in_day

    def return_due(self, actor):
        back = self.return_cost(actor)
        return back is None or not self.phase or (not self.phase.is_day) or (back + 4 >= 71 - self.phase.round_in_day)

    def return_home(self, actor):
        slot = self.return_slots.get(actor)
        if slot is not None:
            self.move(actor, {slot}, 'return_to_battery', adjacent=False)
        elif self.base:
            self.move(actor, station_cells(self.base['cell']), 'return_to_base')
        else:
            self.note(actor, 'base_missing')

    def construction_safe(self, cell):
        """All observed friendly characters must retain a route out, not just some turret neighbour."""
        key = (cell, frozenset(self.v.targets))
        if key in self._connected:
            return self._connected[key]
        build_cells = {tuple((c['targetPos'][0]['x'], c['targetPos'][0]['y'])) for c in self.v.commands.values() if c['action'] == 'build'}
        blocked = set(self.world.static_occupied) | build_cells | {cell}
        outside = {(x, y) for x in range(41) for y in range(32) if x in (0, 40) or y in (0, 31)} - blocked
        reached = set(outside)
        queue = deque(outside)
        while queue:
            for p in neighbors(queue.popleft()):
                if p not in blocked and p not in reached:
                    reached.add(p)
                    queue.append(p)
        ok = all((c['cell'] in reached for c in self.characters.values()))
        ok = ok and all((any((p in reached for p in neighbors(w['cell']))) for w in self.weapons))
        self._connected[key] = ok
        return ok

    def build_weapon(self, actor):
        if self.v.weapon_count >= 3 or self.v.gold < 25:
            return False
        names = {kind: wire for wire, kind in self.rules.weapon_build_names}
        counts = Counter((w['roleType'] for w in self.weapons))
        for c in self.v.commands.values():
            if c['action'] == 'build':
                counts[dict(self.rules.weapon_build_names).get(c['name'])] += 1
        kind = 'rocket' if counts['rocket'] < 2 else 'railgun'
        wire = names.get(kind) or names.get('rocket') or next(iter(names.values()), None)
        if wire is None:
            return False
        old = self.jobs.get(actor, {})
        slots = list(self.weapon_slots)
        target = old.get('cell')
        if old.get('kind') == 'weapon' and target in slots:
            slots.remove(target)
            slots.insert(0, target)
        other = {j.get('cell') for a, j in self.jobs.items() if a != actor and j.get('kind') == 'weapon'}
        for cell in slots:
            if cell in self.world.occupied or cell in self.v.targets or cell in other:
                continue
            route = self.route(actor, {cell})
            if not route or not self.construction_safe(cell):
                continue
            if not self.fits(actor, [({cell}, 1)]):
                continue
            self.jobs[actor] = dict(kind='weapon', cell=cell)
            if len(route) == 1:
                return self.send(actor, dict(action='build', name=wire, targetPos=[dict(x=cell[0], y=cell[1])]), 'build_weapon')
            return self.move(actor, {cell}, 'build_weapon_travel')
        return False

    def wall_candidate(self, actor):
        old = self.jobs.get(actor, {})
        slots = list(self.wall_slots)
        target = old.get('cell')
        if old.get('kind') == 'wall' and target in slots:
            slots.remove(target)
            slots.insert(0, target)
        reserved = {j.get('cell') for a, j in self.jobs.items() if a != actor and j.get('kind') == 'wall'}
        for cell in slots:
            if cell in self.world.occupied or cell in self.v.targets or cell in reserved:
                continue
            if self.route(actor, {cell}, static=True):
                return cell
        return None

    def build_walls(self, actor):
        missing = self.wall_target - self.v.wall_count
        stones = self.rules.wall_stone_cost
        if missing <= 0 or not nonnegative_int(stones) or stones == 0:
            return False
        char = self.characters[actor]
        bag = inventory(char)
        if bag is None:
            return False
        target = self.wall_candidate(actor)
        if target is None:
            self.note(actor, 'no_connected_wall_slot')
            return False
        old = self.jobs.get(actor, {})
        job = old if old.get('kind') == 'wall' else dict(kind='wall', stage='quarry')
        job['cell'] = target
        self.jobs[actor] = job
        have = bag['stone'] // stones
        # A quarry visit has a fixed batch. Do not turn back after the first stone.
        if job.get('stage') == 'build' and have == 0:
            job['stage'] = 'quarry'
        quota = min(missing, job.get('quota', min(8, missing)))
        self.wall_reservations[actor] = quota * stones
        if have >= quota or (have and job.get('stage') == 'build'):
            job['stage'] = 'build'
        if job.get('stage') == 'quarry':
            capacity = char.get('backPackCapability', 100)
            space = capacity - sum(bag.values()) if nonnegative_int(capacity) else 0
            remaining = max(0, min(quota * stones - bag['stone'], space))
            candidates = []
            for mine in sorted(self.world.zones['stone']):
                route = self.route(actor, {mine})
                if not route:
                    continue
                for amount in range(remaining, 0, -1):
                    # At most an eight-wall batch; reserve extra placement travel (3 per wall).
                    total = have + amount // stones
                    if self.fits(actor, [({mine}, amount), ({target}, max(1, 3 * total))]):
                        candidates.append((len(route), mine, amount))
                        break
            if candidates:
                _, mine, amount = min(candidates)
                job['quota'] = min(quota, have + max(1, amount // stones))
                self.wall_reservations[actor] = job['quota'] * stones
                if self.v.near(char, {mine}):
                    return self.send(actor, dict(action='collect', targetPos=[dict(x=mine[0], y=mine[1])]), 'wall_batch_quarry')
                return self.move(actor, {mine}, 'wall_batch_quarry_travel')
            if not have:
                self.note(actor, 'wall_quarry_unreachable_or_deadline')
                return False
            job['stage'] = 'build'
        if not self.fits(actor, [({target}, 1)]):
            self.note(actor, 'wall_delivery_deadline')
            return False
        if not self.construction_safe(target):
            self.note(actor, 'wall_would_trap_actor')
            return False
        if self.v.near(char, {target}):
            return self.send(actor, dict(action='build', name='wall', targetPos=[dict(x=target[0], y=target[1])]), 'wall_batch_build')
        return self.move(actor, {target}, 'wall_batch_deliver')

    def service_candidates(self):
        """Ordered live deficits. Upgrades do not stop permanently at level two."""
        candidates = []
        if self.base:
            level = level_of(self.base)
            if level and level < 3:
                emergency = self.base['health'] < 0.65 * max_health(self.base)
                desired = 2 if self.phase.day <= 2 else 3
                if emergency or (level < desired and self.phase.day >= 2):
                    candidates.append((0 if emergency else 30, self.base, f'StationUpgradeVoucher{level}'))
        for w in self.weapons:
            level = level_of(w)
            if level and level < 3:
                if level == 1:
                    priority = 20 if w['roleType'] == 'rocket' else 25
                else:
                    priority = 35 if w['roleType'] == 'rocket' else 45
                # A full-health L2->L3 is not allowed to starve the opening's affordable L1 upgrades.
                candidates.append((priority, w, f'WeaponUpgradeVoucher{level}'))
        # Wall count first: buying +500 HP must not displace several 1-stone walls.
        for wall in self.walls:
            level = level_of(wall)
            maximum = max_health(wall)
            if level is None or maximum is None:
                continue
            if wall['health'] < maximum * 0.55:
                candidates.append((40, wall, 'WallFixer'))
            elif self.v.wall_count >= min(self.wall_target, 12) and level < 3 and (len(self.weapons) == 3) and all((level_of(w) == 3 for w in self.weapons)) and (level_of(self.base) == 3):
                candidates.append((55, wall, f'WallUpgradeVoucher{level}'))
        return sorted(candidates, key=lambda x: (x[0], x[1]['id'], x[2]))

    def delivery_fits(self, actor: str, route: list) -> bool:
        """Budget the executable route, one use action, and the assigned return.

        Paid goods do not need the extra margin used for speculative purchases.
        An adjacent use still costs a turn; it is not permission to miss dusk.
        """
        if not route or self.phase is None:
            return False
        if not self.phase.is_day:
            return len(route) == 1
        back = self.return_cost(actor, route[-1])
        return back is not None and len(route) + back <= 71 - self.phase.round_in_day

    def held_delivery(self, actor):
        if actor in self.v.busy or self.phase is None:
            return False
        char = self.characters[actor]
        bag = inventory(char) or Counter()
        old = self.jobs.get(actor, {})
        candidates = []
        items = [(name, kinds, required) for name, (kinds, required) in sorted(UPGRADES.items()) if bag[name]]
        if bag['WallFixer']:
            items.append(('WallFixer', {'wall'}, None))
        for name, kinds, required in items:
            for target in self.world.roles.values():
                if (target.get('roleType') not in kinds or not positive_health(target.get('health'))
                        or target['id'] in self.claimed or target['cell'] in self.v.modified):
                    continue
                if required is not None and level_of(target) != required:
                    continue
                if name == 'WallFixer' and (max_health(target) is None or target['health'] >= max_health(target)):
                    continue
                # Dynamic routing prevents a blocked old target from hiding a
                # different, actually executable delivery. No claim before send.
                route = self.route(actor, {target['cell']})
                if not route:
                    continue
                if not self.delivery_fits(actor, route):
                    self.events.append(dict(event='delivery_deferred', actor=actor, target=target['id'],
                                            item=name, reason='return_deadline'))
                    continue
                candidates.append((target['id'] != old.get('target'), len(route), name, target['id'], target, route))
        for _, _, name, _, target, route in sorted(candidates, key=lambda x: x[:4]):
            if len(route) == 1:
                command = dict(action='use', name=name, targetPos=[dict(x=target['cell'][0], y=target['cell'][1])])
                reason = 'apply_observed_item'
            else:
                command = dict(action='move', targetPos=[dict(x=route[1][0], y=route[1][1])])
                reason = 'deliver_observed_item'
            if self.send(actor, command, reason):
                self.jobs[actor] = dict(kind='service', target=target['id'], item=name, stage='deliver')
                self.claimed.add(target['id'])
                return True
        return False

    def rescue_base(self) -> bool:
        """Immediate, already-owned base upgrade; ordinary maintenance stays last.

        65% is the existing procurement emergency threshold, not a game rule.
        Never send a controller travelling during the night for this exception.
        """
        if (self.base is None or level_of(self.base) not in (1, 2)
                or self.base['health'] >= 0.65 * max_health(self.base)
                or self.base['cell'] in self.v.modified or self.base['id'] in self.claimed):
            return False
        name = f"StationUpgradeVoucher{level_of(self.base)}"
        available = [a for a in self.characters if a not in self.v.busy]
        ready = [w for w in self.weapons if w.get('cooldown', 0) == 0
                 and w['cell'] not in self.v.modified and self.defense.attack_plan(w)[2] > 0]
        carriers = [a for a in available if (inventory(self.characters[a]) or Counter())[name]
                    and self.v.near(self.characters[a], {self.base['cell']})]
        # Prefer a spare controller, retaining as many fireable guns as possible.
        carriers.sort(key=lambda a: (-len(self.matching(ready, [b for b in available if b != a])),
                                     -self.characters[a]['health'], a))
        for actor in carriers:
            command = dict(action='use', name=name, targetPos=[dict(x=self.base['cell'][0], y=self.base['cell'][1])])
            if self.send(actor, command, 'rescue_base_upgrade'):
                self.claimed.add(self.base['id'])
                self.jobs[actor] = dict(kind='service', target=self.base['id'], item=name, stage='deliver')
                self.events.append(dict(event='base_rescue', actor=actor, target=self.base['id'],
                                        observed_health=self.base['health'], item=name))
                return True
        return False

    def procure(self, actor, emergency_only=False):
        char = self.characters[actor]
        bag = inventory(char)
        if bag is None:
            return False
        capacity = char.get('backPackCapability', 100 if char['roleType'] == 'worker' else 40)
        if not nonnegative_int(capacity) or sum(bag.values()) >= capacity:
            return False
        old = self.jobs.get(actor, {})
        candidates = self.service_candidates()
        # Keep an affordable delivery destination. Unfunded jobs never seize a worker.
        if old.get('kind') == 'service':
            candidates.sort(key=lambda x: (x[0] == 0, x[1]['id'] == old.get('target')), reverse=True)
        for priority, target, name in candidates:
            if emergency_only and priority != 0:
                continue
            if target['id'] in self.claimed:
                continue
            # A paid voucher already carried by any live owner covers one live deficit.
            held = sum(((inventory(c) or Counter())[name] for c in self.characters.values()))
            ordered = sum((c.get('num', 1) for c in self.v.commands.values() if c['action'] == 'buy' and c.get('name') == name))
            uncovered = sum((n == name for _, _, n in candidates)) - held - ordered
            if uncovered <= 0:
                continue
            price = self.v.prices.get(name)
            build_reserve = max(0, 3 - self.v.weapon_count) * 25
            funds = max(0, self.v.gold - build_reserve)
            if price is None or price > funds:
                continue
            if not self.fits(actor, [(self.world.zones['weaponShop'], 1), ({target['cell']}, 1)]):
                continue
            # At the shop, consolidate identical vouchers for distinct live deficits.
            count = 1
            if price > 0 and self.v.near(char, self.world.zones['weaponShop']):
                eligible = sum((n == name and t['id'] not in self.claimed for _, t, n in candidates))
                count = min(eligible, uncovered, funds // price, capacity - sum(bag.values()), 3)
            self.jobs[actor] = dict(kind='service', target=target['id'], item=name, stage='procure')
            self.claimed.add(target['id'])
            if self.v.near(char, self.world.zones['weaponShop']):
                return self.send(actor, dict(action='buy', name=name, num=count), 'buy_capital_batch')
            return self.move(actor, self.world.zones['weaponShop'], 'procure_capital_travel')
        return False

    def medicine(self, actor, urgent=False):
        char = self.characters[actor]
        bag = inventory(char) or Counter()
        maximum = max_health(char)
        threat = self.defense.exposure(char['cell'])
        if bag['Medicine'] and (char['health'] < maximum * 0.65 or (threat and char['health'] <= 2 * threat)):
            return self.send(actor, dict(action='use', name='Medicine'), 'heal_controller')
        if not self.phase or not self.phase.is_day:
            return False
        need = max(0, 2 - bag['Medicine'])
        price = self.v.prices.get('Medicine')
        funds = max(0, self.v.gold - max(0, 3 - self.v.weapon_count) * 25)
        # Do not spend the last 20 gold on medicine immediately before a funded voucher purchase.
        job = self.jobs.get(actor, {})
        reserved_price = self.v.prices.get(job.get('item')) if job.get('kind') == 'service' else None
        if char['health'] >= maximum * 0.65:
            if reserved_price is None:
                funded = [self.v.prices[n] for _, _, n in self.service_candidates() if n in self.v.prices and self.v.prices[n] <= funds and (not bag[n])]
                reserved_price = funded[0] if funded else None
            if reserved_price is not None and funds >= reserved_price:
                funds -= reserved_price
        capacity = char.get('backPackCapability', 100 if char['roleType'] == 'worker' else 40)
        if not need or price is None or (not nonnegative_int(capacity)):
            return False
        num = min(need, capacity - sum(bag.values()), funds // price if price else need)
        if num <= 0:
            return False
        near = self.v.near(char, self.world.zones['weaponShop'])
        # Dedicated trip only for a hurt controller; healthy actors stock up opportunistically.
        if not near and (not urgent or char['health'] >= maximum * 0.8):
            return False
        if not self.fits(actor, [(self.world.zones['weaponShop'], 1)], margin=5):
            return False
        if near:
            return self.send(actor, dict(action='buy', name='Medicine', num=num), 'stock_controller_medicine')
        self.jobs[actor] = dict(kind='medicine')
        return self.move(actor, self.world.zones['weaponShop'], 'medicine_travel')

    def reserved_wall_stone(self, actor: str) -> int:
        """Return owned stone reserved for an unfinished batch, not all minerals.

        Keep the reservation separate from job.kind: a temporary service trip
        must not silently turn building materials into saleable income.
        """
        missing = max(0, self.wall_target - self.v.wall_count)
        cost = self.rules.wall_stone_cost
        if not missing or not nonnegative_int(cost) or cost == 0:
            self.wall_reservations.pop(actor, None)
            return 0
        job = self.jobs.get(actor, {})
        if job.get('kind') == 'wall':
            quota = job.get('quota', min(8, missing))
            if not nonnegative_int(quota):
                quota = min(8, missing)
            self.wall_reservations[actor] = min(missing, quota) * cost
        wanted = min(self.wall_reservations.get(actor, 0), missing * cost)
        return min((inventory(self.characters[actor]) or Counter())['stone'], wanted)

    def sell(self, actor, force=False):
        char = self.characters[actor]
        bag = inventory(char) or Counter()
        reserved = self.reserved_wall_stone(actor)
        amounts = {m: bag[m] - (reserved if m == 'stone' else 0)
                   for m in MINERALS if self.v.vendor.get(m, 0) > 0}
        minerals = [m for m in amounts if amounts[m] > 0]
        if not minerals:
            if reserved:
                self.note(actor, 'wall_stone_reserved')
            return False
        if not self.fits(actor, [(self.world.zones['vendor'], len(minerals))], margin=3):
            return False
        near = self.v.near(char, self.world.zones['vendor'])
        old = self.jobs.get(actor, {})
        back = self.return_cost(actor)
        due = back is not None and 71 - self.phase.round_in_day < back + 20
        capacity = char.get('backPackCapability', 100 if char['roleType'] == 'worker' else 40)
        full = nonnegative_int(capacity) and sum(bag.values()) >= capacity
        if not (force or near or full or old.get('kind') == 'sell'
                or old.get('cleanup') == 'sell' or sum(amounts[m] for m in minerals) >= 10 or due):
            return False
        name = max(sorted(minerals), key=lambda m: amounts[m] * self.v.vendor[m])
        if near:
            sent = self.send(actor, dict(action='sell', name=name, num=amounts[name]), 'liquidate_inventory')
        else:
            sent = self.move(actor, self.world.zones['vendor'], 'persistent_sale_trip')
        if sent:
            if old.get('kind') == 'wall' and self.v.wall_count < self.wall_target:
                # Liquidating copper/iron frees quarry space without deleting the batch.
                old['cleanup'] = 'sell'
            else:
                self.jobs[actor] = dict(kind='sell')
        return sent

    def income(self, actor):
        char = self.characters[actor]
        if char['roleType'] != 'worker':
            return self.sell(actor, force=True)
        if self.sell(actor):
            return True
        wall_job = self.jobs.get(actor, {}).get('kind') == 'wall' and self.v.wall_count < self.wall_target
        if wall_job and self.reserved_wall_stone(actor):
            # Keep a carried batch intact while its construction is deferred.
            self.note(actor, 'wall_batch_waiting')
            return False
        bag = inventory(char)
        capacity = char.get('backPackCapability', 100)
        if bag is None or not nonnegative_int(capacity) or sum(bag.values()) >= capacity:
            return False
        options = []
        for mineral in sorted(MINERALS):
            price = self.v.vendor.get(mineral, 0)
            if not price:
                continue
            if any((e.get('resource') == mineral and e.get('harvestable') is False and (e.get('start_day', 99) <= self.phase.day <= e.get('end_day', 0)) for e in self.memory.resource_events)):
                continue
            for mine in sorted(self.world.zones[mineral]):
                route = self.route(actor, {mine})
                if not route:
                    continue
                delivery = self.path(route[-1], self.world.zones['vendor'], True, True)
                if not delivery:
                    continue
                back = self.return_cost(actor, delivery[-1])
                if back is None:
                    continue
                sales = sum((bool(bag[m]) for m in MINERALS - {mineral})) + 1
                overhead = len(route) - 1 + len(delivery) - 1 + sales + back + 4
                batch = min(10, capacity - sum(bag.values()), 71 - self.phase.round_in_day - overhead)
                if batch < 1:
                    continue
                score = price * batch / (len(route) - 1 + batch + len(delivery) - 1 + sales)
                retained = self.memory.worker_mines.get(actor) == (mineral, mine)
                options.append((score * (1.1 if retained else 1), mineral, mine, route))
        if not options:
            return self.sell(actor, force=True)
        _, mineral, mine, route = max(options, key=lambda x: x[:3])
        self.memory.worker_mines[actor] = (mineral, mine)
        if wall_job:
            # With no building material to deliver, temporary funding is useful;
            # it must not erase the quarry assignment or its material ownership.
            self.events.append(dict(event='wall_funding', actor=actor, mineral=mineral))
        else:
            self.jobs[actor] = dict(kind='income', mineral=mineral, cell=mine)
        if len(route) == 1:
            return self.send(actor, dict(action='collect', targetPos=[dict(x=mine[0], y=mine[1])]), 'mine_income')
        return self.move(actor, {mine}, 'mine_income_travel')

    def night(self):
        self.rescue_base()
        for actor, char in sorted(self.characters.items()):
            if actor in self.v.busy:
                continue
            if self.medicine(actor):
                continue
            threat = self.defense.exposure(char['cell'])
            if threat and char['health'] <= max(threat * 3, max_health(char) * 0.35):
                options = [p for p in neighbors(char['cell']) if p not in self.world.occupied and p not in self.v.targets and any((distance(p, w['cell']) <= 1 for w in self.weapons))]
                if options:
                    cell = min(options, key=lambda p: (self.defense.exposure(p), p))
                    if self.defense.exposure(cell) < threat:
                        if self.send(actor, dict(action='move', targetPos=[dict(x=cell[0], y=cell[1])]), 'evade_while_covering_gun'):
                            continue
        available = [a for a in self.characters if a not in self.v.busy]
        choices = []
        for w in self.weapons:
            if w.get('cooldown', 0) != 0 or w['cell'] in self.v.modified or w['id'] in self.v.busy:
                continue
            targets, after, score = self.defense.attack_plan(w)
            if score <= 0:
                continue
            options = [None] + [(w, actor, score) for actor in available if self.v.near(self.characters[actor], {w['cell']})]
            choices.append(options)
        best, best_key = ([], None)
        for combo in product(*choices):
            selected = [x for x in combo if x]
            if len({x[1] for x in selected}) != len(selected):
                continue
            key = (sum((x[2] for x in selected)), len(selected))
            if best_key is None or key > best_key:
                best, best_key = (selected, key)
        for w, actor, _ in sorted(best, key=lambda x: (-x[2], x[0]['id'])):
            targets, after, score = self.defense.attack_plan(w)
            if score > 0 and self.send(w['id'], dict(action='attack', controllerId=actor, targetPos=[dict(x=x, y=y) for x, y in targets]), 'fire_with_matching'):
                self.defense.remaining = after
                self.note(actor, 'control_weapon:' + w['id'])
        self.defense.support()
        # Only unused controllers apply ordinary upgrades/repairs. The bounded
        # base-rescue exception above has already removed its carrier from fire.
        for actor in sorted(self.characters):
            if actor in self.v.busy:
                continue
            if self.held_delivery(actor):
                continue
        for actor in sorted(self.characters):
            if actor not in self.v.busy:
                self.return_home(actor)

    def run(self):
        response = empty_response()
        if self.phase is None or self.base is None:
            return (response, self.report())
        self.assign_return_slots()
        if not self.delta.task_active and self.memory.task:
            self.memory.finish_task()
        if self.delta.task_active:
            TaskPlanner(self.v).run(response)
            for actor, c in self.characters.items():
                if c['roleType'] == 'pioneer':
                    self.v.busy.add(actor)
                    self.note(actor, 'active_task')
        if not self.phase.is_day:
            self.night()
        else:
            # Paid inventory deliveries are recovered independently of yesterday's job table.
            for actor in sorted(self.characters):
                if actor in self.v.busy:
                    continue
                if self.medicine(actor):
                    continue
                if self.held_delivery(actor):
                    continue
                if self.return_due(actor):
                    self.return_home(actor)
            workers = [a for a, c in sorted(self.characters.items()) if c['roleType'] == 'worker']
            for actor in workers:
                if actor not in self.v.busy and (not self.return_due(actor)):
                    self.build_weapon(actor)
            # Idle pioneer is the preferred courier. Active tasks remain exclusively owned by TaskPlanner.
            for actor, char in sorted(self.characters.items()):
                if char['roleType'] != 'pioneer' or actor in self.v.busy or self.return_due(actor):
                    continue
                if self.procure(actor, emergency_only=True):
                    continue
                # A begun affordable supply trip is not discarded for another task halfway through.
                if self.jobs.get(actor, {}).get('kind') == 'service' and self.procure(actor):
                    continue
                task_planner = TaskPlanner(self.v)
                feasible = any((route and task_planner.can_finish(char, route) for _, cells in task_options(self.v) for route in [self.route(actor, cells)]))
                if feasible:
                    task_planner.run(response)
                if actor not in self.v.busy:
                    if not self.procure(actor) and not self.sell(actor, force=True):
                        # An idle courier must vacate another controller's assigned slot now,
                        # not wait until its own much shorter return deadline.
                        self.return_home(actor)
            # One dedicated batch builder; the other worker maintains a cash-producing pipeline.
            available = [a for a in workers if a not in self.v.busy and (not self.return_due(a))]
            builder = None
            if available and self.v.wall_count < self.wall_target:
                builder = min(available, key=lambda a: (self.jobs.get(a, {}).get('kind') != 'wall', -(inventory(self.characters[a]) or Counter())['stone'], a))
            for actor in available:
                if self.procure(actor, emergency_only=True):
                    continue
                if self.medicine(actor, urgent=True):
                    continue
                if actor == builder and self.build_walls(actor):
                    continue
                if self.procure(actor):
                    continue
                if self.income(actor):
                    continue
                self.return_home(actor)
        response['roleCommandMap'] = self.v.commands
        return (response, self.report())

    def report(self):
        metrics = dict(round=self.delta.round_no, gold=self.delta.gold, station_hp=[b['health'] for b in self.defense.stations], actors_alive=len(self.characters), weapons_alive=len(self.weapons), weapon_levels=sorted((level_of(w) or 0 for w in self.weapons), reverse=True), walls=len(self.walls), wall_count=len(self.walls), wall_hp=[w['health'] for w in self.walls], wall_total_hp=sum((w['health'] for w in self.walls)), wall_max_hp_total=sum((max_health(w) or 0 for w in self.walls)), actors_hp={a: c['health'] for a, c in self.characters.items()}, controllers_available=len(self.matching()), actual_fire_commands=sum((c['action'] == 'attack' for c in self.v.commands.values())))
        return dict(round=self.delta.round_no, scope='survival_v3', policy_revision=self.revision, strategy_mode='survival', mode='DAY' if self.phase and self.phase.is_day else 'NIGHT', metrics=metrics, jobs={a: dict(j) for a, j in self.jobs.items()}, wall_reservations=dict(self.wall_reservations), decisions=dict(self.decisions), controllers={a: list(s) for a, s in self.return_slots.items()}, events=list(self.events), defense_target=dict(wall_target=self.wall_target, weapon_target=3, weapon_ceiling=3), observed_gold=self.delta.gold, unspent_after_commands=self.v.gold, last_confirmed_spend=self.state.get('last_spend'), last_observed_asset_change=self.state.get('last_asset_change'))
