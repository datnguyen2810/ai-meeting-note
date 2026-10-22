import os
import sys
import uuid
import json
import asyncio
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Optional

import torch
import librosa
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM

from vad_buffer import (
    UtteranceBuffer,
    VadGate,
    pcm_to_float32,
    FRAME_BYTES,
    FRAME_SAMPLES,
    SAMPLE_RATE,
)
import ws_protocol as proto
from summarization import run_summarize

# ==========================================
# 1. Quản lý vòng đời Lifespan & nạp model
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Khoi tao he thong tren device: {device}...")

    # Khởi tạo GPU lock và biến đếm phiên live
    app.state.device = device
    app.state.gpu_lock = asyncio.Lock()
    app.state.active_live_sessions = 0

    # 1. Mo hinh Realtime CTC: Wav2Vec2 Vietnamese 250h (~378MB)
    print("[INFO] Loading Wav2Vec2 (Realtime Live Engine)...")
    t0 = time.perf_counter()
    w2v_pipe = pipeline(
        "automatic-speech-recognition",
        model="nguyenvulebinh/wav2vec2-base-vietnamese-250h",
        device=device,
    )
    # Warmup kernel CUDA cho Wav2Vec2
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    w2v_pipe(silence)
    app.state.w2v_pipe = w2v_pipe
    print(f"[INFO] Wav2Vec2 ready ({time.perf_counter() - t0:.2f}s).")

    # 2. Mo hinh Batch STT: PhoWhisper-small (~967MB)
    print("[INFO] Loading PhoWhisper-small (Batch High-Fidelity Engine)...")
    t0 = time.perf_counter()
    stt_pipe = pipeline(
        "automatic-speech-recognition",
        model="vinai/PhoWhisper-small",
        device=device,
        chunk_length_s=30,
    )
    app.state.stt_pipe = stt_pipe
    print(f"[INFO] PhoWhisper ready ({time.perf_counter() - t0:.2f}s).")

    # 3. Mo hinh LLM: Qwen2.5-1.5B-Instruct (~2.9GB)
    print("[INFO] Loading Qwen2.5-1.5B-Instruct (Summarizer Engine)...")
    t0 = time.perf_counter()
    llm_model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    llm_tokenizer = AutoTokenizer.from_pretrained(llm_model_id)
    llm_model = AutoModelForCausalLM.from_pretrained(
        llm_model_id,
        dtype=torch.float16 if device != "cpu" else torch.float32,
    ).to(device)

    app.state.llm_tokenizer = llm_tokenizer
    app.state.llm_model = llm_model
    print(f"[INFO] Qwen2.5 ready ({time.perf_counter() - t0:.2f}s).")

    print("[INFO] >>> Tat ca mo hinh da san sang! Server hoat dong. <<<")
    yield

    # Dọn dẹp tài nguyên khi tắt server
    print("[INFO] Shutting down AI Service...")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ==========================================
