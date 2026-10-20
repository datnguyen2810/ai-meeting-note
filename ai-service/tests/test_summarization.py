import json
from pathlib import Path
import unittest

from summarization.render import render_markdown
from summarization.schema import Extraction
from summarization.service import split_transcript, summarize_with_generator
from summarization.validation import completed_json, explicit_source_facts, merge_results, parse_extraction, validate_extraction


CASES = json.loads((Path(__file__).parent / "fixtures/summary_cases.json").read_text(encoding="utf-8"))
NOISY = json.loads((Path(__file__).parent / "fixtures/realtime_regression.json").read_text(encoding="utf-8"))[0]
REPEATED_SUBJECT = json.loads((Path(__file__).parent / "fixtures/realtime_regression.json").read_text(encoding="utf-8"))[1]


def payload(**kwargs):
    return {
        **dict(objectives=[], results=[], issues=[], decisions=[], actions=[]), **kwargs
    }


class CharTokenizer:
    def encode(self, text, **kwargs):
        return list(text)


class SummaryTests(unittest.TestCase):
    def test_completion_subject_and_task_boundary_survive_noisy_status_words(self):
        case = REPEATED_SUBJECT
        data = validate_extraction(parse_extraction(json.dumps(case["model_extraction"])), case["transcript"])
        data = merge_results([data, explicit_source_facts(case["transcript"])])
        self.assertEqual(len(data.actions), 3)
        self.assertEqual(data.actions[-1].task, "kiểm tra độ chính xác của phần tổng thất tập trung vào tên người và nhiệm vụ được giao")
        self.assertEqual(data.results[0].text, "nhóm đã hoàn thành giao diện đăng nhập và chức năng cải thiện âm thanh còn hiển thị phụ đề trực tiếp công nhận hoạt động")
        text = render_markdown(data)
        for word in case["required"]:
            self.assertIn(word, text)
        for word in case["forbidden"]:
            self.assertNotIn(word, text)

    def test_work_about_another_person_or_a_temporal_condition_is_not_cut(self):
        for source, expected in [
            ("Anh Minh sẽ kiểm tra công việc của chị Lan trước khi chốt báo cáo", "kiểm tra công việc của chị Lan"),
            ("Anh Minh sẽ rà soát công việc của anh Minh trước khi chốt báo cáo", "rà soát công việc của anh Minh"),
        ]:
            data = explicit_source_facts(source)
            self.assertEqual(data.actions[0].task, expected)
    def test_noisy_realtime_regression_uses_full_source_assignments(self):
        checked = validate_extraction(parse_extraction(json.dumps(NOISY["model_extraction"])), NOISY["transcript"])
        merged = merge_results([checked, explicit_source_facts(NOISY["transcript"])])
        self.assertEqual(len(merged.actions), 3)
        self.assertEqual([a.assignee for a in merged.actions], ["thanh lam", "chị lan", "anh minh"])
        self.assertEqual(merged.actions[1].deadline_text, "trước ngày nay ngày hai mươi năm tháng mười")
        self.assertTrue(merged.actions[0].needs_confirmation)
        self.assertTrue(merged.actions[1].needs_confirmation)
        self.assertNotIn("công việc của anh minh", merged.actions[2].task)
        self.assertNotIn("mọi người cập nhật", merged.actions[2].task)
        self.assertNotIn("chào mọi người", merged.results[0].text)
        self.assertNotIn("nhưng", merged.results[0].text)
        rendered = render_markdown(merged)
        for word in NOISY["required"]:
            self.assertIn(word, rendered)
        for word in NOISY["forbidden"]:
            self.assertNotIn(word, rendered)

    def test_full_deadline_is_recovered_without_erasing_real_conflicts(self):
        source = "Chị Lan sẽ gửi báo cáo trước ngày 25 tháng 10. Chị Lan sẽ gửi báo cáo trước ngày 26 tháng 10."
        raw = payload(actions=["Lan sẽ gửi báo cáo trước ngày 25", "Lan sẽ gửi báo cáo trước ngày 26"])
        data = merge_results([validate_extraction(parse_extraction(json.dumps(raw)), source)])
        self.assertEqual(len(data.actions), 2)
        self.assertEqual({a.deadline_text for a in data.actions}, {"trước ngày 25 tháng 10", "trước ngày 26 tháng 10"})
        self.assertTrue(data.warnings)

    def test_unset_deadline_metadata_does_not_remove_the_assigned_work(self):
        source = "Anh Minh sẽ kiểm tra bản tóm tắt công việc của anh Minh chưa chốt thời hạn sau khi hoàn thành mọi người cập nhật kết quả vào nhóm."
        result = explicit_source_facts(source)
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(result.actions[0].task, "kiểm tra bản tóm tắt")
        self.assertIsNone(result.actions[0].deadline_text)

    def test_reference_actions_are_grounded_and_preserved(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                data = validate_extraction(Extraction(**payload(actions=case["actions"])), case["transcript"])
                self.assertFalse(data.warnings)
                self.assertEqual(len(data.actions), len(case["actions"]))
                rendered = render_markdown(merge_results([data]))
                for forbidden in case["forbidden"]:
                    self.assertNotIn(forbidden.casefold(), rendered.casefold())
                for action in case["actions"]:
                    self.assertIn(action["task"], rendered)
                    if action["deadline_text"]:
                        self.assertIn(action["deadline_text"], rendered)

    def test_invented_fact_or_nonliteral_task_is_rejected(self):
        source = CASES[0]["transcript"]
        data = Extraction(**payload(
            issues=[{"text": "email còn chậm", "evidence": "tốc độ phản hồi tin nhắn còn chậm"}],
            actions=[{**CASES[0]["actions"][1], "task": "chuẩn bị báo cáo cuối năm"}],
        ))
        checked = validate_extraction(data, source)
        self.assertFalse(checked.issues)
        self.assertFalse(checked.actions)
        self.assertTrue(checked.warnings)

    def test_invented_owner_and_deadline_are_removed_not_normalized(self):
        action = {**CASES[0]["actions"][1], "assignee": "giám đốc Hiếu", "deadline_text": "25/10/2026"}
        result = validate_extraction(Extraction(**payload(actions=[action])), CASES[0]["transcript"])
        self.assertIsNone(result.actions[0].assignee)
        self.assertIsNone(result.actions[0].deadline_text)
        self.assertTrue(result.actions[0].needs_confirmation)

    def test_word_boundaries_do_not_accept_partial_names_or_numbers(self):
        action = {"assignee": "Lan", "task": "kiểm tra máy", "deadline_text": "15", "evidence": "Lananh kiểm tra máy ngày 115", "needs_confirmation": False}
        result = validate_extraction(Extraction(**payload(actions=[action])), action["evidence"])
        self.assertIsNone(result.actions[0].assignee)
        self.assertIsNone(result.actions[0].deadline_text)

    def test_conflicting_deadlines_retained_with_warning_and_duplicates_merged(self):
        case = CASES[-1]
        checked = validate_extraction(Extraction(**payload(actions=case["actions"])), case["transcript"])
        merged = merge_results([checked, checked])
        self.assertEqual(len(merged.actions), 2)
        self.assertTrue(merged.warnings)
        self.assertTrue(all(a.needs_confirmation for a in merged.actions))

    def test_schema_rejects_missing_keys_and_coercion(self):
        for raw in ('{}', '[]', '{"actions": "invalid"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_extraction(raw)
        self.assertEqual(parse_extraction('```json\n' + json.dumps(payload()) + '\n```').actions, [])
        result = parse_extraction(json.dumps(payload(actions=[{**CASES[0]["actions"][0], "needs_confirmation": "false"}])))
        self.assertFalse(result.actions)
        self.assertTrue(result.warnings)

    def test_one_malformed_item_does_not_discard_valid_assignments(self):
        result = parse_extraction(json.dumps(payload(decisions=CASES[0]["actions"], actions=[{"task": 42}])))
        self.assertEqual(len(result.actions), 2)
        self.assertTrue(result.warnings)

    def test_omitted_evidence_is_recovered_only_from_same_assignment(self):
        actions = [{k: v for k, v in a.items() if k != "evidence"} for a in CASES[0]["actions"]]
        checked = validate_extraction(Extraction(**payload(actions=actions)), CASES[0]["transcript"])
        self.assertEqual(len(checked.actions), 2)
        self.assertFalse(checked.warnings)
        actions[0]["assignee"] = "anh hiếu"
        checked = validate_extraction(Extraction(**payload(actions=actions)), CASES[0]["transcript"])
        self.assertEqual(len(checked.actions), 1)
        self.assertTrue(checked.warnings)

    def test_verbatim_assignment_quotes_preserve_people_and_spoken_dates(self):
        case = CASES[0]
        raw = json.dumps(payload(actions=[a["evidence"] for a in case["actions"]]))
        checked = validate_extraction(parse_extraction(raw), case["transcript"])
        self.assertEqual(len(checked.actions), 2)
        for original, action in zip(case["actions"], checked.actions):
            self.assertEqual(action.assignee, original["assignee"])
            self.assertEqual(action.task, original["task"])
            self.assertEqual(action.deadline_text, original["deadline_text"])
        self.assertTrue(checked.actions[0].needs_confirmation)

    def test_two_assignments_in_one_quote_are_not_given_to_one_owner(self):
        quote = "Anh Nam sẽ kiểm tra máy chủ trước thứ sáu còn chị Lan sẽ chuẩn bị báo cáo trước ngày 25"
        checked = validate_extraction(parse_extraction(json.dumps(payload(actions=[quote]))), quote)
        self.assertEqual([a.assignee for a in checked.actions], ["Anh Nam", "chị Lan"])
        self.assertEqual([a.deadline_text for a in checked.actions], ["trước thứ sáu", "trước ngày 25"])

    def test_fabricated_assignment_quote_is_rejected(self):
        checked = validate_extraction(parse_extraction(json.dumps(payload(actions=["Anh Nam sẽ gửi email trước ngày 15/9"]))), CASES[1]["transcript"])
        self.assertFalse(checked.actions)
        self.assertTrue(checked.warnings)

    def test_wrong_final_bracket_can_be_repaired_without_changing_values(self):
        raw = json.dumps(payload(decisions=[CASES[0]["actions"][0]["evidence"]], actions=[CASES[0]["actions"][1]["evidence"]]))
        data = parse_extraction(raw[:-1] + "]")
        checked = validate_extraction(data, CASES[0]["transcript"])
        self.assertEqual([a.assignee for a in checked.actions], ["anh kiên", "anh hiếu"])
        self.assertTrue(checked.warnings)
        with self.assertRaises(ValueError):
            parse_extraction(raw[:-15])

    def test_statements_about_missing_assignments_do_not_become_tasks(self):
        raw = json.dumps(payload(actions=["Chưa phân công người phụ trách", "Chưa chốt thời hạn"]))
        self.assertFalse(parse_extraction(raw).actions)

    def test_source_recovery_preserves_explicit_work_even_if_model_omits_it(self):
        for case in CASES[:2]:
            data = explicit_source_facts(case["transcript"])
            self.assertEqual(len(data.actions), 2)
            for reference, actual in zip(case["actions"], data.actions):
                self.assertEqual(actual.assignee.casefold(), reference["assignee"].casefold())
                self.assertEqual(actual.task, reference["task"])
                self.assertEqual(actual.deadline_text, reference["deadline_text"])

    def test_source_recovery_does_not_treat_negation_or_condition_as_completed_work(self):
        data = explicit_source_facts("Nhóm chưa chắc đã hoàn thành giao diện. Nếu đã hoàn thành thì gửi báo cáo. Anh Nam sẽ không kiểm tra máy chủ.")
        self.assertFalse(data.results)
        self.assertFalse(data.actions)

    def test_explicit_unassigned_request_is_kept_without_inventing_owner_or_date(self):
        result = explicit_source_facts(CASES[2]["transcript"])
        self.assertEqual(len(result.actions), 1)
        self.assertIn("kiểm tra máy chủ", result.actions[0].task)
        self.assertIsNone(result.actions[0].assignee)
        self.assertIsNone(result.actions[0].deadline_text)

    def test_json_completion_stops_at_all_expected_fields_without_touching_strings(self):
        obj = payload(actions=['Anh Nam sẽ gửi báo cáo "Q4" trước thứ sáu'])
        raw = json.dumps(obj, ensure_ascii=False)
        self.assertEqual(json.loads(completed_json(raw[:-1] + ',"agenda":[')), obj)
        self.assertEqual(json.loads(completed_json(raw[:-1])), obj)
        self.assertIsNone(completed_json(raw[:-10]))
        self.assertIsNone(completed_json('{"objectives":['))

    def test_greeting_misclassified_as_action_is_not_rendered_as_work(self):
        quote = CASES[3]["transcript"]
        self.assertFalse(parse_extraction(json.dumps(payload(actions=[quote]))).actions)

    def test_short_owner_alias_is_deduplicated_but_two_titles_stay_distinct(self):
        a = CASES[1]["actions"][0]
        full = validate_extraction(Extraction(**payload(actions=[a])), CASES[1]["transcript"])
        short = full.model_copy(deep=True)
        short.actions[0].assignee = "nam"
        merged = merge_results([short, full])
        self.assertEqual(len(merged.actions), 1)
        self.assertEqual(merged.actions[0].assignee, "anh nam")
        other = full.model_copy(deep=True)
        other.actions[0].assignee = "chị nam"
        self.assertEqual(len(merge_results([full, other]).actions), 2)

    def test_retry_is_bounded_and_failure_is_explicit(self):
        calls = []

        def generate(messages):
            calls.append(messages)
            return 'invalid'

        result = summarize_with_generator("nội dung", CharTokenizer(), generate)
        self.assertEqual(len(calls), 2)
        self.assertIn("không tạo được dữ liệu", result)
        self.assertNotIn("không có nội dung thảo luận", result)

    def test_retry_can_recover_and_preserves_source(self):
        outputs = iter(['invalid', json.dumps(payload(actions=CASES[0]["actions"]), ensure_ascii=False)])
        result = summarize_with_generator(CASES[0]["transcript"], CharTokenizer(), lambda _: next(outputs))
        self.assertIn("anh hiếu", result)
        self.assertIn("Hạn: trước ngày hai mươi lăm", result)
        self.assertNotIn("Cần xác nhận lại", result)
        self.assertNotIn("Thời hạn theo phiên âm", result)
        self.assertNotIn("Thời hạn giữ nguyên", result)
        self.assertNotIn("email", result)

    def test_token_budget_and_overlap_preserve_original_text(self):
        source = "Một việc cần kiểm tra máy chủ. " * 20
        chunks = split_transcript(source, CharTokenizer(), budget=100)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(c) <= 100 and c in source for c in chunks))
        # Unique characters verify no input is silently dropped, even without whitespace.
        source = ''.join(chr(0x4e00 + i) for i in range(250))
        self.assertEqual(''.join(split_transcript(source, CharTokenizer(), 100)), source)

    def test_empty_input_does_not_call_model(self):
        self.assertEqual(summarize_with_generator(' ', CharTokenizer(), lambda _: self.fail()), "Không có nội dung để tóm tắt.")

    def test_source_markdown_is_escaped_and_no_empty_headings(self):
        source = "[báo cáo](https://example.com)"
        data = validate_extraction(Extraction(**payload(results=[{"text": source, "evidence": source}])), source)
        output = render_markdown(data)
        self.assertIn(r"\[báo cáo\]", output)
        self.assertNotIn("### Phân công", output)


if __name__ == "__main__":
    unittest.main()
