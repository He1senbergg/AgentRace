"""AgentRace HTTP entry and protocol boundary (AI Spec sections 42–63)."""
from collections import Counter, defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
import argparse
import hashlib
from itertools import product
import json
import logging
import math
import re
import shlex
import sys
import threading
import time

from flask import Flask, g, jsonify, request


# BEGIN PACKAGE IMPORTS
if __package__:
    from .agentrace.model import (
        CHARACTERS, WEAPONS, MINERALS, UPGRADES, SUMMON_ORDERS, USABLE, DEFAULT_STRATEGY_MODE,
        SHADOW_WARN_MS, TOTAL_WARN_MS, valid_position, distance, in_bounds, neighbors,
        station_cells, building_ring, Phase, object_list, position, World, render_map,
        MoveReservations, nonnegative_int, positive_health, level_of, shop_prices, inventory, Rules,
        DefensePolicy, max_health, CanonicalLayout
    )
    from .agentrace.memory import (
        ObservationDelta, RoleJob, ControllerAssignment, Day1Plan, StrategicState, GameMemory
    )
    from .agentrace.actions import (
        empty_response, validate_command_shape, ensure_valid_response, strict_json, ActionValidator,
        BudgetReserve, JobAuthorization, ActionProposal, ActionArbiter
    )
    from .agentrace.economy import (
        EconomyPlanner
    )
    from .agentrace.defense import (
        DefensePlanner, ShadowDefensePlanner
    )
    from .agentrace.task_news import (
        task_options, bounded_text, command_observation, parse_llm_decision, task_discovery_command,
        TaskPlanner, evidence_matches, parse_news_decision, treasure_key, NewsPlanner,
        TreasurePlanner
    )
    from .agentrace.strategy import (
        plan_turn, StrategicPlanner
    )
    from .agentrace.session import (
        GameSession
    )
    from .agentrace import session as _session
else:
    from agentrace.model import (
        CHARACTERS, WEAPONS, MINERALS, UPGRADES, SUMMON_ORDERS, USABLE, DEFAULT_STRATEGY_MODE,
        SHADOW_WARN_MS, TOTAL_WARN_MS, valid_position, distance, in_bounds, neighbors,
        station_cells, building_ring, Phase, object_list, position, World, render_map,
        MoveReservations, nonnegative_int, positive_health, level_of, shop_prices, inventory, Rules,
        DefensePolicy, max_health, CanonicalLayout
    )
    from agentrace.memory import (
        ObservationDelta, RoleJob, ControllerAssignment, Day1Plan, StrategicState, GameMemory
    )
    from agentrace.actions import (
        empty_response, validate_command_shape, ensure_valid_response, strict_json, ActionValidator,
        BudgetReserve, JobAuthorization, ActionProposal, ActionArbiter
    )
    from agentrace.economy import (
        EconomyPlanner
    )
    from agentrace.defense import (
        DefensePlanner, ShadowDefensePlanner
    )
    from agentrace.task_news import (
        task_options, bounded_text, command_observation, parse_llm_decision, task_discovery_command,
        TaskPlanner, evidence_matches, parse_news_decision, treasure_key, NewsPlanner,
        TreasurePlanner
    )
    from agentrace.strategy import (
        plan_turn, StrategicPlanner
    )
    from agentrace.session import (
        GameSession
    )
    from agentrace import session as _session
# END PACKAGE IMPORTS

LOG = logging.getLogger(__name__)
_session.LOG = LOG
# Diagnostics only, not competition rules or decision cutoffs.
app = Flask(__name__)
app.json.ensure_ascii = False


# World geometry: AI Spec sections 3–9, 47–54, 69–70.


# Shared action legality and conservative same-round reservations (§75–76).


SESSION = GameSession()
HTTP_DIAGNOSTIC_LOCK = threading.Lock()
HTTP_DIAGNOSTIC_COUNT = 0


@app.before_request
def trace_request():
    """Trace the first three HTTP exchanges without logging request contents."""
    global HTTP_DIAGNOSTIC_COUNT
    with HTTP_DIAGNOSTIC_LOCK:
        if HTTP_DIAGNOSTIC_COUNT >= 3:
            return
        HTTP_DIAGNOSTIC_COUNT += 1
        g.diagnostic_id = HTTP_DIAGNOSTIC_COUNT
    try:
        LOG.info("[trace_request] 收到HTTP请求 #%s，匹配游戏入口=%s，JSON=%s",
                 g.diagnostic_id, request.endpoint == "process_request", request.is_json)
    except Exception:
        pass  # A failed diagnostic sink must not prevent gameplay dispatch.


@app.after_request
def trace_response(response):
    if hasattr(g, "diagnostic_id"):
        try:
            LOG.info("[trace_response] HTTP响应 #%s，状态=%s，字节数=%s",
                     g.diagnostic_id, response.status_code, response.calculate_content_length())
        except Exception:
            pass  # The session may already have committed this response.
    return response


def callback(json_data):
    return SESSION.handle(json_data)


@app.route("/", methods=["POST"])
def process_request():
    try:
        if not request.is_json:
            raise ValueError("request content type must be JSON")
        data = strict_json(request.get_data().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request must be an object")
        return jsonify(ensure_valid_response(callback(data)))
    except Exception as exc:
        # Exception messages may contain untrusted request data or credentials.
        try:
            LOG.error("[process_request] 请求处理失败: %s", type(exc).__name__)
        except Exception:
            pass  # Error reporting cannot defeat the final protocol fallback.
        return jsonify(empty_response())


def main():
    parser = argparse.ArgumentParser(description="AgentRace HTTP player")
    parser.add_argument("port", type=int)
    parser.add_argument("--strategy-mode", choices=("legacy", "shadow", "defense"), default=DEFAULT_STRATEGY_MODE,
                        help="shadow logs V2 intent and returns legacy; defense explicitly enables defense authority")
    parser.add_argument("--round-origin", type=int, choices=(0, 1), default=None,
                        help="override round origin; otherwise infer from opening observation 0 or 1")
    parser.add_argument("--wall-stone-cost", type=int, default=1,
                        help="confirmed positive stone cost of one wall")
    parser.add_argument("--weapon-build-name", action="append", default=[], metavar="TYPE=NAME",
                        help="confirmed build name, e.g. gatling=gatling; repeat for other types")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.wall_stone_cost is not None and args.wall_stone_cost <= 0:
        parser.error("wall stone cost must be positive")
    names, kinds = {}, set()
    for entry in args.weapon_build_name or [f"{kind}={kind}" for kind in sorted(WEAPONS)]:
        kind, separator, name = entry.partition("=")
        if not separator or kind not in WEAPONS or not name or name == "wall" or name in names or kind in kinds:
            parser.error("weapon build names must be unique TYPE=NAME mappings")
        names[name] = kind
        kinds.add(kind)
    global SESSION
    SESSION = GameSession(origin=args.round_origin, strategy_mode=args.strategy_mode,
                          rules=Rules(args.wall_stone_cost, tuple(names.items())))
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO)
    if not names:
        LOG.warning("[main] 未配置已确认的武器建造名称，自动建造武器已停用")
    if args.round_origin is None:
        LOG.info("[main] 回合起点自动识别：开局0或1；中途接入请配置--round-origin")
    # Keep the SDK positional port; accept judger traffic on all IPv4 interfaces (§43.2).
    app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
