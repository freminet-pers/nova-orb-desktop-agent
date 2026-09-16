"""Optional local speaker verification for Nova's wake phrase.

The wake recognizer still decides *what was said*.  This module only answers
whether a complete, already-recognized wake segment resembles the locally
enrolled speaker.  Raw audio is kept in memory, and the enrollment vector is
stored separately from SQLite in a DPAPI-protected file.
"""
from __future__ import annotations

import base64
import atexit
import hashlib
import json
import math
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio

from .paths import SPEAKER_MODEL_FILE, SPEAKER_MODEL_SHA256, SPEAKER_PROFILE_FILE
from .secure_store import SecureStoreError, available as secure_store_available, protect_blob, unprotect_blob


PROFILE_MAGIC = b"NOVA-SPEAKER-DPAPI-1\n"
PROFILE_FORMAT = 1
SAMPLE_RATE = 16000
MIN_SECONDS = 2.0
# A wake phrase is intentionally much shorter than an enrollment utterance.
# CAM++ can produce an embedding for a real ~0.8 s sample, while treating a
# sub-phrase as unusable.  Keep this separate from enrollment quality: the
# gate still compares the actual captured samples and never pads or repeats
# them to manufacture speaker information.
VERIFY_MIN_SECONDS = 0.75
RECOMMENDED_SECONDS = "5–8"
DEFAULT_THRESHOLD = 0.62


class SpeakerVerificationError(Exception):
    """A safe, user-facing speaker verification error."""


class _SpeakerTaskCancelled(Exception):
    """Internal, silent control flow for a user-cancelled worker."""


def model_sha256(path=SPEAKER_MODEL_FILE):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize_embedding(value):
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    if vector.size == 0 or not np.all(np.isfinite(vector)):
        raise SpeakerVerificationError("声纹向量无效。")
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm < 1e-8:
        raise SpeakerVerificationError("声纹向量为空。")
    return (vector / norm).astype(np.float32)


def cosine_similarity(left, right):
    a = normalize_embedding(left)
    b = normalize_embedding(right)
    if a.size != b.size:
        raise SpeakerVerificationError("声纹模型版本不一致。")
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def quality_check(samples, min_seconds=MIN_SECONDS):
    """Return non-sensitive audio quality facts for UI diagnostics."""
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    result = {"ok": False, "seconds": round(float(audio.size / SAMPLE_RATE), 2),
              "rms": 0.0, "clipped": False, "reason": ""}
    if audio.size < int(SAMPLE_RATE * min_seconds):
        result["reason"] = "short"
        return result
    finite = audio[np.isfinite(audio)]
    if finite.size != audio.size or not finite.size:
        result["reason"] = "invalid"
        return result
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak = float(np.max(np.abs(audio)))
    result["rms"] = round(rms, 5)
    result["clipped"] = bool(np.mean(np.abs(audio) >= 0.985) > 0.01 or peak > 1.05)
    if rms < 0.006:
        result["reason"] = "quiet"
    elif result["clipped"]:
        result["reason"] = "clipped"
    else:
        result["ok"] = True
    return result


def aggregate_embeddings(embeddings, consistency_threshold=0.45):
    vectors = [normalize_embedding(item) for item in embeddings]
    if not vectors:
        raise SpeakerVerificationError("没有可用的声纹片段。")
    dimensions = {item.size for item in vectors}
    if len(dimensions) != 1:
        raise SpeakerVerificationError("声纹片段维度不一致。")
    aggregate = normalize_embedding(np.mean(np.stack(vectors), axis=0))
    scores = [cosine_similarity(item, aggregate) for item in vectors]
    if min(scores) < consistency_threshold:
        raise SpeakerVerificationError("三段录音差异较大，请使用同一人的自然语音重新录入。")
    return aggregate, {"segments": len(vectors), "min_consistency": round(min(scores), 4)}


def _profile_scope(model_hash):
    return f"nova-speaker:{str(model_hash).upper()}:v{PROFILE_FORMAT}"


