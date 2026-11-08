"""Kiểm tra bước dọn lượt nói và cách pipeline dùng nó; không nạp model."""

import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from meeting_processing import service
from meeting_processing.turns import (
    absorb_short_turns,
    merge_same_speaker,
    padded_bounds,
    prepare_turns,
    relabel_by_first_appearance,
)


def t(start, end, spk):
    return {"start": start, "end": end, "speaker_id": spk}


def spans(turns):
    return [(x["start"], x["end"], x["speaker_id"]) for x in turns]


class AbsorbShortTurnsTests(unittest.TestCase):
    def test_short_turn_between_same_speaker_joins_them(self):
        # Mẫu thật: "và giúp" của Lan bị gán Người 1, kẹp giữa hai lượt của Lan
        turns = [t(20.0, 27.0, "speaker_3"), t(27.1, 28.0, "speaker_1"), t(28.1, 29.9, "speaker_3")]
        self.assertEqual(spans(prepare_turns(turns)), [(20.0, 29.9, "speaker_1")])  # đánh lại từ 1

    def test_start_of_new_turn_goes_to_next_speaker(self):
        # Mẫu thật: "vấn đề lớn nhất" đầu lượt Khoa bị gán cho Lan
        turns = [t(30.0, 37.7, "A"), t(38.7, 39.6, "C"), t(39.6, 46.4, "B")]
        out = absorb_short_turns(turns)
        self.assertEqual(out[1]["speaker_id"], "B")

    def test_tie_prefers_next_turn(self):
        turns = [t(0.0, 5.0, "A"), t(5.5, 6.0, "C"), t(6.5, 10.0, "B")]
        self.assertEqual(absorb_short_turns(turns)[1]["speaker_id"], "B")

    def test_closer_previous_turn_wins(self):
        turns = [t(0.0, 5.0, "A"), t(5.1, 6.0, "C"), t(7.5, 10.0, "B")]
        self.assertEqual(absorb_short_turns(turns)[1]["speaker_id"], "A")

    def test_long_turns_untouched(self):
        turns = [t(0.0, 5.0, "A"), t(5.5, 8.0, "B")]
        self.assertEqual(spans(absorb_short_turns(turns)), spans(turns))

    def test_edges_and_tiny_inputs(self):
        self.assertEqual(absorb_short_turns([]), [])
        self.assertEqual(spans(absorb_short_turns([t(0, 0.5, "A")])), [(0, 0.5, "A")])
        self.assertEqual(absorb_short_turns([t(0, 0.5, "C"), t(1.0, 6.0, "A")])[0]["speaker_id"], "A")
        self.assertEqual(absorb_short_turns([t(0, 6.0, "A"), t(6.5, 7.0, "C")])[1]["speaker_id"], "A")

    def test_input_not_mutated(self):
        turns = [t(0.0, 5.0, "A"), t(5.5, 6.0, "C"), t(6.5, 10.0, "B")]
        absorb_short_turns(turns)
        self.assertEqual(turns[1]["speaker_id"], "C")


class PyannoteFlickerTests(unittest.TestCase):
    """Mẩu pyannote thật trên file demo: chuỗi mẩu 0,01–0,4 s xen kẽ hai người ở chỗ
    chuyển lượt. Trước đây không nối được, "vậy" bị tách riêng và PhoWhisper bỏ hết
    số trong câu chốt lại."""

    def test_flicker_before_long_turn_joins_it(self):
        # 106,92–107,49: Lan/Hà/Lan xen kẽ, không ai rõ rệt -> theo lượt dài kề sau (Hà)
        turns = [t(100.81, 105.90, "lan"), t(106.92, 107.09, "lan"), t(107.09, 107.19, "ha"),
                 t(107.19, 107.49, "lan"), t(107.49, 116.28, "ha"), t(117.18, 119.30, "ha")]
        out = prepare_turns(turns)
        self.assertEqual([(x["start"], x["end"]) for x in out], [(100.81, 105.90), (106.92, 119.30)])
        self.assertEqual(out[1]["speaker_id"], "speaker_2")

    def test_block_with_dominant_speaker_follows_that_speaker(self):
        # 29,87–32,36: mở đầu bằng mẩu 0,01 s dính lượt Lan nhưng 1,35 s là lời Hà
        turns = [t(24.55, 29.87, "lan"), t(29.87, 29.88, "ha"), t(30.54, 30.96, "lan"), t(30.96, 31.17, "ha"),
                 t(31.17, 31.23, "lan"), t(31.23, 32.36, "ha"), t(33.24, 37.71, "ha")]
        out = absorb_short_turns(turns)
        self.assertEqual([x["speaker_id"] for x in out[1:6]], ["ha"] * 5)
        self.assertEqual(spans(prepare_turns(turns))[1], (29.87, 37.71, "speaker_2"))

    def test_isolated_short_turn_behaviour_unchanged(self):
        # Mẩu ngắn đứng riêng vẫn theo luật cũ (lượt dài gần hơn)
        turns = [t(0.0, 5.0, "A"), t(5.1, 6.0, "C"), t(7.5, 10.0, "B")]
        self.assertEqual(absorb_short_turns(turns)[1]["speaker_id"], "A")


