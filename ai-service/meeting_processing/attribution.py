"""Gán người nhận việc khi người nói tự xưng ("mình sẽ...", "tôi sẽ...").

Bộ tóm tắt chỉ nhận văn bản không nhãn người nói nên ghi người nhận là "mình".
Pipeline biết mỗi câu thuộc lượt của ai, nên tìm lượt nói chứa nội dung công việc
rồi thay "mình" bằng nhãn người nói của lượt đó (Người 2...).

Chỉ thay khi chắc chắn: nội dung việc khớp với lượt của đúng một người. Không suy
người nhận từ tên riêng trong câu; tên riêng do bộ tóm tắt giữ nguyên.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

FIRST_PERSON = {"mình", "tôi", "em", "tớ", "tui", "bên mình", "chúng mình", "tụi mình"}
# Khớp đúng dòng phân công do summarization/render.py tạo: "- **owner:** việc. Hạn: ..."
ACTION_LINE = re.compile(r"^(?P<prefix>\s*-\s+\*\*)(?P<owner>[^*]+?)(?P<sep>:\*\*\s*)(?P<rest>.*)$")
# Số từ đầu của nội dung việc dùng để dò trong lượt nói
PROBE_WORDS = 6
MIN_PROBE_WORDS = 3


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"\\(.)", r"\1", text)  # bỏ ký tự escape Markdown của render.py
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _task_probe(rest: str) -> Optional[str]:
    task = rest.split(" Hạn:", 1)[0]
    words = _normalize(task).split()
    if len(words) < MIN_PROBE_WORDS:
        return None
    return " ".join(words[:PROBE_WORDS])


def _speaker_for(probe: str, segments: List[Dict[str, Any]]) -> Optional[str]:
    # Chỉ dùng đoạn đã gán người nói; đoạn "chưa rõ người nói" không có căn cứ
    assigned = [
        seg for seg in segments
        if seg.get("speaker_id")
        and seg.get("attribution_status", "assigned") == "assigned"
        and seg.get("speaker_label")
    ]
    # Ưu tiên lượt có người tự nhận việc ("mình sẽ <việc>"): câu chốt của chủ trì
    # nhắc lại việc của người khác ("lan tối ưu trợ lý...") không còn làm mơ hồ.
    claim = re.compile(r"(?<!\w)(?:mình|tôi|em|tớ|tui)\s+(?:sẽ|chịu trách nhiệm)\s+" + re.escape(probe))
    for matcher in (lambda text: claim.search(text) is not None, lambda text: probe in text):
        labels = {seg.get("speaker_label") for seg in assigned if matcher(_normalize(str(seg.get("text", ""))))}
        if labels:
            return labels.pop() if len(labels) == 1 else None
    return None


def attribute_first_person_owners(summary: str, segments: List[Dict[str, Any]]) -> Tuple[str, int]:
    """Trả về (summary đã thay người nhận, số dòng đã thay)."""
    if not summary or not segments:
        return summary, 0
    replaced = 0
    out = []
    for line in summary.split("\n"):
        match = ACTION_LINE.match(line)
        if match and _normalize(match.group("owner")) in FIRST_PERSON:
            probe = _task_probe(match.group("rest"))
            label = _speaker_for(probe, segments) if probe else None
            if label:
                line = f"{match.group('prefix')}{label}{match.group('sep')}{match.group('rest')}"
                replaced += 1
        out.append(line)
    return "\n".join(out), replaced