def save_profile(embedding, path=SPEAKER_PROFILE_FILE, model_hash=SPEAKER_MODEL_SHA256):
    if not secure_store_available():
        raise SpeakerVerificationError("当前系统没有可用的 Windows 用户加密，声纹不会保存。")
    vector = normalize_embedding(embedding)
    body = {
        "format": PROFILE_FORMAT,
        "model": str(model_hash).upper(),
        "dimension": int(vector.size),
        "embedding": base64.b64encode(vector.astype("<f4").tobytes()).decode("ascii"),
    }
    try:
        protected = protect_blob(PROFILE_MAGIC + json.dumps(body, separators=(",", ":")).encode("utf-8"),
                                 scope=_profile_scope(model_hash))
    except SecureStoreError as exc:
        raise SpeakerVerificationError(str(exc)) from None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".nova-speaker-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(protected)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target


def load_profile(path=SPEAKER_PROFILE_FILE, model_hash=SPEAKER_MODEL_SHA256):
    target = Path(path)
    if not target.is_file():
        return None
    try:
        raw = unprotect_blob(target.read_bytes(), scope=_profile_scope(model_hash))
        if not raw.startswith(PROFILE_MAGIC):
            raise SpeakerVerificationError("声纹档案格式无效。")
        body = json.loads(raw[len(PROFILE_MAGIC):].decode("utf-8"))
        if body.get("format") != PROFILE_FORMAT or str(body.get("model", "")).upper() != str(model_hash).upper():
            raise SpeakerVerificationError("声纹档案与当前模型版本不匹配。")
        vector = np.frombuffer(base64.b64decode(body["embedding"], validate=True), dtype="<f4").copy()
        if int(body.get("dimension", 0)) != vector.size:
            raise SpeakerVerificationError("声纹档案维度无效。")
        return {"embedding": normalize_embedding(vector), "model": str(body["model"]).upper(),
                "dimension": vector.size}
    except SpeakerVerificationError:
        raise
    except (SecureStoreError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise SpeakerVerificationError("声纹档案无法读取；请重新录入。") from None


def delete_profile(path=SPEAKER_PROFILE_FILE):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise SpeakerVerificationError("无法删除本地声纹档案，请检查数据目录权限。") from exc


def profile_exists(path=SPEAKER_PROFILE_FILE):
    return Path(path).is_file()


@dataclass
class _ExtractorCacheEntry:
    """One immutable CAM++ model plus its serialization lock."""

    signature: tuple[int, int]
    model_hash: str
    extractor: object
    inference_lock: threading.Lock


# A speaker task is short lived, but the CAM++ weights are not.  This cache is
# deliberately process-scoped: it shares a single CPU extractor across the
# task threads, while each inference is serialized because sherpa-onnx does
# not promise that one extractor can create/compute streams concurrently.
_EXTRACTOR_CACHE: dict[str, _ExtractorCacheEntry] = {}
_EXTRACTOR_CACHE_LOCK = threading.RLock()


def _model_signature(path):
    stat = Path(path).stat()
    return int(stat.st_size), int(stat.st_mtime_ns)


def _check_model_hash(actual_hash, expected_hash):
    if expected_hash and actual_hash != str(expected_hash).upper():
        raise SpeakerVerificationError("声纹模型校验失败，请重新安装官方模型。")


def _create_extractor(model_path):
    """Create one native extractor.  Failures are never put in the cache."""
    try:
        import sherpa_onnx
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig()
        config.model = str(model_path)
        config.provider = "cpu"
        config.num_threads = 1
        if not config.validate():
            raise SpeakerVerificationError("声纹模型配置无效。")
        return sherpa_onnx.SpeakerEmbeddingExtractor(config)
    except SpeakerVerificationError:
        raise
    except Exception as exc:
        raise SpeakerVerificationError("声纹运行库不可用，请检查 sherpa-onnx 安装。") from exc


def _cached_extractor(model_path, expected_hash):
    """Return an extractor isolated by canonical path and on-disk model hash."""
    path = Path(model_path)
    if not path.is_file():
        raise SpeakerVerificationError("声纹模型尚未安装。")
    path = path.resolve()
    cache_key = os.path.normcase(str(path))

    # The lock includes model construction, so simultaneous SpeakerTask
    # instances cannot load duplicate native models for the same file.
    with _EXTRACTOR_CACHE_LOCK:
        signature = _model_signature(path)
        entry = _EXTRACTOR_CACHE.get(cache_key)
        if entry is not None and entry.signature == signature:
            _check_model_hash(entry.model_hash, expected_hash)
            return entry

        actual_hash = model_sha256(path)
        _check_model_hash(actual_hash, expected_hash)
        extractor = _create_extractor(path)
        entry = _ExtractorCacheEntry(signature, actual_hash, extractor, threading.Lock())
        # Replace only after successful construction.  An old entry is left
        # usable by an already-running verifier until it releases its Python
        # reference; new tasks will retry a failed replacement normally.
        _EXTRACTOR_CACHE[cache_key] = entry
        return entry


def clear_extractor_cache():
    """Release process-scoped native extractor references (also useful in tests)."""
    with _EXTRACTOR_CACHE_LOCK:
        _EXTRACTOR_CACHE.clear()


atexit.register(clear_extractor_cache)


class SpeakerVerifier:
    """CPU CAM++ embedding wrapper backed by the process-scoped model cache."""

    def __init__(self, model_path=SPEAKER_MODEL_FILE, expected_hash=SPEAKER_MODEL_SHA256):
        self.model_path = Path(model_path)
        entry = _cached_extractor(self.model_path, expected_hash)
        self.extractor = entry.extractor
        self._inference_lock = entry.inference_lock

    def embed(self, samples, *, min_seconds=MIN_SECONDS):
        quality = quality_check(samples, min_seconds=min_seconds)
        if not quality["ok"]:
            reasons = {"short": "录音太短，请完整说 5–8 秒。", "quiet": "录音音量太低。",
                       "clipped": "录音过载，请降低麦克风音量。"}
            raise SpeakerVerificationError(reasons.get(quality["reason"], "录音质量不合格。"))
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        with self._inference_lock:
            stream = self.extractor.create_stream()
            stream.accept_waveform(SAMPLE_RATE, audio.tolist())
            stream.input_finished()
            embedding = np.asarray(self.extractor.compute(stream), dtype=np.float32)
        if embedding.size == 0:
            raise SpeakerVerificationError("没有提取到稳定的声纹，请换安静环境重试。")
        return normalize_embedding(embedding)

    def enroll(self, segments):
        if len(segments) != 3:
            raise SpeakerVerificationError("需要完成三段录音。")
        embeddings = [self.embed(segment) for segment in segments]
        aggregate, info = aggregate_embeddings(embeddings)
        return aggregate, info

    def verify(self, samples, profile, threshold=DEFAULT_THRESHOLD):
        if not profile or "embedding" not in profile:
            return {"accepted": False, "score": 0.0, "reason": "not_enrolled"}
        # Wake audio is a real, short phrase.  Apply the lower verification
        # floor without padding/repeating it; this lets a 0.95–1.5 s complete
        # wake phrase reach CAM++ while still rejecting fragments and keeping
        # the conservative similarity threshold unchanged.
        try:
            embedding = self.embed(samples, min_seconds=VERIFY_MIN_SECONDS)
        except SpeakerVerificationError as exc:
            if "太短" in str(exc):
                raise SpeakerVerificationError("唤醒短句太短，请完整说 Hey Nova 或 Nova。") from None
            raise
        score = cosine_similarity(embedding, profile["embedding"])
        return {"accepted": bool(score >= threshold), "score": round(score, 4),
                "threshold": threshold, "reason": "match" if score >= threshold else "mismatch"}


class SpeakerTask(QThread):
    """Run model loading/inference away from the Qt GUI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, segments=None, samples=None, threshold=DEFAULT_THRESHOLD, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.segments = segments or []
        self.samples = samples
        self.threshold = threshold

    def _raise_if_interrupted(self):
        if self.isInterruptionRequested():
            raise _SpeakerTaskCancelled()

    def run(self):
        try:
            self._raise_if_interrupted()
            verifier = SpeakerVerifier()
            self._raise_if_interrupted()
            if self.operation == "enroll":
                embedding, info = verifier.enroll(self.segments)
                # A cancellation observed after native inference but before
                # save_profile means no profile write and no success signal.
                self._raise_if_interrupted()
                save_profile(embedding)
                # save_profile is an atomic replace.  Once it has completed,
                # a simultaneously arriving cancellation cannot roll back a
                # newly written profile without risking an older valid one.
                self._raise_if_interrupted()
                self.completed.emit({"operation": "enroll", **info, "dimension": int(embedding.size)})
            elif self.operation == "verify":
                self._raise_if_interrupted()
                profile = load_profile()
                self._raise_if_interrupted()
                result = verifier.verify(self.samples, profile, self.threshold)
                self._raise_if_interrupted()
                self.completed.emit({"operation": "verify", **result})
            else:
                raise SpeakerVerificationError("未知声纹操作。")
        except _SpeakerTaskCancelled:
            return
        except Exception as exc:
            self.failed.emit(str(exc) if isinstance(exc, SpeakerVerificationError) else "声纹处理失败，请稍后重试。")


class SpeakerRecorder(QObject):
    """Memory-only 16 kHz microphone recorder used by the enrollment wizard."""

    started = Signal(str)
    level = Signal(int)
    finished = Signal(object)
    failed = Signal(str)
    active_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = None
        self.stream = None
        self.format = None
        self.audio = bytearray()
        self.active = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.finish)

    def start(self, device_id="", maximum_ms=12000):
        if self.active:
            return False
        devices = QMediaDevices.audioInputs()
        device = next((item for item in devices if bytes(item.id()).hex() == str(device_id)), None)
        if device is None:
            device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.failed.emit("未找到麦克风。")
            return False
        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        self.format = fmt
        self.audio = bytearray()
        self.source = QAudioSource(device, fmt, self)
        self.source.setBufferSize(max(4096, fmt.bytesForDuration(200000)))
        self.stream = self.source.start()
        if self.stream is None or self.source.error() != QtAudio.Error.NoError:
            self.stop(quiet=True)
            self.failed.emit("麦克风打开失败，请检查设备权限。")
            return False
        self.stream.readyRead.connect(self.capture)
        self.active = True
        self.active_changed.emit(True)
        self.started.emit(device.description())
        self.timer.start(max(2000, int(maximum_ms)))
        return True

    def capture(self):
        if self.stream is None:
            return
        from .voice import pcm_float
        raw = bytes(self.stream.readAll())
        self.audio.extend(raw)
        samples = pcm_float(raw, self.format)
        rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        self.level.emit(min(100, round(rms * 600)))

    def _release(self):
        source, self.source = self.source, None
        if self.stream is not None:
            try:
                self.stream.readyRead.disconnect(self.capture)
            except (RuntimeError, TypeError):
                pass
        self.stream = None
        if source is not None:
            source.stop()
            source.deleteLater()
        self.timer.stop()
        self.level.emit(0)

    def finish(self):
        if not self.active:
            return
        self.capture()
        from .voice import pcm_float, resample_audio
        samples = pcm_float(self.audio, self.format)
        rate = self.format.sampleRate()
        self._release()
        self.audio.clear()
        self.active = False
        self.active_changed.emit(False)
        if rate != SAMPLE_RATE:
            samples = resample_audio(samples, rate)
        quality = quality_check(samples)
        if not quality["ok"]:
            reasons = {"short": "这段太短，请完整说 5–8 秒。", "quiet": "没有收到足够声音，请看音量条。",
                       "clipped": "音量过载，请降低麦克风音量。"}
            self.failed.emit(reasons.get(quality["reason"], "录音质量不合格，请重试。"))
            return
        self.finished.emit(np.asarray(samples, dtype=np.float32))

    def stop(self, quiet=False):
        was_active = self.active
        self._release()
        self.audio.clear()
        self.active = False
        if was_active:
            self.active_changed.emit(False)
            if not quiet:
                self.failed.emit("录音已取消。")
