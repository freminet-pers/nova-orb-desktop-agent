import unittest

from coco.assistant import RouteDecision, route_intent


class RouteIntentTests(unittest.TestCase):
    def test_ordinary_chat_is_lightweight(self):
        self.assertEqual(route_intent("你好，今天过得怎么样").mode, "chat")
        self.assertFalse(route_intent("你好，今天过得怎么样").thinking)

    def test_complex_language_selects_thinking_without_model_call(self):
        decision = route_intent("请深度思考并比较两个方案")
        self.assertEqual(decision, RouteDecision("thinking", "complex or explicit reasoning wording", True))

    def test_direct_instruction_wins_over_thinking_words(self):
        decision = route_intent("不要深度思考，直接打开记事本")
        self.assertEqual(decision.mode, "direct")
        self.assertFalse(decision.thinking)

    def test_tool_and_online_are_explicit_modes(self):
        self.assertEqual(route_intent("打开记事本", deterministic_tool=True).mode, "agent")
        self.assertEqual(route_intent("北京明天天气", online=True).mode, "online")

    def test_advanced_override_can_disable_auto_router(self):
        decision = route_intent("请分析一下", auto=False, manual_thinking=False)
        self.assertEqual(decision.mode, "chat")
        decision = route_intent("随便聊聊", auto=False, manual_thinking=True)
        self.assertEqual(decision.mode, "thinking")


if __name__ == "__main__":
    unittest.main()
