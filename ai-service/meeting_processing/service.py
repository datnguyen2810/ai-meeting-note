import os
import time
import librosa
import numpy as np
import soundfile as sf
import tempfile
from typing import Dict, Any, List

from .diarize import run_diarization
from summarization import run_summarize

def process_meeting_pipeline(
    stt_pipe,
    llm_model,
    llm_tokenizer,
    audio_path: str,
    max_speakers: int = 4,
    device: str = "cpu"
) -> Dict[str, Any]:
    """
    Quy trinh xu ly toan dien theo Huong B (M1):
    1. Chay phan doan nguoi noi (Diarization) de xac dinh ranh gioi tung luot noi.
    2. Chay PhoWhisper-small tren tung luot noi de dam bao do chinh xac va moc thoi gian.
    3. Tong hop danh sach speakers va segments theo hop dong V1.
    4. Chay Qwen2.5 de sinh tom tat cuoc hop.
    """
    print(f"[INFO] Bat dau xu ly cuoc hop cho file: {audio_path}")
    t_start = time.perf_counter()
    
    # 1. Phân đoạn người nói
    turns = run_diarization(audio_path, max_speakers=max_speakers, device=device)
    print(f"[INFO] Tim thay {len(turns)} luot noi.")
    
    # Load audio vao RAM
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    
    segments = []
    full_transcript_parts = []
    
    speaker_dict = {}
    
    # 2. Chay ASR PhoWhisper tren tung luot noi
    for i, turn in enumerate(turns):
        s_sec = turn["start"]
        e_sec = turn["end"]
        spk_id = turn["speaker_id"]
        spk_label = turn["label"]
        
        # Ghi nhan speaker dau tien
        if spk_id not in speaker_dict:
            speaker_dict[spk_id] = {
                "speaker_id": spk_id,
                "label": spk_label,
                "first_start_seconds": s_sec
            }
            
        start_sample = int(s_sec * sr)
        end_sample = min(int(e_sec * sr), len(y))
        
        chunk_audio = y[start_sample:end_sample]
        if len(chunk_audio) < int(0.3 * sr): # Bo qua doan duoi 0.3s
            continue
            
        # Nhan dang giong noi bang PhoWhisper
        try:
            out = stt_pipe(chunk_audio)
            text = (out.get("text") or "").strip()
        except Exception as e:
            print(f"[WARN] Loi ASR doan {s_sec}s - {e_sec}s: {e}")
            text = ""
            
        if text:
            seg_id = f"seg_{len(segments)+1:04d}"
            segments.append({
                "segment_id": seg_id,
                "speaker_id": spk_id,
                "speaker_label": spk_label,
                "start_seconds": s_sec,
                "end_seconds": e_sec,
                "text": text,
                "attribution_status": turn.get("attribution_status", "assigned")
            })
            full_transcript_parts.append(f"[{spk_label}]: {text}")
            
    full_transcript = "\n".join(full_transcript_parts)
    
    # 3. Tom tat cuoc hop voi Qwen2.5
    print("[INFO] Dang tao tom tat cuoc hop...")
    summary = ""
    if full_transcript:
        try:
            summary = run_summarize(llm_model, llm_tokenizer, full_transcript, device)
        except Exception as e:
            print(f"[WARN] Loi tom tat Qwen: {e}")
            summary = "Chưa thể tạo tóm tắt do lỗi xử lý mô hình."
            
    speakers_list = list(speaker_dict.values())
    speakers_list.sort(key=lambda s: s["first_start_seconds"])
    
    print(f"[INFO] Xu ly cuoc hop hoan tat trong {time.perf_counter() - t_start:.2f}s.")
    
    return {
        "schema_version": 1,
        "transcript": full_transcript,
        "summary": summary,
        "speakers": speakers_list,
        "segments": segments,
        "warnings": []
    }

