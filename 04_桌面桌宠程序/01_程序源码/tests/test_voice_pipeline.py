import json
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, Signal, QProcess
from PySide6.QtMultimedia import QAudioFormat

from coco.voice import VoiceInput, pcm_float, resample_audio


class FakeProcess(QObject):
    started = Signal()
    readyReadStandardOutput = Signal()
    finished = Signal(int, int)
    errorOccurred = Signal(int)
    ProcessState = QProcess.ProcessState

    def __init__(self, parent):
        super().__init__(parent)
        self.output = b''
        self.killed = False

    def setProgram(self, program):
        self.program = program

    def setWorkingDirectory(self, path):
        self.cwd = path

    def setArguments(self, args):
        self.args = args

    def start(self):
        pass

    def state(self):
        return self.ProcessState.Running

    def kill(self):
        self.killed = True

    def waitForFinished(self, timeout):
        return True

    def readAllStandardOutput(self):
        output, self.output = self.output, b''
        return output


class VoicePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.voice = VoiceInput()
        self.messages = []
        self.voice.status.connect(self.messages.append)
        self.patch = patch('coco.voice.QProcess', FakeProcess)
        self.patch.start()

    def tearDown(self):
        self.voice.stop(quiet=True)
        self.patch.stop()

    def test_microphone_closed_before_transcript_and_partial_utf8(self):
        self.assertFalse(self.voice.active)
        result = []
        self.voice.transcript.connect(lambda text: result.append((text, self.voice.active)))
        self.voice.recognize(np.zeros(16000, dtype=np.float32))
        process = self.voice.process
        self.assertIn('coco.transcribe_worker', process.args)
        line = (json.dumps({'text': '打开计算器'}, ensure_ascii=False) + '\n').encode()
        process.output = line[:12]
        self.voice.read(process)
        self.assertEqual(result, [])
        process.output = line[12:]
        self.voice.read(process)
        self.assertEqual(result, [('打开计算器', False)])
        self.assertTrue(process.killed)

    def test_cancel_discards_late_result(self):
        result = []
        self.voice.transcript.connect(result.append)
        self.voice.recognize(np.zeros(16000, dtype=np.float32))
        process = self.voice.process
        self.voice.stop()
        process.output = b'{"text":"late"}\n'
        self.voice.read(process)
        self.assertEqual(result, [])
        self.assertFalse(self.voice.active)
        self.assertTrue(process.killed)

    def test_timeout_closes_process(self):
        self.voice.recognize(np.zeros(16000, dtype=np.float32))
        process = self.voice.process
        self.voice.timeout()
        self.assertTrue(process.killed)
        self.assertFalse(self.voice.active)
        self.assertIn('超时', self.messages[-1])

    def test_silence_never_sent_to_recognition(self):
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.voice.format = fmt
        self.voice.phase = 'recording'
        self.voice.audio = bytearray(32000)
        self.voice.finish_recording()
        self.assertFalse(self.voice.active)
        self.assertIsNone(self.voice.process)
        self.assertIn('几乎没有', self.messages[-1])

    def test_stereo_float_input_resampled_with_correct_duration(self):
        fmt = QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        mono = np.sin(np.arange(48000) * 2 * np.pi * 440 / 48000).astype(np.float32) * .2
        pcm = np.column_stack([mono, mono]).astype('<f4').tobytes()
        decoded = pcm_float(pcm, fmt)
        np.testing.assert_allclose(decoded, mono)
        converted = resample_audio(decoded, 48000)
        self.assertEqual(len(converted), 16000)
        self.assertAlmostEqual(float(np.sqrt(np.mean(converted ** 2))), .1414, places=3)


if __name__ == '__main__':
    unittest.main()
