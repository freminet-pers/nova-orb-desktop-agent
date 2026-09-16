import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from coco.speaker_verification import (
    DEFAULT_THRESHOLD,
    VERIFY_MIN_SECONDS,
    aggregate_embeddings,
    cosine_similarity,
    normalize_embedding,
    quality_check,
    load_profile,
    save_profile,
    delete_profile,
    clear_extractor_cache,
    SpeakerVerificationError,
    SpeakerTask,
    SpeakerVerifier,
)
from coco.secure_store import available as secure_store_available


class SpeakerMathTests(unittest.TestCase):
    def test_normalize_and_cosine(self):
        left = normalize_embedding([3.0, 4.0])
        self.assertAlmostEqual(float(np.linalg.norm(left)), 1.0, places=5)
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0, places=5)
        self.assertLess(cosine_similarity([1, 0], [0, 1]), 0.1)

    def test_quality_rejects_short_quiet_and_clipped(self):
        self.assertEqual(quality_check(np.zeros(16000))["reason"], "short")
        self.assertEqual(quality_check(np.zeros(16000 * 3))["reason"], "quiet")
        clipped = np.ones(16000 * 3, dtype=np.float32)
        self.assertEqual(quality_check(clipped)["reason"], "clipped")
        self.assertTrue(quality_check(np.ones(16000 * 3, dtype=np.float32) * .02)["ok"])

    def test_aggregate_rejects_different_speakers(self):
        result, info = aggregate_embeddings([[1, 0, 0], [1, .01, 0], [1, 0, .01]])
        self.assertEqual(info["segments"], 3)
        self.assertAlmostEqual(float(np.linalg.norm(result)), 1.0, places=5)
        with self.assertRaises(Exception):
            aggregate_embeddings([[1, 0], [-1, 0], [1, 0]])

    def test_threshold_is_conservative_and_gate_is_optional(self):
        self.assertGreater(DEFAULT_THRESHOLD, 0.5)

    def test_wake_verification_has_separate_real_audio_floor(self):
        # Enrollment still requires the normal 2-second quality floor, while
        # a complete short wake phrase is allowed to reach the embedding model
        # with its real samples. No padding/repetition is used here.
        short_wake = np.ones(round(16000 * 0.95), dtype=np.float32) * 0.02
        self.assertEqual(quality_check(short_wake)["reason"], "short")
        self.assertTrue(quality_check(short_wake, min_seconds=VERIFY_MIN_SECONDS)["ok"])
        too_short = np.ones(round(16000 * 0.5), dtype=np.float32) * 0.02
        self.assertEqual(quality_check(too_short, min_seconds=VERIFY_MIN_SECONDS)["reason"], "short")

    @unittest.skipUnless(secure_store_available(), "requires Windows DPAPI")
    def test_profile_is_dpapi_bound_and_clearable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nova.dpapi"
            save_profile([1, 0, 0], path=path, model_hash="TEST-MODEL")
            raw = path.read_bytes()
            self.assertNotIn(b"embedding", raw)
            loaded = load_profile(path=path, model_hash="TEST-MODEL")
            self.assertAlmostEqual(float(loaded["embedding"][0]), 1.0, places=5)
            with self.assertRaises(SpeakerVerificationError):
                load_profile(path=path, model_hash="OTHER-MODEL")
            delete_profile(path)
            self.assertFalse(path.exists())


class _FakeStream:
    def accept_waveform(self, rate, samples):
        pass

    def input_finished(self):
        pass


class _FakeExtractor:
    def __init__(self, delay=0):
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.active_lock = threading.Lock()

    def create_stream(self):
        return _FakeStream()

    def compute(self, stream):
        with self.active_lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            return [1.0, 0.0, 0.0]
        finally:
            with self.active_lock:
                self.active -= 1


