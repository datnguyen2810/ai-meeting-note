"""Chấm bước phân người nói với file đáp án thời gian.

Chỉ chạy bộ phân người (pyannote nếu có HF_TOKEN và đã cài, ngược lại dùng bộ
phân cụm pitch/MFCC); không nạp PhoWhisper/Qwen.

Chạy từ thư mục ai-service:
    .\\venv\\Scripts\\python.exe -m tests.evaluate_diarization ^
        --audio ../data_test/demo_meeting/demo_meeting.wav ^
        --reference ../data_test/demo_meeting/demo_meeting_reference.json

    # So sánh tự đoán với số người nhập tay
    ... --num-speakers 3

File đáp án dạng JSON (ví dụ do data_test/demo_meeting/make_demo_audio.py tạo):
    {"segments": [{"speaker_id": "speaker_1", "start_seconds": 0.5,
                   "end_seconds": 10.9, "text": "..."}, ...]}
Với bản ghi người thật, gán nhãn tay theo cùng định dạng (nghe và ghi mốc giây).

Chỉ số:
- Gán đúng: phần trăm thời gian tiếng nói trong đáp án được gán đúng người,
  sau khi ghép mỗi cụm của hệ thống với đúng một người trong đáp án sao cho
  tổng thời gian trùng lớn nhất (thuật toán Hungarian).
- Bỏ sót: phần trăm thời gian tiếng nói trong đáp án không thuộc đoạn nào của hệ thống.
- Thứ tự nhãn: Người 1, 2... của hệ thống có trùng với thứ tự xuất hiện trong đáp án.
Độ phân giải 10 ms, không có vùng dung sai ở biên; không phải DER chuẩn.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

STEP = 0.01  # giây
PACKAGE_DIR = Path(__file__).resolve().parent.parent / "meeting_processing"


def load_module(name):
    # Nạp trực tiếp từng file để không kéo theo summarization/chat của package.
    spec = importlib.util.spec_from_file_location(f"{name}_eval", PACKAGE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def to_frames(segments, total, key_of, start_of, end_of):
    labels = np.full(total, "", dtype=object)
    for seg in segments:
        s = max(0, int(round(start_of(seg) / STEP)))
        e = min(total, int(round(end_of(seg) / STEP)))
        labels[s:e] = key_of(seg)
    return labels


def evaluate(reference, hypothesis):
    ref_segments = reference["segments"]
    end = max(
        [s["end_seconds"] for s in ref_segments] + [h["end"] for h in hypothesis] + [0.0]
    )
    total = int(np.ceil(end / STEP)) + 1

    ref = to_frames(ref_segments, total, lambda s: s["speaker_id"],
                    lambda s: s["start_seconds"], lambda s: s["end_seconds"])
    hyp = to_frames(hypothesis, total, lambda h: h["speaker_id"],
                    lambda h: h["start"], lambda h: h["end"])

    ref_ids = list(dict.fromkeys(s["speaker_id"] for s in ref_segments))
    hyp_ids = list(dict.fromkeys(h["speaker_id"] for h in hypothesis))
    speech = ref != ""
    speech_frames = int(speech.sum())

    # Ma trận số khung trùng giữa người trong đáp án và cụm của hệ thống
    overlap = np.zeros((len(ref_ids), max(1, len(hyp_ids))))
    for i, r in enumerate(ref_ids):
        for j, h in enumerate(hyp_ids):
            overlap[i, j] = np.sum((ref == r) & (hyp == h))
    rows, cols = linear_sum_assignment(-overlap)
    mapping = {hyp_ids[c]: ref_ids[r] for r, c in zip(rows, cols) if c < len(hyp_ids)}
    correct = sum(overlap[r, c] for r, c in zip(rows, cols) if c < len(hyp_ids))

    turns = []
    for seg in ref_segments:
        s = int(round(seg["start_seconds"] / STEP))
        e = int(round(seg["end_seconds"] / STEP))
        window = hyp[s:e]
        assigned = [x for x in window if x]
        if assigned:
            top = max(set(assigned), key=assigned.count)
            share = assigned.count(top) / max(1, len(window))
        else:
            top, share = None, 0.0
        turns.append({
            "segment_id": seg.get("segment_id"),
            "reference_speaker": seg["speaker_id"],
            "system_speaker": top,
            "mapped_to": mapping.get(top),
            "share": round(share, 3),
            "correct": mapping.get(top) == seg["speaker_id"],
        })

    return {
        "reference_speakers": len(ref_ids),
        "system_speakers": len(hyp_ids),
        "attribution_accuracy": round(correct / max(1, speech_frames), 4),
        "missed_speech": round(float(np.sum(speech & (hyp == ""))) / max(1, speech_frames), 4),
        "label_order_matches": all(h == r for h, r in mapping.items()),
        "mapping": mapping,
        "turns": turns,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--num-speakers", type=int, default=None,
                        help="Số người chính xác; bỏ trống để hệ thống tự đoán")
    parser.add_argument("--max-speakers", type=int, default=4)
    parser.add_argument("--output", type=Path, help="Ghi kết quả JSON")
    parser.add_argument("--raw", action="store_true",
                        help="Chấm kết quả thô của bộ phân người, bỏ qua bước dọn lượt nói của pipeline")
    parser.add_argument("--verbose", action="store_true", help="Hiện log của bộ phân người")
    parser.add_argument("--engine", choices=("auto", "acoustic"), default="auto",
                        help="auto: pyannote nếu dùng được, ngược lại pitch/MFCC; acoustic: ép dùng pitch/MFCC")
    args = parser.parse_args()

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    diarize = load_module("diarize")
    if args.engine == "acoustic":
        diarize.get_diarization_pipeline = lambda *a, **k: None

    log = io.StringIO()
    started = time.perf_counter()
    with contextlib.redirect_stdout(log):
        hypothesis, engine, warnings = diarize.diarize_with_engine(
            str(args.audio), max_speakers=args.max_speakers, device="cpu", num_speakers=args.num_speakers
        )
    elapsed = time.perf_counter() - started
    if args.verbose:
        print(log.getvalue().rstrip())
    print(f"Bộ phân người: {engine} ({elapsed:.1f} s, CPU, gồm cả nạp model)")
    for warning in warnings:
        print(f"Cảnh báo: {warning}")
    if not args.raw:
        # Cùng bước dọn lượt nói mà pipeline dùng trước khi chạy ASR
        hypothesis = load_module("turns").prepare_turns(hypothesis)

    result = evaluate(reference, hypothesis)
    result["audio"] = str(args.audio)
    result["engine"] = engine
    result["seconds"] = round(elapsed, 2)
    result["num_speakers_input"] = args.num_speakers
    result["postprocessed"] = not args.raw
    result["system_turns"] = len(hypothesis)

    mode = f"số người nhập tay = {args.num_speakers}" if args.num_speakers else "tự đoán số người"
    print(f"Chế độ: {mode}, {'kết quả thô' if args.raw else 'đã dọn lượt nói như pipeline'}")
    print(f"Số lượt hệ thống: {len(hypothesis)} (đáp án {len(reference['segments'])})")
    print(f"Số người: đáp án {result['reference_speakers']}, hệ thống {result['system_speakers']}")
    print(f"Gán đúng: {100 * result['attribution_accuracy']:.1f}% thời gian tiếng nói")
    print(f"Bỏ sót: {100 * result['missed_speech']:.1f}%")
    print(f"Thứ tự nhãn đúng: {'có' if result['label_order_matches'] else 'không'} {result['mapping']}")
    wrong = [t for t in result["turns"] if not t["correct"]]
    print(f"Lượt gán sai: {len(wrong)}/{len(result['turns'])}")
    for t in wrong:
        print(f"  {t['segment_id']}: đáp án {t['reference_speaker']} -> hệ thống {t['system_speaker']} "
              f"({100 * t['share']:.0f}% lượt), cụm này được ghép với {t['mapped_to']}")

    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã ghi {args.output}")


if __name__ == "__main__":
    main()
