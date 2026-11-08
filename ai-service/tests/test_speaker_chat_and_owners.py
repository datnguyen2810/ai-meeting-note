"""Chat theo người nói, gán "mình" cho người đang nói, và mã bộ phân người.

Không nạp model: phần tổng hợp theo người không gọi mô hình; các phần khác dùng mock.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from meeting_processing import service
from meeting_processing.attribution import attribute_first_person_owners
from meeting_processing.summary_supplement import supplement_summary
from meeting_processing.chat import (
    GROUNDING_MIN,
    _cap_words,
    count_turns,
    idea_phrase,
    classify_idea,
    display_idea,
    find_speaker_reference,
    grounding_ratio,
    is_overview_question,
    participant_answer,
    rank_relevant_segments,
    run_meeting_chat,
    speaker_key_points,
    split_ideas,
    strip_segment_tags,
)

# Trích từ bản ghi demo thật (lời ASR giữ nguyên lỗi nghe nhầm)
SEGMENTS = [
    {"segment_id": "seg_0001", "speaker_id": "speaker_1", "speaker_label": "Người 1", "start_seconds": 1.0,
     "end_seconds": 6.0, "text": "chào mọi người hôm nay mình học nhanh để chúc tiến độ đồ án."},
    {"segment_id": "seg_0002", "speaker_id": "speaker_2", "speaker_label": "Người 2", "start_seconds": 12.0,
     "end_seconds": 20.0, "text": "bên mình đã hoàn thành phần nhận dạng giọng nói."},
    {"segment_id": "seg_0003", "speaker_id": "speaker_3", "speaker_label": "Người 3", "start_seconds": 21.0,
     "end_seconds": 30.0, "text": "phần giao diện cũng đã xong trang lịch sử cuộc họp."},
    {"segment_id": "seg_0004", "speaker_id": "speaker_2", "speaker_label": "Người 2", "start_seconds": 39.0,
     "end_seconds": 47.0, "text": "vấn đề lớn nhất là phân biệt người nói."},
    {"segment_id": "seg_0005", "speaker_id": "speaker_2", "speaker_label": "Người 2", "start_seconds": 67.0,
     "end_seconds": 73.0, "text": "mình đồng ý mình sẽ thu thêm năm đoạn ghi âm của người thật hạn là thứ sáu tuần này."},
    {"segment_id": "seg_0006", "speaker_id": "speaker_3", "speaker_label": "Người 3", "start_seconds": 101.0,
     "end_seconds": 106.0, "text": "mình sẽ chuẩn bị sẵn một cuộc họp mẫu trong lịch sử để phòng khi trình diễn lỗi."},
]


def no_llm(*args, **kwargs):
    raise AssertionError("Câu hỏi tổng hợp theo người không được gọi mô hình")


class SpeakerReferenceTests(unittest.TestCase):
    def test_numbers_and_words(self):
        cases = {
            "người hai nói về cái gì": 2, "Người 2 nói gì?": 2, "người số 3 đã nói gì": 3,
            "người thứ nhất nói gì": 1, "NGƯỜI MỘT phát biểu gì": 1, "người tư nói gì": 4,
        }
        for question, expected in cases.items():
            self.assertEqual(find_speaker_reference(question), expected, question)

    def test_not_a_speaker_reference(self):
        for question in ("mục tiêu của cuộc họp là gì", "hai người có giọng gần giống nhau không",
                         "người nói nhiều nhất là ai", "thu thêm năm đoạn của người thật"):
            self.assertIsNone(find_speaker_reference(question), question)

    def test_overview_vs_narrow(self):
        self.assertTrue(is_overview_question("người hai nói về cái gì"))
        self.assertTrue(is_overview_question("tóm tắt ý kiến của người 3"))
        self.assertFalse(is_overview_question("người 2 được giao việc gì"))
        self.assertFalse(is_overview_question("người 2 nói hạn khi nào"))


class SpeakerChatTests(unittest.TestCase):
    def ask(self, question, speaker_id=None):
        with patch("meeting_processing.chat._generate", side_effect=no_llm):
            return run_meeting_chat(None, None, question, SEGMENTS, speaker_id)

    def test_overview_groups_key_points_with_citations(self):
        result = self.ask("người hai nói về cái gì")
        self.assertFalse(result["insufficient_evidence"])
        self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0002", "seg_0004", "seg_0005"])
        answer = result["answer"]
        # Một đoạn, theo thứ tự thời gian, mỗi ý một cụm ngắn
        self.assertEqual(answer, "Người 2 (3 lượt nói) báo hoàn thành phần nhận dạng giọng nói; nêu vấn đề phân biệt "
                                 "người nói; sẽ thu thêm năm đoạn ghi âm của người thật (hạn thứ sáu tuần này).")
        self.assertTrue(all(c["quote"] == "" for c in result["citations"]))  # không chép lại nguyên văn
        self.assertNotIn("mình đồng ý", answer)  # câu xã giao bị bỏ
        self.assertNotIn("giao diện", answer)  # không lẫn lời Người 3

    def test_question_speaker_wins_over_ui_filter(self):
        result = self.ask("người 3 nói gì", speaker_id="speaker_2")
        self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0003", "seg_0006"])

    def test_unknown_speaker_number(self):
        result = self.ask("người 5 nói gì")
        self.assertTrue(result["insufficient_evidence"])
        self.assertIn("không có Người 5", result["answer"])
        self.assertIn("Người 1, Người 2, Người 3", result["answer"])

    def test_ui_filter_overview_gives_key_points(self):
        result = self.ask("nói gì", speaker_id="speaker_2")
        self.assertTrue(result["answer"].startswith("Người 2 (3 lượt nói) báo hoàn thành"))
        self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0002", "seg_0004", "seg_0005"])


class ParticipantQuestionTests(unittest.TestCase):
    """Câu hỏi về người tham gia trả lời từ dữ liệu phân người, không qua mô hình."""

    def ask(self, question):
        with patch("meeting_processing.chat._generate", side_effect=AssertionError("không được gọi model")):
            return run_meeting_chat(None, None, question, SEGMENTS)

    def test_count(self):
        for q in ("có bao nhiêu người trong cuộc họp", "cuộc họp có mấy người", "những ai tham gia"):
            result = self.ask(q)
            self.assertIn("phân biệt được 3 người nói", result["answer"], q)
            self.assertIn("có thể chưa đúng", result["answer"])
            self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0001", "seg_0002", "seg_0003"])

    def test_most(self):
        result = self.ask("ai nói nhiều nhất")
        self.assertTrue(result["answer"].startswith("Người 2 nói nhiều nhất: 3 lượt"))

    def test_not_participant_question(self):
        self.assertIsNone(participant_answer("người 2 nói gì", SEGMENTS))


class TurnCountTests(unittest.TestCase):
    def test_split_turn_counted_once(self):
        # pyannote chia một lượt của Lan thành 2 đoạn (nghỉ 1 s giữa câu)
        segs = [
            {"speaker_label": "Người 3", "start_seconds": 20.7, "end_seconds": 23.5},
            {"speaker_label": "Người 3", "start_seconds": 24.6, "end_seconds": 29.9},
            {"speaker_label": "Người 1", "start_seconds": 29.9, "end_seconds": 37.7},
            {"speaker_label": "Người 3", "start_seconds": 47.3, "end_seconds": 49.9},
        ]
        self.assertEqual(count_turns(segs), {"Người 3": 2, "Người 1": 1})

    def test_far_apart_segments_are_separate_turns(self):
        # Danh sách con: hai đoạn liền nhau nhưng cách 28 s là hai lượt
        segs = [{"speaker_label": "Người 2", "start_seconds": 39, "end_seconds": 47},
                {"speaker_label": "Người 2", "start_seconds": 67, "end_seconds": 73}]
        self.assertEqual(count_turns(segs), {"Người 2": 2})

    def test_participant_citations_have_no_quote(self):
        result = run_meeting_chat(None, None, "có mấy người", SEGMENTS)
        self.assertTrue(result["citations"])
        self.assertTrue(all(c["quote"] == "" for c in result["citations"]))


class SummarySupplementTests(unittest.TestCase):
    """Qwen trên GPU chỉ trả Kết quả + Phân công (bản demo); quy tắc thêm các mục thiếu."""

    SEGS = [
        {"speaker_id": "speaker_1", "speaker_label": "Người 1", "start_seconds": 0.5, "end_seconds": 10.9,
         "text": "chào mọi người hôm nay mình học nhanh để chốt tiến độ đồ án ghi chú cuộc họp trước buổi báo cáo "
                 "mục tiêu là thống nhất phần nào đã xong phần nào còn thiếu và phân công cho tuần tới."},
        {"speaker_id": "speaker_2", "speaker_label": "Người 2", "start_seconds": 11.7, "end_seconds": 19.7,
         "text": "bên mình đã hoàn thành phần nhận dạng giọng nói hệ thống chuyển được tệp ghi âm thành văn bản."},
        {"speaker_id": "speaker_3", "speaker_label": "Người 3", "start_seconds": 20.7, "end_seconds": 23.5,
         "text": "phần giao diện cũng đã xong trang lịch sử cuộc họp."},
        {"speaker_id": "speaker_2", "speaker_label": "Người 2", "start_seconds": 38.8, "end_seconds": 46.4,
         "text": "vấn đề lớn nhất là phân biệt người nói khi hai người có giọng gần giống nhau hệ thống đôi khi "
                 "gán nhầm lời của người này sang người kia."},
        {"speaker_id": "speaker_1", "speaker_label": "Người 1", "start_seconds": 56.7, "end_seconds": 65.3,
         "text": "vậy mình quyết định thế này nhóm sẽ giữ mô hình hiện tại cho buổi báo cáo không đổi sang mô "
                 "hình mới vì không đủ thời gian kiểm thử."},
    ]
    QWEN = ("### Kết quả / Tiến độ\n- bên mình đã hoàn thành phần nhận dạng giọng nói hệ thống chuyển được tệp "
            "ghi âm thành văn bản\n\n### Phân công công việc\n- **Người 2:** thu thêm năm đoạn ghi âm. Hạn: thứ sáu.")

    def test_missing_sections_added_in_order(self):
        out, added = supplement_summary(self.QWEN, self.SEGS)
        self.assertEqual(added, 4)
        titles = [line for line in out.split("\n") if line.startswith("### ")]
        self.assertEqual(titles, ["### Mục tiêu cuộc họp", "### Kết quả / Tiến độ", "### Vấn đề cần xử lý",
                                  "### Quyết định", "### Phân công công việc"])
        self.assertIn("- Thống nhất phần nào đã xong phần nào còn thiếu và phân công cho tuần tới (Người 1)", out)
        # Điều kiện "khi ..." được giữ, phần dính sau ("hệ thống đôi khi...") bị cắt
        self.assertIn("- Phân biệt người nói khi hai người có giọng gần giống nhau (Người 2)", out)
        # Giữ lý do và từ phủ định của quyết định
        self.assertIn("không đổi sang mô hình mới vì không đủ thời gian kiểm thử (Người 1)", out)
        # "họp nhanh để chốt tiến độ" là mục đích, không phải quyết định
        self.assertNotIn("chốt tiến độ", out)

    def test_existing_lines_kept_and_not_duplicated(self):
        out, _ = supplement_summary(self.QWEN, self.SEGS)
        result_section = out.split("### Kết quả / Tiến độ\n")[1].split("\n\n")[0].split("\n")
        self.assertEqual(result_section[0], "- bên mình đã hoàn thành phần nhận dạng giọng nói hệ thống chuyển "
                                            "được tệp ghi âm thành văn bản")  # dòng Qwen giữ nguyên
        self.assertEqual(result_section[1:], ["- Phần giao diện cũng đã xong trang lịch sử cuộc họp (Người 3)"])
        self.assertIn("- **Người 2:** thu thêm năm đoạn ghi âm. Hạn: thứ sáu.", out)

    def test_no_change_without_new_points_or_segments(self):
        self.assertEqual(supplement_summary(self.QWEN, []), (self.QWEN, 0))
        out, _ = supplement_summary(self.QWEN, self.SEGS)
        self.assertEqual(supplement_summary(out, self.SEGS), (out, 0))  # chạy lại không thêm gì

    def test_error_text_kept_as_preamble(self):
        out, added = supplement_summary("Chưa thể tạo tóm tắt do lỗi xử lý mô hình.", self.SEGS)
        self.assertTrue(out.startswith("Chưa thể tạo tóm tắt do lỗi xử lý mô hình.\n\n### Mục tiêu cuộc họp"))
        self.assertGreater(added, 0)


class AssignmentGroupTests(unittest.TestCase):
    def test_assignment_to_other_person(self):
        self.assertEqual(classify_idea("ngoài ra tuấn sẽ phụ trách viết báo cáo và làm bài trình chiếu"), "Giao việc")
        self.assertEqual(classify_idea("anh khoa sẽ kiểm tra máy chủ"), "Giao việc")
        self.assertEqual(classify_idea("mình sẽ nhấn riêng cho tuấn sau buổi học"), "Sẽ làm")
        self.assertEqual(classify_idea("mình cũng sẽ viết báo cáo"), "Sẽ làm")
        self.assertEqual(classify_idea("còn mình sẽ tối ưu trợ lý hỏi đáp"), "Sẽ làm")


class LongMeetingContextTests(unittest.TestCase):
    """Cuộc họp > 35 đoạn: đoạn khớp câu hỏi phải nằm trong ngữ cảnh đưa cho mô hình."""

    def test_best_match_after_first_twenty_is_kept(self):
        segs = [{"segment_id": f"seg_{i:04d}", "speaker_id": "speaker_1", "speaker_label": "Người 1",
                 "start_seconds": i, "end_seconds": i + 1, "text": "chúng ta tiếp tục thảo luận nội dung chung"}
                for i in range(60)]
        segs[45] = {**segs[45], "text": "ngân sách quảng cáo tháng sau là năm mươi triệu"}
        selected, _, max_score = rank_relevant_segments("ngân sách quảng cáo bao nhiêu", segs, top_k=20)
        ids = [s["segment_id"] for s in selected]
        self.assertGreater(max_score, 0)
        self.assertIn("seg_0045", ids)
        self.assertLessEqual(len(ids), 20)
        self.assertEqual(ids, sorted(ids))  # vẫn theo thứ tự thời gian


class SegmentTagTests(unittest.TestCase):
    def test_tags_removed_from_answer(self):
        self.assertEqual(strip_segment_tags("Người 2 sẽ thu âm [seg_0005]."), "Người 2 sẽ thu âm.")
        self.assertEqual(strip_segment_tags("Đã xong [seg_0002], [seg_0003]"), "Đã xong")
        self.assertEqual(strip_segment_tags("A (seg_0001, seg_0002) và B"), "A và B")
        self.assertEqual(strip_segment_tags("dòng 1\ndòng 2"), "dòng 1\ndòng 2")


class KeyPointRulesTests(unittest.TestCase):
    """Quy tắc tách/xếp nhóm ý, lấy từ bản ghi demo thật."""

    def test_split_drops_pleasantries_and_splits_commitments(self):
        ideas = split_ideas(
            "mình đồng ý mình sẽ thu thêm năm đoạn ghi âm hạn là thứ sáu tuần này "
            "còn mình sẽ tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây"
        )
        self.assertEqual(ideas, [
            "mình sẽ thu thêm năm đoạn ghi âm hạn là thứ sáu tuần này",
            "mình sẽ tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây",
        ])  # "mình đồng ý" và chữ "còn" đứng lẻ bị bỏ

    def test_classification(self):
        cases = {
            "mục tiêu là thống nhất phần nào đã xong": "Mục tiêu",
            "vậy mình quyết định thế này nhóm sẽ giữ mô hình hiện tại": "Quyết định",
            "mình đề xuất cả nhóm chạy thử toàn bộ hệ thống": "Đề xuất",
            "hiện giờ nhóm mình đang vướng ở chỗ nào nhiều nhất có việc gì cần xử lý gấp không": "Câu hỏi",
            "tuấn sẽ phụ trách viết báo cáo": "Giao việc",  # việc của người khác, không phải người nói
            "mình sẽ thu thêm năm đoạn ghi âm": "Sẽ làm",
            "bên mình đã hoàn thành phần nhận dạng giọng nói": "Đã làm",
            "trợ lý hỏi đáp vẫn còn chậm": "Vấn đề",
        }
        for idea, group in cases.items():
            self.assertEqual(classify_idea(idea), group, idea)

    def test_meaning_kept_and_long_ideas_shortened(self):
        decision = "vậy mình quyết định thế này nhóm sẽ giữ mô hình hiện tại không đổi sang mô hình mới"
        self.assertEqual(display_idea(decision, "Quyết định"), "Nhóm sẽ giữ mô hình hiện tại không đổi sang mô hình mới")
        long_idea = " ".join(["từ"] * 30)
        self.assertTrue(display_idea(long_idea, "Vấn đề").endswith("…"))
        self.assertEqual(len(display_idea(long_idea, "Vấn đề").split()), 18)

    def test_frames_purpose_and_deadline(self):
        self.assertEqual(display_idea("mình đề xuất cả nhóm chạy thử toàn bộ hệ thống trên máy của lan vào tối thứ năm "
                                      "để kiểm tra trước khi báo cáo", "Đề xuất"),
                         "Cả nhóm chạy thử toàn bộ hệ thống trên máy của lan vào tối thứ năm")
        self.assertEqual(display_idea("mình sẽ thu thêm năm đoạn ghi âm của người thật để đánh giá lại phần phân biệt "
                                      "người nói hạn là thứ sáu tuần này", "Sẽ làm"),
                         "Thu thêm năm đoạn ghi âm của người thật để đánh giá lại phần phân biệt người nói "
                         "(hạn: thứ sáu tuần này)")  # vừa giới hạn: giữ cả mục đích
        # Quá dài: cắt ở mệnh đề phụ xa nhất còn vừa giới hạn, giữ mục tiêu "dưới mười giây"
        self.assertEqual(display_idea("mình sẽ tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây đồng thời "
                                      "hiển thị đoạn nguồn bên cạnh câu trả lời", "Sẽ làm"),
                         "Tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây")
        self.assertEqual(display_idea("vấn đề lớn nhất là phân biệt người nói khi hai người có giọng gần giống nhau",
                                      "Vấn đề"), "Phân biệt người nói khi hai người có giọng gần giống nhau")
        # Chủ ngữ không phải đại từ ("phần giao diện") được giữ
        self.assertEqual(display_idea("phần giao diện cũng đã xong trang lịch sử cuộc họp", "Đã làm"),
                         "Phần giao diện cũng đã xong trang lịch sử cuộc họp")
        # "không" sau quyết định không bị cắt mất
        self.assertIn("không đổi sang mô hình mới vì không đủ thời gian",
                      display_idea("nhóm sẽ giữ mô hình hiện tại không đổi sang mô hình mới vì không đủ thời gian", "Quyết định"))

    def test_only_pleasantries(self):
        result = speaker_key_points("Người 3", [{**SEGMENTS[2], "text": "cảm ơn mọi người"}])
        self.assertIn("chỉ có lời chào hỏi", result["answer"])

    def test_paragraph_phrase_boundaries(self):
        # "vẫn còn" và "phòng khi" không phải chỗ bắt đầu mệnh đề mới
        self.assertEqual(idea_phrase("trợ lý hỏi đáp vẫn còn chậm mỗi câu hỏi mất khoảng mười lăm giây", "Vấn đề"),
                         "nêu vấn đề trợ lý hỏi đáp vẫn còn chậm")
        self.assertEqual(idea_phrase("mình sẽ chuẩn bị sẵn một cuộc họp mẫu trong lịch sử để phòng khi trình diễn "
                                     "trực tiếp bị lỗi", "Sẽ làm"),
                         "sẽ chuẩn bị sẵn một cuộc họp mẫu trong lịch sử")
        # Chủ ngữ mới + động từ là ranh giới; "toàn bộ hệ thống trên máy" thì không
        self.assertEqual(idea_phrase("bên mình đã hoàn thành phần nhận dạng giọng nói hệ thống chuyển được tệp ghi âm",
                                     "Đã làm"), "báo hoàn thành phần nhận dạng giọng nói")
        self.assertEqual(idea_phrase("mình đề xuất cả nhóm chạy thử toàn bộ hệ thống trên máy của lan", "Đề xuất"),
                         "đề xuất cả nhóm chạy thử toàn bộ hệ thống trên máy của lan")
        self.assertEqual(idea_phrase("vậy chốt lại khoa đánh giá phân biệt người nói trước thứ sáu", "Quyết định"),
                         "chốt lại: khoa đánh giá phân biệt người nói trước thứ sáu")
        self.assertIsNone(idea_phrase("hiện giờ nhóm mình đang vướng ở chỗ nào", "Câu hỏi"))

    def test_cap_never_stops_right_before_negation(self):
        words = "a b c d e f g h i j k l m n o p không đổi".split()
        self.assertEqual(_cap_words(words, 16), "a b c d e f g h i j k l m n o".split() + ["…"])


class GroundingTests(unittest.TestCase):
    """Câu trả lời của mô hình không bám biên bản phải được thay bằng trích nguyên văn."""

    GOAL_SEGMENTS = SEGMENTS + [{
        "segment_id": "seg_0007", "speaker_id": "speaker_1", "speaker_label": "Người 1", "start_seconds": 0.0,
        "end_seconds": 10.0, "text": "chào mọi người hôm nay mình học nhanh để chúc tiến độ đồ án ghi chú cuộc họp "
                                     "mục tiêu là thống nhất phần nào đã xong phần nào còn thiếu",
    }]

    def ask(self, question, model_answer):
        with patch("meeting_processing.chat._generate", return_value=model_answer):
            return run_meeting_chat(None, None, question, self.GOAL_SEGMENTS)

    def test_hallucinated_answer_replaced_by_source_quote(self):
        # Câu trả lời thật Qwen đã sinh khi thử: đảo quyết định, tự thêm ngày 20/11
        bad = ("Mục tiêu của cuộc họp là chốt lại và xác định kế hoạch tiếp theo cho dự án đồ án, bao gồm việc "
               "chọn mô hình mới, cải thiện tốc độ trả lời của trợ lý hỏi đáp, và chuẩn bị cho buổi báo cáo "
               "cuối cùng vào ngày 20/11.")
        # Câu hỏi không nhắc "mục tiêu" để đi qua mô hình (câu có "mục tiêu" trả bằng quy tắc)
        result = self.ask("cuộc họp nhằm thống nhất điều gì", bad)
        self.assertIn("thống nhất phần nào đã xong phần nào còn thiếu", result["answer"].lower())
        self.assertNotIn("20/11", result["answer"])
        self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0007"])

    def test_grounded_answer_kept(self):
        good = "Mục tiêu là thống nhất phần nào đã xong phần nào còn thiếu [seg_0007]."
        shown = "Mục tiêu là thống nhất phần nào đã xong phần nào còn thiếu."  # bỏ mã nguồn khi hiển thị
        result = self.ask("cuộc họp nhằm thống nhất điều gì", good)
        self.assertEqual(result["answer"], shown)
        self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0007"])

    def test_goal_question_answered_from_source_not_model(self):
        # Câu Qwen đã sinh khi thử lại: ghép chữ có thật thành mục tiêu không ai nói
        bad = "Mục tiêu của cuộc họp là đánh giá phân biệt người nói, tối ưu trợ lý hỏi đáp, và chuẩn bị cho buổi báo cáo."
        result = self.ask("mục tiêu của cuộc họp là gì", bad)
        self.assertEqual(result["answer"],
                         "Mục tiêu theo biên bản:\n- Thống nhất phần nào đã xong phần nào còn thiếu (Người 1, 00:00)")
        self.assertEqual([c["segment_id"] for c in result["citations"]], ["seg_0007"])
        self.assertEqual(result["citations"][0]["quote"], "")

    def test_group_question_by_speaker(self):
        with patch("meeting_processing.chat._generate", side_effect=AssertionError("không được gọi model")):
            result = run_meeting_chat(None, None, "người 2 gặp vấn đề gì", SEGMENTS)
        self.assertIn("- Phân biệt người nói (Người 2, 00:39)", result["answer"])
        self.assertNotIn("Người 3", result["answer"])

    def test_ungrounded_answer_without_matching_source_is_insufficient(self):
        result = self.ask("ngân sách dự án là bao nhiêu", "Ngân sách là năm mươi triệu đồng cho quý tới.")
        self.assertTrue(result["insufficient_evidence"])
        self.assertEqual(result["citations"], [])

    def test_ratio_values(self):
        self.assertEqual(grounding_ratio("Người 2 nói về vấn đề phân biệt người nói.", "vấn đề phân biệt người nói"), 1.0)
        self.assertLess(grounding_ratio("chọn mô hình mới vào ngày 20/11", "giữ mô hình hiện tại"), GROUNDING_MIN)


class OwnerAttributionTests(unittest.TestCase):
    SUMMARY = (
        "### Phân công công việc\n"
        "- **mình:** thu thêm năm đoạn ghi âm của người thật để đánh giá lại. Hạn: thứ sáu tuần này.\n"
        "- **tuấn:** phụ trách viết báo cáo và làm bài trình chiếu.\n"
        "- **mình:** chuẩn bị sẵn một cuộc họp mẫu trong lịch sử.\n"
        "- **mình:** làm việc không có trong biên bản nào cả."
    )

    def test_first_person_replaced_by_speaker_label(self):
        out, count = attribute_first_person_owners(self.SUMMARY, SEGMENTS)
        self.assertEqual(count, 2)
        self.assertIn("- **Người 2:** thu thêm năm đoạn", out)
        self.assertIn("- **Người 3:** chuẩn bị sẵn", out)
        self.assertIn("- **tuấn:** phụ trách", out)  # tên riêng giữ nguyên
        self.assertIn("- **mình:** làm việc không có", out)  # không tìm thấy thì không đoán

    def test_ambiguous_match_kept(self):
        segments = SEGMENTS + [{**SEGMENTS[4], "speaker_label": "Người 1", "segment_id": "seg_0099"}]
        out, count = attribute_first_person_owners(self.SUMMARY, segments)
        self.assertIn("- **mình:** thu thêm năm đoạn", out)
        self.assertEqual(count, 1)

    def test_markdown_escape_and_other_lines_untouched(self):
        summary = "### Kết quả\n- mình đã xong\n- **tôi:** chuẩn bị sẵn một cuộc họp mẫu \\(bản demo\\)."
        out, count = attribute_first_person_owners(summary, SEGMENTS)
        self.assertEqual(count, 1)
        self.assertTrue(out.startswith("### Kết quả\n- mình đã xong\n"))

    def test_recap_by_chair_does_not_block_self_claim(self):
        # Người 1 chốt lại "lan tối ưu trợ lý hỏi đáp" nhưng người tự nhận việc là Người 3
        segments = [
            {**SEGMENTS[2], "text": "còn mình sẽ tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây"},
            {**SEGMENTS[0], "text": "vậy chốt lại lan tối ưu trợ lý hỏi đáp và cả nhóm chạy thử vào tối thứ năm"},
        ]
        summary = "### Phân công công việc\n- **mình:** tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây."
        out, count = attribute_first_person_owners(summary, segments)
        self.assertEqual(count, 1)
        self.assertIn("- **Người 3:** tối ưu trợ lý", out)

    def test_empty_inputs(self):
        self.assertEqual(attribute_first_person_owners("", SEGMENTS), ("", 0))
        self.assertEqual(attribute_first_person_owners("- **mình:** x y z", []), ("- **mình:** x y z", 0))


class PipelineModelsTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(self.path, np.zeros(16000 * 12, dtype=np.float32), 16000)

    def tearDown(self):
        os.remove(self.path)

    def run_pipeline(self, diarize):
        texts = iter(["mình sẽ chuẩn bị sẵn một cuộc họp mẫu trong lịch sử", "đồng ý"])

        def asr(chunk):
            return {"text": next(texts, "")}

        summary = "### Phân công công việc\n- **mình:** chuẩn bị sẵn một cuộc họp mẫu trong lịch sử."
        with patch.object(service, "diarize_with_engine", **diarize), \
             patch.object(service, "run_summarize", return_value=summary):
            return service.process_meeting_pipeline(asr, object(), object(), self.path)

    def test_reports_engine_and_attributes_owner(self):
        turns = [{"start": 0.5, "end": 5.0, "speaker_id": "speaker_1"},
                 {"start": 6.0, "end": 11.0, "speaker_id": "speaker_2"}]
        result = self.run_pipeline({"return_value": (turns, "acoustic-pitch-mfcc", [])})
        self.assertEqual(result["models"]["diarization"], "acoustic-pitch-mfcc")
        self.assertEqual(result["models"]["asr"], "vinai/PhoWhisper-small")
        self.assertIn("- **Người 1:** chuẩn bị sẵn", result["summary"])

    def test_diarization_failure_keeps_transcript_without_fake_speakers(self):
        result = self.run_pipeline({"side_effect": RuntimeError("hỏng")})
        self.assertEqual(result["models"]["diarization"], "none")
        self.assertEqual(result["speakers"], [])
        self.assertEqual(result["segments"][0]["attribution_status"], "unknown")
        self.assertIsNone(result["segments"][0]["speaker_id"])
        self.assertTrue(any("Không phân được người nói" in w for w in result["warnings"]))
        self.assertIn("- **mình:**", result["summary"])  # không có người nói thì không thay

    def test_speaker_without_text_not_listed(self):
        # Lượt của speaker_2 nhận dạng ra chuỗi rỗng: không tạo nút lọc rỗng cho người này
        turns = [{"start": 0.5, "end": 5.0, "speaker_id": "speaker_1"},
                 {"start": 6.0, "end": 11.0, "speaker_id": "speaker_2"}]
        texts = iter(["mình sẽ chuẩn bị sẵn một cuộc họp mẫu", ""])
        with patch.object(service, "diarize_with_engine", return_value=(turns, "acoustic-pitch-mfcc", [])), \
             patch.object(service, "run_summarize", return_value=""):
            result = service.process_meeting_pipeline(lambda c: {"text": next(texts, "")}, object(), object(), self.path)
        self.assertEqual([s["label"] for s in result["speakers"]], ["Người 1"])
        self.assertEqual(len(result["segments"]), 1)


if __name__ == "__main__":
    unittest.main()
