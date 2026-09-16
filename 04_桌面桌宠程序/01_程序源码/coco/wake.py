"""Local English wake listener backed by a constrained Whisper stream.

Windows on this machine only exposes a Chinese System.Speech recognizer.  The
assistant therefore does not send Chinese audio through an English grammar or
fall back to substring matching.  When enabled, this module captures short
VAD-gated microphone windows and sends them to the independent Whisper worker
with ``language='en'``.  A wake event is emitted only for one of the complete
phrases in :data:`WAKE_PHRASES`.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import struct
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio

from .paths import APP_DIR, FROZEN, MODEL_DIR


WAKE_PHRASES = (
    "nova",
    "hey nova",
    "hi nova",
    "hello nova",
    "are you there nova",
    "nova are you there",
    "okay nova",
    "ok nova",
    "nova can you help",
    "nova can you help me",
    "nova help me",
)
# The local small model scores a clean synthetic ``Hey Nova`` at about
# 0.50, while exact phrase matching remains the stronger false-positive gate.
# Keep a floor so low-confidence fragments cannot wake the assistant.
WAKE_CONFIDENCE = 0.48
MAX_RESTARTS = 3
RESTART_WINDOW_SECONDS = 60.0
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize_wake_text(text: str) -> str:
    """Normalize punctuation/case while preserving phrase boundaries."""
    value = str(text or "").replace("’", "'").casefold()
    value = _PUNCTUATION.sub(" ", value)
    return _SPACE.sub(" ", value).strip()


def is_wake_phrase(text: str, phrases=WAKE_PHRASES) -> bool:
    """Return true only when the whole recognition is one allowed phrase."""
    value = normalize_wake_text(text)
    allowed = {normalize_wake_text(item) for item in phrases}
    return bool(value) and value in allowed


def canonical_phrases(value: str | None = None) -> tuple[str, ...]:
    """Migrate old/custom settings to the fixed explicit English phrase set."""
    if value and normalize_wake_text(value) in {normalize_wake_text(p) for p in WAKE_PHRASES}:
        chosen = normalize_wake_text(value)
        return tuple(dict.fromkeys((chosen, *WAKE_PHRASES)))
    return WAKE_PHRASES


class WakeListener(QObject):
    awakened = Signal()
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process: QProcess | None = None
        self.source: QAudioSource | None = None
        self.stream = None
        self.format = None
        self.buffer = bytearray()
        self.process_buffer = b""
        self.worker_ready = False
        self.worker_busy = False
        self.failed = False
        self.phrases = WAKE_PHRASES
        self.device_id = ""
        self.started_at = 0.0
        self.ready_at = 0.0
        self.last_send_at = 0.0
        self.last_samples = None
        self.last_phrase = "hey nova"
        self.restart_attempts = 0
        self.restart_window_started = 0.0
        self.generation = 0
        self.intentional_stop = False
        self.flush_ticks = 0
        self.short_windows = 0
        self.silence_windows = 0
        self.tail_windows = 0
        self.sent_windows = 0
        self.result_count = 0
        self.logger = logging.getLogger("coco.wake")
        self.flush_timer = QTimer(self)
        # Short rolling windows let a completed name be checked soon after its
        # tail silence.  Back-pressure below prevents overlapping inferences.
        self.flush_timer.setInterval(700)
        self.flush_timer.timeout.connect(self.flush_window)

    @property
    def active(self):
        return self.process is not None or self.source is not None

    def _worker_command(self):
        if FROZEN:
            return str(Path(APP_DIR) / "CocoSpeech.exe"), [str(MODEL_DIR), "--wake-stream"]
        return str(sys.executable), ["-m", "coco.transcribe_worker", str(MODEL_DIR), "--wake-stream"]

    def start(self, phrase=None, device_id=""):
        if self.active or self.failed:
            return
        if not (MODEL_DIR / "model.bin").is_file():
            self.failed = True
            self.status.emit("英文唤醒不可用：本地 Whisper 模型尚未安装；仍可用中键手动语音。")
            return
        self.phrases = canonical_phrases(phrase)
        self.last_phrase = str(phrase or "hey nova")
        self.device_id = device_id or ""
        self.intentional_stop = False
        self.generation += 1
        self.started_at = time.monotonic()
        self.ready_at = 0.0
        self.last_send_at = 0.0
        devices = QMediaDevices.audioInputs()
        device = next((d for d in devices if bytes(d.id()).hex() == self.device_id), None)
        if device is None:
            device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.failed = True
            self.status.emit("英文唤醒不可用：未找到麦克风；仍可用中键手动语音。")
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        self.format = fmt
        program, args = self._worker_command()
        if FROZEN and not Path(program).is_file():
            self.failed = True
            self.status.emit("英文唤醒不可用：独立语音程序不存在；仍可用中键手动语音。")
            return
        process = QProcess(self)
        self.process = process
        self.process_buffer = b""
        self.worker_ready = False
        self.worker_busy = False
        process.setProgram(program)
        process.setArguments(args)
        process.setWorkingDirectory(str(APP_DIR))
        generation = self.generation
        process.readyReadStandardOutput.connect(lambda p=process, g=generation: self.read_worker(p, g))
        process.errorOccurred.connect(lambda *_args, p=process, g=generation: self.worker_error(p, g))
        process.finished.connect(lambda *_args, p=process, g=generation: self.worker_error(p, g))
        process.start()
        if not process.waitForStarted(2500):
            self.worker_error(process)
            return
        self.source = QAudioSource(device, fmt, self)
        self.source.setBufferSize(max(4096, fmt.bytesForDuration(250000)))
        self.stream = self.source.start()
        if self.stream is None or self.source.error() != QtAudio.Error.NoError:
            self.stop()
            self.failed = True
            self.status.emit("英文唤醒不可用：麦克风打开失败；仍可用中键手动语音。")
            return
        self.stream.readyRead.connect(self.capture)
        self.buffer.clear()
        self.flush_timer.start()
        self.status.emit("正在准备英文唤醒识别（仅完整呼叫 Nova）…")

    def reset_failures(self):
        """Allow an explicit user retry to start a fresh restart budget."""
        self.failed = False
        self.restart_attempts = 0
        self.restart_window_started = 0.0

    def capture(self):
        if self.stream is not None:
            self.buffer.extend(bytes(self.stream.readAll()))
            # QAudioSource commonly delivers sub-window chunks. Keep a
            # bounded rolling tail until the flush decision is made.
            self._trim_buffer()

    def _trim_buffer(self):
        if self.format is None:
            return
        try:
            maximum = max(4096, int(self.format.bytesForDuration(6_000_000)))
        except (AttributeError, TypeError, ValueError):
            maximum = 16000 * 4 * 6
        if len(self.buffer) > maximum:
            del self.buffer[:-maximum]

    def flush_window(self):
        if not self.worker_ready or self.worker_busy or self.stream is None or self.process is None:
            return
        if not self.buffer:
            return
        self.flush_ticks += 1
        raw = bytes(self.buffer)
        try:
            from .voice import pcm_float, resample_audio
            samples = pcm_float(raw, self.format)
            if self.format.sampleRate() != 16000:
                samples = resample_audio(samples, self.format.sampleRate())
        except Exception:
            return
        # Keep a short rolling tail while waiting for the first complete name;
        # a name followed by a brief pause is normally available by 0.95 s.
        if samples.size < 16000 * 0.95:
            self.short_windows += 1
            self._trim_buffer()
            return
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
        if not math.isfinite(rms) or rms < 0.006:
            self.silence_windows += 1
            self._trim_buffer()
            return
        tail = samples[-min(samples.size, 3200):]
        tail_rms = float(np.sqrt(np.mean(tail * tail))) if tail.size else 0.0
        if tail_rms > 0.012 and samples.size < 16000 * 2.5:
            # Wait for a short tail pause so the next inference sees the whole
            # call instead of repeatedly recognizing a clipped prefix.
            self.tail_windows += 1
            self._trim_buffer()
            return
        samples = samples[-16000 * 3:].astype("<f4", copy=False)
        # Keep this candidate only in memory until the controller has decided
        # whether the optional speaker gate is enabled.  It is cleared after
        # that decision and is never written to logs or disk.
        self.last_samples = samples.copy()
        payload = samples.tobytes()
        self.worker_busy = True
        self.last_send_at = time.monotonic()
        self.sent_windows += 1
        self.logger.info("wake window send elapsed_ms=%.0f audio_ms=%.0f", (self.last_send_at - self.started_at) * 1000, samples.size / 16)
        self.process.write(struct.pack("<I", len(payload)) + payload)
        self.buffer.clear()

    def read_worker(self, process, generation=None):
        if process is not self.process or (generation is not None and generation != self.generation):
            return
        self.process_buffer += bytes(process.readAllStandardOutput())
        while b"\n" in self.process_buffer:
            line, self.process_buffer = self.process_buffer.split(b"\n", 1)
            try:
                item = json.loads(line.decode("utf-8-sig"))
            except (UnicodeError, ValueError):
                continue
            if item.get("ready"):
                self.worker_ready = True
                self.ready_at = time.monotonic()
                self.logger.info("wake worker ready cold_ms=%.0f", (self.ready_at - self.started_at) * 1000)
                self.status.emit("英文唤醒已开启 · 只接受完整呼叫 Nova / hey Nova / are you there Nova 等固定句式")
                continue
            if item.get("error"):
                self.worker_error(process, generation, reason="worker_error")
                return
            self.worker_busy = False
            self.result_count += 1
            text = str(item.get("text", ""))
            confidence = float(item.get("confidence", 0) or 0)
            matched = confidence >= WAKE_CONFIDENCE and is_wake_phrase(text, self.phrases)
            self.logger.info("wake result elapsed_ms=%.0f infer_ms=%.0f confidence=%.3f matched=%s", (time.monotonic() - self.started_at) * 1000, (time.monotonic() - self.last_send_at) * 1000 if self.last_send_at else 0, confidence, matched)
            if matched:
                self.logger.info("wake phrase matched result_count=%d sent_windows=%d", self.result_count, self.sent_windows)
                self.status.emit("听到你叫 Nova 了，请说下一句…")
                candidate = self.last_samples
                self.stop()
                owner = self.parent()
                handler = getattr(owner, "handle_wake_candidate", None) if owner is not None else None
                if callable(handler):
                    handler(candidate)
                else:
                    self.awakened.emit()

    def worker_error(self, process, generation=None, reason="worker_exit"):
        if process is not self.process or (generation is not None and generation != self.generation):
            return
        if self.intentional_stop:
            self._stop_resources()
            return
        self._stop_resources()
        now = time.monotonic()
        if now - self.restart_window_started > RESTART_WINDOW_SECONDS:
            self.restart_attempts = 0
            self.restart_window_started = now
        self.restart_attempts += 1
        if self.restart_attempts > MAX_RESTARTS:
            self.failed = True
            self.status.emit("英文唤醒不可用：语音进程连续异常，已暂停；请点应用唤醒词重试。")
            self.logger.error("wake restart limit reached reason=%s", reason)
            return
        delay_ms = min(8000, 1000 * (2 ** (self.restart_attempts - 1)))
        generation = self.generation
        self.failed = False
        self.status.emit(f"英文唤醒进程异常，正在第 {self.restart_attempts} 次重试…")
        self.logger.warning("wake restart scheduled attempt=%d delay_ms=%d reason=%s", self.restart_attempts, delay_ms, reason)
        QTimer.singleShot(delay_ms, lambda g=generation: self._restart_if_current(g))

    def _restart_if_current(self, generation):
        if generation != self.generation or self.intentional_stop or self.active:
            return
        owner = self.parent()
        if owner is not None:
            if getattr(owner, "stopping", False) or getattr(owner, "busy", False):
                wake_timer = getattr(owner, "wake_timer", None)
                if wake_timer is not None and not getattr(owner, "stopping", False):
                    wake_timer.start(1500)
                return
            service = getattr(owner, "service", None)
            if service is not None and not service.setting("wake_enabled", False):
                return
        self.start(self.last_phrase, self.device_id)

    def _stop_resources(self):
        self.generation += 1
        self.flush_timer.stop()
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
        process, self.process = self.process, None
        self.worker_ready = False
        self.worker_busy = False
        self.buffer.clear()
        self.process_buffer = b""
        # The candidate is passed by reference to the controller's short-lived
        # speaker task.  Drop the listener's owning reference whenever the
        # worker/audio resources stop so a failed, cancelled, or stale wake
        # cannot retain microphone samples until the next start.
        self.last_samples = None
        if process is not None:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
            process.deleteLater()

    def stop(self):
        self.intentional_stop = True
        self._stop_resources()
