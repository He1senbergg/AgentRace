import json
import unittest

from src import main3 as main
from test_actions import role, state, zone, validator


LEGEND = '宝藏在(6,5)，从回合2到回合10开放，需要两份StarSand，不多不少。'
OFFICIAL = '第2天到第3天铁矿停采，价格上涨。'


def news_state(round_no=0):
    data = state(role(11, 'pioneer', 5, 5),
                 worldNews={'folkLegends': LEGEND, 'officialNews': OFFICIAL},
                 weaponShopList=[{'name': 'StarSand', 'price': 15}])
    data['roundNo'] = round_no
    data['teamOur']['roles'][0]['backpack'] = ['StarSand', 'StarSand']
    return data


def interpretation():
    return {'events': [{'resource': 'iron', 'start_day': 2, 'end_day': 3,
                        'harvestable': False, 'price_direction': 'up', 'evidence': [OFFICIAL]}],
            'treasure': {'position': {'x': 6, 'y': 5}, 'open_round': 2, 'close_round': 10,
                         'items': ['StarSand', 'StarSand'], 'confidence': 'high',
                         'evidence': {'position': [LEGEND], 'time': [LEGEND], 'items': [LEGEND]}}}


class NewsTests(unittest.TestCase):
    def test_long_multiday_news_preserved_in_prompt(self):
        session = main.GameSession()
        data = news_state()
        data['worldNews']['folkLegends'] = 'DAY1 START ' + '甲' * 60000 + ' DAY1 END'
        first_clue = data['worldNews']['folkLegends']
        self.assertIn(first_clue, session.handle(data)['prompt'])
        data['roundNo'] = 130
        data['worldNews']['folkLegends'] = 'DAY2 START ' + '乙' * 60000 + ' DAY2 END'
        prompt = session.handle(data)['prompt']
        self.assertIn(first_clue, prompt)
        self.assertIn(data['worldNews']['folkLegends'], prompt)
        self.assertEqual(len(session.memory.news), 2)

    def test_platform_quota_error_stops_ordinary_retries_until_day_reset(self):
        session = main.GameSession()
        data = news_state()
        session.handle(data)
        data['roundNo'] = 1
        data['errors'] = [{'errorCode': 5}]
        self.assertFalse(session.handle(data)['prompt'])
        self.assertEqual(session.memory.llm_calls_today, 3)
        data['roundNo'] = 2
        data['errors'] = []
        self.assertFalse(session.handle(data)['prompt'])
        data['roundNo'] = 130
        data['errors'] = [{'errorCode': 5}]  # Previous day's exhausted quota does not consume the new day.
        self.assertTrue(session.handle(data)['prompt'])

    def test_two_independent_readings_then_exact_sacrifice(self):
        session = main.GameSession()
        first = news_state()
        self.assertTrue(session.handle(first)['prompt'])
        first['roundNo'] = 1
        first['llmResp'] = json.dumps(interpretation(), ensure_ascii=False)
        response = session.handle(first)
        self.assertTrue(response['prompt'])
        self.assertEqual(response['roleCommandMap'], {})
        first['roundNo'] = 2
        response = session.handle(first)
        self.assertFalse(response['prompt'])
        self.assertEqual(response['roleCommandMap']['11'], {
            'action': 'summonTreasure', 'targetPos': [{'x': 6, 'y': 5}], 'item': ['StarSand', 'StarSand']})
        self.assertEqual(response, session.handle(first))
        self.assertEqual(session.memory.llm_calls_today, 2)

    def test_bad_evidence_unknown_items_bounds_and_disagreement(self):
        news = [{'day': 1, 'round': 0, 'text': news_state()['worldNews']}]
        for mutate in (lambda t: t.update(position={'x': 41, 'y': 1}),
                       lambda t: t.update(open_round=True), lambda t: t.update(close_round=1300),
                       lambda t: t.update(items=['Invented']), lambda t: t.update(confidence='low'),
                       lambda t: t['evidence'].update(time=['invented quote'])):
            decision = interpretation()
            mutate(decision['treasure'])
            self.assertIsNone(main.parse_news_decision(json.dumps(decision), news, 0, {'StarSand'}))
        session = main.GameSession()
        data = news_state()
        session.handle(data)
        data['roundNo'] = 1
        data['llmResp'] = json.dumps(interpretation())
        session.handle(data)
        decision = interpretation()
        decision['treasure']['items'] = ['StarSand']
        data['roundNo'] = 2
        data['llmResp'] = json.dumps(decision)
        self.assertEqual(session.handle(data)['roleCommandMap'], {})
        self.assertIsNone(session.memory.treasure)

    def test_all_result_codes_and_gap_do_not_repeat_consumption(self):
        for code in range(5):
            session = main.GameSession()
            data = news_state()
            session.handle(data)
            for round_no in (1, 2):
                data['roundNo'] = round_no
                data['llmResp'] = json.dumps(interpretation())
                session.handle(data)
            data['roundNo'] = 3
            data['lastSummonTreasureResult'] = code
            response = session.handle(data)
            self.assertEqual(response['roleCommandMap'], {})
            self.assertEqual(session.memory.treasure_result, code)
            self.assertEqual(session.memory.treasure_terminal, {1: 'obtained', 4: 'empty'}.get(code, ''))
        data['roundNo'] = 0
        session = main.GameSession()
        session.handle(data)
        for round_no in (1, 2):
            data['roundNo'] = round_no
            session.handle(data)
        data['roundNo'] = 4
        session.handle(data)
        self.assertEqual(session.memory.treasure_terminal, 'unknown_after_gap')

    def test_snapshot_change_gap_task_quota_and_half_reset(self):
        for change in ('news', 'gap', 'active'):
            session = main.GameSession()
            data = news_state()
            session.handle(data)
            data['roundNo'] = 1
            data['llmResp'] = json.dumps(interpretation())
            if change == 'news':
                data['worldNews']['folkLegends'] += '新增线索'
            elif change == 'gap':
                data['roundNo'] = 2
            else:
                data['phaseTask'] = 'Active task'
            response = session.handle(data)
            self.assertNotIn('summonTreasure', str(response['roleCommandMap']))
            if change in ('gap', 'active'):
                self.assertFalse(response['prompt'])
        session = main.GameSession()
        data = news_state()
        for round_no in range(4):
            data['roundNo'] = round_no
            data['llmResp'] = 'invalid'
            response = session.handle(data)
            self.assertEqual(bool(response['prompt']), round_no < 3)
        session.handle({'roundNo': 0, 'teamOur': {'teamId': 7, 'type': 'challenger'}})
        self.assertEqual(session.memory.news, [])
        self.assertEqual(session.memory.resource_events, [])
        self.assertEqual(session.memory.treasure_attempts, set())

    def test_purchase_observe_inventory_wait_window_and_expiry(self):
        data = news_state(1)
        data['teamOur']['roles'][0]['backpack'] = []
        zone(data, 'weaponShop', 4, 5)
        v = validator(data)
        v.memory.last_round = 1
        v.memory.treasure = interpretation()['treasure']
        main.TreasurePlanner(v).run()
        self.assertEqual(v.commands['11'], {'action': 'buy', 'name': 'StarSand', 'num': 2})
        self.assertIsNone(v.memory.treasure_pending)
        for round_no, expected in ((1, None), (2, 'summonTreasure'), (11, None)):
            v = validator(news_state(round_no))
            v.memory.last_round = round_no
            v.memory.treasure = interpretation()['treasure']
            main.TreasurePlanner(v).run()
            self.assertEqual(v.commands.get('11', {}).get('action'), expected)
            if round_no == 1:
                self.assertIn('11', v.busy)

    def test_insufficient_budget_capacity_or_travel_time_no_purchase(self):
        for variant in ('budget', 'capacity', 'time'):
            data = news_state()
            data['teamOur']['roles'][0]['backpack'] = []
            zone(data, 'weaponShop', 4, 5)
            if variant == 'budget':
                data['teamOur']['goldNum'] = 29
            elif variant == 'capacity':
                data['teamOur']['roles'][0]['backPackCapability'] = 1
            else:
                data['teamOur']['roles'][0]['pos'] = {'x': 40, 'y': 31}
            v = validator(data)
            v.memory.last_round = 2
            v.memory.treasure = interpretation()['treasure']
            main.TreasurePlanner(v).run()
            self.assertEqual(v.commands, {})

    def test_harvest_event_expires_and_runtime_price_controls_choice(self):
        data = state(role(1, 'worker', 5, 5), vendorShopList=[{'name': 'iron', 'price': 100},
                                                            {'name': 'copper', 'price': 5}])
        zone(data, 'iron', 6, 5)
        zone(data, 'copper', 4, 5)
        for day, target in ((2, {'x': 4, 'y': 5}), (4, {'x': 6, 'y': 5})):
            v = validator(data, main.Phase(day, 1))
            v.memory.resource_events = interpretation()['events']
            main.EconomyPlanner(v).workers()
            self.assertEqual(v.commands['1']['targetPos'], [target])
