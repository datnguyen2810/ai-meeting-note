"""Bổ sung vào bản tóm tắt các mục Qwen bỏ sót, bằng quy tắc gom ý của chat.

Trên GPU, Qwen 1.5B thường chỉ trả "Kết quả" và "Phân công" (bản demo 3 người: mất
mục tiêu, 2 vấn đề và quyết định), trong khi bộ quy tắc trong chat.py tìm được đúng
các ý đó. Hàm ở đây thêm các ý còn thiếu vào đúng mục, câu chữ lấy nguyên từ biên
bản, kèm người nói. Không gọi model.

Chỉ thêm, không sửa hay xóa dòng Qwen đã viết. Ý đã có trong mục (khớp chữ) thì bỏ qua.
"""

import re
import unicodedata
from typing import Any, Dict, List, Tuple

from summarization.render import plain

from .chat import classify_idea, compact_idea, split_ideas

# Nhóm ý -> tiêu đề mục do summarization/render.py dùng
GROUP_SECTIONS = {
    "Mục tiêu": "Mục tiêu cuộc họp",
    "Đã làm": "Kết quả / Tiến độ",
    "Vấn đề": "Vấn đề cần xử lý",
    "Quyết định": "Quyết định",
}
# Thứ tự mục trong bản tóm tắt (giống render.py), các mục khác giữ nguyên ở sau
SECTION_ORDER = ["Mục tiêu cuộc họp", "Kết quả / Tiến độ", "Vấn đề cần xử lý", "Quyết định",
                 "Phân công công việc", "Cần kiểm tra"]
MAX_ADDED_PER_SECTION = 6


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"\\(.)", r"\1", text)  # bỏ escape Markdown của render.py
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def _parse_sections(summary: str) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
    """(dòng trước tiêu đề đầu tiên, [(tiêu đề, các dòng)])."""
    preamble: List[str] = []
    sections: List[Tuple[str, List[str]]] = []
    for line in summary.split("\n"):
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            sections.append((heading.group(1), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return preamble, sections


def _rule_points(segments: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, str]]]:
    """Tiêu đề mục -> [(nội dung hiển thị, nhãn người nói)] theo thứ tự thời gian."""
    points: Dict[str, List[Tuple[str, str]]] = {title: [] for title in GROUP_SECTIONS.values()}
    for seg in segments:
        label = seg.get("speaker_label") or ""
        for idea in split_ideas(seg.get("text", "")):
            group = classify_idea(idea)
            title = GROUP_SECTIONS.get(group)
            if not title:
                continue
            # Cắt phần dính sau khi lời không có dấu câu ("... giọng nói hệ thống chuyển
            # được ..."), nhưng giữ điều kiện "khi ..." và lý do của quyết định
            text = compact_idea(idea, group, keep_condition=True)
            text = text[:1].upper() + text[1:]
            points[title].append((text, label))
    return points


def supplement_summary(summary: str, segments: List[Dict[str, Any]]) -> Tuple[str, int]:
    """Trả về (bản tóm tắt đã bổ sung, số dòng đã thêm)."""
    if not segments:
        return summary, 0
    # Thông báo lỗi/không có dữ kiện của bộ tóm tắt (không có tiêu đề) giữ làm phần mở đầu
    preamble, sections = _parse_sections(summary or "")
    by_title = {title: lines for title, lines in sections}
    added = 0
    for title, candidates in _rule_points(segments).items():
        lines = by_title.get(title)
        existing = _norm("\n".join(lines or []))
        new_lines = []
        for text, label in candidates:
            core = _norm(text.rstrip("…"))
            if not core or core in existing:
                continue
            existing += "\n" + core
            suffix = f" ({plain(label)})" if label else ""
            new_lines.append(f"- {plain(text)}{suffix}")
            if len(new_lines) >= MAX_ADDED_PER_SECTION:
                break
        if not new_lines:
            continue
        added += len(new_lines)
        if lines is None:
            sections.append((title, new_lines))
            by_title[title] = new_lines
        else:
            # Chèn sau dòng cuối có nội dung của mục
            last = max((i for i, line in enumerate(lines) if line.strip()), default=-1)
            lines[last + 1:last + 1] = new_lines
    if not added:
        return summary, 0

    def order(item):
        title = item[0]
        return SECTION_ORDER.index(title) if title in SECTION_ORDER else len(SECTION_ORDER) - 1

    sections.sort(key=order)
    blocks = []
    if any(line.strip() for line in preamble):
        blocks.append("\n".join(preamble).strip())
    for title, lines in sections:
        body = "\n".join(line for line in lines if line.strip())
        blocks.append(f"### {title}\n{body}" if body else f"### {title}")
    return "\n\n".join(blocks), added
