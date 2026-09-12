"""Default startup and observational-only instrumentation contracts."""
from copy import deepcopy
from itertools import count
import json
import unittest
from unittest.mock import patch

from src import main3 as main
from src.agentrace import strategy
from src.agentrace import session as session_module
from test_actions import role, state, target
from test_shadow import opening


class InstrumentationTests(unittest.TestCase):
    def test_port_only_cli_preserves_default_session_and_bind(self):
        for port in (1, 9123, 65535):
            with patch.object(main, 'SESSION'), patch.object(main.sys, 'argv', ['main3.py', str(port)]), \
                    patch.object(main.app, 'run') as run, patch.object(main, 'LOG'), \
                    patch.object(main.sys, 'stdout'), patch.object(main.sys, 'stderr'), \
                    patch.object(main.logging, 'basicConfig'):
                main.main()
                self.assertEqual(main.SESSION.strategy_mode, 'defense')
                self.assertIsNone(main.SESSION.origin)
                self.assertEqual(main.SESSION.rules.wall_stone_cost, 1)
                self.assertEqual(dict(main.SESSION.rules.weapon_build_names),
                                 {'gatling': 'gatling', 'railgun': 'railgun', 'rocket': 'rocket'})
                run.assert_called_once_with(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        self.assertEqual(main.DEFAULT_STRATEGY_MODE, 'defense')
        self.assertEqual(main.GameSession().strategy_mode, 'defense')

    def test_fields_timing_and_actual_response_match_explicit_legacy(self):
        data = opening()
        expected = main.GameSession(strategy_mode='legacy').handle(deepcopy(data))
        with self.assertLogs(main.LOG, level='INFO') as logs:
            response = main.GameSession(strategy_mode='shadow').handle(data)
        self.assertEqual(response, expected)
        report = next(json.loads(line.split('[shadow_turn] ', 1)[1]) for line in logs.output if '[shadow_turn] ' in line)
        self.assertEqual(report['strategy_mode'], 'shadow')
        for key in ('defense_target', 'jobs', 'controllers', 'budget', 'timing_ms', 'divergence',
                    'wall_target_changed', 'pre_night', 'task'):
            self.assertIn(key, report)
        self.assertTrue({'weapon_target', 'weapon_level_target', 'wall_target', 'controllers_target',
                         'benchmark_wall_target', 'execution_wall_target', 'unmet_wall_target'} <= set(report['defense_target']))
        self.assertEqual(set(report['budget']), {'observed_gold', 'staged_gold', 'reserved_gold', 'free_gold'})
        for job in report['jobs'].values():
            self.assertTrue({'job_type', 'phase', 'target', 'deadline'} <= set(job))
        self.assertTrue(all(value >= 0 for value in report['timing_ms'].values()))
        self.assertGreaterEqual(report['timing_ms']['total'], report['timing_ms']['legacy'] + report['timing_ms']['shadow'])
        self.assertEqual(report['wall_target_changed']['old'], 8)

    def test_shadow_mutation_exception_and_log_failure_never_change_response(self):
        data = opening()
        expected = main.GameSession(strategy_mode='legacy').handle(deepcopy(data))
        def broken(_planner, response):
            response['roleCommandMap'].clear()
            response['prompt'] = 'must not escape'
            response['executeCmd'] = 'must not escape'
            raise RuntimeError('instrumentation failed')
        with patch.object(strategy.StrategicPlanner, 'run', broken), \
                patch.object(session_module.LOG, 'info', side_effect=RuntimeError('log failed')), \
                patch.object(session_module.LOG, 'error', side_effect=RuntimeError('error logger failed')):
            session = main.GameSession(strategy_mode='shadow')
            self.assertEqual(session.handle(data), expected)
            self.assertEqual(session.handle(data), expected)
            self.assertEqual(session.memory.previous_actions, expected['roleCommandMap'])

    def test_performance_warning_is_diagnostic_only(self):
        data = opening()
        expected = main.GameSession(strategy_mode='legacy').handle(deepcopy(data))
        with patch.object(session_module.time, 'perf_counter', side_effect=count(0, 1)), \
                patch.object(session_module.LOG, 'warning') as warning:
            self.assertEqual(main.GameSession(strategy_mode='shadow').handle(data), expected)
        self.assertEqual(warning.call_count, 1)
        self.assertEqual(warning.call_args.args[0], '[shadow_performance] %s')
        with patch.object(session_module.time, 'perf_counter', side_effect=count(0, 1)), \
                patch.object(session_module.LOG, 'warning', side_effect=RuntimeError('warning failed')):
            self.assertEqual(main.GameSession(strategy_mode='shadow').handle(data), expected)

    def test_weapon_and_controller_divergence_and_return_diagnostics(self):
        data = state(role(1, 'worker', 9, 10), role(4, 'pioneer', 10, 9),
                     role(2, 'rocket', 10, 10, level=1), role(9, 'station', 10, 12, level=1))
        data['roundNo'] = 71
        data['robot'] = [role(100, 'smallRobot', 11, 10)]
        world = main.World(data)
        memory = main.GameMemory((7, 'challenger'), 0)
        delta = memory.observe(world, 71)
        actual = main.empty_response()
        actual['roleCommandMap'] = {'2': target('attack', 11, 10, controllerId='4')}
        _, report = main.StrategicPlanner(world, memory, delta, main.Rules()).run(actual)
        diff = report['divergence']
        self.assertEqual(diff['intended']['2']['controllerId'], '1')
        self.assertEqual(diff['actual']['2']['controllerId'], '4')
        self.assertIn('2', diff['divergent_actor_ids'])
        self.assertEqual(report['controllers'][0]['weapon_id'], '2')
        self.assertIn('assignment_status', report['controllers'][0])
        self.assertIn('1', report['pre_night']['estimated_return_costs'])
        self.assertEqual(set(report['task']), {'pioneer_job', 'estimated_finish', 'return_deadline',
                                              'task_started', 'task_end', 'task_error_codes', 'gold_before', 'gold_after'})


if __name__ == '__main__':
    unittest.main()
