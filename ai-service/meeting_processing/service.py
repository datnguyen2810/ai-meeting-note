import os
import time
import librosa
import numpy as np
import soundfile as sf
import tempfile
from typing import Dict, Any, List, Optional

from .attribution import attribute_first_person_owners
from .diarize import PYANNOTE_ENGINE, diarize_with_engine
from .summary_supplement import supplement_summary
from .turns import ASR_PAD_SECONDS, PYANNOTE_ASR_PAD_SECONDS, padded_bounds, prepare_turns
import llm_backend
from summarization.service import run_summarize_with_info

ASR_MODEL_FALLBACK = "vinai/PhoWhisper-small"
SUMMARY_MODEL_FALLBACK = "Qwen/Qwen2.5-1.5B-Instruct"
# Mã khi không phân được người nói (bộ phân người lỗi)
NO_DIARIZATION = "none"


def _model_name(obj, fallback: str) -> str:
    """Tên model thật đang nạp (pipeline hoặc model HF), không có thì dùng tên mặc định."""
    model = getattr(obj, "model", obj)
    name = getattr(getattr(model, "config", None), "_name_or_path", None)
    return name if isinstance(name, str) and name else fallback


class AudioDecodeError(ValueError):
    """Không giải mã được tệp âm thanh (định dạng không hỗ trợ hoặc tệp hỏng)."""


def load_audio(audio_path: str, sr: int = 16000):
    """Đọc audio mono ở `sr` Hz; lỗi giải mã thành AudioDecodeError có thông báo rõ.

    WebM/Opus (MediaRecorder của trình duyệt) và M4A cần FFmpeg, máy chưa cài sẽ
    rơi vào lỗi audioread với thông báo rỗng, nên phải bọc lại.
    """
    try:
        y, _ = librosa.load(audio_path, sr=sr, mono=True)
    except Exception as exc:
        raise AudioDecodeError(
            "Không đọc được tệp âm thanh. Hãy dùng WAV, MP3, FLAC hoặc OGG; "
            "WebM/M4A cần cài FFmpeg trên máy chạy AI."
        ) from exc
    if len(y) == 0:
        raise AudioDecodeError("Tệp âm thanh rỗng.")
    return y, sr