class MergeAndRelabelTests(unittest.TestCase):
    def test_merge_respects_gap_and_max_length(self):
        turns = [t(0, 10, "A"), t(10.5, 20, "A"), t(22.0, 24, "A"), t(24.2, 30, "A")]
        out = merge_same_speaker(turns, max_gap=1.0, max_seconds=25.0)
        self.assertEqual(spans(out), [(0, 20, "A"), (22.0, 30, "A")])

    def test_never_merges_different_speakers(self):
        self.assertEqual(len(merge_same_speaker([t(0, 5, "A"), t(5.1, 9, "B")])), 2)

    def test_relabel_follows_first_appearance(self):
        out = relabel_by_first_appearance([t(0, 5, "speaker_3"), t(6, 9, "speaker_1"), t(10, 12, "speaker_3")])
        self.assertEqual([x["speaker_id"] for x in out], ["speaker_1", "speaker_2", "speaker_1"])
        self.assertEqual([x["label"] for x in out], ["Người 1", "Người 2", "Người 1"])

    def test_speaker_with_only_short_turns_disappears_and_numbers_stay_dense(self):
        turns = [t(0, 6, "speaker_1"), t(6.2, 7.0, "speaker_2"), t(7.2, 13, "speaker_1"), t(14, 20, "speaker_3")]
        out = prepare_turns(turns)
        self.assertEqual([x["speaker_id"] for x in out], ["speaker_1", "speaker_2"])
        self.assertEqual(out[1]["start"], 14)

    def test_prepare_sorts_unordered_input(self):
        out = prepare_turns([t(10, 15, "B"), t(0, 5, "A")])
        self.assertEqual(spans(out), [(0, 5, "speaker_1"), (10, 15, "speaker_2")])


class PaddedBoundsTests(unittest.TestCase):
    def test_pad_limited_to_half_gap_and_file_bounds(self):
        turns = [t(0.1, 5.0, "A"), t(5.1, 9.0, "B"), t(10.0, 11.9, "A")]
        self.assertEqual(padded_bounds(turns, 0, 12.0), (0.0, 5.05))
        start, end = padded_bounds(turns, 1, 12.0)
        self.assertAlmostEqual(start, 5.05)
        self.assertAlmostEqual(end, 9.2)
        self.assertEqual(padded_bounds(turns, 2, 12.0), (9.8, 12.0))

    def test_touching_turns_get_no_overlap(self):
        turns = [t(0, 5, "A"), t(5, 9, "B")]
        self.assertEqual(padded_bounds(turns, 0, 9)[1], 5)
        self.assertEqual(padded_bounds(turns, 1, 9)[0], 5)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(self.path, np.zeros(16000 * 20, dtype=np.float32), 16000)

    def tearDown(self):
        os.remove(self.path)

    def run_pipeline(self, raw_turns, engine="acoustic-pitch-mfcc"):
        chunks = []

        def asr(chunk):
            chunks.append(len(chunk) / 16000)
            return {"text": f"câu số {len(chunks)}"}

        with patch.object(service, "diarize_with_engine", return_value=(raw_turns, engine, [])), \
             patch.object(service, "run_summarize_with_info", return_value=("### Tóm tắt", None)) as summarize:
            result = service.process_meeting_pipeline(asr, object(), object(), self.path, num_speakers=2)
        return result, summarize, chunks

    def test_summary_gets_text_without_speaker_labels(self):
        raw = [t(1.0, 6.0, "speaker_1"), t(7.0, 12.0, "speaker_2")]
        result, summarize, _ = self.run_pipeline(raw)
        summary_input = summarize.call_args.args[2]
        self.assertNotIn("[Người", summary_input)
        self.assertEqual(summary_input, "câu số 1 câu số 2")
        self.assertIn("[Người 1]: câu số 1", result["transcript"])  # bản lưu vẫn có nhãn

    def test_short_fragment_absorbed_and_audio_padded_but_times_kept(self):
        raw = [t(1.0, 6.0, "speaker_1"), t(7.0, 7.8, "speaker_1"), t(7.8, 12.0, "speaker_2")]
        result, _, chunks = self.run_pipeline(raw)
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(result["segments"][1]["start_seconds"], 7.0)
        self.assertEqual(result["segments"][1]["speaker_id"], "speaker_2")
        self.assertAlmostEqual(chunks[1], 12.0 - 7.0 + 0.2 + 0.2, places=2)

    def test_pyannote_turns_get_wider_asr_padding(self):
        # Biên pyannote sát hơn: nới 0,3 s mỗi bên (vẫn không quá nửa khoảng nghỉ)
        raw = [t(1.0, 6.0, "speaker_1"), t(7.0, 12.0, "speaker_2")]
        _, _, chunks = self.run_pipeline(raw, engine="pyannote/speaker-diarization-community-1")
        self.assertAlmostEqual(chunks[1], 12.0 - 7.0 + 0.3 + 0.3, places=2)

    def test_warning_when_fewer_speakers_than_requested(self):
        result, _, _ = self.run_pipeline([t(1.0, 6.0, "speaker_1")])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
