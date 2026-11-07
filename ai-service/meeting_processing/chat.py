import re
from typing import List, Dict, Any, Optional, Tuple

VIETNAMESE_STOP_WORDS = {
    "là", "gì", "thế", "nào", "sao", "ai", "ở", "đâu", "khi", "bao", "nhiêu",
    "có", "không", "được", "các", "những", "cho", "về", "của", "trong", "và",
    "với", "như", "thì", "đã", "sẽ", "đang", "hãy", "tôi", "bạn", "nói", "biết",
    "hỏi", "xin", "này", "đó", "kia", "một", "hai", "ba", "làm", "cần", "phải",
    "việc", "ra", "lại", "đến", "đi", "người", "gặp"
}

# Các từ khóa đồng nghĩa/liên quan khi câu hỏi hỏi về điểm chưa tốt, tồn đọng, sự cố
ISSUE_SYNONYMS = {
    "chưa", "chậm", "kém", "lỗi", "hỏng", "khó", "hạn chế", "tồn đọng",
    "phản hồi", "phàn nàn", "hài lòng", "khắc phục", "vấn đề", "sai"
}


def extract_keywords(text: str) -> List[str]:
    """Tách từ khóa quan trọng, loại bỏ stop words tiếng Việt."""
    words = [w.lower() for w in re.findall(r"\w+", text) if len(w) > 1]
    return [w for w in words if w not in VIETNAMESE_STOP_WORDS]


def rank_relevant_segments(
    question: str,
    segments: List[Dict[str, Any]],
    top_k: int = 15
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, Dict[str, Any]]], int]:
    """
    Xếp hạng đoạn hội thoại hoặc chọn context phù hợp.
    - Nếu cuộc họp ngắn (<= 35 đoạn): Giữ toàn bộ biên bản để mô hình có đầy đủ ngữ cảnh liên tục.
    - Nếu cuộc họp dài (> 35 đoạn): Xếp hạng từ khóa kết hợp mở rộng cửa sổ ngữ cảnh lân cận (i-1, i+1).
    """
    if not segments:
        return [], [], 0

    total_count = len(segments)
    # Với các cuộc họp ngắn, cung cấp toàn bộ đoạn theo thứ tự thời gian
    if total_count <= 35:
        # Vẫn tính score để hỗ trợ fallback citations nếu cần
        q_clean = question.strip().lower()
        keywords = extract_keywords(question)
        if any(w in q_clean for w in ["chưa tốt", "chưa được tốt", "vấn đề", "hạn chế", "khó khăn", "tồn đọng"]):
            keywords = list(set(keywords) | ISSUE_SYNONYMS)

        scored = []
        for seg in segments:
            text = seg.get("text", "").lower()
            seg_words = set(w.lower() for w in re.findall(r"\w+", text))
            score = 0
            if len(q_clean) > 3 and q_clean in text:
                score += 12
            for kw in keywords:
                if kw in seg_words:
                    score += 3
            scored.append((score, seg))

        max_score = max((sc for sc, _ in scored), default=0)
        return list(segments), scored, max_score

    # Cuộc họp dài (> 35 đoạn): Lọc theo từ khóa và mở rộng cửa sổ ngữ cảnh
    q_clean = question.strip().lower()
    keywords = extract_keywords(question)
    if any(w in q_clean for w in ["chưa tốt", "chưa được tốt", "vấn đề", "hạn chế", "khó khăn", "tồn đọng"]):
        keywords = list(set(keywords) | ISSUE_SYNONYMS)

    if not keywords:
        keywords = [w.lower() for w in re.findall(r"\w+", question) if len(w) > 1]

    scored = []
    indexed_scored = []
    for idx, seg in enumerate(segments):
        text = seg.get("text", "").lower()
        seg_words = set(w.lower() for w in re.findall(r"\w+", text))
        score = 0
        if len(q_clean) > 3 and q_clean in text:
            score += 12
        for kw in keywords:
            if kw in seg_words:
                score += 3
        scored.append((score, seg))
        indexed_scored.append((score, idx, seg))

    # Sắp xếp theo điểm giảm dần
    indexed_scored.sort(key=lambda x: x[0], reverse=True)
    max_score = indexed_scored[0][0] if indexed_scored else 0

    # Lấy các chỉ số đoạn có điểm cao nhất và mở rộng lân cận (i-1, i, i+1)
    selected_indices = set()
    for sc, idx, seg in indexed_scored[:6]:
        if sc > 0 or max_score == 0:
            selected_indices.add(idx)
            if idx > 0:
                selected_indices.add(idx - 1)
            if idx + 1 < total_count:
                selected_indices.add(idx + 1)

    # Nếu vẫn còn ít, thêm các đoạn đầu
    if len(selected_indices) < top_k:
        for idx in range(min(total_count, top_k)):
            selected_indices.add(idx)

    sorted_indices = sorted(selected_indices)[:top_k]
    selected = [segments[i] for i in sorted_indices]
    return selected, scored, max_score


