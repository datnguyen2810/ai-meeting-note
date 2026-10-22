"""Token-budgeted extraction, bounded retry and deterministic rendering."""

import logging
import re

from .prompts import messages_for
from .render import render_markdown
from .schema import SummaryData
from .validation import completed_json, explicit_source_facts, merge_results, parse_extraction, validate_extraction

logger = logging.getLogger(__name__)
MAX_NEW_TOKENS = 1400
MAX_TRANSCRIPT_TOKENS = 1000
MAX_CONTEXT_TOKENS = 4096


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


def summarize_with_generator(transcript, tokenizer, generate):
    """Pure orchestration; tests inject generation without loading model weights."""
    if not transcript.strip():
        return "Không có nội dung để tóm tắt."
    parts = []
    for index, chunk in enumerate(split_transcript(transcript, tokenizer), start=1):
        best = None
        for attempt in range(2):
            try:
                extraction = parse_extraction(generate(messages_for(chunk, retry=attempt > 0)))
                candidate = validate_extraction(extraction, chunk)
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
        parts.append(merge_results([best, explicit_source_facts(chunk)]))
    return render_markdown(merge_results(parts))


def run_summarize(llm_model, llm_tokenizer, transcript: str, device: str) -> str:
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
            return completed_json(raw) or raw
        finally:
            del inputs, outputs
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    try:
        return summarize_with_generator(transcript, llm_tokenizer, generate)
    except torch.cuda.OutOfMemoryError:
        logger.exception("Summary inference ran out of GPU memory")
        return "Không thể hoàn tất tóm tắt do thiếu bộ nhớ GPU. Phiên âm vẫn có thể sử dụng; hãy thử lại với đoạn ngắn hơn."
