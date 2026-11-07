import os
import torch
import numpy as np
import librosa
from typing import List, Dict, Any, Optional

HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

_diarize_pipeline = None


def get_diarization_pipeline(device: str = "cpu"):
    global _diarize_pipeline
    if _diarize_pipeline is not None:
        return _diarize_pipeline

    if HF_TOKEN:
        try:
            from pyannote.audio import Pipeline
            print("[INFO] Nap model pyannote/speaker-diarization-community-1...")
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                token=HF_TOKEN
            )
            if pipeline is not None:
                pipeline.to(torch.device(device))
                _diarize_pipeline = pipeline
                return _diarize_pipeline
        except Exception as e:
            print(f"[WARN] Khong the nap pyannote voi HF_TOKEN: {e}")

    return None


def merge_consecutive_speaker_turns(
    segments: List[Dict[str, Any]],
    max_gap: float = 0.5,
    max_duration: float = 18.0
) -> List[Dict[str, Any]]:
    """
    Gộp các đoạn phát biểu liên tiếp của CÙNG MỘT NGƯỜI NÓI nếu khoảng ngắt giọng ngắn (< max_gap giây).
    Giúp câu không bị ngắt vụn thành các từ/cụm từ rời rạc ("nhìn chung.", "và đã hoàn thành...").
    Đảm bảo tổng thời lượng mỗi đoạn không vượt quá max_duration (18s) để PhoWhisper
    hoạt động chính xác nhất và trọn vẹn ngữ pháp.
    """
    if not segments:
        return []

    merged = []
    for seg in segments:
        if not merged:
            merged.append(dict(seg))
            continue

        prev = merged[-1]
        same_speaker = (
            (prev.get("speaker_raw") and prev.get("speaker_raw") == seg.get("speaker_raw")) or
            (prev.get("speaker_id") and prev.get("speaker_id") == seg.get("speaker_id"))
        )
        gap = round(seg["start"] - prev["end"], 2)
        combined_dur = round(seg["end"] - prev["start"], 2)

        # Nếu cùng người nói, khoảng nghỉ nhỏ hơn max_gap và thời lượng chưa vượt max_duration
        if same_speaker and gap <= max_gap and combined_dur <= max_duration:
            prev["end"] = seg["end"]
        else:
            merged.append(dict(seg))

    return merged


def run_diarization(audio_path: str, max_speakers: int = 4, device: str = "cpu") -> List[Dict[str, Any]]:
    """
    Phân đoạn người nói: trả về danh sách các đoạn:
    [{ "start": 0.5, "end": 4.2, "speaker_raw": "SPEAKER_00" }, ...]
    """
    pipeline = get_diarization_pipeline(device)

    if pipeline is not None:
        try:
            print(f"[INFO] Dang phan doan nguoi noi voi pyannote (max_speakers={max_speakers})...")
            diarization = pipeline(audio_path, max_speakers=max_speakers)

            raw_segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                raw_segments.append({
                    "start": round(float(turn.start), 2),
                    "end": round(float(turn.end), 2),
                    "speaker_raw": str(speaker)
                })

            if raw_segments:
                # Gộp các đoạn nói liên tiếp của cùng người nếu khoảng ngắt ngắn
                merged = merge_consecutive_speaker_turns(raw_segments, max_gap=0.5, max_duration=18.0)
                return _assign_speaker_labels(merged)
        except Exception as e:
            print(f"[WARN] Loi trong qua trinh chay pyannote: {e}. Chuyen sang fallback.")

    # Fallback VAD energy segmenter khi khong co HF_TOKEN
    return _fallback_vad_segmenter(audio_path)


def _assign_speaker_labels(raw_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Quy tắc ở Mức 1: Gán Người 1, Người 2... theo lần xuất hiện đầu tiên trong bản ghi.
    """
    speaker_map = {}
    speaker_counter = 1

    formatted_segments = []
    for seg in raw_segments:
        raw_spk = seg["speaker_raw"]
        if raw_spk not in speaker_map:
            speaker_map[raw_spk] = {
                "speaker_id": f"speaker_{speaker_counter}",
                "label": f"Người {speaker_counter}",
                "first_start": seg["start"]
            }
            speaker_counter += 1

        info = speaker_map[raw_spk]
        formatted_segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "speaker_id": info["speaker_id"],
            "label": info["label"],
            "attribution_status": "assigned"
        })

    return formatted_segments


def _fallback_vad_segmenter(audio_path: str) -> List[Dict[str, Any]]:
    """
    Fallback chia đoạn khi chưa có token Hugging Face.
    Dùng librosa phát hiện khoảng lặng và chia thành các lượt nói tự nhiên,
    không cắt rời các câu phát biểu liên tục.
    """
    print("[INFO] Chay fallback VAD segmenter...")
    try:
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        # top_db=28 để bắt âm thanh tiếng nói chuẩn xác hơn, không bị ngắt đuôi âm
        intervals = librosa.effects.split(y, top_db=28, frame_length=2048, hop_length=512)

        raw_segments = []
        for i, (start_idx, end_idx) in enumerate(intervals):
            start_s = round(float(start_idx) / sr, 2)
            end_s = round(float(end_idx) / sr, 2)
            if end_s - start_s >= 0.3:
                raw_segments.append({
                    "start": start_s,
                    "end": end_s,
                    "speaker_raw": "SPEAKER_00"
                })

        # Gộp các khoảng nghỉ ngắn (< 0.5s) để tạo thành câu hoàn chỉnh
        merged_segments = merge_consecutive_speaker_turns(raw_segments, max_gap=0.5, max_duration=18.0)

        if not merged_segments:
            duration = round(float(len(y)) / sr, 2)
            merged_segments.append({
                "start": 0.0,
                "end": max(duration, 1.0),
                "speaker_raw": "SPEAKER_00"
            })

        return _assign_speaker_labels(merged_segments)
    except Exception as e:
        print(f"[ERROR] Loi fallback segmenter: {e}")
        return [{
            "start": 0.0,
            "end": 10.0,
            "speaker_id": "speaker_1",
            "label": "Người 1",
            "attribution_status": "assigned"
        }]
