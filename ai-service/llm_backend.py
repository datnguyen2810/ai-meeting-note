"""Chọn mô hình ngôn ngữ cho tóm tắt và chat: Gemini API hoặc Qwen chạy local.

Cấu hình qua biến môi trường (hoặc file `.env` ở `ai-service/` hay gốc repo):
- `LLM_BACKEND`: `gemini` hoặc `local`. Bỏ trống thì dùng Gemini khi có khóa.
- `GEMINI_API_KEY`: khóa lấy ở Google AI Studio. Không ghi vào code/tài liệu.
- `GEMINI_MODEL`: mã model, mặc định `DEFAULT_GEMINI_MODEL`.
- `GEMINI_TIMEOUT`: số giây chờ mỗi request, mặc định 90.
- `GEMINI_FALLBACK_MODELS`: model thử tiếp khi model chính quá tải (phân cách bằng dấu phẩy),
  mặc định `DEFAULT_FALLBACK_MODELS`; đặt `none` để tắt.

Lỗi tạm thời (500, 503, mất kết nối) được thử lại `RETRIES` lần với thời gian chờ tăng
dần, rồi mới chuyển sang model dự phòng. Hết hạn mức (429) thì chuyển model ngay.

Gọi REST bằng thư viện chuẩn để không thêm dependency. Mọi lỗi (mạng, hết hạn mức,
phản hồi rỗng) ném `GeminiError`; bên gọi tự quay về Qwen.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Gói free (đo 2026-11-08): flash-lite 15 request/phút, 500/ngày, ~1 s, tóm tắt bản demo
# đúng như flash; gemini-3.5-flash chỉ 5/phút, 20/ngày (tính chung hạn mức "3.6 Flash")
# và hay trả 503 khi quá tải, nên làm dự phòng.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_FALLBACK_MODELS = "gemini-3.5-flash"
RETRIES = 2
RETRY_DELAYS = (2.0, 5.0)
# 429 là hết hạn mức (thường theo ngày): không thử lại cùng model mà chuyển model khác
TRANSIENT_HTTP = {500, 502, 503, 504}
QUOTA_HTTP = 429
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ENV_KEYS = ("LLM_BACKEND", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT", "GEMINI_FALLBACK_MODELS", "HF_TOKEN", "HUGGINGFACE_TOKEN")
_ENV_FILES = (Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / ".env")
_env_loaded = False
# Model đã trả lời lần gọi thành công gần nhất (gọi tuần tự dưới gpu_lock)
last_model_used = None


class GeminiError(RuntimeError):
    """Gọi Gemini thất bại; thông báo không chứa khóa API."""

    def __init__(self, message, transient=False, status=None):
        super().__init__(message)
        self.transient = transient
        self.status = status


def load_env_files(paths=_ENV_FILES) -> None:
    """Nạp các biến LLM từ `.env` (chỉ các khóa trong ENV_KEYS, không ghi đè biến đã có)."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    for path in paths:
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key in ENV_KEYS and value and key not in os.environ:
                os.environ[key] = value


def gemini_enabled() -> bool:
    load_env_files()
    backend = os.getenv("LLM_BACKEND", "").strip().lower()
    if backend == "local":
        return False
    has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
    if backend == "gemini" and not has_key:
        logger.warning("LLM_BACKEND=gemini nhưng thiếu GEMINI_API_KEY; dùng Qwen local.")
    return has_key


def gemini_model() -> str:
    load_env_files()
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL


def gemini_models() -> list[str]:
    """Model chính rồi các model dự phòng, không trùng."""
    load_env_files()
    raw = os.getenv("GEMINI_FALLBACK_MODELS")
    raw = DEFAULT_FALLBACK_MODELS if raw is None else raw
    extra = [] if raw.strip().lower() == "none" else [m.strip() for m in raw.split(",") if m.strip()]
    models = [gemini_model()]
    for model in extra:
        if model not in models:
            models.append(model)
    return models


def gemini_model_label(model: str | None = None) -> str:
    """Tên lưu vào `models.summary` để giao diện hiện đúng model đã dùng."""
    return f"google/{model or last_model_used or gemini_model()}"


def build_request_body(messages, response_schema=None, max_output_tokens=8192) -> dict:
    """Chuyển messages kiểu OpenAI (system/user/assistant) sang body của Gemini."""
    system_parts, contents = [], []
    for message in messages:
        role, text = message.get("role"), str(message.get("content", ""))
        if role == "system":
            system_parts.append({"text": text})
        else:
            contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
    if not contents:
        raise ValueError("Cần ít nhất một message user")
    config = {"temperature": 0, "maxOutputTokens": max_output_tokens}
    if response_schema is not None:
        config["responseMimeType"] = "application/json"
        config["responseSchema"] = response_schema
    body = {"contents": contents, "generationConfig": config}
    if system_parts:
        body["systemInstruction"] = {"parts": system_parts}
    return body


def extract_text(data: dict) -> str:
    """Lấy văn bản trả lời (bỏ phần suy nghĩ); báo lỗi rõ khi bị chặn hoặc cụt."""
    feedback = data.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise GeminiError(f"Gemini chặn yêu cầu: {feedback['blockReason']}")
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiError("Gemini không trả về kết quả")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    reason = candidate.get("finishReason")
    if reason == "MAX_TOKENS":
        raise GeminiError("Gemini dừng vì hết giới hạn token; kết quả bị cụt")
    if not text.strip():
        raise GeminiError(f"Gemini trả về rỗng (finishReason={reason})")
    return text.strip()


def _request_once(model, key, body, timeout, opener) -> str:
    request = urllib.request.Request(
        API_URL.format(model=model),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        raise GeminiError(f"Gemini HTTP {exc.code} ({model}): {detail[:200]}", exc.code in TRANSIENT_HTTP, exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GeminiError(f"Không kết nối được Gemini ({model}): {type(exc).__name__}", True) from None
    except json.JSONDecodeError:
        raise GeminiError(f"Phản hồi Gemini không phải JSON ({model})") from None
    return extract_text(data)


def gemini_generate(messages, response_schema=None, max_output_tokens=8192,
                    opener=urllib.request.urlopen, sleep=time.sleep) -> str:
    """Gọi generateContent: thử lại lỗi tạm thời rồi chuyển model dự phòng.

    `opener`/`sleep` thay được khi kiểm thử. Lỗi không tạm thời (400, 403, bị chặn,
    phản hồi cụt) dừng ở model đó và thử model kế tiếp.
    """
    global last_model_used
    load_env_files()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiError("Thiếu GEMINI_API_KEY")
    body = json.dumps(build_request_body(messages, response_schema, max_output_tokens), ensure_ascii=False).encode("utf-8")
    timeout = float(os.getenv("GEMINI_TIMEOUT", "90") or 90)
    errors = []
    for model in gemini_models():
        for attempt in range(RETRIES + 1):
            try:
                text = _request_once(model, key, body, timeout, opener)
                last_model_used = model
                return text
            except GeminiError as exc:
                if not exc.transient or attempt == RETRIES:
                    errors.append(str(exc))
                    break
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                print(f"[WARN] {exc}; thu lai sau {delay:.0f}s.")
                sleep(delay)
        if model != gemini_models()[-1]:
            print(f"[WARN] {errors[-1]}; chuyen sang model du phong.")
    raise GeminiError("; ".join(errors))
