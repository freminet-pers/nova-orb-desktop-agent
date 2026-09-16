import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from coco.wake import WAKE_PHRASES, WakeListener, canonical_phrases, is_wake_phrase, normalize_wake_text


class WakePhraseTests(unittest.TestCase):
    def test_normalization_keeps_full_phrase_boundaries(self):
        self.assertEqual(normalize_wake_text("  Hey, NOVA!  "), "hey nova")
        self.assertEqual(normalize_wake_text("Are you there—Nova?"), "are you there nova")

    def test_allowed_full_phrases(self):
        for text in (
            "Nova", "hey Nova", "are you there, Nova", "Nova are you there",
            "HI NOVA!", "hello Nova", "okay Nova", "ok Nova",
            "Nova can you help", "Nova help me",
        ):
            self.assertTrue(is_wake_phrase(text), text)

    def test_substrings_chinese_and_extra_words_are_rejected(self):
        for text in (
            "hey Nova open calculator",
            "are you there Nova please",
            "I heard hey Nova in a movie",
            "嘿，Nova",
            "today is Nova",
            "we will meet Nova",
            "hey Coco",
            "",
        ):
            self.assertFalse(is_wake_phrase(text), text)

    def test_old_custom_phrase_migrates_without_widening_match(self):
        self.assertEqual(canonical_phrases("你好口口"), WAKE_PHRASES)
        self.assertEqual(canonical_phrases("HEY SATURDAY")[0], "nova")
        self.assertTrue(is_wake_phrase("hey nova", canonical_phrases("HEY SATURDAY")))
        self.assertFalse(is_wake_phrase("hey saturday", canonical_phrases("HEY SATURDAY")))
        self.assertFalse(is_wake_phrase("coco", canonical_phrases("HEY SATURDAY")))

    def _listener_for_flush(self):
        listener = WakeListener.__new__(WakeListener)
        listener.worker_ready = True
        listener.worker_busy = False
        listener.stream = object()
        listener.process = MagicMock()
        listener.format = SimpleNamespace(
            sampleRate=lambda: 16000,
            bytesForDuration=lambda micros: int(16000 * 2 * micros / 1_000_000),
        )
        listener.buffer = bytearray(b"short-audio")
        listener.flush_ticks = 0
        listener.short_windows = 0
        listener.silence_windows = 0
        listener.tail_windows = 0
        listener.sent_windows = 0
        listener.started_at = 0.0
        listener.last_send_at = 0.0
        listener.logger = MagicMock()
        listener._trim_buffer = WakeListener._trim_buffer.__get__(listener, WakeListener)
        return listener

    def test_flush_keeps_subsecond_chunks_until_next_tick(self):
        listener = self._listener_for_flush()
        original = bytes(listener.buffer)
        with patch("coco.voice.pcm_float", return_value=np.zeros(8000, dtype=np.float32)):
            WakeListener.flush_window(listener)
        self.assertEqual(bytes(listener.buffer), original)
        self.assertEqual(listener.short_windows, 1)
        self.assertEqual(listener.sent_windows, 0)

    def test_flush_sends_after_tail_silence_and_then_clears(self):
        listener = self._listener_for_flush()
        samples = np.concatenate((np.ones(16000, dtype=np.float32) * 0.03,
                                  np.zeros(3200, dtype=np.float32)))
        with patch("coco.voice.pcm_float", return_value=samples):
            WakeListener.flush_window(listener)
        self.assertEqual(listener.sent_windows, 1)
        self.assertTrue(listener.worker_busy)
        self.assertEqual(listener.buffer, bytearray())
        payload = listener.process.write.call_args.args[0]
        self.assertEqual(int.from_bytes(payload[:4], "little"), len(payload) - 4)

    def test_worker_restart_is_bounded_and_stop_does_not_restart(self):
        listener = WakeListener.__new__(WakeListener)
        listener.process = object()
        listener.generation = 7
        listener.intentional_stop = False
        listener.restart_attempts = 0
        listener.restart_window_started = 0.0
        listener.failed = False
        listener.last_phrase = "hey nova"
        listener.device_id = ""
        listener.status = MagicMock()
        listener.logger = MagicMock()
        listener._stop_resources = MagicMock()
        process = listener.process
        with patch("coco.wake.QTimer.singleShot") as schedule:
            for _ in range(3):
                WakeListener.worker_error(listener, process, 7, reason="test")
            self.assertFalse(listener.failed)
            self.assertEqual(listener.restart_attempts, 3)
            self.assertEqual(schedule.call_count, 3)
            WakeListener.worker_error(listener, process, 7, reason="test")
        self.assertTrue(listener.failed)
        self.assertEqual(schedule.call_count, 3)
        listener.failed = False
        listener.intentional_stop = True
        listener.restart_attempts = 0
        with patch("coco.wake.QTimer.singleShot") as schedule:
            WakeListener.worker_error(listener, process, 7, reason="intentional")
        schedule.assert_not_called()
        listener.intentional_stop = False
        listener.generation = 8
        listener._stop_resources.reset_mock()
        with patch("coco.wake.QTimer.singleShot") as schedule:
            WakeListener.worker_error(listener, process, 7, reason="stale")
        listener._stop_resources.assert_not_called()
        schedule.assert_not_called()

    def test_stop_drops_pending_audio_candidate(self):
        listener = WakeListener.__new__(WakeListener)
        listener.generation = 3
        listener.flush_timer = MagicMock()
        listener.source = None
        listener.stream = None
        listener.process = None
        listener.buffer = bytearray(b"private-audio")
        listener.process_buffer = b"partial-json"
        listener.last_samples = np.ones(16000, dtype=np.float32)
        WakeListener._stop_resources(listener)
        self.assertIsNone(listener.last_samples)
        self.assertEqual(listener.buffer, bytearray())
        self.assertEqual(listener.process_buffer, b"")


if __name__ == "__main__":
    unittest.main()
