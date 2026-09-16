"""Static checks for the self-contained Nova Orb web asset boundary."""
import json
import re
import unittest
from pathlib import Path


WEB = Path(__file__).parents[1] / "coco" / "web"
ASSETS = tuple(WEB / name for name in ("nova.html", "nova.css", "nova_states.js", "nova_renderer.js", "nova_bridge.js"))


class NovaWebAssetTests(unittest.TestCase):
    def test_entrypoint_uses_only_local_assets_and_qt_channel(self):
        html = (WEB / "nova.html").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", html)
        self.assertIn('script-src \'self\' qrc:', html)
        self.assertNotRegex(html, r"(?:https?|wss?)://")
        for name in ("nova.css", "nova_states.js", "nova_renderer.js", "nova_bridge.js"):
            self.assertIn(f'"{name}"', html)
        self.assertIn("qrc:///qtwebchannel/qwebchannel.js", html)

    def test_orb_has_the_required_authored_layers(self):
        html = (WEB / "nova.html").read_text(encoding="utf-8")
        for element_id in ("contact-shadow", "body-base", "body-sheen", "body-highlight", "body-environment", "body-rim", "eye-left", "eye-right", "orbit-back", "orbit-front", "particles"):
            self.assertIn(f'id="{element_id}"', html)
        renderer = (WEB / "nova_renderer.js").read_text(encoding="utf-8")
        shape_a = renderer.split("const SHAPE_A", 1)[1].split("const SHAPE_B", 1)[0]
        self.assertEqual(len(re.findall(r"\[\s*\d+,\s*\d+\s*\]", shape_a)), 12)
        self.assertIn("requestAnimationFrame", renderer)
        self.assertIn("document.hidden", renderer)
        self.assertIn("Math.sqrt(tx * tx + ty * ty)", renderer)

    def test_all_assets_are_offline_and_free_of_restricted_visual_names(self):
        for path in ASSETS:
            content = path.read_text(encoding="utf-8")
            self.assertNotRegex(content, r"(?:https?|wss?)://")
            self.assertNotRegex(content.casefold(), r"grok|xai|dicebear|replica")

    def test_state_file_declares_all_legacy_states(self):
        contract = json.loads(Path(__file__).with_name("visual_contract.json").read_text(encoding="utf-8"))
        states = [state for values in contract["state_groups"].values() for state in values]
        source = (WEB / "nova_states.js").read_text(encoding="utf-8")
        for state in sorted(set(states)):
            self.assertRegex(source, rf"['\"]?{re.escape(state)}['\"]?\s*:")


if __name__ == "__main__":
    unittest.main()
