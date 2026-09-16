"""On-demand microphone capture and cancellable local Whisper recognition. No TTS."""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices, QtAudio

from .paths import MODEL_DIR, FROZEN, APP_DIR


def pcm_float(raw, fmt):
    types = {QAudioFormat.SampleFormat.UInt8: ('u1', 128., 128.),
             QAudioFormat.SampleFormat.Int16: ('<i2', 0., 32768.),
             QAudioFormat.SampleFormat.Int32: ('<i4', 0., 2147483648.),
             QAudioFormat.SampleFormat.Float: ('<f4', 0., 1.)}
    dtype, offset, scale = types[fmt.sampleFormat()]
    frame = np.dtype(dtype).itemsize * fmt.channelCount()
    size = len(raw) // frame * frame
    if not size:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(raw[:size], dtype=dtype).astype(np.float32)
    return ((samples - offset) / scale).reshape(-1, fmt.channelCount()).mean(axis=1)


def resample_audio(samples, rate):
    if rate == 16000:
        return samples.astype(np.float32)
    import av
    frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='fltp', layout='mono')
    frame.sample_rate = rate
    converter = av.AudioResampler(format='fltp', layout='mono', rate=16000)
    frames = converter.resample(frame) + converter.resample(None)
    return np.concatenate([f.to_ndarray().flatten() for f in frames]).astype(np.float32)


