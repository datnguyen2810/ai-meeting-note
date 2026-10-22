"""Rendering never asks the LLM to embellish extracted facts."""

import re

from .schema import SummaryData


def plain(text: str) -> str:
    text = " ".join(text.split())
    return re.sub(r"([\\`*_{}\[\]<>#|!])", r"\\\1", text)


def render_markdown(data: SummaryData) -> str:
    sections = []
    for field, title in (
        ("objectives", "Mục tiêu cuộc họp"),
        ("results", "Kết quả / Tiến độ"),
        ("issues", "Vấn đề cần xử lý"),
        ("decisions", "Quyết định"),
    ):
        facts = getattr(data, field)
        if facts:
            sections.append(f"### {title}\n" + "\n".join(f"- {plain(f.text)}" for f in facts))
    if data.actions:
        lines = []
        for action in data.actions:
            owner = plain(action.assignee) if action.assignee else "Chưa xác định người phụ trách"
            deadline = f" Hạn: {plain(action.deadline_text)}." if action.deadline_text else ""
            lines.append(f"- **{owner}:** {plain(action.task)}.{deadline}")
        sections.append("### Phân công công việc\n" + "\n".join(lines))
    if not sections:
        sections.append("Chưa trích xuất được dữ kiện có thể kiểm chứng. Vui lòng xem lại phiên âm; không suy ra cuộc họp không có nội dung.")
    if data.warnings:
        sections.append("### Cần kiểm tra\n" + "\n".join(f"- {plain(w)}" for w in data.warnings))
    return "\n\n".join(sections)
