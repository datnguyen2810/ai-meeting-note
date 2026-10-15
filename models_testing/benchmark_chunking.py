#!/usr/bin/env python
"""
=============================================================================
PHASE 0 — DE-RISK SPIKE
Đo WER và độ trễ của từng chính sách cắt chunk cho engine realtime (Wav2Vec2).
=============================================================================

Vì sao cần script này: toàn bộ đồ án đang đứng trên một giả định chưa ai kiểm
chứng — "Wav2Vec2 decode trên cụm từ ngắn ra được text dùng được". Chưa ai biết
câu trả lời. Nếu giả định sai thì phải đổi model hoặc đổi kiến trúc, và phát
hiện điều đó ở Phase 3 sẽ là thảm hoạ. Xem mục 5 của PLAN_REALTIME_HYBRID_ASR.md.

Script dùng CHUNG module vad_buffer.py với ai-service/, nên số đo ở đây chính
là hành vi thật của hệ thống ở Phase 1 — không có chuyện benchmark lệch production.

-----------------------------------------------------------------------------
CÁCH CHẠY
-----------------------------------------------------------------------------
# Cách 1 — bộ VIVOS (có ground truth, cho số WER dùng được trong báo cáo)
python benchmark_chunking.py --vivos-root /duong/dan/toi/vivos --limit 50

# Cách 2 — file manifest tự tạo (TSV: đường_dẫn<TAB>câu_đúng)
python benchmark_chunking.py --manifest manifest.tsv

# Cách 3 — CHỈ nghe cảm nhận, không có ground truth (Phase 0.5)
python benchmark_chunking.py --qualitative ../data_test/test_2.mp3

# Cách 4 — trả lời dứt điểm "6GB VRAM có đủ cho 3 model không" (Phase 0.4)
python benchmark_chunking.py --measure-full-vram

-----------------------------------------------------------------------------
ĐỊNH NGHĨA ĐỘ TRỄ (đọc kỹ, đừng để hội đồng hỏi xoáy)
-----------------------------------------------------------------------------
Với một chunk dài D (ms) và thời gian inference I (ms):
  - Âm thanh ở ĐẦU chunk phải chờ D + I ms mới hiện lên màn hình (xấu nhất)
  - Âm thanh ở CUỐI chunk chỉ chờ I ms (tốt nhất)
  - Trung bình = D/2 + I

Script báo cáo TRUNG BÌNH (D/2 + I) làm số chính, kèm p95 của cùng đại lượng.
Đây là cách tính chuẩn khi đánh giá streaming ASR. KHÔNG được lấy I (thời gian
inference thuần) rồi gọi đó là "độ trễ" — đó là lỗi của bản plan 1.0.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Windows console mặc định là cp1252 -> in tiếng Việt sẽ crash. Phải ép UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# vad_buffer.py nằm ở ai-service/ — dùng chung, KHÔNG copy sang đây
_AI_SERVICE = Path(__file__).resolve().parent.parent / "ai-service"
if str(_AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(_AI_SERVICE))

from vad_buffer import (  # noqa: E402
    DEFAULT_MAX_UTTERANCE_MS,
    DEFAULT_MIN_SPEECH_MS,
    DEFAULT_SILENCE_MS,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    UtteranceBuffer,
    VadGate,
    pcm_to_float32,
)

MODEL_ID = "nguyenvulebinh/wav2vec2-base-vietnamese-250h"

# Các chính sách cắt chunk sẽ đem ra so sánh
POLICIES = ["full", "fixed_500", "fixed_800", "fixed_1500", "vad"]


# =============================================================================
# Chuẩn hoá text & tính WER
# =============================================================================
def clean_text(text: str) -> str:
    """
    Giống hệt notebook benchmark cũ của nhóm để số liệu so sánh được với nhau:
    lowercase, bỏ dấu câu. Lưu ý \\w trong Python là Unicode-aware nên dấu
    tiếng Việt (ế, ộ, ữ...) ĐƯỢC GIỮ LẠI — đúng như mong muốn.
    """
    text = text.lower().strip()
    return re.sub(r"[^\w\s]", "", text)


def compute_wer(refs: list[str], hyps: list[str]):
    """
    WER toàn bộ tập (corpus-level), không phải trung bình WER từng file.
    Corpus-level là cách tính đúng theo chuẩn — trung bình từng file sẽ cho
    trọng số sai (file ngắn được coi ngang file dài).
    """
    try:
        import jiwer
    except ImportError:
        print("\n[!] Thiếu thư viện jiwer. Cài bằng:  pip install jiwer")
        return None

    refs = [clean_text(r) for r in refs]
    hyps = [clean_text(h) for h in hyps]

    # jiwer ném ValueError nếu reference rỗng -> loại các cặp đó ra
    pairs = [(r, h) for r, h in zip(refs, hyps) if r.strip()]
    skipped = len(refs) - len(pairs)
    if skipped:
        print(f"    (bỏ qua {skipped} mẫu vì ground truth rỗng)")

    if not pairs:
        return None

    r_list, h_list = zip(*pairs)
    try:
        return float(jiwer.wer(list(r_list), list(h_list)))
    except Exception as exc:
        print(f"    [!] jiwer lỗi ({exc}), thử tính từng file rồi lấy trung bình")
        vals = []
        for r, h in pairs:
            try:
                vals.append(jiwer.wer(r, h))
            except Exception:
                pass
        return float(statistics.mean(vals)) if vals else None


# =============================================================================
# Cắt audio theo từng chính sách
# =============================================================================
def iter_segments(policy: str, pcm: np.ndarray):
    """
    Sinh ra các đoạn audio (int16) theo chính sách.
    Trả về generator để không phải giữ toàn bộ trong RAM cùng lúc.
    """
    if policy == "full":
        yield pcm
        return

    if policy.startswith("fixed_"):
        step_ms = int(policy.split("_")[1])
        step = step_ms * SAMPLE_RATE // 1000
        for i in range(0, len(pcm), step):
            seg = pcm[i : i + step]
            if len(seg) >= FRAME_SAMPLES:
                yield seg
        return

    if policy == "vad":
        buf = make_buffer()
        n_frames = (len(pcm) // FRAME_SAMPLES) * FRAME_SAMPLES
        for i in range(0, n_frames, FRAME_SAMPLES):
            utt = buf.push(pcm[i : i + FRAME_SAMPLES].tobytes())
            if utt is not None:
                yield utt.audio
        tail = buf.flush()
        if tail is not None:
            yield tail.audio
        return

    raise ValueError(f"Chính sách không hợp lệ: {policy}")


def iter_segments_vad_verbose(pcm: np.ndarray):
    """
    Như iter_segments('vad') nhưng trả kèm vad_ratio — cần cho việc lọc cụm
    nghi là nhiễu và cho báo cáo.
    """
    buf = make_buffer()
    n_frames = (len(pcm) // FRAME_SAMPLES) * FRAME_SAMPLES
    for i in range(0, n_frames, FRAME_SAMPLES):
        utt = buf.push(pcm[i : i + FRAME_SAMPLES].tobytes())
        if utt is not None:
            yield utt.audio, utt.vad_ratio
    tail = buf.flush()
    if tail is not None:
        yield tail.audio, tail.vad_ratio


# =============================================================================
# Kết quả
# =============================================================================
@dataclass
class PolicyResult:
    policy: str
    n_files: int = 0
    n_segments: int = 0
    refs: list[str] = field(default_factory=list)
    hyps: list[str] = field(default_factory=list)
    audio_ms_total: float = 0.0
    infer_ms_total: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    seg_durations_ms: list[float] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)

    # Thống kê VAD: bao nhiêu cụm bị nghi là nhiễu (vad_ratio thấp)
    vad_ratios: list[float] = field(default_factory=list)

    # Điền một lần trong finalize() — không tính lại mỗi lần truy cập
    wer_value: float | None = None

    def finalize(self):
        self.wer_value = compute_wer(self.refs, self.hyps)
        return self

    @property
    def noise_ratio(self) -> float:
        """Tỉ lệ cụm có vad_ratio < 0.3 — sẽ bị lọc ở tầng trên, không gửi cho client."""
        if not self.vad_ratios:
            return 0.0
        return sum(1 for r in self.vad_ratios if r < 0.3) / len(self.vad_ratios)

    @property
    def rtf(self) -> float:
        return self.infer_ms_total / self.audio_ms_total if self.audio_ms_total else 0.0

    @property
    def mean_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if len(self.latencies_ms) < 2:
            return self.mean_latency_ms
        ordered = sorted(self.latencies_ms)
        idx = min(int(len(ordered) * 0.95), len(ordered) - 1)
        return ordered[idx]

    @property
    def mean_infer_ms(self) -> float:
        return self.infer_ms_total / self.n_segments if self.n_segments else 0.0

    @property
    def mean_seg_ms(self) -> float:
        return statistics.mean(self.seg_durations_ms) if self.seg_durations_ms else 0.0


STATE: dict = {}


def make_buffer() -> UtteranceBuffer:
    """
    Tạo UtteranceBuffer theo cấu hình đang chạy (STATE).

    Cố ý gom vào MỘT chỗ: trước đây hai nơi tự gọi `UtteranceBuffer(gate=...)`
    nên `--silence-ms` và `--min-speech-ms` được argparse nhận nhưng bị BỎ QUA âm
    thầm — quét 250/350/500ms sẽ ra kết quả giống hệt nhau và dễ kết luận sai là
    "ngưỡng này không ảnh hưởng". Dùng chung một hàm thì không thể quên lần nữa.

    Dùng .get() để hàm vẫn chạy được khi STATE chưa được main() thiết lập
    (ví dụ khi import module để test).
    """
    return UtteranceBuffer(
        gate=STATE.get("gate") or VadGate(),
        silence_ms=STATE.get("silence_ms", DEFAULT_SILENCE_MS),
        min_speech_ms=STATE.get("min_speech_ms", DEFAULT_MIN_SPEECH_MS),
        max_utterance_ms=STATE.get("max_utterance_ms", DEFAULT_MAX_UTTERANCE_MS),
    )


# =============================================================================
# Nạp model
# =============================================================================
def load_asr_model(device: str):
    import torch
    from transformers import pipeline

    print(f"[INFO] Đang nạp {MODEL_ID} trên {device} ...")
    t0 = time.perf_counter()
    pipe = pipeline(
        "automatic-speech-recognition",
        model=MODEL_ID,
        device=device,
    )
    print(f"[INFO] Nạp xong sau {time.perf_counter() - t0:.1f}s")
    return pipe


def warmup(pipe, n: int = 3):
    """Lần inference đầu tiên chậm hơn hẳn (khởi tạo kernel CUDA). Phải warmup."""
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    for _ in range(n):
        pipe(silence)
    print(f"[INFO] Warmup {n} lượt xong")


def decode(pipe, pcm: np.ndarray) -> tuple[str, float]:
    """Trả về (text, thời_gian_inference_ms)."""
    audio = pcm_to_float32(pcm)
    t0 = time.perf_counter()
    out = pipe(audio)
    dt = (time.perf_counter() - t0) * 1000.0
    return (out.get("text") or "").strip(), dt


# =============================================================================
# Chạy benchmark trên một tập file
# =============================================================================
def run_benchmark(pipe, dataset, policies, limit):
    results = {p: PolicyResult(policy=p) for p in policies}

    for idx, (path, ref) in enumerate(dataset[:limit], 1):
        try:
            import librosa

            audio_f, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
        except Exception as exc:
            print(f"[{idx}/{min(limit, len(dataset))}] BỎ QUA {Path(path).name}: {exc}")
            continue

        if len(audio_f) < SAMPLE_RATE * 0.5:
            print(f"[{idx}/{min(limit, len(dataset))}] BỎ QUA (quá ngắn): {Path(path).name}")
            continue

        pcm = np.clip(audio_f * 32768.0, -32768, 32767).astype(np.int16)
        dur_s = len(pcm) / SAMPLE_RATE
        print(f"[{idx}/{min(limit, len(dataset))}] {Path(path).name}  ({dur_s:.2f}s)")

        for policy in policies:
            res = results[policy]
            t_file = time.perf_counter()
            parts: list[str] = []

            if policy == "vad":
                seg_iter = iter_segments_vad_verbose(pcm)
            else:
                seg_iter = ((s, 1.0) for s in iter_segments(policy, pcm))

            for seg, ratio in seg_iter:
                seg_ms = len(seg) / SAMPLE_RATE * 1000.0
                if seg_ms < 100:  # quá ngắn để CTC làm gì có nghĩa
                    continue
                text, infer_ms = decode(pipe, seg)

                res.n_segments += 1
                res.audio_ms_total += seg_ms
                res.infer_ms_total += infer_ms
                res.seg_durations_ms.append(seg_ms)
                # Độ trễ trung bình của nội dung trong chunk này
                res.latencies_ms.append(seg_ms / 2.0 + infer_ms)
                if policy == "vad":
                    res.vad_ratios.append(ratio)
                parts.append(text)

            joined = " ".join(p for p in parts if p)
            res.n_files += 1
            res.refs.append(ref or "")
            res.hyps.append(joined)

            if len(res.samples) < 3:
                res.samples.append(
                    {
                        "file": Path(path).name,
                        "reference": ref or "",
                        "hypothesis": joined,
                        "_time_s": round(time.perf_counter() - t_file, 2),
                    }
                )

            if policy == "vad":
                n_seg = res.n_segments
                print(f"       vad   -> {n_seg} cụm tích luỹ")

    return {p: r.finalize() for p, r in results.items()}


# =============================================================================
# Báo cáo
# =============================================================================
def print_table(results: dict[str, PolicyResult]):
    print("\n" + "=" * 100)
    print("KẾT QUẢ — Wav2Vec2 theo từng chính sách cắt chunk")
    print("=" * 100)
    header = (
        f"{'Chính sách':<12} {'WER':>8} {'Số cụm':>8} {'Dur TB':>9} "
        f"{'Infer TB':>9} {'Trễ TB':>9} {'Trễ p95':>9} {'RTF':>7}"
    )
    print(header)
    print("-" * 100)

    for policy, r in results.items():
        wer = r.wer_value
        wer_s = f"{wer * 100:.2f}%" if wer is not None else "  n/a"
        print(
            f"{policy:<12} {wer_s:>8} {r.n_segments:>8} "
            f"{r.mean_seg_ms:>8.0f}ms {r.mean_infer_ms:>8.0f}ms "
            f"{r.mean_latency_ms:>8.0f}ms {r.p95_latency_ms:>8.0f}ms {r.rtf:>7.4f}"
        )

    print("-" * 100)
    print("Trễ TB = dur_chunk/2 + infer  (độ trễ trung bình của nội dung trong chunk)")
    print("RTF   = tổng thời gian inference / tổng thời gian audio (càng nhỏ càng tốt)")

    vad_res = results.get("vad")
    if vad_res and vad_res.vad_ratios:
        print()
        print("VAD:")
        print(f"  - Độ dài cụm từ trung bình : {vad_res.mean_seg_ms:.0f} ms")
        print(f"  - Cụm nghi là nhiễu (vad_ratio < 0.3): {vad_res.noise_ratio * 100:.1f}%")
        print("    → đây là tỉ lệ cụm sẽ bị LỌC BỎ ở tầng trên (không gửi cho client),")
        print("      nhờ vậy chữ rác do im lặng/nhiễu không hiện lên màn hình.")
    print()
    print("⚠️  NHẮC LẠI: đây là WER đo trên dữ liệu ĐỌC, THU ÂM STUDIO, MỘT NGƯỜI NÓI.")
    print("   Trong phòng họp thật (mic xa, nhiễu, nói chen ngang) WER sẽ cao hơn đáng kể.")
    print("   Phải ghi rõ điều kiện này khi đưa số vào báo cáo.")


def _result_suffix() -> str:
    """
    Hậu tố tên file theo cấu hình cắt, để các lần QUÉT THAM SỐ không ghi đè nhau.
    Giữ tên gốc khi dùng cấu hình mặc định để không phá kết quả cũ.

    Cần thiết vì việc 0.7 (quét silence_ms và trần cụm) chạy script nhiều lần liên
    tiếp; nếu tên file cố định thì các lần sau đè mất lần trước, không so sánh được.
    """
    sil = STATE.get("silence_ms", DEFAULT_SILENCE_MS)
    mins = STATE.get("min_speech_ms", DEFAULT_MIN_SPEECH_MS)
    mx = STATE.get("max_utterance_ms", DEFAULT_MAX_UTTERANCE_MS)
    parts = []
    if sil != DEFAULT_SILENCE_MS:
        parts.append(f"sil{sil}")
    if mins != DEFAULT_MIN_SPEECH_MS:
        parts.append(f"min{mins}")
    if mx != DEFAULT_MAX_UTTERANCE_MS:
        parts.append(f"max{mx}")
    return f"_{'_'.join(parts)}" if parts else ""


def write_outputs(results: dict[str, PolicyResult], out_dir: Path, dataset_name: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = _result_suffix()

    payload = {
        "model": MODEL_ID,
        "dataset": dataset_name,
        "vad_backend": STATE.get("gate").backend if STATE.get("gate") else "?",
        # Ghi cả cấu hình cắt vào kết quả — không có mấy số này thì file JSON
        # không tự giải thích được nó được tạo bằng ngưỡng nào.
        "config": {
            "silence_ms": STATE.get("silence_ms", DEFAULT_SILENCE_MS),
            "min_speech_ms": STATE.get("min_speech_ms", DEFAULT_MIN_SPEECH_MS),
            "max_utterance_ms": STATE.get("max_utterance_ms", DEFAULT_MAX_UTTERANCE_MS),
            "vad_mode": STATE.get("gate").mode if STATE.get("gate") else "?",
        },
        "policies": {
            p: {
                "wer": r.wer_value,
                "n_files": r.n_files,
                "n_segments": r.n_segments,
                "mean_segment_ms": round(r.mean_seg_ms, 1),
                "mean_infer_ms": round(r.mean_infer_ms, 1),
                "mean_latency_ms": round(r.mean_latency_ms, 1),
                "p95_latency_ms": round(r.p95_latency_ms, 1),
                "rtf": round(r.rtf, 5),
                "noise_ratio": round(r.noise_ratio, 4),
                "samples": r.samples,
            }
            for p, r in results.items()
        },
    }
    (out_dir / f"chunking_results{suffix}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# Kết quả Phase 0 — Wav2Vec2 theo chính sách cắt chunk",
        "",
        f"- **Model:** `{MODEL_ID}`",
        f"- **Tập dữ liệu:** {dataset_name}",
        f"- **VAD backend:** `{payload['vad_backend']}`",
        f"- **Ngày chạy:** {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Chính sách | WER | Số cụm | Dur TB | Infer TB | Trễ TB | Trễ p95 | RTF |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for p, r in results.items():
        wer_s = f"{r.wer_value * 100:.2f}%" if r.wer_value is not None else "n/a"
        lines.append(
            f"| `{p}` | {wer_s} | {r.n_segments} | {r.mean_seg_ms:.0f}ms | "
            f"{r.mean_infer_ms:.0f}ms | {r.mean_latency_ms:.0f}ms | "
            f"{r.p95_latency_ms:.0f}ms | {r.rtf:.4f} |"
        )
    lines += [
        "",
        "> Trễ TB = `dur_chunk/2 + infer`. RTF = thời gian inference / thời gian audio.",
        ">",
        "> ⚠️ WER đo trên dữ liệu đọc, thu âm studio, một người nói. Phòng họp thật sẽ cao hơn.",
        "",
    ]
    (out_dir / f"chunking_results{suffix}.md").write_text("\n".join(lines), encoding="utf-8")

    for p, r in results.items():
        if not r.samples:
            continue
        body = []
        for s in r.samples:
            body += [f"### {s['file']}", "", f"**Chuẩn:** {s['reference']}", "", f"**AI:** {s['hypothesis']}", ""]
        (out_dir / f"samples_{p}{suffix}.md").write_text("\n".join(body), encoding="utf-8")

    print(f"\n[INFO] Đã ghi kết quả vào {out_dir.resolve()}")
    print(f"       - chunking_results{suffix}.json  (dữ liệu thô)")
    print(f"       - chunking_results{suffix}.md    (bảng markdown, dán thẳng vào báo cáo)")
    print(f"       - samples_*{suffix}.md           (ví dụ output từng chính sách)")
    if suffix:
        print(f"       (hậu tố '{suffix}' vì đã đổi ngưỡng cắt — xem STATE trong file JSON)")


# =============================================================================
# Chế độ phụ
# =============================================================================
def run_qualitative(pipe, path: Path, out_dir: Path | None = None):
    """Phase 0.5 — nghe cảm nhận, không có ground truth."""
    import librosa

    print(f"\n=== CHẾ ĐỘ NGHE CẢM NHẬN: {path.name} ===")
    print("Không có ground truth nên KHÔNG tính được WER — chỉ để đọc xem có hiểu được không.\n")

    audio_f, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    pcm = np.clip(audio_f * 32768.0, -32768, 32767).astype(np.int16)
    print(f"Độ dài: {len(pcm) / SAMPLE_RATE:.1f}s\n")

    report = [
        "# Phase 0.5 — Nghe cảm nhận (không có ground truth)",
        "",
        f"- **File:** `{path.name}` ({len(pcm) / SAMPLE_RATE:.1f}s)",
        f"- **Model:** `{MODEL_ID}`",
        f"- **VAD backend:** `{STATE['gate'].backend if STATE.get('gate') else '?'}`",
        f"- **Ngày chạy:** {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "> Mục đích: kiểm tra bằng TAI. WER thấp chưa chắc đọc lên đã hiểu được.",
        "> Chú ý các token `<unk>` — dấu hiệu model không nhận ra tiếng nói.",
        "",
    ]

    for policy in ["fixed_500", "fixed_1500", "vad"]:
        print(f"--- {policy} ---")
        t0 = time.perf_counter()
        parts = []
        for seg, ratio in (
            iter_segments_vad_verbose(pcm) if policy == "vad"
            else ((s, 1.0) for s in iter_segments(policy, pcm))
        ):
            if len(seg) / SAMPLE_RATE < 0.1:
                continue
            text, _ = decode(pipe, seg)
            if text:
                parts.append(text)
        joined = " ".join(parts)
        elapsed = time.perf_counter() - t0
        print(joined[:1500])
        print(f"[{policy}] {len(parts)} cụm, {elapsed:.1f}s\n")

        n_unk = joined.count("<unk>")
        report += [
            f"## `{policy}`",
            "",
            f"- Số cụm: **{len(parts)}**",
            f"- Thời gian: **{elapsed:.2f}s** (RTF ≈ {elapsed / (len(pcm) / SAMPLE_RATE):.4f})",
            f"- Số token `<unk>`: **{n_unk}**  ← càng nhiều càng tệ",
            "",
            "```text",
            joined,
            "```",
            "",
        ]

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / f"qualitative_{path.stem}.md"
        dst.write_text("\n".join(report), encoding="utf-8")
        print(f"[INFO] Đã ghi bằng chứng vào {dst.resolve()}")


def run_full_vram_check():
    """
    Phase 0.4 — trả lời dứt điểm: 6GB VRAM của RTX 4050 có đủ cho 3 model không.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

    if not torch.cuda.is_available():
        print("[!] Không có CUDA — không đo được VRAM.")
        return

    device = "cuda:0"
    print(f"[INFO] GPU: {torch.cuda.get_device_name(0)}")
    props = torch.cuda.get_device_properties(0)
    total_gb = props.total_memory / 1024**3
    print(f"[INFO] Tổng VRAM: {total_gb:.2f} GB")
    print("[INFO] LƯU Ý: con số này là VRAM khả dụng lúc đo. Trên laptop Windows,")
    print("       desktop + Chrome đang chiếm một phần, nên thực tế ít hơn." + "\n")

    torch.cuda.reset_peak_memory_stats()

    def report(label):
        alloc = torch.cuda.memory_allocated() / 1024**3
        peak = torch.cuda.max_memory_allocated() / 1024**3
        resv = torch.cuda.max_memory_reserved() / 1024**3
        print(f"  {label:<28} đang dùng {alloc:5.2f} GB | đỉnh {peak:5.2f} GB | reserved {resv:5.2f} GB")

    print("[1/3] PhoWhisper-small ...")
    pho = pipeline("automatic-speech-recognition", model="vinai/PhoWhisper-small", device=device)
    report("+ PhoWhisper")

    print("[2/3] Qwen2.5-1.5B-Instruct (fp16) ...")
    qid = "Qwen/Qwen2.5-1.5B-Instruct"
    qtok = AutoTokenizer.from_pretrained(qid)
    qmodel = AutoModelForCausalLM.from_pretrained(qid, dtype=torch.float16).to(device)
    report("+ Qwen2.5-1.5B")

    print("[3/3] Wav2Vec2 ...")
    w2v = pipeline("automatic-speech-recognition", model=MODEL_ID, device=device)
    report("+ Wav2Vec2")

    print("\n[INFO] Chạy thử 20 lượt inference để đo đỉnh thật khi có activation ...")
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    short = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
    for _ in range(10):
        pho(silence)
        w2v(short)
    inputs = qtok(["Tóm tắt: hôm nay họp về ngân sách"], return_tensors="pt").to(device)
    for _ in range(5):
        with torch.no_grad():
            qmodel.generate(**inputs, max_new_tokens=64)
    report("sau khi chạy inference")

    peak = torch.cuda.max_memory_allocated() / 1024**3
    print("\n" + "=" * 70)
    print(f"KẾT LUẬN: đỉnh {peak:.2f} GB / {total_gb:.2f} GB khả dụng")
    if peak > total_gb * 0.9:
        print("  ⚠️  RẤT SÁT TRẦN — nguy cơ OOM cao khi họp dài.")
        print("  → Đối sách: del Wav2Vec2 + torch.cuda.empty_cache() trước khi chạy batch.")
        print("    (Hai engine không cần chạy đồng thời — xem mục 9.1 của plan.)")
    elif peak > total_gb * 0.75:
        print("  ⚠️  Khá sát — nên có phương án dự phòng.")
    else:
        print("  ✅ Còn dư địa, kiến trúc 3 model giữ nguyên được.")
    print("=" * 70)