def process_meeting_pipeline(
    stt_pipe,
    llm_model,
    llm_tokenizer,
    audio_path: str,
    max_speakers: int = 4,
    device: str = "cpu",
    num_speakers: Optional[int] = None,
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

    # Đọc audio trước: tệp không giải mã được phải báo lỗi rõ, không để bộ phân
    # người nuốt lỗi rồi trả về một lượt nói giả.
    y, sr = load_audio(audio_path)
    total_seconds = len(y) / sr

    # 1. Phân đoạn người nói
    warnings: List[str] = []
    try:
        raw_turns, diarization_engine, diarize_warnings = diarize_with_engine(
            audio_path, max_speakers=max_speakers, device=device, num_speakers=num_speakers
        )
        warnings.extend(diarize_warnings)
        # Nhập mẩu ngắn ở chỗ chuyển người vào lượt bên cạnh, nối lượt liền nhau của
        # cùng người, đánh lại Người 1/2... theo lần xuất hiện đầu tiên.
        turns = prepare_turns(raw_turns)
    except Exception as exc:
        # Vẫn phiên âm và tóm tắt cả bản ghi, nhưng không gán người nói giả
        print(f"[WARN] Phan nguoi noi that bai: {exc}")
        raw_turns, diarization_engine = [], NO_DIARIZATION
        turns = [{
            "start": 0.0, "end": round(total_seconds, 2), "speaker_id": None,
            "label": "Chưa rõ người nói", "attribution_status": "unknown",
        }]
        warnings.append("Không phân được người nói; bản phiên âm chưa gán theo người.")
    print(f"[INFO] Phan nguoi noi bang {diarization_engine}: {len(raw_turns)} luot, con {len(turns)} luot sau khi don.")

    # pyannote cắt biên sát hơn bộ pitch/MFCC nên cần nới nhiều hơn (xem turns.py)
    asr_pad = PYANNOTE_ASR_PAD_SECONDS if diarization_engine == PYANNOTE_ENGINE else ASR_PAD_SECONDS

    segments = []
    full_transcript_parts = []
    summary_parts = []

    speaker_dict = {}

    # 2. Chay ASR PhoWhisper tren tung luot noi
    for i, turn in enumerate(turns):
        s_sec = turn["start"]
        e_sec = turn["end"]
        spk_id = turn["speaker_id"]
        spk_label = turn["label"]

        # Cắt audio nới biên một chút để không mất âm đầu/cuối từ; thời gian
        # lưu cho đoạn vẫn là start/end gốc.
        cut_start, cut_end = padded_bounds(turns, i, total_seconds, asr_pad)
        start_sample = int(cut_start * sr)
        end_sample = min(int(cut_end * sr), len(y))

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
            # Chỉ ghi nhận người nói có ít nhất một đoạn có chữ; người không có đoạn
            # nào sẽ thành nút lọc rỗng trên giao diện. Bỏ qua đoạn chưa rõ người nói.
            if spk_id is not None and spk_id not in speaker_dict:
                speaker_dict[spk_id] = {
                    "speaker_id": spk_id,
                    "label": spk_label,
                    "first_start_seconds": s_sec,
                }
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
            summary_parts.append(text)

    # Bản có nhãn để hiển thị/lưu; bản không nhãn để tóm tắt. Nhãn [Người N]
    # làm Qwen trả sai cấu trúc và lọt vào phần kết quả (đã đo trên file demo).
    full_transcript = "\n".join(full_transcript_parts)
    # Gemini: dấu chấm giữa các lượt cho biết chỗ chuyển người (lời ASR không có dấu câu,
    # đo trên bản demo: thiếu nó thì câu trả lời "được" của lượt sau dính vào việc của Lan).
    # Qwen giữ cách nối cũ vì chưa đo ảnh hưởng.
    summary_input = (". " if llm_backend.gemini_enabled() else " ").join(summary_parts)

    # 3. Tom tat cuoc hop (Gemini neu co khoa, nguoc lai Qwen2.5)
    print("[INFO] Dang tao tom tat cuoc hop...")
    summary = ""
    summary_model = None  # tên Gemini nếu đã dùng; None là Qwen local
    if summary_input:
        try:
            summary, summary_model = run_summarize_with_info(llm_model, llm_tokenizer, summary_input, device)
        except Exception as e:
            print(f"[WARN] Loi tom tat Qwen: {e}")
            summary = "Chưa thể tạo tóm tắt do lỗi xử lý mô hình."

    # Người nói tự xưng "mình sẽ..." -> ghi phân công cho đúng người đang nói
    summary, owners_replaced = attribute_first_person_owners(summary, segments)
    if owners_replaced:
        print(f"[INFO] Da gan nguoi nhan viec theo nguoi noi cho {owners_replaced} muc.")

    # Qwen hay bỏ mục tiêu/vấn đề/quyết định; thêm các ý đó từ biên bản bằng quy tắc.
    # Không áp dụng cho Gemini: đo trên bản demo, Gemini đã đủ các mục và quy tắc chỉ
    # thêm dòng trùng (quyết định lặp lại, câu "chốt lại" dính liền).
    if summary_model is None:
        summary, supplemented = supplement_summary(summary, segments)
        if supplemented:
            print(f"[INFO] Bo sung {supplemented} y vao tom tat bang quy tac.")

    speakers_list = list(speaker_dict.values())
    speakers_list.sort(key=lambda s: s["first_start_seconds"])

    # Bộ pitch/MFCC tự đoán gần như luôn ra 2 người (đã đo: silhouette phẳng theo k);
    # file demo 3 người để "Tự động" bị gộp Người 2 và Người 3.
    if not num_speakers and diarization_engine == "acoustic-pitch-mfcc" and speakers_list:
        warnings.append(
            f"Số người do hệ thống tự đoán ({len(speakers_list)} người) và hay bị thiếu khi có giọng gần giống nhau; "
            "nếu cuộc họp có nhiều người hơn, hãy chọn đúng số người rồi xử lý lại."
        )

    if num_speakers and diarization_engine != NO_DIARIZATION and len(speakers_list) < num_speakers:
        warnings.append(
            f"Đã nhập {num_speakers} người nhưng chỉ tách được {len(speakers_list)} người; "
            "bản ghi có thể quá ngắn hoặc có người nói quá ít."
        )
    
    print(f"[INFO] Xu ly cuoc hop hoan tat trong {time.perf_counter() - t_start:.2f}s.")
    
    return {
        "schema_version": 1,
        "transcript": full_transcript,
        "summary": summary,
        "speakers": speakers_list,
        "segments": segments,
        "warnings": warnings,
        # Giao diện hiển thị đúng bộ phân người đã dùng thay vì ghi cố định "Pyannote"
        "models": {
            "diarization": diarization_engine,
            "asr": _model_name(stt_pipe, ASR_MODEL_FALLBACK),
            "summary": summary_model or _model_name(llm_model, SUMMARY_MODEL_FALLBACK),
        },
    }

