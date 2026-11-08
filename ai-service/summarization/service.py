"""Token-budgeted extraction, bounded retry and deterministic rendering."""

import json
import logging
import re

from .prompts import gemini_messages_for, messages_for
from .render import render_markdown
from .schema import SummaryData
from .validation import completed_json, explicit_source_facts, merge_results, parse_extraction, validate_extraction

logger = logging.getLogger(__name__)
MAX_NEW_TOKENS = 1400
MAX_TRANSCRIPT_TOKENS = 1000
MAX_CONTEXT_TOKENS = 4096
# Gemini có context rất lớn: mỗi phần ~12k token Qwen (cỡ 40 phút họp) để ít phải chia.
GEMINI_TRANSCRIPT_TOKENS = 12000
SUMMARY_SECTIONS = ("objectives", "results", "issues", "decisions", "actions")
# Ép Gemini trả đúng cấu trúc; nội dung vẫn được kiểm tra khớp nguồn như với Qwen.
# Phân công là object để khỏi tách người/việc/hạn bằng regex (hỏng khi lời không dấu câu).
_ACTION_FIELDS = ("assignee", "task", "deadline_text", "evidence")
GEMINI_SUMMARY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        **{name: {"type": "ARRAY", "items": {"type": "STRING"}} for name in SUMMARY_SECTIONS[:-1]},
        "actions": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {
                "assignee": {"type": "STRING", "nullable": True},
                "task": {"type": "STRING"},
                "deadline_text": {"type": "STRING", "nullable": True},
                "evidence": {"type": "STRING"},
            },
            "required": list(_ACTION_FIELDS),
            "propertyOrdering": list(_ACTION_FIELDS),
        }},
    },
    "required": list(SUMMARY_SECTIONS),
    "propertyOrdering": list(SUMMARY_SECTIONS),
}


def split_transcript(text, tokenizer, budget=MAX_TRANSCRIPT_TOKENS):
    """Split original text (not decoded tokens); overlap retains boundary context."""
    if budget < 1:
        raise ValueError("Token budget must be positive")
    chunks = []
    start = 0
    while start < len(text):
        # Bound tokenization work per chunk for long transcripts. Conservative
        # character cap is only a search window; actual limits use tokenizer.
        low, high = start + 1, min(len(text), start + budget * 8)
        end = start
        while low <= high:
            mid = (low + high) // 2
            if len(tokenizer.encode(text[start:mid], add_special_tokens=False)) <= budget:
                end, low = mid, mid + 1
            else:
                high = mid - 1
        if end == start:
            raise ValueError("Một ký tự vượt token budget")
        if end < len(text):
            # Prefer sentence boundaries near the end, then whitespace.
            boundary = list(re.finditer(r"[.!?]\s+", text[start:end]))
            candidates = [m.end() for m in boundary if m.end() > (end - start) * 0.65]
            if not candidates:
                boundary = list(re.finditer(r"\s+", text[start:end]))
                candidates = [m.end() for m in boundary if m.end() > (end - start) * 0.65]
            if candidates:
                end = start + candidates[-1]
        # BPE token counts can change at a newly selected word boundary.
        while end > start and len(tokenizer.encode(text[start:end], add_special_tokens=False)) > budget:
            end -= 1
        if end == start:
            raise ValueError("Không tìm được đoạn trong token budget")
        chunks.append(text[start:end])
        if end == len(text):
            break
        # Up to 20% overlap, never get stuck on short inputs.
        overlap = list(re.finditer(r"\s+", text[start:end]))
        choices = [start + m.end() for m in overlap if m.end() >= (end - start) * 0.8]
        start = choices[0] if choices and choices[0] < end else end
    return chunks