# =============================================================================
# Nạp dataset
# =============================================================================
def load_vivos(root: Path, limit: int):
    """
    VIVOS: <root>/test/prompts.txt  +  <root>/test/waves/<speaker>/<id>.wav
    Định dạng prompts.txt: mỗi dòng  "<audio_id> <câu đúng>"
    """
    test_dir = root / "test" if (root / "test").exists() else root
    prompts = test_dir / "prompts.txt"
    waves = test_dir / "waves"

    if not prompts.exists():
        raise FileNotFoundError(f"Không thấy {prompts}")

    refs: dict[str, str] = {}
    for line in prompts.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            refs[parts[0]] = parts[1]

    dataset = []
    for wav in sorted(waves.rglob("*.wav")):
        aid = wav.stem
        if aid in refs:
            dataset.append((wav, refs[aid]))
        if len(dataset) >= limit:
            break

    if not dataset:
        raise RuntimeError(f"Không ghép được file audio nào với ground truth trong {waves}")
    return dataset


def load_manifest(path: Path, limit: int):
    """TSV: mỗi dòng  '<đường_dẫn_file_audio>\\t<câu đúng>'"""
    dataset = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            print(f"  [!] Dòng {i + 1} thiếu tab phân cách, bỏ qua")
            continue
        audio = Path(parts[0].strip())
        if not audio.is_absolute():
            audio = (path.parent / audio).resolve()
        dataset.append((audio, parts[1].strip()))
        if len(dataset) >= limit:
            break

    if not dataset:
        raise RuntimeError(f"Manifest rỗng hoặc sai định dạng: {path}")
    return dataset


