"""Dọn danh sách lượt nói sau phân người, trước khi chạy ASR từng lượt.

Bộ phân người cắt theo khoảng lặng nên hay sinh mẩu rất ngắn ở chỗ chuyển người
(ví dụ 1 giây đầu lượt của người B bị gán cho người A). Mẩu ngắn vừa dễ gán nhầm,
vừa làm PhoWhisper nghe sai vì bị cắt giữa từ. Các hàm ở đây là hàm thuần (không
nạp model) để kiểm thử và để script chấm dùng chung với pipeline.

Mỗi lượt là dict có ít nhất: start, end (giây), speaker_id.
"""

from typing import Any, Dict, List, Tuple

# Lượt ngắn hơn ngưỡng này bị nhập vào lượt bên cạnh
MIN_TURN_SECONDS = 1.5
# Gộp hai lượt liền nhau của cùng người nếu nghỉ không quá ngưỡng này
MERGE_GAP_SECONDS = 1.0
# Không gộp quá độ dài này để mỗi lượt vẫn gọn trong một cửa sổ PhoWhisper
MAX_TURN_SECONDS = 25.0
# Nới biên khi cắt audio cho ASR, để không mất phụ âm đầu/cuối từ (luôn giới hạn ở
# nửa khoảng nghỉ). Đo trên file demo, đếm 8 cụm số/từ khóa PhoWhisper nghe đúng:
# - pitch/MFCC: 0,2 s -> 8/8; 0,3 s -> 7/8 (mất "trước thứ sáu").
# - pyannote (biên sát hơn): 0,2 s -> 6/8 ("thứ sáu tuần này" thành "thứ tư này",
#   "ngày hai mươi tháng mười một" thành "ngày mười"); 0,3 s -> 8/8.
ASR_PAD_SECONDS = 0.2
PYANNOTE_ASR_PAD_SECONDS = 0.3


def _duration(turn: Dict[str, Any]) -> float:
    return turn["end"] - turn["start"]


# Trong một khối lượt ngắn, một người được coi là nói rõ rệt nếu tổng thời gian của
# người đó đạt ngưỡng này và gấp ít nhất DOMINANT_RATIO lần người đứng thứ hai.
DOMINANT_SECONDS = 1.0
DOMINANT_RATIO = 2.0


def _dominant_speaker(block: List[Dict[str, Any]]) -> Any:
    """Người nói chiếm phần lớn khối mẩu ngắn, hoặc None nếu không ai rõ rệt.

    Ví dụ đo được: khối 29,87–32,36 s mở đầu bằng mẩu 0,01 s của người trước nhưng
    1,35 s là lời người sau; chỉ dựa vào lượt dài gần nhất sẽ gán nhầm cả khối.
    """
    totals: Dict[Any, float] = {}
    for turn in block:
        totals[turn["speaker_id"]] = totals.get(turn["speaker_id"], 0.0) + _duration(turn)
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top_speaker, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top >= DOMINANT_SECONDS and top >= DOMINANT_RATIO * second:
        return top_speaker
    return None