def run_meeting_chat(
    llm_model,
    llm_tokenizer,
    question: str,
    segments: List[Dict[str, Any]],
    speaker_id: Optional[str] = None,
    device: str = "cpu"
) -> Dict[str, Any]:
    """Xử lý hỏi đáp về cuộc họp với Qwen2.5 và trích dẫn căn cứ nguồn."""
    if not segments:
        return {
            "answer": "Không có dữ liệu biên bản cuộc họp để trả lời.",
            "citations": [],
            "insufficient_evidence": True
        }

    # Lọc theo speaker_id nếu người dùng chọn người nói cụ thể
    target_segments = segments
    if speaker_id:
        filtered = [s for s in segments if s.get("speaker_id") == speaker_id]
        if filtered:
            target_segments = filtered

    relevant, scored_list, max_score = rank_relevant_segments(question, target_segments, top_k=20)

    # Xây dựng context
    context_lines = []
    for s in relevant:
        sid = s.get("segment_id", "")
        spk = s.get("speaker_label") or s.get("speaker_id", "Người nói")
        txt = s.get("text", "")
        context_lines.append(f"[{sid}] ({spk}): {txt}")

    context_text = "\n".join(context_lines)

    system_prompt = (
        "Bạn là trợ lý AI thư ký cuộc họp chuyên nghiệp, trả lời chính xác dựa trên các đoạn phát biểu được cung cấp.\n\n"
        "Quy tắc quan trọng:\n"
        "1. Đồng nhất phạm vi: Các từ như 'dự án', 'hệ thống', 'nhóm', 'công việc' đều đề cập đến toàn bộ hoạt động chung của nhóm trong cuộc họp.\n"
        "2. Về vấn đề/khó khăn: Bất kỳ phản ánh chưa hài lòng, sự chậm trễ (như phản hồi tin nhắn chậm), lỗi, sự cố hay khâu cần kiểm tra khắc phục đều là vấn đề tồn đọng của dự án/công việc cần nêu rõ.\n"
        "3. Về phân công người làm: Khi hỏi về một người cụ thể (ví dụ: 'Hiếu', 'Kiên', 'anh Hiếu cần làm gì'): "
        "Bạn BẮT BUỘC phải đọc kỹ và CHỈ trả lời công việc được gán trực tiếp cho đúng người đó (sau 'anh/chị [Tên] sẽ/cần/phải/chịu trách nhiệm...'). "
        "TUYỆT ĐỐI KHÔNG nhầm lẫn hoặc gộp công việc của người khác vào.\n"
        "4. Trích dẫn: Hãy đính kèm mã trích dẫn tương ứng ở cuối câu trả lời (ví dụ: [seg_0003], [seg_0004]). Không đặt toàn bộ câu trả lời trong ngoặc vuông.\n"
        "5. Nếu trong biên bản hoàn toàn không nhắc gì đến chủ đề được hỏi: Hãy trả lời: 'Biên bản cuộc họp không có thông tin về vấn đề này.' Tuyệt đối không bịa đặt."
    )

    user_prompt = f"Các đoạn phát biểu trong cuộc họp:\n{context_text}\n\nCâu hỏi: {question.strip()}\nTrả lời ngắn gọn, chính xác:"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    import torch
    text_input = llm_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = llm_tokenizer(text_input, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = llm_model.generate(
            **inputs,
            max_new_tokens=300,
            do_sample=False,
            repetition_penalty=1.05
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    answer = llm_tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

    # Loại bỏ dấu ngoặc bao bọc toàn bộ câu nếu có
    if answer.startswith("[") and answer.endswith("]") and not re.search(r"seg_\d+", answer):
        answer = answer[1:-1].strip()

    # Kiểm tra xem câu trả lời có phải là không đủ thông tin hay không
    answer_lower = answer.lower()
    insufficient = any(phrase in answer_lower for phrase in [
        "không có thông tin", "chưa có thông tin", "không đề cập",
        "không nhắc đến", "không thấy nhắc", "không được nhắc",
        "chưa được đề cập", "không tìm thấy"
    ])

    # Trích xuất segment_id từ answer
    raw_cited = re.findall(r"\[?\b(seg_\d+)\b\]?", answer, re.IGNORECASE)
    cited_ids = {cid.lower() for cid in raw_cited}

    citations = []
    if not insufficient:
        # 1. Nếu có cited_ids do LLM đánh dấu
        if cited_ids:
            for s in target_segments:
                sid = str(s.get("segment_id", "")).lower()
                if sid in cited_ids:
                    citations.append({
                        "segment_id": s.get("segment_id"),
                        "speaker_id": s.get("speaker_id", ""),
                        "speaker_label": s.get("speaker_label") or s.get("speaker_id", "Người nói"),
                        "start_seconds": s.get("start_seconds", 0.0),
                        "end_seconds": s.get("end_seconds", 0.0),
                        "quote": s.get("text", "")
                    })

        # 2. Nếu LLM trả lời nhưng không ghi [seg_XXXX], chỉ lấy citations khi thực sự có keyword match (score > 0)
        if not citations and max_score > 0:
            scored_sorted = sorted(scored_list, key=lambda x: x[0], reverse=True)
            for score, s in scored_sorted:
                if score > 0 and len(citations) < 2:
                    citations.append({
                        "segment_id": s.get("segment_id"),
                        "speaker_id": s.get("speaker_id", ""),
                        "speaker_label": s.get("speaker_label") or s.get("speaker_id", "Người nói"),
                        "start_seconds": s.get("start_seconds", 0.0),
                        "end_seconds": s.get("end_seconds", 0.0),
                        "quote": s.get("text", "")
                    })

    return {
        "answer": answer,
        "citations": citations,
        "insufficient_evidence": insufficient
    }
