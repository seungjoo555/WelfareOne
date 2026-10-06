import unittest

from app.search_profiles import (
    SITUATION_CONFIDENT_DISTANCE,
    SITUATION_MAX_DISTANCE,
    SITUATION_REGION_BONUS_SCALE,
    search_options,
)
from app.search_service import MAX_DISTANCE


class SearchOptionsTest(unittest.TestCase):
    def test_situation_search_uses_stricter_distance_and_no_region_bonus(self):
        options = search_options("situation_search")
        self.assertEqual(options["max_distance"], SITUATION_MAX_DISTANCE)
        self.assertEqual(options["region_bonus_scale"], SITUATION_REGION_BONUS_SCALE)
        self.assertLess(options["max_distance"], MAX_DISTANCE)

    def test_other_routes_keep_the_defaults(self):
        for route in ("specific_policy", "current_policy_question", None):
            self.assertEqual(search_options(route), {}, route)

    def test_confident_distance_is_within_the_hard_limit(self):
        self.assertLess(SITUATION_CONFIDENT_DISTANCE, SITUATION_MAX_DISTANCE)


if __name__ == "__main__":
    unittest.main()