class VoiceInput(QObject):
    transcript = Signal(str)
    status = Signal(str)
    active_changed = Signal(bool)
    level = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.source = None
        self.stream = None
        self.phase = 'idle'
        self.audio = bytearray()
        self.buffer = b''
        self.received = False
        self.auto_finish = False
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.timeout)
        self.audio_watch = QTimer(self)
        self.audio_watch.setInterval(150)
        self.audio_watch.timeout.connect(self.audio_state)

    @property
    def active(self):
        return self.phase != 'idle'

    def start(self, device_id='', auto_finish=False):
        if self.active:
            return
        if not (MODEL_DIR / 'model.bin').is_file():
            self.status.emit('本地语音模型尚未安装完成，请先完成语音模型准备。')
            return
        devices = QMediaDevices.audioInputs()
        device = next((d for d in devices if bytes(d.id()).hex() == device_id), None)
        if device is None:
            device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.status.emit('未找到麦克风，请在语音页选择可用输入设备。')
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        self.format = fmt
        self.auto_finish = auto_finish
        self.speech_seen = False
        self.record_started = self.last_speech = time.monotonic()
        self.audio = bytearray()
        self.source = QAudioSource(device, fmt, self)
        self.source.setBufferSize(max(4096, fmt.bytesForDuration(100000)))
        self.stream = self.source.start()
        if self.stream is None or self.source.error() != QtAudio.Error.NoError:
            self.stop(quiet=True)
            self.status.emit('麦克风打开失败，请检查设备是否被占用或未获权限。')
            return
        self.phase = 'recording'
        self.stream.readyRead.connect(self.capture)
        # PySide6 6.11.2 cannot marshal QAudio::State reliably on this machine.
        self.audio_watch.start()
        self.active_changed.emit(True)
        self.deadline.start(30000)
        self.status.emit('我在听，说完停顿一下即可。' if auto_finish else '正在听（' + device.description() + '）。说完点「完成」，最长 30 秒。')

    def audio_state(self):
        if self.source is not None and self.source.error() != QtAudio.Error.NoError:
            self.stop(quiet=True)
            self.status.emit('麦克风已断开或采集失败，请重新选择输入设备。')

    def capture(self):
        if self.stream is None:
            return
        raw = bytes(self.stream.readAll())
        self.audio.extend(raw)
        samples = pcm_float(raw, self.format)
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.
        self.level.emit(min(100, round(rms * 600)))
        if self.auto_finish:
            now = time.monotonic()
            if rms > .008:
                self.speech_seen = True
                self.last_speech = now
            if self.speech_seen and now - self.last_speech > 1.2:
                self.auto_finish = False
                QTimer.singleShot(0, self.finish_recording)
            elif not self.speech_seen and now - self.record_started > 8:
                self.auto_finish = False
                QTimer.singleShot(0, self.finish_recording)

    def release_audio(self):
        self.audio_watch.stop()
        source, self.source = self.source, None
        if self.stream is not None:
            self.stream.readyRead.disconnect(self.capture)
        self.stream = None
        if source is not None:
            source.stop()
            source.deleteLater()
        self.level.emit(0)

    def finish_recording(self):
        if self.phase != 'recording':
            return
        self.capture()
        self.release_audio()
        samples = pcm_float(self.audio, self.format)
        self.audio.clear()
        if samples.size < self.format.sampleRate() * .3 or np.sqrt(np.mean(samples * samples)) < .001:
            self.stop(quiet=True)
            self.status.emit('几乎没有收到声音。请在语音页选择实际麦克风，确认音量条会动，再试一次。')
            return
        samples = resample_audio(samples, self.format.sampleRate())
        self.recognize(samples)

    def recognize(self, samples):
        self.phase = 'recognizing'
        self.buffer = b''
        self.received = False
        program = Path(APP_DIR / 'CocoSpeech.exe') if FROZEN else Path(sys.executable)
        arguments = [str(MODEL_DIR)] if FROZEN else ['-m', 'coco.transcribe_worker', str(MODEL_DIR)]
        if FROZEN and not program.is_file():
            self.stop(quiet=True)
            self.status.emit('独立语音程序不存在，请重新解压完整的 Nova 包。')
            return
        process = QProcess(self)
        self.process = process
        process.setProgram(str(program))
        process.setWorkingDirectory(str(APP_DIR))
        process.setArguments(arguments)
        process.readyReadStandardOutput.connect(lambda: self.read(process))
        process.finished.connect(lambda *_: self.finished(process))
        process.errorOccurred.connect(lambda _: self.failed(process))
        payload = samples.astype('<f4').tobytes()
        process.started.connect(lambda: self.write_audio(process, payload))
        self.active_changed.emit(True)
        self.status.emit('录音已结束，正在本机识别中文… 可以取消。')
        self.deadline.start(90000)
        process.start()

    def write_audio(self, process, payload):
        if process is self.process:
            process.write(payload)
            process.closeWriteChannel()

    def read(self, process):
        if process is not self.process:
            return
        self.buffer += bytes(process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                item = json.loads(line.decode('utf-8-sig'))
            except (UnicodeError, ValueError):
                continue
            if 'text' in item:
                self.received = True
                text = str(item['text']).strip()[:2000]
                self.stop(quiet=True)
                if text:
                    self.transcript.emit(text)
                else:
                    self.status.emit('没有识别到清晰语音，请靠近麦克风再说一次。')
                return
            if 'error' in item:
                self.received = True
                self.stop(quiet=True)
                self.status.emit('本地识别失败，请检查语音模型和依赖是否完整。')
                return

    def finished(self, process):
        if process is self.process:
            self.read(process)
            if process is self.process:
                self.stop(quiet=True)
                self.status.emit('识别进程未正常返回，请重试或检查本地模型。')

    def failed(self, process):
        if process is self.process:
            self.stop(quiet=True)
            self.status.emit('无法启动本地识别，请检查 Python 语音依赖。')

    def timeout(self):
        if self.phase == 'recording':
            self.finish_recording()
        else:
            self.stop(quiet=True)
            self.status.emit('本次识别超时，已取消。请缩短句子后重试。')

    def stop(self, quiet=False):
        was_active = self.active
        self.deadline.stop()
        self.release_audio()
        self.audio.clear()
        process, self.process = self.process, None
        self.phase = 'idle'
        if process is not None:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
            process.deleteLater()
        if was_active:
            self.active_changed.emit(False)
            if not quiet:
                self.status.emit('已取消，麦克风已关闭。')
