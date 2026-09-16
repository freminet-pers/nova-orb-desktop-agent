import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from coco.ui import Controller


class VoiceRoutingTests(unittest.TestCase):
    def make_controller(self, *, review=False, auto=False):
        controller = Controller.__new__(Controller)
        controller.busy = False
        controller.wake_command = True
        controller.wake_transcript_consumed = False
        controller.wake_timer = SimpleNamespace(start=Mock())
        controller.service = SimpleNamespace(setting=lambda key, default=None: {
            "wake_review_text": review,
            "voice_auto_send": auto,
        }.get(key, default))
        controller.panel = SimpleNamespace(
            voice_hint=SimpleNamespace(setText=Mock()),
            input=SimpleNamespace(setText=Mock(), setFocus=Mock()),
        )
        controller.pet = SimpleNamespace(say=Mock())
        controller.show_chat = Mock()
        controller.send = Mock()
        return controller

    def test_wake_transcript_is_sent_once_without_manual_send(self):
        controller = self.make_controller()
        controller.on_transcript("打开记事本")
        controller.on_transcript("打开记事本")
        controller.send.assert_called_once_with("打开记事本")

    def test_review_mode_only_fills_editor(self):
        controller = self.make_controller(review=True, auto=True)
        controller.on_transcript("请总结刚才内容")
        controller.send.assert_not_called()
        controller.panel.input.setText.assert_called_once_with("请总结刚才内容")

    def test_pure_wake_phrase_is_not_a_task(self):
        controller = self.make_controller()
        controller.on_transcript("hey nova")
        controller.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
