"""HTTP contract checks without loading models or opening the microphone."""

import asyncio
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
import main


class SummaryApiTests(unittest.TestCase):
    def setUp(self):
        # No lifespan context: model startup is intentionally bypassed.
        self.client = TestClient(main.app)
        main.app.state.gpu_lock = asyncio.Lock()
        main.app.state.active_live_sessions = 0
        main.app.state.llm_model = object()
        main.app.state.llm_tokenizer = object()
        main.app.state.device = "cpu"
        main.app.state.stt_pipe = lambda *args, **kwargs: {"text": "anh hiếu chuẩn bị báo cáo"}

    def tearDown(self):
        self.client.close()

    def test_text_summary_keeps_existing_contract(self):
        with patch.object(main, "run_summarize", return_value="### Phân công\n- anh hiếu") as generate:
            response = self.client.post("/api/summarize", json={"transcript": "anh hiếu chuẩn bị báo cáo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "summary": "### Phân công\n- anh hiếu"})
        generate.assert_called_once()

    def test_empty_transcript_rejected(self):
        self.assertEqual(self.client.post("/api/summarize", json={"transcript": " "}).status_code, 400)

    def test_upload_keeps_transcript_and_summary_and_cleans_temporary_file(self):
        paths = []

        def load(path, **kwargs):
            paths.append(path)
            return np.zeros(160), 16000

        with patch.object(main.librosa, "load", side_effect=load), patch.object(main, "run_summarize", return_value="Bản tóm tắt"):
            response = self.client.post("/api/transcribe", files={"file": ("meeting.wav", b"mock audio", "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "success", "filename": "meeting.wav",
            "transcript": "anh hiếu chuẩn bị báo cáo", "summary": "Bản tóm tắt",
        })
        from pathlib import Path
        self.assertTrue(paths)
        self.assertTrue(all(not Path(path).exists() for path in paths))

    def test_batch_still_blocked_while_live_is_active(self):
        main.app.state.active_live_sessions = 1
        response = self.client.post("/api/transcribe", files={"file": ("meeting.wav", b"audio", "audio/wav")})
        self.assertEqual(response.status_code, 409)

    def test_websocket_final_audio_precedes_closed_and_releases_live_session(self):
        main.app.state.w2v_pipe = lambda audio: {"text": "đã kiểm tra"}
        speech = (np.sin(np.arange(16000) * 0.1) * 10000).astype(np.int16).tobytes()
        with patch.object(main, "VadGate") as gate:
            gate.return_value.is_speech.return_value = True
            with self.client.websocket_connect("/ws/live-stream") as socket:
                socket.send_json({"type": "start", "sample_rate": 16000})
                self.assertEqual(socket.receive_json()["type"], "ready")
                for start in range(0, len(speech), 6400):
                    socket.send_bytes(speech[start:start + 6400])
                socket.send_json({"type": "stop"})
                messages = []
                while True:
                    message = socket.receive_json()
                    messages.append(message)
                    if message["type"] == "closed":
                        break
                self.assertTrue(any(m["type"] == "final" and m["text"] == "đã kiểm tra" for m in messages))
        self.assertEqual(main.app.state.active_live_sessions, 0)


if __name__ == "__main__":
    unittest.main()
