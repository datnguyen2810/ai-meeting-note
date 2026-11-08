import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import llm_backend
from summarization import service as summary_service


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def gemini_reply(text, finish="STOP", thought=None):
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    return {"candidates": [{"content": {"parts": parts}, "finishReason": finish}]}


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()


class GeminiBackendTest(unittest.TestCase):
    def env(self, **values):
        return patch.dict(os.environ, values, clear=False)

    def test_backend_selection(self):
        with self.env(LLM_BACKEND="", GEMINI_API_KEY="k"):
            self.assertTrue(llm_backend.gemini_enabled())
        with self.env(LLM_BACKEND="local", GEMINI_API_KEY="k"):
            self.assertFalse(llm_backend.gemini_enabled())
        with self.env(LLM_BACKEND="gemini", GEMINI_API_KEY=""):
            self.assertFalse(llm_backend.gemini_enabled())

    def test_env_file_only_loads_llm_keys_without_overriding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".env")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("DB_PASSWORD=secret\nGEMINI_MODEL='gemini-test'\nGEMINI_TIMEOUT=5\n")
            with patch.dict(os.environ, {"GEMINI_TIMEOUT": "30"}, clear=False), \
                 patch.object(llm_backend, "_env_loaded", False):
                os.environ.pop("GEMINI_MODEL", None)
                os.environ.pop("DB_PASSWORD", None)
                llm_backend.load_env_files([path])
                self.assertEqual(os.environ["GEMINI_MODEL"], "gemini-test")
                self.assertEqual(os.environ["GEMINI_TIMEOUT"], "30")
                self.assertNotIn("DB_PASSWORD", os.environ)
                os.environ.pop("GEMINI_MODEL", None)

    def test_request_body_maps_roles_and_schema(self):
        body = llm_backend.build_request_body(
            [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
            response_schema={"type": "OBJECT"},
        )
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "S"}]})
        self.assertEqual(body["contents"], [{"role": "user", "parts": [{"text": "U"}]}])
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["generationConfig"]["temperature"], 0)

    def test_generate_sends_key_in_header_and_skips_thoughts(self):
        seen = {}

        def opener(request, timeout):
            seen["url"], seen["key"] = request.full_url, request.get_header("X-goog-api-key")
            return FakeResponse(json.dumps(gemini_reply("trả lời", thought="nháp")).encode())

        with self.env(GEMINI_API_KEY="abc", GEMINI_MODEL="gemini-x"):
            text = llm_backend.gemini_generate([{"role": "user", "content": "hỏi"}], opener=opener)
        self.assertEqual(text, "trả lời")
        self.assertEqual(seen["key"], "abc")
        self.assertIn("gemini-x:generateContent", seen["url"])
        self.assertNotIn("abc", seen["url"])

    def test_errors_are_gemini_errors_without_key(self):
        def http_error(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "quota", {}, io.BytesIO(b'{"error":{"message":"Quota exceeded"}}'))

        with self.env(GEMINI_API_KEY="abc", GEMINI_FALLBACK_MODELS="none"):
            with self.assertRaises(llm_backend.GeminiError) as ctx:
                llm_backend.gemini_generate([{"role": "user", "content": "x"}], opener=http_error, sleep=lambda d: None)
        self.assertIn("429", str(ctx.exception))
        self.assertNotIn("abc", str(ctx.exception))
        with self.assertRaises(llm_backend.GeminiError):
            llm_backend.extract_text(gemini_reply("{\"a\":", finish="MAX_TOKENS"))

    def test_retries_transient_error_then_succeeds(self):
        calls, waits = [], []

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, io.BytesIO(b"{}"))
            return FakeResponse(json.dumps(gemini_reply("ok")).encode())

        with self.env(GEMINI_API_KEY="k", GEMINI_MODEL="main-model", GEMINI_FALLBACK_MODELS="none"):
            self.assertEqual(llm_backend.gemini_generate([{"role": "user", "content": "x"}], opener=opener, sleep=waits.append), "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(waits, [llm_backend.RETRY_DELAYS[0]])
        self.assertEqual(llm_backend.last_model_used, "main-model")

    def test_switches_to_fallback_model_after_retries(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if "main-model" in request.full_url:
                raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, io.BytesIO(b"{}"))
            return FakeResponse(json.dumps(gemini_reply("lite ok")).encode())

        with self.env(GEMINI_API_KEY="k", GEMINI_MODEL="main-model", GEMINI_FALLBACK_MODELS="lite-model"):
            text = llm_backend.gemini_generate([{"role": "user", "content": "x"}], opener=opener, sleep=lambda d: None)
            self.assertEqual(llm_backend.gemini_model_label(), "google/lite-model")
        self.assertEqual(text, "lite ok")
        self.assertEqual(sum("main-model" in u for u in calls), llm_backend.RETRIES + 1)

    def test_quota_error_switches_model_without_retry(self):
        calls, waits = [], []

        def opener(request, timeout):
            calls.append(request.full_url)
            if "main-model" in request.full_url:
                raise urllib.error.HTTPError(request.full_url, 429, "quota", {}, io.BytesIO(b"{}"))
            return FakeResponse(json.dumps(gemini_reply("ok")).encode())

        with self.env(GEMINI_API_KEY="k", GEMINI_MODEL="main-model", GEMINI_FALLBACK_MODELS="other"):
            self.assertEqual(llm_backend.gemini_generate([{"role": "user", "content": "x"}], opener=opener, sleep=waits.append), "ok")
        self.assertEqual(sum("main-model" in u for u in calls), 1)
        self.assertEqual(waits, [])

    def test_non_transient_error_is_not_retried(self):
        calls = []

        def opener(request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b"{}"))

        with self.env(GEMINI_API_KEY="k", GEMINI_FALLBACK_MODELS="none"):
            with self.assertRaises(llm_backend.GeminiError):
                llm_backend.gemini_generate([{"role": "user", "content": "x"}], opener=opener, sleep=lambda d: None)
        self.assertEqual(len(calls), 1)

    def test_summary_uses_gemini_and_reports_model(self):
        source = "Họp để chốt kế hoạch. Anh An sẽ kiểm tra máy chủ trước thứ sáu."
        reply = json.dumps({"objectives": ["chốt kế hoạch"], "results": [], "issues": [], "decisions": [],
                            "actions": [
                                {"assignee": "Anh An", "task": "kiểm tra máy chủ", "deadline_text": "thứ sáu",
                                 "evidence": "Anh An sẽ kiểm tra máy chủ trước thứ sáu"},
                                # trường rỗng là không nói tới; trích sai nguồn thì bị loại
                                {"assignee": "", "task": "viết báo cáo", "deadline_text": None,
                                 "evidence": "ai đó viết báo cáo"},
                            ]}, ensure_ascii=False)
        with self.env(LLM_BACKEND="gemini", GEMINI_API_KEY="k", GEMINI_MODEL="gemini-x"), \
             patch.object(llm_backend, "gemini_generate", return_value=reply) as call, \
             patch.object(summary_service, "run_summarize_local", side_effect=AssertionError("không được dùng Qwen")):
            summary, model = summary_service.run_summarize_with_info(None, FakeTokenizer(), source, "cpu")
        self.assertEqual(model, "google/gemini-x")
        self.assertIn("- **Anh An:** kiểm tra máy chủ. Hạn: thứ sáu.", summary)
        self.assertNotIn("viết báo cáo", summary)
        self.assertIn("responseSchema", json.dumps(llm_backend.build_request_body(
            call.call_args.args[0], call.call_args.kwargs["response_schema"])))

    def test_summary_falls_back_to_local_when_gemini_fails(self):
        with self.env(LLM_BACKEND="gemini", GEMINI_API_KEY="k"), \
             patch.object(llm_backend, "gemini_generate", side_effect=llm_backend.GeminiError("HTTP 429")), \
             patch.object(summary_service, "run_summarize_local", return_value="Qwen") as local:
            summary, model = summary_service.run_summarize_with_info(None, FakeTokenizer(), "nội dung họp", "cpu")
        self.assertEqual((summary, model), ("Qwen", None))
        local.assert_called_once()

    def test_chat_generate_falls_back_to_local(self):
        from meeting_processing import chat

        with self.env(LLM_BACKEND="gemini", GEMINI_API_KEY="k"), \
             patch.object(llm_backend, "gemini_generate", side_effect=llm_backend.GeminiError("mạng")), \
             patch.object(chat, "_generate_local", return_value="Qwen trả lời") as local:
            self.assertEqual(chat._generate(None, None, [{"role": "user", "content": "x"}], "cpu"), "Qwen trả lời")
        local.assert_called_once()
        with self.env(LLM_BACKEND="gemini", GEMINI_API_KEY="k"), \
             patch.object(llm_backend, "gemini_generate", return_value="Gemini trả lời"):
            self.assertEqual(chat._generate(None, None, [{"role": "user", "content": "x"}], "cpu"), "Gemini trả lời")


if __name__ == "__main__":
    unittest.main()
