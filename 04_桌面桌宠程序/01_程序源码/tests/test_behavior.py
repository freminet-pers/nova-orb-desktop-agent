import unittest

from coco.behavior import PHASES, SCENE_RULES, SCENES, STATE_RULES, UPSTREAM_GROUPS, UPSTREAM_STATES, interaction_scene


class BehaviorTests(unittest.TestCase):
    def test_upstream_table_covers_exactly_thirty_nine_unique_states(self):
        self.assertEqual(len(UPSTREAM_STATES), 39)
        self.assertEqual(len(set(UPSTREAM_STATES)), 39)
        self.assertEqual(set(UPSTREAM_STATES), {
            state for states in UPSTREAM_GROUPS.values() for state in states
        })

    def test_each_upstream_state_is_used_by_a_scene(self):
        used = {beat.state for beats in SCENES.values() for beat in beats}
        self.assertEqual(set(UPSTREAM_STATES), used)
        self.assertEqual(set(UPSTREAM_STATES), set(STATE_RULES))

    def test_rejected_food_never_uses_feed_scene(self):
        rejected = {"accepted": False, "state": {"fullness": 76}}
        self.assertEqual(interaction_scene("feed", rejected), "cooldown")
        self.assertEqual(interaction_scene("treat", {"accepted": False, "state": {"fullness": 96}}), "full")

    def test_touch_can_acknowledge_cooldown_without_reward(self):
        self.assertEqual(interaction_scene("pet", {"accepted": False, "state": {"fullness": 70}}), "pet")

    def test_locked_user_scenes_are_above_ambient_reactions(self):
        self.assertGreater(SCENE_RULES["sleep"].priority, SCENE_RULES["reply"].priority)
        self.assertGreater(SCENE_RULES["feed"].priority, SCENE_RULES["reply"].priority)
        self.assertFalse(SCENE_RULES["sleep"].interruptible)

    def test_business_progress_names_resolve_to_visual_states(self):
        self.assertEqual({"planning": "thinking", "working": "working", "success": "saved",
                          "failure": "error", "cancel": "idle"},
                         {key: PHASES[key] for key in ("planning", "working", "success", "failure", "cancel")})


if __name__ == "__main__":
    unittest.main()