def summarize_with_generator(
    transcript, tokenizer, generate, budget=MAX_TRANSCRIPT_TOKENS, prompt=messages_for, rule_repair=True
):
    """Pure orchestration; tests inject generation without loading model weights.

    `rule_repair` bật các quy tắc vá cho Qwen: nối phân công bị cắt cụt và thêm mệnh đề
    giao việc tìm bằng regex để bù chỗ bỏ sót. Tắt với Gemini: đo trên bản demo, regex
    cắt sai câu khi lời không có dấu câu và thay câu đầy đủ của Gemini bằng bản cụt.
    """
    if not transcript.strip():
        return "Không có nội dung để tóm tắt."
    parts = []
    for index, chunk in enumerate(split_transcript(transcript, tokenizer, budget), start=1):
        best = None
        for attempt in range(2):
            try:
                extraction = parse_extraction(generate(prompt(chunk, retry=attempt > 0)))
                candidate = validate_extraction(extraction, chunk, align=rule_repair)
                # A valid first attempt is retained if the retry fails.
                def score(result):
                    count = sum(len(getattr(result, name)) for name in ("objectives", "results", "issues", "decisions", "actions"))
                    return count, -len(result.warnings)

                if best is None or score(candidate) > score(best):
                    best = candidate
                if not candidate.warnings:
                    break
            except (ValueError, TypeError) as exc:
                logger.warning("Summary extraction part %s attempt %s: %s", index, attempt + 1, type(exc).__name__)
        if best is None:
            best = SummaryData(objectives=[], results=[], issues=[], decisions=[], actions=[], warnings=[
                f"Phần {index}: không tạo được dữ liệu đúng cấu trúc sau 2 lần thử; cần xem phiên âm gốc."
            ])
        # Explicit source clauses supplement omissions without another LLM call.
        parts.append(merge_results([best, explicit_source_facts(chunk)]) if rule_repair else merge_results([best]))
    return render_markdown(merge_results(parts))


def summarize_with_gemini(transcript: str, tokenizer) -> str:
    """Cùng quy trình trích xuất + kiểm tra nguồn, chỉ thay bước sinh bằng Gemini.

    Lỗi gọi API (mạng, hạn mức) ném GeminiError ngay thay vì bị coi là JSON sai.
    """
    from llm_backend import gemini_generate

    def generate(messages):
        raw = json.loads(gemini_generate(messages, response_schema=GEMINI_SUMMARY_SCHEMA))
        # Schema bắt buộc có khóa; giá trị rỗng/null nghĩa là không nói tới
        for action in raw.get("actions", []):
            for field in ("assignee", "deadline_text"):
                if not (isinstance(action.get(field), str) and action[field].strip()):
                    action[field] = None
        return json.dumps(raw, ensure_ascii=False)

    return summarize_with_generator(
        transcript, tokenizer, generate, budget=GEMINI_TRANSCRIPT_TOKENS,
        prompt=gemini_messages_for, rule_repair=False,
    )


def run_summarize_with_info(llm_model, llm_tokenizer, transcript: str, device: str) -> tuple[str, str | None]:
    """Trả (tóm tắt, tên model Gemini nếu đã dùng); Gemini lỗi thì quay về Qwen (None)."""
    import llm_backend

    if transcript.strip() and llm_backend.gemini_enabled():
        llm_backend.last_model_used = None
        try:
            summary = summarize_with_gemini(transcript, llm_tokenizer)
            if summary and "Chưa trích xuất được dữ kiện" not in summary:
                return summary, llm_backend.gemini_model_label()
            logger.warning("Gemini không trích xuất được dữ kiện; thử lại bằng Qwen.")
        except Exception as exc:
            # Thông báo GeminiError không chứa khóa API
            print(f"[WARN] Tom tat bang Gemini loi ({exc}); dung Qwen local.")
    return run_summarize_local(llm_model, llm_tokenizer, transcript, device), None


def run_summarize(llm_model, llm_tokenizer, transcript: str, device: str) -> str:
    return run_summarize_with_info(llm_model, llm_tokenizer, transcript, device)[0]


