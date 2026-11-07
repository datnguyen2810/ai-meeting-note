import os
import torch
import numpy as np
import librosa
from typing import List, Dict, Any, Optional
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

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

    # Fallback phan doan nguoi noi bang dac trung am hoc (Pitch F0 + MFCCs + Clustering)
    return _acoustic_cluster_diarizer(audio_path, max_speakers=max_speakers)


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


def _acoustic_cluster_diarizer(audio_path: str, max_speakers: int = 4) -> List[Dict[str, Any]]:
    """
    Bo phan doan nguoi noi am hoc thong minh (Acoustic Speaker Clustering Diarizer).
    Hoat dong doc lap, khong can HF_TOKEN va khong can mang Internet.
    Trich xuat dac trung sinh trac hoc giong noi (Pitch F0, MFCCs, Spectral Centroid, Bandwidth)
    va phan cum Agglomerative Clustering de tach biet chinh xac tung nguoi noi.
    """
    print("[INFO] Chay acoustic cluster diarizer...")
    try:
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        intervals = librosa.effects.split(y, top_db=28, frame_length=2048, hop_length=512)

        raw_segments = []
        features = []
        pitches = []

        for s_idx, e_idx in intervals:
            s_sec = round(float(s_idx) / sr, 2)
            e_sec = round(float(e_idx) / sr, 2)
            dur = e_sec - s_sec
            if dur < 0.35:
                continue

            seg_y = y[s_idx:e_idx]

            # 1. Uoc luong cao do giong noi (F0 Pitch)
            f0 = librosa.yin(seg_y, fmin=60, fmax=400, sr=sr)
            f0_valid = f0[~np.isnan(f0)]
            median_f0 = float(np.median(f0_valid)) if len(f0_valid) > 0 else 150.0
            mean_f0 = float(np.mean(f0_valid)) if len(f0_valid) > 0 else 150.0

            # 2. He so pho Mel (MFCCs)
            mfcc = librosa.feature.mfcc(y=seg_y, sr=sr, n_mfcc=13)
            mfcc_mean = mfcc.mean(axis=1)
            mfcc_std = mfcc.std(axis=1)

            # 3. Dac trung pho am thanh
            cent = float(np.mean(librosa.feature.spectral_centroid(y=seg_y, sr=sr)))
            bw = float(np.mean(librosa.feature.spectral_bandwidth(y=seg_y, sr=sr)))

            feat = np.hstack([
                [median_f0, mean_f0],
                mfcc_mean[1:9],
                mfcc_std[1:9],
                [cent, bw]
            ])

            raw_segments.append({
                "start": s_sec,
                "end": e_sec,
                "f0": median_f0,
            })
            features.append(feat)
            pitches.append(median_f0)

        if not raw_segments:
            duration = round(float(len(y)) / sr, 2)
            return [{
                "start": 0.0,
                "end": max(duration, 1.0),
                "speaker_id": "speaker_1",
                "label": "Người 1",
                "attribution_status": "assigned"
            }]

        pitch_std = float(np.std(pitches)) if len(pitches) > 1 else 0.0
        best_k = 1
        best_labels = [0] * len(raw_segments)

        if len(raw_segments) >= 4:
            X = np.array(features)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            max_k = min(max_speakers, len(raw_segments) - 1)

            # Thu nghiem k=2
            clusterer_2 = AgglomerativeClustering(n_clusters=2, metric="euclidean", linkage="ward")
            labels_2 = clusterer_2.fit_predict(X_scaled)

            f0_c0 = np.mean([pitches[i] for i, l in enumerate(labels_2) if l == 0])
            f0_c1 = np.mean([pitches[i] for i, l in enumerate(labels_2) if l == 1])
            pitch_diff_2 = abs(f0_c0 - f0_c1)
            sil_score_2 = silhouette_score(X_scaled, labels_2)

            print(f"[INFO] Danh gia phan cum k=2: pitch_diff={pitch_diff_2:.1f}Hz, sil_score={sil_score_2:.3f}, pitch_std={pitch_std:.1f}")

            # Neu co su khac biet ro ret ve cao do (> 45Hz giua nam/nu) hoac silhouette score tot
            if pitch_diff_2 >= 45.0 or (pitch_std >= 30.0 and sil_score_2 >= 0.20):
                best_k = 2
                best_labels = labels_2

                if max_k >= 3:
                    for k in range(3, max_k + 1):
                        clusterer_k = AgglomerativeClustering(n_clusters=k, metric="euclidean", linkage="ward")
                        labels_k = clusterer_k.fit_predict(X_scaled)
                        score_k = silhouette_score(X_scaled, labels_k)
                        sizes = [np.sum(labels_k == ci) for ci in range(k)]
                        if min(sizes) >= 3 and score_k > sil_score_2 + 0.08:
                            best_k = k
                            best_labels = labels_k
            elif sil_score_2 >= 0.32:
                best_k = 2
                best_labels = labels_2

        print(f"[INFO] Acoustic diarizer xac dinh {best_k} nguoi noi.")

        # Gan cluster vao speaker_raw theo thu tu xuat hien
        cluster_order = {}
        speaker_idx = 0
        for idx, seg in enumerate(raw_segments):
            c = best_labels[idx]
            if c not in cluster_order:
                cluster_order[c] = f"SPEAKER_{speaker_idx:02d}"
                speaker_idx += 1
            seg["speaker_raw"] = cluster_order[c]

        # Gop cac khoang nghi ngan cua cung nguoi noi
        merged = merge_consecutive_speaker_turns(raw_segments, max_gap=0.5, max_duration=18.0)
        return _assign_speaker_labels(merged)
    except Exception as e:
        print(f"[ERROR] Loi acoustic diarizer: {e}")
        return [{
            "start": 0.0,
            "end": 10.0,
            "speaker_id": "speaker_1",
            "label": "Người 1",
            "attribution_status": "assigned"
        }]