# 2. Khoi tao FastAPI Server
# ==========================================
app = FastAPI(title="AI Meeting Note Service - Realtime Hybrid ASR", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# 3. Helper Functions: Inference Core
# ==========================================
def run_ctc_inference(pipe, pcm_int16: np.ndarray) -> str:
    """Inference Wav2Vec2 CTC cho chunk Int16 mono 16kHz."""
    if pcm_int16 is None or len(pcm_int16) < FRAME_SAMPLES:
        return ""
    audio_f32 = pcm_to_float32(pcm_int16)
    out = pipe(audio_f32)
    return (out.get("text") or "").strip()


# ==========================================
# 4. WebSocket: Realtime Streaming ASR
# ==========================================
@app.websocket("/ws/live-stream")
async def websocket_live_stream(websocket: WebSocket):
    # (a) Kiểm tra Origin nếu kết nối từ browser
    # Cho phép tất cả origin khi deploy qua Cloudflare Tunnel
    origin = websocket.headers.get("origin")
    allowed_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
    if origin and origin not in allowed_origins:
        # Cho phép các origin từ trycloudflare.com tunnel
        if not origin.endswith(".trycloudflare.com") and not origin.startswith("https://"):
            await websocket.close(code=1008)
            return

    await websocket.accept()

    session_id = uuid.uuid4().hex[:6]
    app.state.active_live_sessions += 1
    print(f"[WS] Client connected. Session ID: {session_id} (Active live: {app.state.active_live_sessions})")

    # Khởi tạo VAD buffer cho phiên này (1 gate duy nhất xuyên suốt)
    buf = UtteranceBuffer(gate=VadGate())
    current_seq = 0
    interim_task = None
    interim_period = 0.7  # ~700ms

    async def interim_worker():
        """Task nền định kỳ decode phần audio đang tích luỹ và gửi interim caption."""
        nonlocal current_seq
        try:
            while True:
                await asyncio.sleep(interim_period)
                audio_peek = buf.peek()
                # Chỉ decode interim khi đã có tối thiểu 5 frame (100ms) âm thanh
                if audio_peek is None or len(audio_peek) < FRAME_SAMPLES * 5:
                    continue

                seq_at_peek = current_seq
                t0 = time.perf_counter()
                async with app.state.gpu_lock:
                    text = await asyncio.to_thread(
                        run_ctc_inference, app.state.w2v_pipe, audio_peek
                    )
                infer_ms = (time.perf_counter() - t0) * 1000.0

                # Nếu sau khi decode xong mà seq chưa đổi và có text -> gửi interim
                if text and seq_at_peek == current_seq:
                    try:
                        await websocket.send_json({
                            "type": proto.SERVER_INTERIM,
                            "seq": seq_at_peek,
                            "text": text,
                            "infer_ms": round(infer_ms, 1),
                        })
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass

    try:
        # Chờ gói tin start handshake
        init_raw = await websocket.receive_text()
        init_data = json.loads(init_raw)
        if init_data.get("type") != proto.CLIENT_START:
            await websocket.send_json({
                "type": proto.SERVER_ERROR,
                "message": f"Expected start handshake, got: {init_data.get('type')}",
                "fatal": True,
            })
            await websocket.close(code=1003)
            return

        # Handshake thành công -> gửi ready
        await websocket.send_json({
            "type": proto.SERVER_READY,
            "session_id": session_id,
        })

        # Bật vòng lặp interim
        interim_task = asyncio.create_task(interim_worker())

        # Vòng lặp nhận audio binary hoặc text control
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                raw_bytes = message["bytes"]
                # Chunk từ client có thể gồm nhiều frame (10 frame = 6400 bytes).
                for offset in range(0, len(raw_bytes), FRAME_BYTES):
                    frame = raw_bytes[offset:offset + FRAME_BYTES]
                    if len(frame) < FRAME_BYTES:
                        continue

                    utt = buf.push(frame)
                    if utt is not None:
                        # Lọc rác: vad_ratio < 0.3 nghi ngờ là tiếng ồn/nhiễu
                        if utt.vad_ratio >= 0.3:
                            t0 = time.perf_counter()
                            async with app.state.gpu_lock:
                                text = await asyncio.to_thread(
                                    run_ctc_inference, app.state.w2v_pipe, utt.audio
                                )
                            infer_ms = (time.perf_counter() - t0) * 1000.0

                            if text:
                                await websocket.send_json({
                                    "type": proto.SERVER_FINAL,
                                    "seq": current_seq,
                                    "text": text,
                                    "t_start": round(utt.t_start, 2),
                                    "t_end": round(utt.t_end, 2),
                                    "vad_ratio": round(utt.vad_ratio, 2),
                                    "infer_ms": round(infer_ms, 1),
                                })
                                current_seq += 1

            elif "text" in message and message["text"]:
                cmd_data = json.loads(message["text"])
                if cmd_data.get("type") == proto.CLIENT_STOP:
                    print(f"[WS] Session {session_id}: Received stop signal.")
                    break

        # Hủy interim worker trước khi flush phần đuôi
        if interim_task and not interim_task.done():
            interim_task.cancel()
            await asyncio.gather(interim_task, return_exceptions=True)

        # Flush nốt phần audio dở dang trong buffer
        tail_utt = buf.flush()
        if tail_utt is not None and tail_utt.vad_ratio >= 0.3:
            t0 = time.perf_counter()
            async with app.state.gpu_lock:
                tail_text = await asyncio.to_thread(
                    run_ctc_inference, app.state.w2v_pipe, tail_utt.audio
                )
            infer_ms = (time.perf_counter() - t0) * 1000.0
            if tail_text:
                await websocket.send_json({
                    "type": proto.SERVER_FINAL,
                    "seq": current_seq,
                    "text": tail_text,
                    "t_start": round(tail_utt.t_start, 2),
                    "t_end": round(tail_utt.t_end, 2),
                    "vad_ratio": round(tail_utt.vad_ratio, 2),
                    "infer_ms": round(infer_ms, 1),
                })
                current_seq += 1

        # Gửi thông báo đóng sạch
        await websocket.send_json({
            "type": proto.SERVER_CLOSED,
            "total_segments": current_seq,
        })
        await websocket.close()

    except WebSocketDisconnect:
        print(f"[WS] Session {session_id}: Client disconnected.")
    except Exception as exc:
        print(f"[WS] Session {session_id} error: {exc}")
        try:
            await websocket.send_json({
                "type": proto.SERVER_ERROR,
                "message": str(exc),
                "fatal": False,
            })
        except Exception:
            pass
    finally:
        if interim_task and not interim_task.done():
            interim_task.cancel()
        app.state.active_live_sessions = max(0, app.state.active_live_sessions - 1)
        print(f"[WS] Session {session_id} ended. (Active live: {app.state.active_live_sessions})")


# ==========================================
# 5. API: Gỡ băng chính thức + Tóm tắt (PhoWhisper + Qwen)
# ==========================================
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # Tránh tranh chấp tài nguyên GPU khi đang có phiên live
    if app.state.active_live_sessions > 0:
        raise HTTPException(
            status_code=409,
            detail="Đang có phiên họp trực tiếp. Vui lòng kết thúc phiên live trước khi gỡ băng chính thức.",
        )

    if not file.filename.lower().endswith((".wav", ".mp3", ".m4a", ".ogg", ".flac")):
        raise HTTPException(
            status_code=400,
            detail="Định dạng không hỗ trợ. Vui lòng tải file .wav, .mp3, .m4a",
        )

    suffix = os.path.splitext(file.filename)[1]
    # Sửa lỗi bảo mật & xung đột tên file bằng NamedTemporaryFile
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_file_path = tmp.name

    try:
        content = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(content)

        # Đọc audio 16kHz
        speech, _ = librosa.load(temp_file_path, sr=SAMPLE_RATE, mono=True)

        # Chạy PhoWhisper với GPU lock
        print(f"[INFO] Batch transcribing {file.filename} ({len(speech)/SAMPLE_RATE:.1f}s)...")
        async with app.state.gpu_lock:
            stt_result = await asyncio.to_thread(
                app.state.stt_pipe,
                speech,
                generate_kwargs={"language": "vietnamese"},
            )
            transcript = stt_result["text"].strip()
            print(f"[INFO] PhoWhisper done ({len(transcript)} chars). Summarizing...")

            # Giải phóng mảng âm thanh lớn và dọn bộ nhớ đệm CUDA
            del speech
            del stt_result
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            summary = await asyncio.to_thread(
                run_summarize,
                app.state.llm_model,
                app.state.llm_tokenizer,
                transcript,
                app.state.device,
            )
            print("[INFO] Summarization complete.")

        return {
            "status": "success",
            "filename": file.filename,
            "transcript": transcript,
            "summary": summary,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


# ==========================================
# 6. API: Tóm tắt văn bản trực tiếp
# ==========================================
class SummarizeRequest(BaseModel):
    transcript: str


@app.post("/api/summarize")
async def summarize_endpoint(body: SummarizeRequest):
    if not body.transcript or not body.transcript.strip():
        raise HTTPException(status_code=400, detail="transcript must not be empty")

    try:
        async with app.state.gpu_lock:
            summary = await asyncio.to_thread(
                run_summarize,
                app.state.llm_model,
                app.state.llm_tokenizer,
                body.transcript,
                app.state.device,
            )
        return {
            "status": "success",
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
