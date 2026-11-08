"""Bảo đảm stdout/stderr ghi được tiếng Việt.

Trên Windows, khi log được chuyển hướng ra file hoặc pipe, Python dùng bảng mã
hệ thống (cp1252) nên `print` một thông báo lỗi tiếng Việt sẽ ném
UnicodeEncodeError. Lỗi này từng làm sập cả nhánh dự phòng khi phân người lỗi.
"""
import sys


def ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if reconfigure and encoding != "utf8":
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
