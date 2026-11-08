"""Focused tests and opt-in offline model evaluation."""
import os

from stdio_utf8 import ensure_utf8_stdio

ensure_utf8_stdio()
# Unit test không được gọi Gemini thật khi máy có GEMINI_API_KEY trong .env;
# test của llm_backend tự đặt biến môi trường cần thiết.
os.environ.setdefault("LLM_BACKEND", "local")
