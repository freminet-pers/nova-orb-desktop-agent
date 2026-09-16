"""Isolated local Whisper process for dictation and English wake windows."""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys


def load_model(path):
    import os
    from faster_whisper import WhisperModel
    return WhisperModel(path, device="cpu", compute_type="int8",
                        cpu_threads=max(1, min(8, os.cpu_count() or 1)),
                        local_files_only=True)


def recognize(model, audio, language):
    kwargs = {
        "language": language,
        # Wake phrases are short and still require an exact full-match gate;
        # greedy decoding lowers hot-path latency without widening activation.
        "beam_size": 1 if language == "en" else 5,
        "vad_filter": True,
        "condition_on_previous_text": False,
        "temperature": 0,
    }
    if language != "en":
        kwargs["initial_prompt"] = "简体中文对话。"
    segments, _ = model.transcribe(audio, **kwargs)
    parts = []
    avg_logprobs = []
    no_speech = []
    for part in segments:
        text = str(part.text or "")
        if text.strip():
            parts.append(text)
        if getattr(part, "avg_logprob", None) is not None:
            avg_logprobs.append(float(part.avg_logprob))
        if getattr(part, "no_speech_prob", None) is not None:
            no_speech.append(float(part.no_speech_prob))
    text = "".join(parts).strip()
    # Whisper has no universal confidence field.  This conservative score
    # combines segment log probability and the model's no-speech probability;
    # the UI still requires an exact full wake phrase afterwards.
    logprob = sum(avg_logprobs) / len(avg_logprobs) if avg_logprobs else -10.0
    silence = sum(no_speech) / len(no_speech) if no_speech else 1.0
    confidence = max(0.0, min(1.0, math.exp(min(0.0, logprob)))) * (1.0 - max(0.0, min(1.0, silence)))
    return text, confidence


def read_exact(stream, size):
    chunks = []
    remaining = size
    while remaining:
        part = stream.read(remaining)
        if not part:
            return None
        chunks.append(part)
        remaining -= len(part)
    return b"".join(chunks)


def stream_mode(model, language="en"):
    import numpy as np
    sys.stdout.write(json.dumps({"ready": True, "language": language}) + "\n")
    sys.stdout.flush()
    while True:
        header = read_exact(sys.stdin.buffer, 4)
        if header is None:
            return
        size = struct.unpack("<I", header)[0]
        if size <= 0 or size > 16000 * 4 * 8:
            print(json.dumps({"text": "", "confidence": 0}), flush=True)
            continue
        payload = read_exact(sys.stdin.buffer, size)
        if payload is None:
            return
        audio = np.frombuffer(payload, dtype="<f4").copy()
        text, confidence = recognize(model, audio, language)
        print(json.dumps({"text": text, "confidence": round(confidence, 4)}, ensure_ascii=True), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir")
    parser.add_argument("--language", choices=("zh", "en"), default="zh")
    parser.add_argument("--wake-stream", action="store_true")
    parser.add_argument("--speaker-smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.speaker_smoke:
        from .speaker_verification import SpeakerVerifier
        verifier = SpeakerVerifier(args.model_dir)
        print(json.dumps({"ready": True, "speaker_dim": int(verifier.extractor.dim)}), flush=True)
        return
    import numpy as np
    model = load_model(args.model_dir)
    if args.wake_stream:
        stream_mode(model, "en")
        return
    audio = np.frombuffer(sys.stdin.buffer.read(16000 * 4 * 31), dtype="<f4").copy()
    text, _ = recognize(model, audio, args.language)
    print(json.dumps({"text": text}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}), flush=True)
        raise SystemExit(1)
