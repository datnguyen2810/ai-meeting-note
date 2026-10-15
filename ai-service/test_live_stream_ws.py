"""
test_live_stream_ws.py - Kiểm thử tự động WebSocket endpoint /ws/live-stream của AI Service
Chạy khi server AI Service đang chạy (hoặc dùng uvicorn test process).
"""

import asyncio
import json
import sys
import time
from pathlib import Path
import numpy as np
import librosa
import websockets

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


WS_URL = "ws://localhost:8000/ws/live-stream"
AUDIO_FILE = Path(__file__).resolve().parent.parent / "data_test" / "test_2.mp3"


async def run_test():
    print(f"[TEST] Kết nối tới {WS_URL}...")
    try:
        async with websockets.connect(WS_URL) as ws:
            # 1. Gửi handshake start
            start_payload = {"type": "start", "sample_rate": 16000}
            await ws.send(json.dumps(start_payload))
            print("[TEST] Đã gửi start handshake.")

            # 2. Nhận ready
            ready_msg = await ws.recv()
            ready_data = json.loads(ready_msg)
            print(f"[TEST] Nhận ready: {ready_data}")
            assert ready_data.get("type") == "ready", f"Mong đợi 'ready', nhận: {ready_data}"

            # 3. Đọc 10 giây đầu của file test_2.mp3 để stream
            print(f"[TEST] Đọc audio từ {AUDIO_FILE.name}...")
            y, sr = librosa.load(str(AUDIO_FILE), sr=16000, mono=True, duration=8.0)
            pcm = np.clip(y * 32768.0, -32768, 32767).astype(np.int16)
            pcm_bytes = pcm.tobytes()

            chunk_size = 3200  # 200ms = 1600 samples = 3200 bytes
            print(f"[TEST] Bắt đầu stream {len(pcm_bytes)} bytes (~{len(pcm)/16000:.1f}s) theo chunks 200ms...")

            interim_count = 0
            final_count = 0

            async def receiver():
                nonlocal interim_count, final_count
                try:
                    while True:
                        msg_str = await ws.recv()
                        msg = json.loads(msg_str)
                        m_type = msg.get("type")
                        if m_type == "interim":
                            interim_count += 1
                            print(f"  [INTERIM seq={msg.get('seq')}] {msg.get('text')} ({msg.get('infer_ms')}ms)")
                        elif m_type == "final":
                            final_count += 1
                            print(f"  ✅ [FINAL seq={msg.get('seq')}] {msg.get('text')} [{msg.get('t_start')}s-{msg.get('t_end')}s]")
                        elif m_type == "closed":
                            print(f"  [CLOSED] Phiên kết thúc. Tổng cụm final: {msg.get('total_segments')}")
                            break
                        elif m_type == "error":
                            print(f"  [ERROR] {msg.get('message')}")
                            break
                except websockets.exceptions.ConnectionClosed:
                    pass

            # Bật task nhận message song song
            recv_task = asyncio.create_task(receiver())

            # Gửi từng chunk 200ms, sleep thời gian thực để mô phỏng người nói trực tiếp
            for i in range(0, len(pcm_bytes), chunk_size):
                chunk = pcm_bytes[i:i + chunk_size]
                await ws.send(chunk)
                await asyncio.sleep(0.18)  # ~180-200ms

            print("[TEST] Đã gửi hết audio. Chờ 2s rồi gửi STOP...")
            await asyncio.sleep(2.0)

            # Gửi lệnh STOP
            await ws.send(json.dumps({"type": "stop"}))
            print("[TEST] Đã gửi lệnh STOP.")

            await recv_task
            print(f"\n===== KẾT QUẢ TEST WEBSOCKET =====")
            print(f"Số gói interim nhận được: {interim_count}")
            print(f"Số gói final nhận được:   {final_count}")
            assert final_count >= 1, "Cần nhận được ít nhất 1 cụm final"
            print(">>>>> TEST WEBSOCKET LIVE STREAM THÀNH CÔNG! <<<<<")

    except Exception as exc:
        print(f"[TEST FAIL] Lỗi: {exc}")
        raise


if __name__ == "__main__":
    asyncio.run(run_test())
