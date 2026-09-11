"""AgentRace session; mechanically extracted from frozen V2.2."""
from copy import deepcopy
import hashlib
import json
import threading
import time
from .model import (
    CHARACTERS,
    DEFAULT_STRATEGY_MODE,
    DefensePolicy,
    MINERALS,
    Rules,
    SHADOW_WARN_MS,
    TOTAL_WARN_MS,
    USABLE,
    WEAPONS,
    World,
    distance,
    inventory,
    object_list,
    position,
    render_map,
    shop_prices
)
from .memory import (
    GameMemory
)
from .actions import (
    ActionValidator,
    empty_response,
    ensure_valid_response
)
from .task_news import (
    command_observation,
    parse_llm_decision
)
from .strategy import (
    StrategicPlanner,
    plan_turn
)
import logging
LOG = logging.getLogger("src.main3")


class GameSession:
    """Atomic in-process planning; transport delivery is not an execution ack."""
    def __init__(self, planner=None, origin=None, rules=None, strategy_mode=DEFAULT_STRATEGY_MODE, policy=None):
        if origin is not None and (type(origin) is not int or origin not in (0, 1)):
            raise ValueError("invalid round origin")
        self.origin = origin
        if strategy_mode not in {"legacy", "shadow", "defense"}:
            raise ValueError("unknown strategy mode")
        self.strategy_mode = strategy_mode
        self.policy = policy or DefensePolicy()
        self.rules = rules or Rules()
        self.planner = planner if planner is not None else lambda w, m: plan_turn(w, m, self.rules)
        self.memory = None
        self.fingerprint = None
        self.response = None
        self.lock = threading.Lock()
        self.diagnostic_turns = 0
        self.diagnostic_failures = 0

    def trace_turn(self, data, world=None, memory=None, response=None, reason=None):
        try:
            self._trace_turn(data, world, memory, response, reason)
        except Exception as exc:
            # Diagnostic failure must not replace a committed gameplay response.
            try:
                LOG.error("[trace_turn] 诊断失败: %s", type(exc).__name__)
            except Exception:
                pass

    def _trace_turn(self, data, world=None, memory=None, response=None, reason=None):
        """Bounded metadata only; called under the session lock for valid turns."""
        self.diagnostic_turns += 1
        errors = object_list(data.get("errors"))
        feedback = data.get("lastRoundRoleActionResults")
        failed = isinstance(feedback, dict) and any(v is False for v in feedback.values())
        exceptional = bool(reason or errors or failed)
        phase = memory.phase if memory else None
        boundary = phase is not None and phase.round_in_day in (1, 70, 71, 130)
        detailed = (self.diagnostic_turns <= 10 or self.diagnostic_turns % 10 == 0 or boundary
                    or exceptional and self.diagnostic_failures < 20)
        if not detailed and world is None:
            return
        if exceptional:
            self.diagnostic_failures += 1

        def number(value):
            return value if type(value) is int and abs(value) < 10**12 else None

        def actor_id(value):
            if type(value) is int:
                return number(value)
            return value if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 20 else None

        our = data.get("teamOur")
        our = our if isinstance(our, dict) else {}
        raw_roles = object_list(our.get("roles"))
        roles = []
        for role in raw_roles[:12]:
            kind = role.get("roleType")
            bag = inventory(role)
            roles.append({"id": actor_id(role.get("id")),
                          "kind": kind if isinstance(kind, str) and kind in CHARACTERS | WEAPONS | {"station", "wall"} else "unknown",
                          "pos": position(role.get("pos")), "health": number(role.get("health")),
                          "backpack_type": type(role.get("backpack")).__name__,
                          "bag_count": sum(bag.values()) if bag is not None else None,
                          "medicine": bag["Medicine"] if bag is not None else None,
                          "minerals": {k: bag[k] for k in sorted(MINERALS)} if bag is not None else None,
                          "capacity": number(role.get("backPackCapability"))})
        commands = []
        for actor, command in list((response or empty_response())["roleCommandMap"].items())[:12]:
            # Do not log taskAnswer, dynamic item names, prompts or sandbox commands.
            commands.append({"id": actor_id(actor), "action": command["action"],
                             "name": command.get("name") if isinstance(command.get("name"), str)
                             and command["name"] in USABLE | MINERALS | WEAPONS | {"wall"} else None,
                             "targetPos": command.get("targetPos"),
                             "controllerId": actor_id(command.get("controllerId")),
                             "num": number(command.get("num"))})
        phase = memory.phase if memory else None
        summary = {"round": number(data.get("roundNo")), "reason": reason,
                   "field_types": {k: type(data.get(k)).__name__ for k in
                                   ("roundNo", "teamOur", "mapInfo", "vendorShopList", "lastRoundRoleActionResults")},
                   "origin": memory.origin if memory else self.origin,
                   "phase": {"day": phase.day, "round": phase.round_in_day, "daytime": phase.is_day} if phase else None,
                   "gold": number(our.get("goldNum")), "roles_total": len(raw_roles), "roles": roles,
                   "recognized_characters": len(world.characters) if world else None,
                   "weapons": sum(isinstance(r.get("roleType"), str) and r["roleType"] in WEAPONS
                                  for r in world.roles.values()) if world else None,
                   "robots": len(world.robots) if world else None,
                   "task": {"active": bool(data.get("phaseTask")),
                            "pending": memory.task.get("pending") if memory and memory.task else None,
                            "deadline": memory.task.get("deadline") if memory and memory.task else None,
                            "expired": memory.task.get("expired") if memory and memory.task else None,
                            "answer_only": memory.task.get("answer_only", False) if memory and memory.task else False,
                            "command_count": memory.task.get("command_count", 0) if memory and memory.task else 0,
                            "command_result": {k: v for k, v in command_observation(data.get("lastCmdResult")).items()
                                               if k != "result"},
                            "llm_type": type(data.get("llmResp")).__name__,
                            "llm_decision_valid": parse_llm_decision(data.get("llmResp")) is not None,
                            "llm_chars": len(data["llmResp"]) if isinstance(data.get("llmResp"), str) else None},
                   "zones": {k: len(world.zones.get(k, ())) for k in
                             ("stone", "iron", "copper", "vendor", "weaponShop")} if world else None,
                   "vendor_prices": {k: shop_prices(data.get("vendorShopList")).get(k) for k in sorted(MINERALS)},
                   "actions": commands, "actions_total": len((response or empty_response())["roleCommandMap"]),
                   "feedback": [{"id": actor_id(k), "success": v if type(v) is bool else None}
                                for k, v in list(feedback.items())[:12]] if isinstance(feedback, dict) else None,
                   "feedback_associated": memory.feedback.get("associated") if memory else False,
                   "error_codes": [number(e.get("errorCode")) for e in errors[:12]],
                   "prompt_chars": len((response or empty_response())["prompt"]),
                   "execute_chars": len((response or empty_response())["executeCmd"])}
        if world:
            outgoing = (response or empty_response())["roleCommandMap"]
            controlled = {c.get("controllerId"): actor_id(actor) for actor, c in outgoing.items()
                          if c.get("action") == "attack"}
            activity = []
            for actor, role in sorted(world.characters.items()):
                command = outgoing.get(actor)
                status = (command["action"] if command else "control_weapon" if actor in controlled
                          else "active_task" if role.get("roleType") == "pioneer" and data.get("phaseTask")
                          else "no_command")
                activity.append({"id": actor_id(actor), "status": status,
                                 "weapon": controlled.get(actor)})
            weapons = []
            for actor, role in sorted(world.roles.items()):
                if isinstance(role.get("roleType"), str) and role["roleType"] in WEAPONS:
                    weapons.append({"id": actor_id(actor), "kind": role["roleType"],
                                    "level": number(role.get("level")),
                                    "cooldown": number(role.get("cooldown")),
                                    "range": number(role.get("attackRange")),
                                    "adjacent": [actor_id(i) for i, r in sorted(world.characters.items())
                                                 if distance(r["cell"], role["cell"]) <= 1]})
            short = {"round": summary["round"], "gold": summary["gold"],
                     "actions": commands, "activity": activity, "weapons": weapons,
                     "robots": summary["robots"], "task": summary["task"],
                     "feedback": summary["feedback"], "errors": summary["error_codes"],
                     "prompt_chars": summary["prompt_chars"], "execute_chars": summary["execute_chars"]}
            LOG.info("[turn] %s", json.dumps(short, ensure_ascii=False, allow_nan=False))
        if not detailed:
            return
        LOG.info("[trace_turn] %s", json.dumps(summary, ensure_ascii=False, allow_nan=False))
        if world and (self.diagnostic_turns == 1 or self.diagnostic_turns % 50 == 0 or boundary):
            LOG.info("[trace_map] round=%s\n%s", number(data.get("roundNo")), render_map(world))

    def handle(self, data):
        processing_started = time.perf_counter()
        if not isinstance(data, dict):
            return empty_response()
        round_no = data.get("roundNo")
        our = data.get("teamOur")
        if type(round_no) is not int or not 0 <= round_no <= 1300 or not isinstance(our, dict):
            with self.lock:
                self.trace_turn(data, reason="invalid_round_or_teamOur")
            return empty_response()
        team_id, side = our.get("teamId"), our.get("type")
        if (type(team_id) not in (str, int) or team_id == ""
                or not isinstance(side, str) or side not in {"challenger", "defender"}):
            with self.lock:
                self.trace_turn(data, reason="invalid_team_identity_or_side")
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
            if reset and current is not None and current.identity[0] == identity[0]:
                # Carry only labelled procedural hints; no pending task, map or quota.
                candidate.task_experience = deepcopy(current.task_experience)
            if candidate.origin == 1 and round_no == 0:
                raise ValueError("round contradicts configured origin")
            world = World(data)
            delta = candidate.observe(world, round_no)
            shadow_memory, shadow_report, shadow_ms = None, None, 0.0
            if self.strategy_mode == "shadow":
                shadow_started = time.perf_counter()
                try:
                    shadow_memory = deepcopy(candidate)
                except Exception as exc:
                    shadow_report = {"round": round_no, "error": type(exc).__name__}
                shadow_ms = (time.perf_counter() - shadow_started) * 1000
            legacy_started = time.perf_counter()
            if self.strategy_mode == 'defense':
                defense = StrategicPlanner(world, candidate, delta, self.rules, self.policy, authority=True)
                candidate.strategic, shadow_report = defense.run(empty_response())
                response = ensure_valid_response(defense.intended_response)
            else:
                response = ensure_valid_response(self.planner(world, candidate))
            legacy_ms = (time.perf_counter() - legacy_started) * 1000
            defense_ms = legacy_ms if self.strategy_mode == 'defense' else 0.0
            if self.strategy_mode == 'defense':
                legacy_ms = 0.0
            active_task = isinstance(data.get("phaseTask"), str) and bool(data["phaseTask"])
            if response["executeCmd"] and not active_task:
                raise ValueError("sandbox command outside task")
            if response["prompt"] and not active_task:
                if not candidate.llm_day_known or candidate.llm_calls_today >= 3:
                    raise ValueError("ordinary LLM quota unavailable")
                candidate.llm_calls_today += 1
            gate = ActionValidator(world, candidate, self.rules)
            for actor, command in response["roleCommandMap"].items():
                if not gate.add(actor, command):
                    raise ValueError("planner produced illegal action")
            candidate.summon_attempts = gate.summons
            # Serialization and copies can fail; finish them before committing.
            json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")
            cached_response = deepcopy(response)
            outgoing = deepcopy(response)
            if shadow_memory is not None:
                shadow_started = time.perf_counter()
                try:
                    strategic, shadow_report = StrategicPlanner(world, shadow_memory, delta, self.rules, self.policy).run(deepcopy(outgoing))
                    json.dumps(shadow_report, ensure_ascii=False, allow_nan=False)
                    candidate.strategic = strategic
                except Exception as exc:
                    # Keep the previous strategic checkpoint, never partial shadow state.
                    shadow_report = {"round": round_no, "error": type(exc).__name__}
                shadow_ms += (time.perf_counter() - shadow_started) * 1000
            candidate.previous_actions = deepcopy(response["roleCommandMap"])
            self.memory, self.fingerprint, self.response = candidate, fingerprint, cached_response
            self.trace_turn(data, world, candidate, outgoing)
            if shadow_report is not None:
                try:
                    shadow_report["strategy_mode"] = self.strategy_mode
                    for key in ("defense_target", "jobs", "controllers", "budget", "divergence",
                                "wall_target_changed", "pre_night", "task"):
                        shadow_report.setdefault(key, None)
                    shadow_report["timing_ms"] = {
                        "legacy": max(0.0, legacy_ms), "shadow": max(0.0, shadow_ms),
                        "defense": max(0.0, defense_ms),
                        "total": max(0.0, (time.perf_counter() - processing_started) * 1000),
                    }
                    LOG.info("[shadow_turn] %s", json.dumps(shadow_report, ensure_ascii=False, allow_nan=False))
                    timing = shadow_report["timing_ms"]
                    if timing["total"] > TOTAL_WARN_MS or timing["shadow"] > SHADOW_WARN_MS:
                        LOG.warning("[shadow_performance] %s", json.dumps({
                            "round": round_no, "timing_ms": timing,
                            "diagnostic_threshold_ms": {"total": TOTAL_WARN_MS, "shadow": SHADOW_WARN_MS}}))
                except Exception:
                    pass  # Logging cannot invalidate an already committed response.
            return outgoing
