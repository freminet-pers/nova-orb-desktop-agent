"""Machine-readable compatibility contract for the character bridge.

This test describes the stable protocol without importing or executing any
renderer. The contract is the seam the Nova renderer must preserve.
"""
import json
import re
import unittest
from pathlib import Path

from coco.behavior import SCENES, STATE_RULES, UPSTREAM_GROUPS, UPSTREAM_STATES, payload
from coco.nova import NovaCanvas


CONTRACT_FILE = Path(__file__).with_name("visual_contract.json")
HOST_FILE = Path(__file__).parents[1] / "coco" / "web" / "nova_bridge.js"
NOVA_FILE = Path(__file__).parents[1] / "coco" / "nova.py"


class VisualContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
        cls.host = HOST_FILE.read_text(encoding="utf-8")

    def test_contract_matches_the_39_legacy_states(self):
        groups = self.contract["state_groups"]
        self.assertEqual({key: list(value) for key, value in UPSTREAM_GROUPS.items()}, groups)
        states = [state for value in groups.values() for state in value]
        self.assertEqual(self.contract["state_count"], 39)
        self.assertEqual(len(states), self.contract["state_count"])
        self.assertEqual(len(set(states)), self.contract["state_count"])
        self.assertEqual(tuple(states), UPSTREAM_STATES)
        self.assertEqual(set(states), set(STATE_RULES))

    def test_every_state_is_reachable_from_a_scene(self):
        used = {beat.state for beats in SCENES.values() for beat in beats}
        self.assertEqual(used, set(UPSTREAM_STATES))
        for name in SCENES:
            for beat in payload(name):
                self.assertEqual(set(beat), set(self.contract["renderer_bridge"]["scene_beat_fields"]))
                self.assertIn(beat["state"], UPSTREAM_STATES)
                self.assertGreaterEqual(beat["ms"], 1)

    def test_javascript_bridge_exports_the_stable_methods(self):
        bridge = self.contract["renderer_bridge"]
        self.assertIn("global.coco =", self.host)
        for name in bridge["javascript_methods"] + bridge["diagnostic_methods"]:
            self.assertRegex(self.host, rf"\b{re.escape(name)}\s*(?::|\()")

    def test_qt_adapter_keeps_the_stable_python_methods(self):
        for name in self.contract["renderer_bridge"]["python_methods"]:
            self.assertTrue(callable(getattr(NovaCanvas, name, None)), name)

    def test_qt_event_names_remain_whitelisted_and_bridged(self):
        events = self.contract["renderer_bridge"]["events"]
        for event in events:
            self.assertIn(repr(event), self.host)
        nova_source = NOVA_FILE.read_text(encoding="utf-8")
        for event in events:
            self.assertIn(repr(event), nova_source)

    def test_desktop_runtime_selects_only_the_nova_adapter(self):
        desktop = Path(__file__).parents[1].joinpath("coco", "desktop.py").read_text(encoding="utf-8")
        self.assertIn("from .nova import NovaCanvas", desktop)
        self.assertIn("self.character = NovaCanvas(self)", desktop)


if __name__ == "__main__":
    unittest.main()
