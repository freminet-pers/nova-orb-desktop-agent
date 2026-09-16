"""Small in-memory checks for the wake-to-speaker-gate hand-off.

These tests deliberately use a fake worker response and fake extractor output;
they never open a microphone, read the user's profile, or write audio.  The
real ``SpeakerVerifier.verify`` method is still exercised so a short wake
candidate cannot be rejected by the enrollment-only quality gate.
"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication, QObject

from coco.speaker_verification import (
    DEFAULT_THRESHOLD,
    VERIFY_MIN_SECONDS,
    SpeakerVerificationError,
    SpeakerVerifier,
)
from coco.wake import WAKE_PHRASES, WakeListener
from coco.ui import Controller


class _WakeOwner(QObject):
    def __init__(self):
        super().__init__()
        self.candidates = []

    def handle_wake_candidate(self, samples):
        self.candidates.append(samples)


class WakeSpeakerPipelineTests(unittest.TestCase):
    def test_short_candidate_reaches_real_verify_method(self):
        verifier = object.__new__(SpeakerVerifier)
        calls = []

        def fake_embed(samples, *, min_seconds=2.0):
            calls.append((len(samples), min_seconds))
            return np.asarray([1.0, 0.0], dtype=np.float32)

        verifier.embed = fake_embed
        candidate = np.ones(round(16000 * 0.95), dtype=np.float32) * 0.02
        result = verifier.verify(candidate, {"embedding": np.asarray([1.0, 0.0])})
        self.assertTrue(result["accepted"])
        self.assertEqual(calls, [(len(candidate), VERIFY_MIN_SECONDS)])
        self.assertGreater(len(candidate), 0)

    def test_short_verify_failure_is_explicit(self):
        verifier = object.__new__(SpeakerVerifier)

        def reject_short(_samples, *, min_seconds=2.0):
            raise SpeakerVerificationError("录音太短")

        verifier.embed = reject_short
        with self.assertRaisesRegex(SpeakerVerificationError, "唤醒短句太短"):
            verifier.verify(np.ones(12000, dtype=np.float32), {"embedding": np.ones(2)})

    def test_matched_worker_candidate_is_consumed_and_late_result_is_ignored(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        owner = _WakeOwner()
        listener = WakeListener(owner)
        listener.process = MagicMock()
        process = listener.process
        process.readAllStandardOutput.return_value = (
            json.dumps({"text": "hey nova", "confidence": 0.9}) + "\n"
        ).encode("utf-8")
        process.state.return_value = 0
        listener.generation = 4
        listener.phrases = WAKE_PHRASES
        listener.process_buffer = b""
        listener.worker_busy = True
        listener.result_count = 0
        listener.started_at = 0.0
        listener.last_send_at = 0.0
        listener.sent_windows = 1
        listener.last_samples = np.ones(16000, dtype=np.float32) * 0.02
        listener.logger = MagicMock()

        listener.read_worker(process, 4)
        self.assertEqual(len(owner.candidates), 1)
        self.assertIsNone(listener.last_samples)
        # stop() invalidates the process/generation; a late line cannot invoke
        # the wake owner a second time.
        process.readAllStandardOutput.return_value = (
            json.dumps({"text": "hey nova", "confidence": 0.9}) + "\n"
        ).encode("utf-8")
        listener.read_worker(process, 4)
        self.assertEqual(len(owner.candidates), 1)
        app.processEvents()

    def test_shutdown_wait_is_bounded_and_does_not_terminate_worker(self):
        task = MagicMock()
        task.isRunning.return_value = True
        controller = SimpleNamespace(
            _quit_exit_scheduled=False,
            _quit_deadline=0.0,
            speaker_task=task,
            _quit_poll_timer=MagicMock(),
        )
        with patch("coco.ui.QTimer.singleShot") as single_shot:
            Controller._finish_quit(controller)
        task.requestInterruption.assert_called_once()
        task.wait.assert_called_once_with(250)
        task.terminate.assert_not_called()
        controller._quit_poll_timer.stop.assert_called_once()
        single_shot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
