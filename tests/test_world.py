import unittest
from src.main import World, Phase, MoveReservations, station_cells, building_ring, neighbors


def role(actor, kind, x, y):
    return {'id': actor, 'roleType': kind, 'pos': {'x': x, 'y': y}, 'health': 100}


class WorldTests(unittest.TestCase):
    def test_phase_boundaries(self):
        for origin in (0, 1):
            for index, expected in [(0, (1, 1, True)), (69, (1, 70, True)),
                                    (70, (1, 71, False)), (129, (1, 130, False)),
                                    (130, (2, 1, True)), (1299, (10, 130, False))]:
                p = Phase.from_round(index + origin, origin)
                self.assertEqual((p.day, p.round_in_day, p.is_day), expected)
        for args in [(1, None), (True, 1), (-1, 0), (1301, 1)]:
            with self.assertRaises(ValueError):
                Phase.from_round(*args)

    def test_station_and_rings(self):
        self.assertEqual(station_cells((10, 10)), {(10, 10), (11, 10), (10, 9), (11, 9)})
        self.assertEqual(len(building_ring((10, 10), 1)), 12)
        self.assertEqual(len(building_ring((10, 10), 2)), 20)
        self.assertFalse(building_ring((10, 10), 1) & building_ring((10, 10), 2))
        self.assertEqual(set(neighbors((0, 0))), {(1, 0), (0, 1), (1, 1)})

    def test_multicell_dynamic_obstacles(self):
        data = {'mapInfo': {'zones': [
            {'neutralType': 'challengerTaskPoint2', 'pos': {'x': 4, 'y': 4}},
            {'neutralType': 'challengerTaskPoint2', 'pos': {'x': 5, 'y': 4}}]},
            'teamOur': {'roles': [role(1, 'station', 10, 10)]},
            'teamEnemy': {'roles': [role(2, 'worker', 6, 6)]}}
        w = World(data)
        self.assertEqual(w.zones['challengerTaskPoint2'], {(4, 4), (5, 4)})
        self.assertTrue({(10, 9), (11, 9), (6, 6)} <= w.occupied)
        self.assertFalse(World({}).occupied)
        data['teamEnemy']['roles'] = []
        self.assertNotIn((6, 6), World(data).occupied)

    def test_shortest_path_and_corner_cut(self):
        w = World({})
        w.occupied = {(1, 0), (0, 1)}
        self.assertEqual(w.path((0, 0), {(1, 1)}), [(0, 0), (1, 1)])
        self.assertEqual(len(w.path((0, 0), {(40, 31)})), 41)
        w.occupied.add((1, 1))
        self.assertIsNone(w.path((0, 0), {(2, 2)}))
        self.assertEqual(w.path((0, 0), {(0, 0)}), [(0, 0)])
        self.assertIsNone(w.path((0, 0), {(1, 0)}))

    def test_move_conflicts(self):
        w = World({'teamOur': {'roles': [role(1, 'worker', 1, 1), role(2, 'worker', 2, 1)]}})
        r = MoveReservations(w)
        self.assertFalse(r.reserve('1', (2, 1)))
        self.assertFalse(r.reserve('2', (1, 1)))
        self.assertTrue(r.reserve('1', (2, 2)))
        self.assertFalse(r.reserve('2', (2, 2)))
        self.assertFalse(r.reserve('1', (0, 0)))
        self.assertTrue(r.reserve('2', (3, 1)))

    def test_malformed_and_duplicate_roles(self):
        for data in (None, [], {'teamOur': None}, {'mapInfo': {'zones': [None, {}]}}):
            self.assertEqual(World(data).roles, {})
        w = World({'teamOur': {'roles': [role(1, 'worker', 1, 1), role('01', 'worker', 2, 2)]}})
        self.assertEqual(w.roles, {})
        self.assertEqual(w.occupied, {(1, 1), (2, 2)})
        malformed = World({'teamOur': {'roles': [role(2, [], 2, 2), role('9' * 5000, 'worker', 3, 3)]}})
        self.assertNotIn('2', malformed.characters)
        self.assertIn((2, 2), malformed.occupied)
        self.assertIn('9' * 5000, malformed.characters)