# =============================================================================
# main
# =============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Phase 0 — đo WER & độ trễ theo chính sách cắt chunk",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--vivos-root", type=Path, help="Thư mục gốc bộ VIVOS")
    src.add_argument("--manifest", type=Path, help="File TSV: đường_dẫn<TAB>câu_đúng")
    src.add_argument("--qualitative", type=Path, help="1 file audio, chỉ nghe cảm nhận")
    src.add_argument("--measure-full-vram", action="store_true", help="Đo VRAM đỉnh với đủ 3 model")

    ap.add_argument("--limit", type=int, default=50, help="Số mẫu tối đa (mặc định 50)")
    ap.add_argument("--device", default=None, help="cuda:0 hoặc cpu (mặc định tự chọn)")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "results",
                    help="Thư mục ghi kết quả (mặc định models_testing/results/)")
    ap.add_argument("--policies", nargs="+", default=POLICIES, choices=POLICIES)
    ap.add_argument(
        "--silence-ms",
        type=int,
        default=DEFAULT_SILENCE_MS,
        help="Ngưỡng im lặng để cắt (VAD)",
    )
    ap.add_argument(
        "--min-speech-ms",
        type=int,
        default=DEFAULT_MIN_SPEECH_MS,
        help="Tiếng nói tối thiểu (đo theo TIẾNG NÓI thực, không phải tổng buffer)",
    )
    ap.add_argument(
        "--max-utterance-ms",
        type=int,
        default=DEFAULT_MAX_UTTERANCE_MS,
        help=(
            "Cắt cưỡng bức khi cụm dài quá mức này. ĐÂY LÀ TRẦN CỨNG CHO ĐỘ TRỄ: "
            "cắt ở N ms thì trễ tối đa N/2 ms. Mặc định "
            f"{DEFAULT_MAX_UTTERANCE_MS} (trễ tối đa {DEFAULT_MAX_UTTERANCE_MS/2000:.1f}s)."
        ),
    )
    ap.add_argument("--vad-mode", type=int, default=2, choices=[0, 1, 2, 3])
    args = ap.parse_args()

    if args.measure_full_vram:
        run_full_vram_check()
        return

    if not (args.vivos_root or args.manifest or args.qualitative):
        ap.error("Cần một trong: --vivos-root / --manifest / --qualitative / --measure-full-vram")

    import torch

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Thiết bị: {device}")
    if device == "cpu":
        print("[!] Đang chạy CPU — số liệu độ trễ sẽ KHÔNG đại diện cho máy demo có GPU.")

    STATE["gate"] = VadGate(mode=args.vad_mode)
    STATE["silence_ms"] = args.silence_ms
    STATE["min_speech_ms"] = args.min_speech_ms
    STATE["max_utterance_ms"] = args.max_utterance_ms
    print(f"[INFO] VAD backend: {STATE['gate'].backend}")
    print(
        f"[INFO] Cấu hình cắt: silence_ms={args.silence_ms}ms, "
        f"min_speech_ms={args.min_speech_ms}ms, "
        f"max_utterance_ms={args.max_utterance_ms}ms "
        f"(trần độ trễ {args.max_utterance_ms/2000:.1f}s), "
        f"vad_mode={args.vad_mode}"
    )
    print(
        f"[INFO] NHẮC: webrtcvad không tất định — số cụm có sai số ±1 giữa các lần chạy. "
        f"Luôn dùng MỘT VadGate xuyên suốt (make_buffer đã bảo đảm điều này)."
    )
    if STATE["gate"].backend == "rms":
        print("       (webrtcvad chưa cài — đang dùng fallback ngưỡng năng lượng)")
        print("       Cài đúng cách:  pip install webrtcvad-wheels")

    pipe = load_asr_model(device)
    warmup(pipe)

    if args.qualitative:
        run_qualitative(pipe, args.qualitative, args.out)
        return

    if args.vivos_root:
        dataset = load_vivos(args.vivos_root, args.limit)
        dataset_name = f"VIVOS ({args.vivos_root})"
    else:
        dataset = load_manifest(args.manifest, args.limit)
        dataset_name = f"manifest ({args.manifest.name})"

    print(f"[INFO] {len(dataset)} mẫu có ground truth\n")

    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    results = run_benchmark(pipe, dataset, args.policies, args.limit)

    if device.startswith("cuda"):
        peak = torch.cuda.max_memory_allocated() / 1024**3
        print(f"\n[INFO] VRAM đỉnh khi chạy (chỉ Wav2Vec2): {peak:.2f} GB")
        print("       → Muốn đo đủ 3 model: python benchmark_chunking.py --measure-full-vram")

    print_table(results)
    write_outputs(results, args.out, dataset_name)

    print("\n" + "=" * 100)
    print("VIỆC CẦN LÀM TIẾP (Phase 0.6):")
    print("  1. Đọc bảng trên, chọn chính sách có WER chấp nhận được và độ trễ thấp nhất.")
    print("  2. Nghe file samples_*.md — WER thấp chưa chắc đọc lên đã hiểu được.")
    print("  3. Ghi kết luận vào đầu notebook, rồi cập nhật mục 4 của PLAN_REALTIME_HYBRID_ASR.md")
    print("     (silence_ms / min_speech_ms / chính sách cắt) bằng số liệu THẬT.")
    print("  4. Nếu WER tốt nhất vẫn > 20% → kích hoạt phương án pivot ở mục 5.2 của plan.")
    print("=" * 100)


if __name__ == "__main__":
    main()