def absorb_short_turns(turns: List[Dict[str, Any]], min_seconds: float = MIN_TURN_SECONDS) -> List[Dict[str, Any]]:
    """Gán lại người nói cho các lượt ngắn theo lượt dài gần nhất hai bên.

    Một chuỗi lượt ngắn liền nhau được xử lý như một khối và gán chung một người:
    pyannote hay sinh chuỗi mẩu 0,01–0,4 s xen kẽ hai người ở chỗ chuyển lượt
    (đo trên file demo). Trước đây mỗi mẩu lấy nhãn của mẩu bên cạnh, vốn cũng là
    mẩu ngắn, nên chuỗi vẫn xen kẽ, không nối được và PhoWhisper nhận đoạn bắt đầu
    giữa câu (bỏ mất các từ chỉ số).

    - Trong khối có một người nói rõ rệt (`_dominant_speaker`): lấy người đó.
    - Kẹp giữa hai lượt dài cùng một người: lấy người đó.
    - Ngược lại: lấy người của lượt dài gần hơn về thời gian; bằng nhau thì lấy lượt
      sau, vì lỗi hay gặp là đầu lượt mới bị gán cho người vừa nói xong.
    Chỉ đổi speaker_id, giữ nguyên thời gian; việc nối lượt do merge_same_speaker.
    """
    result = [dict(t) for t in turns]
    if len(result) < 2:
        return result

    is_short = [_duration(t) < min_seconds for t in result]
    if all(is_short):
        return result  # không có lượt dài nào làm mốc

    i = 0
    while i < len(result):
        if not is_short[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(result) and is_short[j + 1]:
            j += 1
        prev = result[i - 1] if i > 0 else None  # lượt dài (hoặc không có)
        nxt = result[j + 1] if j + 1 < len(result) else None
        dominant = _dominant_speaker(result[i:j + 1])
        if dominant is not None:
            speaker = dominant
        elif prev and nxt and prev["speaker_id"] == nxt["speaker_id"]:
            speaker = prev["speaker_id"]
        elif prev and nxt:
            gap_prev = result[i]["start"] - prev["end"]
            gap_next = nxt["start"] - result[j]["end"]
            speaker = prev["speaker_id"] if gap_prev < gap_next else nxt["speaker_id"]
        else:
            speaker = (prev or nxt)["speaker_id"]
        for k in range(i, j + 1):
            result[k]["speaker_id"] = speaker
        i = j + 1
    return result


def merge_same_speaker(
    turns: List[Dict[str, Any]],
    max_gap: float = MERGE_GAP_SECONDS,
    max_seconds: float = MAX_TURN_SECONDS,
) -> List[Dict[str, Any]]:
    """Nối các lượt liền nhau của cùng người nếu nghỉ ngắn và tổng chưa quá dài."""
    merged: List[Dict[str, Any]] = []
    for turn in turns:
        if (
            merged
            and merged[-1]["speaker_id"] == turn["speaker_id"]
            and turn["start"] - merged[-1]["end"] <= max_gap
            and turn["end"] - merged[-1]["start"] <= max_seconds
        ):
            merged[-1]["end"] = max(merged[-1]["end"], turn["end"])
        else:
            merged.append(dict(turn))
    return merged


def relabel_by_first_appearance(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Đánh lại speaker_1, speaker_2... theo lần xuất hiện đầu tiên.

    Cần sau khi nhập lượt ngắn: một người chỉ có mẩu ngắn có thể biến mất, hoặc
    thứ tự xuất hiện đầu tiên thay đổi.
    """
    mapping: Dict[str, int] = {}
    result = []
    for turn in turns:
        old = turn["speaker_id"]
        if old not in mapping:
            mapping[old] = len(mapping) + 1
        number = mapping[old]
        new = dict(turn)
        new["speaker_id"] = f"speaker_{number}"
        new["label"] = f"Người {number}"
        result.append(new)
    return result


def prepare_turns(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Toàn bộ bước dọn lượt nói dùng trong pipeline và script chấm."""
    ordered = sorted((dict(t) for t in turns), key=lambda t: t["start"])
    return relabel_by_first_appearance(merge_same_speaker(absorb_short_turns(ordered)))


def padded_bounds(
    turns: List[Dict[str, Any]],
    index: int,
    total_seconds: float,
    pad: float = ASR_PAD_SECONDS,
) -> Tuple[float, float]:
    """Biên cắt audio cho ASR: nới mỗi bên tối đa `pad` giây nhưng không vượt
    quá nửa khoảng nghỉ tới lượt bên cạnh, để không lẫn lời người khác.
    Thời gian lưu cho đoạn vẫn là start/end gốc, chỉ phần cắt audio được nới."""
    turn = turns[index]
    left = pad
    right = pad
    if index > 0:
        left = min(pad, max(0.0, (turn["start"] - turns[index - 1]["end"]) / 2))
    if index + 1 < len(turns):
        right = min(pad, max(0.0, (turns[index + 1]["start"] - turn["end"]) / 2))
    return max(0.0, turn["start"] - left), min(total_seconds, turn["end"] + right)