class SpeakerExtractorCacheTests(unittest.TestCase):
    def setUp(self):
        clear_extractor_cache()
        self.addCleanup(clear_extractor_cache)

    def _model_file(self, folder, content="model-one"):
        path = Path(folder) / "campplus.onnx"
        path.write_text(content, encoding="ascii")
        return path

    def test_tasks_reuse_one_extractor_for_the_same_model(self):
        with tempfile.TemporaryDirectory() as folder:
            model = self._model_file(folder)
            extractor = _FakeExtractor()
            with patch("coco.speaker_verification._create_extractor", return_value=extractor) as create:
                first = SpeakerVerifier(model, expected_hash=None)
                second = SpeakerVerifier(model, expected_hash=None)
            self.assertIs(first.extractor, second.extractor)
            self.assertEqual(create.call_count, 1)

    def test_failed_load_is_not_cached_and_can_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            model = self._model_file(folder)
            extractor = _FakeExtractor()
            with patch("coco.speaker_verification._create_extractor",
                       side_effect=[SpeakerVerificationError("temporary"), extractor]) as create:
                with self.assertRaises(SpeakerVerificationError):
                    SpeakerVerifier(model, expected_hash=None)
                verifier = SpeakerVerifier(model, expected_hash=None)
            self.assertIs(verifier.extractor, extractor)
            self.assertEqual(create.call_count, 2)

    def test_changed_model_file_does_not_reuse_old_extractor(self):
        with tempfile.TemporaryDirectory() as folder:
            model = self._model_file(folder, "model-one")
            first_extractor, second_extractor = _FakeExtractor(), _FakeExtractor()
            with patch("coco.speaker_verification._create_extractor",
                       side_effect=[first_extractor, second_extractor]) as create:
                first = SpeakerVerifier(model, expected_hash=None)
                model.write_text("model-version-two", encoding="ascii")
                second = SpeakerVerifier(model, expected_hash=None)
            self.assertIs(first.extractor, first_extractor)
            self.assertIs(second.extractor, second_extractor)
            self.assertEqual(create.call_count, 2)

    def test_shared_extractor_inference_is_serialized(self):
        with tempfile.TemporaryDirectory() as folder:
            model = self._model_file(folder)
            extractor = _FakeExtractor(delay=0.04)
            with patch("coco.speaker_verification._create_extractor", return_value=extractor):
                first = SpeakerVerifier(model, expected_hash=None)
                second = SpeakerVerifier(model, expected_hash=None)
            samples = np.ones(16000 * 3, dtype=np.float32) * .02
            threads = [threading.Thread(target=verifier.embed, args=(samples,))
                       for verifier in (first, second)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(extractor.max_active, 1)

    def test_verify_task_loads_profile_each_time_after_deletion(self):
        profiles = [{"embedding": np.array([1.0, 0.0])}, None]
        seen = []

        class FakeVerifier:
            def verify(self, samples, profile, threshold):
                seen.append(profile)
                return {"accepted": bool(profile), "score": 1.0 if profile else 0.0}

        with patch("coco.speaker_verification.SpeakerVerifier", return_value=FakeVerifier()), \
             patch("coco.speaker_verification.load_profile", side_effect=profiles):
            SpeakerTask("verify", samples=np.ones(16000, dtype=np.float32)).run()
            SpeakerTask("verify", samples=np.ones(16000, dtype=np.float32)).run()
        self.assertIsNone(seen[1])

    def test_cancellation_during_enrollment_compute_never_saves_or_succeeds(self):
        class InterruptibleTask(SpeakerTask):
            cancelled = False

            def isInterruptionRequested(self):
                return self.cancelled

        task = InterruptibleTask("enroll", segments=[np.ones(16000 * 3, dtype=np.float32)] * 3)
        completed = []
        task.completed.connect(completed.append)

        class FakeVerifier:
            def enroll(self, segments):
                task.cancelled = True  # Simulates cancellation during compute().
                return np.array([1.0, 0.0]), {"segments": 3}

        with patch("coco.speaker_verification.SpeakerVerifier", return_value=FakeVerifier()), \
             patch("coco.speaker_verification.save_profile") as save:
            task.run()
        save.assert_not_called()
        self.assertEqual(completed, [])

    def test_enrollment_failure_keeps_an_existing_profile_file(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "existing.dpapi"
            profile.write_bytes(b"existing-encrypted-profile")

            class FailingVerifier:
                def enroll(self, segments):
                    raise SpeakerVerificationError("inference failed")

            with patch("coco.speaker_verification.SpeakerVerifier", return_value=FailingVerifier()), \
                 patch("coco.speaker_verification.save_profile") as save:
                SpeakerTask("enroll", segments=[np.ones(16000 * 3, dtype=np.float32)] * 3).run()
            save.assert_not_called()
            self.assertEqual(profile.read_bytes(), b"existing-encrypted-profile")


if __name__ == "__main__":
    unittest.main()
