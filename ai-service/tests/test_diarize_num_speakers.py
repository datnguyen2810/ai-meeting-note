"""Kiểm tra tham số num_speakers của bộ phân người, không nạp model, không cần mạng.

Dùng audio tổng hợp: mỗi "người" là một tín hiệu điều hòa có cao độ và âm sắc riêng,
các lượt cách nhau bằng khoảng lặng để bộ cắt theo khoảng lặng tìm ra đúng từng lượt.
"""

import asyncio
import importlib.util
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

SR = 16000
DIARIZE_PATH = Path(__file__).resolve().parent.parent / "meeting_processing" / "diarize.py"
_spec = importlib.util.spec_from_file_location("diarize_under_test", DIARIZE_PATH)
diarize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diarize)

# (cao độ Hz, độ suy giảm hài) cho ba người giả lập
VOICES = {"A": (110.0, 0.5), "B": (210.0, 0.8), "C": (320.0, 0.3)}
ORDER = ["A", "B", "C", "A", "B", "C", "A", "B", "C"]


def tone(f0, decay, seconds, seed):
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * seconds)) / SR
    vibrato = 1 + 0.01 * np.sin(2 * np.pi * 5 * t)
    signal = sum((decay ** k) * np.sin(2 * np.pi * f0 * (k + 1) * vibrato * t) for k in range(8))
    signal += 0.01 * rng.standard_normal(len(t))
    return (0.3 * signal / np.max(np.abs(signal))).astype(np.float32)


def write_meeting(path):
    gap = np.zeros(int(SR * 0.6), dtype=np.float32)
    parts, truth, cursor = [gap], [], 0.6
    for i, who in enumerate(ORDER):
        clip = tone(*VOICES[who], seconds=1.4, seed=i)
        truth.append((who, cursor, cursor + len(clip) / SR))
        parts += [clip, gap]
        cursor += (len(clip) + len(gap)) / SR
    sf.write(path, np.concatenate(parts), SR)
    return truth


def speaker_of(turns, start, end):
    """Nhãn hệ thống chiếm nhiều thời gian nhất trong [start, end]."""
    votes = Counter()
    for t in turns:
        overlap = min(end, t["end"]) - max(start, t["start"])
        if overlap > 0:
            votes[t["speaker_id"]] += overlap
    return votes.most_common(1)[0][0] if votes else None


class NumSpeakersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cls.truth = write_meeting(cls.path)

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.path)

    def run_acoustic(self, **kwargs):
        # Ép dùng bộ phân cụm âm học kể cả khi máy có HF_TOKEN
        with patch.object(diarize, "get_diarization_pipeline", return_value=None):
            return diarize.run_diarization(self.path, max_speakers=4, **kwargs)

    def test_exact_count_separates_three_voices_consistently(self):
        turns = self.run_acoustic(num_speakers=3)
        self.assertEqual(len({t["speaker_id"] for t in turns}), 3)
        mapping = {}
        for who, start, end in self.truth:
            got = speaker_of(turns, start, end)
            self.assertEqual(mapping.setdefault(who, got), got, f"Người {who} bị gán nhiều nhãn")
        self.assertEqual(len(set(mapping.values())), 3)

    def test_labels_follow_first_appearance(self):
        turns = self.run_acoustic(num_speakers=3)
        first = [speaker_of(turns, s, e) for _, s, e in self.truth[:3]]
        self.assertEqual(first, ["speaker_1", "speaker_2", "speaker_3"])

    def test_single_speaker(self):
        turns = self.run_acoustic(num_speakers=1)
        self.assertEqual({t["speaker_id"] for t in turns}, {"speaker_1"})

    def test_count_larger_than_segments_does_not_crash(self):
        turns = self.run_acoustic(num_speakers=50)
        self.assertTrue(turns)
        self.assertLessEqual(len({t["speaker_id"] for t in turns}), len(ORDER))

    def test_auto_mode_still_returns_turns(self):
        self.assertTrue(self.run_acoustic())


class ProcessMeetingApiTests(unittest.TestCase):
    """Hợp đồng HTTP của num_speakers, không nạp model."""

    def setUp(self):
        from fastapi.testclient import TestClient
        import main

        self.main = main
        self.client = TestClient(main.app)
        main.app.state.gpu_lock = asyncio.Lock()
        main.app.state.active_live_sessions = 0
        main.app.state.llm_model = object()
        main.app.state.llm_tokenizer = object()
        main.app.state.device = "cpu"
        main.app.state.stt_pipe = object()

    def tearDown(self):
        self.client.close()

    def post(self, query):
        return self.client.post(
            f"/api/process-meeting{query}", files={"file": ("a.wav", b"RIFF0000", "audio/wav")}
        )

    def test_invalid_num_speakers_rejected(self):
        for value in (0, -1, 11):
            with patch.object(self.main, "process_meeting_pipeline") as pipeline:
                self.assertEqual(self.post(f"?num_speakers={value}").status_code, 400)
                pipeline.assert_not_called()

    def test_num_speakers_forwarded_to_pipeline(self):
        result = {"schema_version": 1, "segments": [], "speakers": [], "warnings": []}
        with patch.object(self.main, "process_meeting_pipeline", return_value=result) as pipeline:
            response = self.post("?num_speakers=3&max_speakers=4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pipeline.call_args.args[-1], 3)

    def test_undecodable_audio_returns_clear_400(self):
        # Mẫu thật: MediaRecorder gửi WebM dán nhãn .wav, máy không có FFmpeg
        response = self.client.post(
            "/api/process-meeting?num_speakers=3",
            files={"file": ("recording.wav", b"\x1aE\xdf\xa3 not really audio", "audio/wav")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Không đọc được tệp âm thanh", response.json()["detail"])

    def test_temp_file_keeps_original_extension(self):
        result = {"schema_version": 1, "segments": [], "speakers": [], "warnings": []}
        for name, expected in (("meeting.MP3", ".mp3"), ("a.wav", ".wav"), ("noext", "")):
            with patch.object(self.main, "process_meeting_pipeline", return_value=result) as pipeline:
                self.client.post("/api/process-meeting", files={"file": (name, b"x", "audio/mpeg")})
            path = pipeline.call_args.args[3]
            self.assertEqual(os.path.splitext(path)[1], expected)

    def test_omitted_num_speakers_means_auto(self):
        result = {"schema_version": 1, "segments": [], "speakers": [], "warnings": []}
        with patch.object(self.main, "process_meeting_pipeline", return_value=result) as pipeline:
            self.post("")
        self.assertIsNone(pipeline.call_args.args[-1])


if __name__ == "__main__":
    unittest.main()
