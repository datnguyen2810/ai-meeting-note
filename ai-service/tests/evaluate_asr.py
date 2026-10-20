"""Compare decoding on the SAME saved audio, using only cached PhoWhisper.

python -m tests.evaluate_asr --audio ../data_test/test_2.mp3 --output temp_asr.json
Add --reference path/to/manually_verified_transcript.txt to measure normalized WER.
Never treat another model's transcript as ground truth.
"""

import argparse
import json
from pathlib import Path
import re
import sys
import time
import unicodedata


def normalize(text):
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", text).casefold()).split())


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default=None)
    parser.add_argument("--beams", type=int, nargs="+", default=[1, 5])
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error("Audio file does not exist")
    import librosa
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model_id = "vinai/PhoWhisper-small"
    processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(model_id, local_files_only=True).to(device).eval()
    asr = pipeline("automatic-speech-recognition", model=model, tokenizer=processor.tokenizer,
                   feature_extractor=processor.feature_extractor, device=device, chunk_length_s=30)
    speech, _ = librosa.load(args.audio, sr=16000, mono=True)
    reference = args.reference.read_text(encoding="utf-8") if args.reference else None
    reports = []
    for beams in args.beams:
        if beams < 1:
            parser.error("beams must be positive")
        started = time.perf_counter()
        kwargs = {"language": "vietnamese", "task": "transcribe", "do_sample": False, "num_beams": beams}
        with torch.inference_mode():
            text = asr(speech, generate_kwargs=kwargs)["text"].strip()
        report = dict(num_beams=beams, audio=str(args.audio), audio_seconds=round(len(speech)/16000, 2),
                      seconds=round(time.perf_counter()-started, 2), transcript=text)
        if reference is not None:
            from jiwer import wer
            report["wer"] = wer(normalize(reference), normalize(text))
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if args.output:
            args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