def run_summarize_local(llm_model, llm_tokenizer, transcript: str, device: str) -> str:
    import torch
    from transformers import StoppingCriteria, StoppingCriteriaList

    class CompleteExtraction(StoppingCriteria):
        def __init__(self, prompt_length):
            self.prompt_length = prompt_length

        def __call__(self, input_ids, scores, **kwargs):
            raw = llm_tokenizer.decode(input_ids[0][self.prompt_length:], skip_special_tokens=True)
            return completed_json(raw) is not None

    def generate(messages):
        inputs = outputs = None
        try:
            prompt = llm_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = llm_tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(device)
            limit = min(MAX_CONTEXT_TOKENS, getattr(llm_model.config, "max_position_embeddings", MAX_CONTEXT_TOKENS))
            if inputs.input_ids.shape[1] + MAX_NEW_TOKENS > limit:
                raise ValueError("Prompt vượt ngân sách context; không cắt mất nguồn âm thầm")
            with torch.inference_mode():
                outputs = llm_model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    do_sample=False,
                    num_beams=1,
                    repetition_penalty=1.0,
                    no_repeat_ngram_size=0,
                    stopping_criteria=StoppingCriteriaList([CompleteExtraction(inputs.input_ids.shape[1])]),
                )
            raw = llm_tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
            comp = completed_json(raw)
            if comp:
                return comp
            raw_str = raw.strip()
            if raw_str.startswith("{") and not raw_str.endswith("}"):
                raw_str += "\n}"
            return raw_str
        finally:
            del inputs, outputs
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    try:
        summary = summarize_with_generator(transcript, llm_tokenizer, generate)
        if (
            not summary
            or "Chưa trích xuất được dữ kiện" in summary
            or summary.strip().startswith("Chưa trích xuất")
        ):
            logger.info("Summary fallback to direct structured summarization.")
            summary = generate_direct_summary(llm_model, llm_tokenizer, transcript, device)
        return summary
    except torch.cuda.OutOfMemoryError:
        logger.exception("Summary inference ran out of GPU memory")
        return "Không thể hoàn tất tóm tắt do thiếu bộ nhớ GPU. Phiên âm vẫn có thể sử dụng; hãy thử lại với đoạn ngắn hơn."
    except Exception as exc:
        logger.warning("Summarize with generator failed (%s); falling back to direct summary", exc)
        try:
            return generate_direct_summary(llm_model, llm_tokenizer, transcript, device)
        except Exception as e:
            logger.exception("Direct summary also failed: %s", e)
            return "Chưa thể tạo tóm tắt do lỗi xử lý mô hình."


def generate_direct_summary(llm_model, llm_tokenizer, transcript: str, device: str) -> str:
    """Tóm tắt trực tiếp bằng Qwen2.5 khi bộ trích xuất dữ kiện khắt khe không khớp."""
    import torch

    inputs = outputs = None
    try:
        system_prompt = (
            "Bạn là trợ lý AI chuyên tóm tắt biên bản cuộc họp tiếng Việt chuyên nghiệp, khách quan.\n"
            "Nhiệm vụ: Phân tích toàn bộ nội dung biên bản cuộc họp và viết một bản tóm tắt hoàn chỉnh theo định dạng Markdown.\n\n"
            "Cấu trúc tóm tắt:\n"
            "### Mục tiêu cuộc họp\n"
            "- Nêu rõ mục tiêu hoặc lý do tổ chức cuộc họp.\n\n"
            "### Kết quả / Tiến độ\n"
            "- Các kết quả, tiến độ công việc hoặc điểm sáng đã đạt được.\n\n"
            "### Kế hoạch / Nhiệm vụ tiếp theo\n"
            "- Các công việc cần triển khai, bước đi tiếp theo và người phụ trách nếu có.\n\n"
            "### Vấn đề cần xử lý\n"
            "- Các tồn đọng, khó khăn, phản hồi chưa tốt hoặc sự cố cần khắc phục (nếu không có, có thể bỏ qua mục này).\n\n"
            "Quy tắc quan trọng:\n"
            "1. Chỉ tóm tắt dựa trên sự thật có trong biên bản, không suy diễn hoặc bịa đặt.\n"
            "2. Không sử dụng biểu tượng hoặc emoji.\n"
            "3. Trình bày ngắn gọn, súc tích, theo từng gạch đầu dòng rõ ràng."
        )
        user_prompt = f"Biên bản cuộc họp:\n{transcript}\n\nHãy viết bản tóm tắt cuộc họp theo cấu trúc trên:"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        prompt = llm_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = llm_tokenizer(prompt, return_tensors="pt").to(device)
        with torch.inference_mode():
            outputs = llm_model.generate(
                **inputs,
                max_new_tokens=800,
                do_sample=False,
                repetition_penalty=1.05
            )
        return llm_tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
    finally:
        del inputs, outputs
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
