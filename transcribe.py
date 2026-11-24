#!/usr/bin/env python3
"""Transcribe a voice note locally with the Hebrew-tuned Whisper model in ./models.
Usage: .venv/bin/python transcribe.py <audio file> [--lang he|en|auto]
Prints JSON: {"language": ..., "text": ..., "avg_logprob": ...}
"""
import argparse, json, os, sys
from faster_whisper import WhisperModel

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "ivrit-whisper-large-v3-turbo-ct2")

ap = argparse.ArgumentParser()
ap.add_argument("audio")
ap.add_argument("--lang", default="auto")
a = ap.parse_args()

model = WhisperModel(MODEL, device="cpu", compute_type="int8")
segments, info = model.transcribe(a.audio, language=None if a.lang == "auto" else a.lang,
                                  beam_size=5, vad_filter=True, condition_on_previous_text=False)
segs = list(segments)
text = " ".join(s.text.strip() for s in segs).strip()
lp = sum(s.avg_logprob for s in segs) / len(segs) if segs else None
print(json.dumps({"language": info.language, "language_prob": round(info.language_probability, 2),
                  "duration": round(info.duration, 1), "text": text,
                  "avg_logprob": round(lp, 2) if lp is not None else None}, ensure_ascii=False))
