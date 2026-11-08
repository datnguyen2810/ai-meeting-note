import re
from typing import List, Dict, Any, Optional, Tuple

VIETNAMESE_STOP_WORDS = {
    "là", "gì", "thế", "nào", "sao", "ai", "ở", "đâu", "khi", "bao", "nhiêu",
    "có", "không", "được", "các", "những", "cho", "về", "của", "trong", "và",
    "với", "như", "thì", "đã", "sẽ", "đang", "hãy", "tôi", "bạn", "nói", "biết",
    "hỏi", "xin", "này", "đó", "kia", "một", "hai", "ba", "làm", "cần", "phải",
    "việc", "ra", "lại", "đến", "đi", "người", "gặp",
    # Từ chung của mọi cuộc họp: khớp "cuộc họp" không phải căn cứ trả lời
    "cuộc", "họp", "buổi", "mọi",
}

# Các từ khóa đồng nghĩa/liên quan khi câu hỏi hỏi về điểm chưa tốt, tồn đọng, sự cố
ISSUE_SYNONYMS = {
    "chưa", "chậm", "kém", "lỗi", "hỏng", "khó", "hạn chế", "tồn đọng",
    "phản hồi", "phàn nàn", "hài lòng", "khắc phục", "vấn đề", "sai"
}


NUMBER_WORDS = {
    "một": 1, "nhất": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
}
# "người 2", "người hai", "người số 2", "người thứ hai"
SPEAKER_REF = re.compile(
    r"\bngười\s+(?:số\s+|thứ\s+)?(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\b",
    re.IGNORECASE,
)
# Câu hỏi muốn biết toàn bộ phần phát biểu của một người
OVERVIEW_WORDS = ("nói", "phát biểu", "trình bày", "ý kiến", "đề cập", "chia sẻ", "tóm tắt", "báo cáo gì")
# Câu hỏi hẹp (việc được giao, thời hạn...): vẫn dùng mô hình trên các đoạn của người đó
NARROW_WORDS = ("giao", "phân công", "làm gì", "hạn", "nhiệm vụ", "khi nào", "bao giờ", "đồng ý", "đề xuất")
MAX_OVERVIEW_CITATIONS = 40


def find_speaker_reference(question: str) -> Optional[int]:
    """Số thứ tự người nói được nhắc trong câu hỏi ("người hai" -> 2), hoặc None."""
    match = SPEAKER_REF.search(question.lower())
    if not match:
        return None
    token = match.group(1)
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def is_overview_question(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in OVERVIEW_WORDS) and not any(w in q for w in NARROW_WORDS)


def _fmt_time(seconds: Any) -> str:
    total = max(0, int(float(seconds or 0)))
    return f"{total // 60:02d}:{total % 60:02d}"


def _citation(seg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "segment_id": seg.get("segment_id"),
        "speaker_id": seg.get("speaker_id", ""),
        "speaker_label": seg.get("speaker_label") or seg.get("speaker_id", "Người nói"),
        "start_seconds": seg.get("start_seconds", 0.0),
        "end_seconds": seg.get("end_seconds", 0.0),
        "quote": seg.get("text", ""),
    }


# ---------------------------------------------------------------------------
# Gom ý chính theo quy tắc (không qua mô hình)
#
# Đã thử dùng bộ tóm tắt Qwen cho lời của từng người: nó đảo nghĩa ("không đổi
# sang mô hình mới" thành "sang mô hình mới") và bỏ gần hết ý. Vì vậy ý chính được
# tách và xếp nhóm bằng quy tắc, câu chữ lấy nguyên từ biên bản.
# ---------------------------------------------------------------------------

# Tách một lượt nói thành các ý: dấu câu, hoặc trước các từ nối mở ý mới
IDEA_SPLIT = re.compile(
    r"[.?!;]+\s*|\s+(?=(?:ngoài ra|còn mình sẽ|còn tôi sẽ|còn em sẽ|nhân tiện|mục tiêu là"
    r"|vấn đề lớn nhất|vậy chốt lại|mình sẽ|tôi sẽ|em sẽ)\b)",
    re.IGNORECASE,
)
# Câu xã giao, bỏ khỏi ý chính
FILLERS = re.compile(
    r"\b(?:xin\s+)?chào\s+(?:mọi người|các bạn|cả nhà)\b|\bcảm ơn\s+(?:mọi người|hai bạn|các bạn|bạn|anh|chị)\b"
    r"|\btốt quá\b|\bkết thúc buổi\s+(?:họp|học)\b|\b(?:mình|tôi|em)\s+đồng ý\b",
    re.IGNORECASE,
)
# Từ nối/khung ở đầu ý, bỏ khi hiển thị (đã dùng để xếp nhóm)
LEADING = re.compile(
    r"^(?:ngoài ra|còn|vậy|nhân tiện|thì|và|nhưng|ừ|à|thế|mình quyết định thế này|quyết định thế này"
    r"|chốt lại|mục tiêu là)\b\s*",
    re.IGNORECASE,
)
QUESTION = re.compile(r"\b(?:chỗ nào|việc gì|khi nào|bao giờ|thế nào|tại sao|vì sao)\b|\bkhông$", re.IGNORECASE)
# Thứ tự ưu tiên khi xếp nhóm; nhóm đứng trước cũng hiển thị trước
IDEA_GROUPS = [
    ("Mục tiêu", r"\bmục tiêu\b"),
    # "chốt" đứng riêng không đủ: "họp nhanh để chốt tiến độ" là mục đích, không phải quyết định
    ("Quyết định", r"\bquyết định\b|\bchốt lại\b|\bchốt là\b|\bthống nhất là\b"),
    ("Đề xuất", r"\bđề xuất\b|\bđề nghị\b"),
    ("Câu hỏi", None),
    ("Sẽ làm", r"\bsẽ\b|\bphụ trách\b|\bhạn\s+(?:là|nộp)\b|\btrước thứ\b|\bchịu trách nhiệm\b"),
    ("Đã làm", r"\bđã hoàn thành\b|\bđã xong\b|\bhoàn thành\b|\bcũng đã\b"),
    ("Vấn đề", r"\bvấn đề\b|\bchậm\b|\blỗi\b|\bnhầm\b|\bvướng\b|\bchờ lâu\b|\bkhó khăn\b|\bchưa\b"),
]
# "Sẽ làm" mà chủ thể là người khác ("tuấn sẽ phụ trách...") là giao việc, không phải
# việc của chính người nói. Chủ thể ngôi thứ nhất/tập thể vẫn là "Sẽ làm".
# Không gồm "anh/chị": "anh khoa sẽ..." thường là giao cho người khác.
SELF_SUBJECTS = {"mình", "tôi", "em", "tớ", "tao", "chúng", "ta", "nhóm", "bên", "team"}
ASSIGN_GROUP = "Giao việc"
MIN_IDEA_WORDS = 4
MAX_IDEA_WORDS = 18
MAX_RECAP_WORDS = 40  # câu "chốt lại" liệt kê nhiều việc, cho dài hơn
MAX_KEY_POINTS = 12


def split_ideas(text: str) -> List[str]:
    """Tách lời nói thành các ý, đã bỏ câu xã giao; giữ nguyên câu chữ còn lại."""
    ideas = []
    for part in IDEA_SPLIT.split(str(text or "")):
        part = " ".join(FILLERS.sub(" ", part or "").split()).strip(" ,")
        if len(part.split()) >= MIN_IDEA_WORDS:
            ideas.append(part)
    return ideas


def _is_assignment_to_other(idea: str) -> bool:
    """'ngoài ra tuấn sẽ phụ trách...' -> True; 'mình (cũng) sẽ...' -> False."""
    match = re.search(r"\bsẽ\b", idea, re.IGNORECASE)
    if not match:
        return False
    before = re.findall(r"\w+", idea[:match.start()].lower())[-3:]
    return bool(before) and not any(w in SELF_SUBJECTS for w in before)


def classify_idea(idea: str) -> str:
    for name, pattern in IDEA_GROUPS:
        if name == "Câu hỏi":
            if QUESTION.search(idea.strip(" ?.")):
                return name
        elif re.search(pattern, idea, re.IGNORECASE):
            if name == "Sẽ làm" and _is_assignment_to_other(idea):
                return ASSIGN_GROUP
            return name
    return "Khác"


# Khung câu ở đầu ý, bỏ khi hiển thị vì nhãn nhóm đã nói thay ("Đề xuất: cả nhóm...")
SUBJECT = r"(?:(?:bên\s+|chúng\s+|tụi\s+)?(?:mình|tôi|em|tớ|nhóm)\s+)?"
GROUP_FRAMES = {
    "Đề xuất": re.compile(r"^" + SUBJECT + r"(?:xin\s+)?(?:đề xuất|đề nghị)\s+(?:là\s+)?", re.IGNORECASE),
    "Sẽ làm": re.compile(r"^" + SUBJECT + r"(?:cũng\s+)?sẽ\s+", re.IGNORECASE),
    "Đã làm": re.compile(r"^" + SUBJECT + r"(?:cũng\s+)?đã\s+", re.IGNORECASE),
    "Vấn đề": re.compile(r"^vấn đề(?:\s+(?:lớn nhất|chính|hiện tại|còn lại))?\s+là\s+", re.IGNORECASE),
}
# Mệnh đề phụ (mục đích, lý do...) cắt khi ý quá dài. Không cắt ở "khi": điều
# kiện thường là một phần của vấn đề ("phân biệt người nói khi hai giọng giống nhau").
SUBORDINATE = re.compile(r"\s+(?:để|vì|nên|đồng thời|nhưng)\s+", re.IGNORECASE)
SPOKEN_DEADLINE = re.compile(r"\s+hạn(?:\s+nộp)?\s+là\s+(.+)$", re.IGNORECASE)
MIN_MAIN_WORDS = 3


def _idea_core(idea: str, group: str) -> Tuple[str, Optional[str]]:
    """Bỏ từ nối đầu ý, khung câu theo nhóm và tách hạn nói miệng: (nội dung, hạn)."""
    text = idea
    while True:
        stripped = LEADING.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    text = text or idea
    deadline = None
    if group != "Quyết định":
        frame = GROUP_FRAMES.get(group)
        if frame:
            text = frame.sub("", text, count=1) or text
        found = SPOKEN_DEADLINE.search(text)
        if found and len(text[:found.start()].split()) >= MIN_MAIN_WORDS:
            deadline = found.group(1).strip()
            text = text[:found.start()]
    return text, deadline


def display_idea(idea: str, group: str) -> str:
    """Rút gọn một ý để hiển thị; câu chữ còn lại lấy nguyên từ biên bản.

    "Quyết định" giữ cả lý do và chỉ cắt theo độ dài; các nhóm khác bỏ khung câu,
    tách hạn ("hạn là thứ sáu" -> "(hạn: thứ sáu)") và bỏ mệnh đề phụ.
    """
    text, deadline = _idea_core(idea, group)
    words = text.split()
    limit = MAX_RECAP_WORDS if group == "Quyết định" else MAX_IDEA_WORDS
    if group != "Quyết định" and len(words) > limit:
        # Quá dài: cắt ở mệnh đề phụ xa nhất mà phần trước vẫn vừa giới hạn, để giữ
        # mục đích quan trọng ("tối ưu trợ lý để thời gian trả lời dưới mười giây")
        cuts = [m.start() for m in SUBORDINATE.finditer(text)
                if MIN_MAIN_WORDS <= len(text[:m.start()].split()) <= limit]
        if cuts:
            text = text[:cuts[-1]]
            words = text.split()
    shown = " ".join(words[:limit]) + ("…" if len(words) > limit else "")
    if deadline:
        shown += f" (hạn: {deadline})"
    return shown[:1].upper() + shown[1:]


# --- Đoạn ý chính của một người -------------------------------------------------
# Mỗi ý thành một cụm ngắn sau động từ dẫn theo nhóm, nối theo thứ tự thời gian:
# "Người 2 báo hoàn thành phần nhận dạng giọng nói; nêu vấn đề phân biệt người nói;
# sẽ thu thêm năm đoạn ghi âm ... (hạn thứ sáu tuần này); đề xuất ...". Ghép bằng quy
# tắc vì Qwen 1.5B tóm lời một người thì đảo nghĩa (đã đo). Câu hỏi không phải ý chính.
GROUP_VERBS = {
    "Mục tiêu": "nêu mục tiêu",
    "Quyết định": "quyết định",
    "Đề xuất": "đề xuất",
    "Sẽ làm": "sẽ",
    "Giao việc": "giao việc:",
    "Đã làm": "báo",
    "Vấn đề": "nêu vấn đề",
}
# Chỗ bắt đầu mệnh đề mới trong lời ASR không dấu câu: từ nối, hoặc chủ ngữ mới +
# động từ ("... giọng nói hệ thống chuyển được ..."). Không coi "hệ thống" đứng lẻ là
# ranh giới: "chạy thử toàn bộ hệ thống trên máy" vẫn là một ý.
# "vẫn còn chậm", "phòng khi", "trước khi", "đôi khi" không phải ranh giới.
_CLAUSE_BASE = (
    r"(?<!vẫn)(?<!chỉ)(?<!cũng)\s+còn\s+"
    r"|\s+(?:mỗi|nên|đồng thời|nhưng|tuy nhiên|ngoài ra)\s+"
    r"|\s+(?:hệ thống|người dùng|khách hàng|ứng dụng|mình|nhóm|chúng ta)\s+"
    r"(?=(?:đã|vẫn|có thể|đôi khi|chuyển|bị|sẽ|cũng|đang|không|chưa)\b)"
)
NEW_CLAUSE = re.compile(
    _CLAUSE_BASE + r"|(?<!phòng)(?<!trước)(?<!sau)(?<!đôi)(?<!những)(?<!mỗi)\s+khi\s+",
    re.IGNORECASE,
)
# Như NEW_CLAUSE nhưng giữ vế "khi ...": dùng cho tóm tắt, nơi điều kiện là một phần
# của vấn đề ("phân biệt người nói khi hai người có giọng gần giống nhau")
NEW_CLAUSE_KEEP_CONDITION = re.compile(_CLAUSE_BASE, re.IGNORECASE)
PURPOSE = re.compile(r"\s+(?:để|vì)\s+", re.IGNORECASE)
NEGATION = {"không", "chưa", "chẳng", "đừng", "chả"}
MAX_PHRASE_WORDS = 16


def _cap_words(words: List[str], limit: int) -> List[str]:
    """Cắt còn `limit` từ nhưng không dừng ngay trước từ phủ định (đổi nghĩa câu)."""
    if len(words) <= limit:
        return words
    end = limit
    while end > MIN_MAIN_WORDS and words[end].lower() in NEGATION:
        end -= 1
    return words[:end] + ["…"]


def idea_phrase(idea: str, group: str) -> Optional[str]:
    """Cụm ngắn cho đoạn ý chính, hoặc None nếu ý không đưa vào đoạn (câu hỏi...)."""
    verb = GROUP_VERBS.get(group)
    if verb is None:
        return None
    if group == "Quyết định" and re.match(r"(?:vậy\s+)?chốt lại\b", idea, re.IGNORECASE):
        verb = "chốt lại:"
    return f"{verb} {compact_idea(idea, group)}"


def compact_idea(idea: str, group: str, keep_condition: bool = False) -> str:
    """Cụm ngắn của một ý (không có động từ dẫn): bỏ khung câu, cắt ở mệnh đề mới,
    quá dài thì cắt ở "để/vì", không dừng trước từ phủ định, kèm "(hạn X)".
    keep_condition: không cắt ở "khi" (dùng cho tóm tắt)."""
    text, deadline = _idea_core(idea, group)
    limit = MAX_RECAP_WORDS if group == "Quyết định" else MAX_PHRASE_WORDS
    if group not in ("Quyết định", "Mục tiêu"):
        clause = (NEW_CLAUSE_KEEP_CONDITION if keep_condition else NEW_CLAUSE).search(text)
        if clause and len(text[:clause.start()].split()) >= MIN_MAIN_WORDS:
            text = text[:clause.start()]
        if len(text.split()) > limit:
            cuts = [m.start() for m in PURPOSE.finditer(text)
                    if MIN_MAIN_WORDS <= len(text[:m.start()].split()) <= limit]
            if cuts:
                text = text[:cuts[-1]]
    phrase = " ".join(_cap_words(text.split(), limit)).replace(" …", "…")
    if deadline:
        phrase += f" (hạn {deadline})"
    return phrase


# Hai đoạn liền nhau của cùng người cách nhau không quá ngưỡng này là cùng một lượt
TURN_GAP_SECONDS = 2.0


def count_turns(segments: List[Dict[str, Any]]) -> Dict[str, int]:
    """Số lượt nói của mỗi người: các đoạn liền nhau của cùng một người tính là một
    lượt. pyannote chia một lượt thành nhiều đoạn khi giữa câu nghỉ hơn 1 s (bản demo:
    Lan 4 lượt thành 7 đoạn), nên đếm số đoạn sẽ ra số lượt quá cao."""
    counts: Dict[str, int] = {}
    previous, previous_end = None, None
    for seg in segments:
        label = seg.get("speaker_label")
        start = float(seg.get("start_seconds") or 0)
        gap = start - previous_end if previous_end is not None else None
        if label and (label != previous or gap is None or gap > TURN_GAP_SECONDS):
            counts[label] = counts.get(label, 0) + 1
        previous, previous_end = label, float(seg.get("end_seconds") or start)
    return counts


def speaker_key_points(label: str, speaker_segments: List[Dict[str, Any]],
                       turn_count: Optional[int] = None) -> Dict[str, Any]:
    """Ý chính của một người thành một đoạn ngắn, theo thứ tự thời gian; trích dẫn là
    mọi lượt nói của người đó (chỉ mốc thời gian, bấm để nghe). `turn_count` tính
    trên toàn cuộc họp (count_turns); thiếu thì dùng số đoạn."""
    phrases = []
    for seg in speaker_segments:
        for idea in split_ideas(seg.get("text", "")):
            phrase = idea_phrase(idea, classify_idea(idea))
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    turns = f"{label} ({turn_count or len(speaker_segments)} lượt nói)"
    if not phrases:
        answer = f"{turns} chỉ có lời chào hỏi/xã giao hoặc câu hỏi, không có ý nội dung."
    else:
        shown = phrases[:MAX_KEY_POINTS]
        more = f"; và {len(phrases) - MAX_KEY_POINTS} ý khác" if len(phrases) > MAX_KEY_POINTS else ""
        answer = f"{turns} " + "; ".join(shown) + more + "."
    return {"answer": answer, "citations": _timestamp_citations(speaker_segments), "insufficient_evidence": False}


def _timestamp_citations(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trích dẫn chỉ có người nói + mốc thời gian (bấm để nghe). Ý chính đã trích từ
    các lượt này; chép lại nguyên văn bên dưới làm câu trả lời dài gấp đôi."""
    return [{**_citation(s), "quote": ""} for s in segments[:MAX_OVERVIEW_CITATIONS]]


# Câu hỏi chung về mục tiêu/quyết định/vấn đề/đề xuất: trả các ý thuộc nhóm đó, lấy
# nguyên câu từ biên bản. Qwen từng ghép chữ có thật thành mục tiêu không ai nói
# ("đánh giá phân biệt người nói, tối ưu trợ lý...") mà kiểm tra bám nguồn theo chữ
# vẫn cho qua.
# Chặt hơn IDEA_GROUPS: câu hỏi cụ thể như "trợ lý chậm bao nhiêu giây" không được
# biến thành liệt kê mọi vấn đề.
GROUP_QUESTIONS = {
    "Mục tiêu": re.compile(r"\bmục (?:tiêu|đích)\b", re.IGNORECASE),
    "Quyết định": re.compile(r"\bquyết định\b|\bchốt\b", re.IGNORECASE),
    "Vấn đề": re.compile(r"\bvấn đề\b|\bkhó khăn\b|\bvướng\b|\btồn đọng\b|\bhạn chế\b", re.IGNORECASE),
    "Đề xuất": re.compile(r"\bđề xuất\b|\bđề nghị\b", re.IGNORECASE),
}
MAX_GROUP_POINTS = 8


def question_group(question: str) -> Optional[str]:
    return next((name for name, pattern in GROUP_QUESTIONS.items() if pattern.search(question)), None)


def group_answer(question: str, segments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    group = question_group(question)
    if group is None:
        return None
    points = []
    for seg in segments:
        for idea in split_ideas(seg.get("text", "")):
            if classify_idea(idea) == group:
                points.append((display_idea(idea, group), seg))
    if not points:
        return None  # biên bản không có ý rõ thuộc nhóm này: để mô hình xử lý
    lines = [f"{group} theo biên bản:"]
    for text, seg in points[:MAX_GROUP_POINTS]:
        label = seg.get("speaker_label") or "Người nói"
        lines.append(f"- {text} ({label}, {_fmt_time(seg.get('start_seconds'))})")
    cited = []
    for _, seg in points[:MAX_GROUP_POINTS]:
        if seg not in cited:
            cited.append(seg)
    return {"answer": "\n".join(lines), "citations": _timestamp_citations(cited), "insufficient_evidence": False}


# ---------------------------------------------------------------------------
# Câu hỏi về người tham gia (số người, ai nói nhiều nhất): trả lời từ dữ liệu phân
# người. Trước đây câu "có bao nhiêu người" đi qua mô hình rồi rơi về một câu trích
# không liên quan chỉ vì khớp chữ "cuộc họp".
# ---------------------------------------------------------------------------

COUNT_QUESTION = re.compile(
    r"\b(?:bao nhiêu|mấy)\s+(?:người|thành viên|bạn)\b|\bnhững ai\b|\bai\s+(?:tham gia|tham dự|có mặt)\b"
    r"|\bgồm\s+(?:những\s+)?ai\b|\bsố\s+(?:người|thành viên)\b",
    re.IGNORECASE,
)
MOST_QUESTION = re.compile(r"\bai\s+(?:nói|phát biểu)\s+(?:nhiều|lâu)\s+nhất\b|\bngười nào\s+nói\s+nhiều nhất\b", re.IGNORECASE)
DIARIZATION_CAVEAT = (
    "Số người được suy ra từ giọng nói nên có thể chưa đúng: hai giọng gần giống nhau có thể bị gộp làm một. "
    "Nếu biết chính xác số người, hãy chọn đúng số người rồi xử lý lại."
)


def speaker_stats(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mỗi người nói: nhãn, số lượt, số giây nói, đoạn đầu tiên; theo lần xuất hiện."""
    stats: Dict[str, Dict[str, Any]] = {}
    turns = count_turns(segments)
    for seg in segments:
        label = seg.get("speaker_label")
        if not label or seg.get("speaker_id") is None:
            continue
        item = stats.setdefault(label, {"label": label, "turns": turns.get(label, 0), "seconds": 0.0, "first": seg})
        item["seconds"] += max(0.0, float(seg.get("end_seconds") or 0) - float(seg.get("start_seconds") or 0))
    return list(stats.values())


def participant_answer(question: str, segments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Trả lời câu hỏi về người tham gia, hoặc None nếu không phải loại câu này."""
    asks_count = bool(COUNT_QUESTION.search(question))
    asks_most = bool(MOST_QUESTION.search(question))
    if not (asks_count or asks_most):
        return None
    stats = speaker_stats(segments)
    if not stats:
        return {
            "answer": "Cuộc họp này chưa phân được người nói nên không biết có bao nhiêu người.",
            "citations": [],
            "insufficient_evidence": True,
        }
    total = sum(s["seconds"] for s in stats) or 1.0

    def details(s):
        return f"{s['turns']} lượt, khoảng {round(s['seconds'])} giây, {round(100 * s['seconds'] / total)}%"

    def describe(s):
        return f"{s['label']} ({details(s)})"

    if asks_most:
        top = max(stats, key=lambda s: s["seconds"])
        lines = [f"{top['label']} nói nhiều nhất: {details(top)}."]
        lines.append("Toàn bộ: " + "; ".join(describe(s) for s in stats) + ".")
    else:
        lines = [f"Hệ thống phân biệt được {len(stats)} người nói: " + "; ".join(describe(s) for s in stats) + "."]
    lines.append(DIARIZATION_CAVEAT)
    return {
        "answer": "\n".join(lines),
        "citations": _timestamp_citations([s["first"] for s in stats]),
        "insufficient_evidence": False,
    }


# ---------------------------------------------------------------------------
# Kiểm tra câu trả lời của mô hình có bám biên bản không
# ---------------------------------------------------------------------------

# Tỷ lệ tối thiểu chữ nội dung trong câu trả lời phải có trong các đoạn đưa cho mô
# hình. Câu bịa "chọn mô hình mới… ngày 20/11" chỉ đạt ~0,6; câu bám nguồn ~1,0.
GROUNDING_MIN = 0.8


def grounding_ratio(answer: str, source_text: str) -> float:
    tokens = re.findall(r"\d+/\d+|\w+", answer.lower())
    content = [
        t for t in tokens
        if not t.startswith("seg_") and t not in VIETNAMESE_STOP_WORDS and not (t.isdigit() and len(t) <= 2)
    ]
    if not content:
        return 1.0
    source = set(re.findall(r"\w+", source_text.lower()))
    return sum(t in source for t in content) / len(content)


def extractive_answer(question: str, scored: List[Tuple[int, Dict[str, Any]]]) -> Dict[str, Any]:
    """Trích nguyên văn ý khớp câu hỏi nhất, dùng khi câu trả lời của mô hình không bám nguồn."""
    keywords = set(extract_keywords(question))
    best = max(scored, key=lambda x: x[0], default=(0, None))
    # Một âm tiết trùng (ví dụ "án" trong "dự án" và "đồ án") chưa đủ là căn cứ:
    # cần khớp ít nhất 2 từ khóa khác nhau (hoặc toàn bộ nếu câu hỏi chỉ có 1).
    needed = min(2, len(keywords)) or 1
    hits = len(keywords & set(re.findall(r"\w+", str(best[1].get("text", "")).lower()))) if best[1] else 0
    if best[0] <= 0 or best[1] is None or hits < needed:
        return {
            "answer": "Biên bản không có thông tin rõ ràng để trả lời câu hỏi này.",
            "citations": [],
            "insufficient_evidence": True,
        }
    seg = best[1]
    # Câu hỏi về "mục tiêu"/"quyết định"... thì ưu tiên ý thuộc đúng nhóm đó
    question_group = classify_idea(question)

    def idea_score(idea: str) -> int:
        hits = len(keywords & set(re.findall(r"\w+", idea.lower())))
        bonus = 3 if question_group not in ("Khác", "Câu hỏi") and classify_idea(idea) == question_group else 0
        return hits + bonus

    ideas = split_ideas(seg.get("text", "")) or [str(seg.get("text", ""))]
    idea = max(ideas, key=idea_score)
    label = seg.get("speaker_label") or "Người nói"
    text = display_idea(idea, "Quyết định")
    return {
        "answer": f"Theo biên bản, {label} [{_fmt_time(seg.get('start_seconds'))}] nói: \"{text}\"",
        "citations": [_citation(seg)],
        "insufficient_evidence": False,
    }


def _generate(llm_model, llm_tokenizer, messages: List[Dict[str, str]], device: str) -> str:
    """Sinh câu trả lời bằng Gemini nếu có khóa, lỗi thì dùng Qwen (tách riêng để mock khi test)."""
    import llm_backend

    if llm_backend.gemini_enabled():
        try:
            return llm_backend.gemini_generate(messages, max_output_tokens=4096)
        except Exception as exc:
            print(f"[WARN] Chat bang Gemini loi ({exc}); dung Qwen local.")
    return _generate_local(llm_model, llm_tokenizer, messages, device)


def _generate_local(llm_model, llm_tokenizer, messages: List[Dict[str, str]], device: str) -> str:
    """Gọi Qwen local sinh câu trả lời."""
    import torch

    text_input = llm_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = llm_tokenizer(text_input, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = llm_model.generate(**inputs, max_new_tokens=300, do_sample=False, repetition_penalty=1.05)
    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    return llm_tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


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

    # Lấy các chỉ số đoạn có điểm cao nhất và mở rộng lân cận (i-1, i, i+1).
    # Thêm theo thứ tự điểm, để khi vượt top_k thì đoạn khớp nhất không bị loại.
    selected_indices = []

    def add(idx: int) -> None:
        if idx not in selected_indices and len(selected_indices) < top_k:
            selected_indices.append(idx)

    for sc, idx, seg in indexed_scored[:6]:
        if sc > 0 or max_score == 0:
            add(idx)
            if idx > 0:
                add(idx - 1)
            if idx + 1 < total_count:
                add(idx + 1)

    # Còn chỗ thì bổ sung các đoạn đầu (thường là phần mở đầu, nêu mục tiêu). Trước
    # đây code thêm 20 đoạn đầu rồi cắt theo số thứ tự, làm đoạn khớp nằm sau vị trí
    # 20 bị loại khỏi ngữ cảnh.
    for idx in range(total_count):
        add(idx)

    selected = [segments[i] for i in sorted(selected_indices)]
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

    # Số người / ai nói nhiều nhất: tính từ dữ liệu phân người (bỏ qua bộ lọc người nói)
    participants = participant_answer(question, segments)
    if participants is not None:
        return participants

    # Người được nhắc trong câu hỏi ("người hai") ưu tiên hơn bộ lọc chọn trên giao diện
    target_segments = segments
    speaker_number = find_speaker_reference(question)
    if speaker_number is not None:
        label = f"Người {speaker_number}"
        filtered = [s for s in segments if (s.get("speaker_label") or "").lower() == label.lower()]
        if not filtered:
            labels = sorted({s.get("speaker_label") for s in segments if s.get("speaker_label")})
            return {
                "answer": f"Cuộc họp không có {label}. Các người nói được nhận diện: {', '.join(labels) or 'không có'}.",
                "citations": [],
                "insufficient_evidence": True,
            }
        if is_overview_question(question):
            return speaker_key_points(label, filtered, count_turns(segments).get(label))
        target_segments = filtered
    elif speaker_id:
        filtered = [s for s in segments if s.get("speaker_id") == speaker_id]
        if filtered:
            # Chọn người ở bộ lọc rồi hỏi "nói gì" cũng trả ý chính như khi gõ "người 2"
            if is_overview_question(question):
                label = filtered[0].get("speaker_label") or speaker_id
                return speaker_key_points(label, filtered, count_turns(segments).get(label))
            target_segments = filtered

    grouped = group_answer(question, target_segments)
    if grouped is not None:
        return grouped

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

    answer = _generate(llm_model, llm_tokenizer, messages, device)

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

    # Mô hình 1.5B đôi khi bịa (ví dụ đảo quyết định, tự thêm ngày). Câu trả lời có
    # nhiều chữ nội dung không có trong các đoạn đã đưa thì thay bằng trích nguyên văn.
    if not insufficient:
        ratio = grounding_ratio(answer, " ".join(str(s.get("text", "")) for s in relevant))
        if ratio < GROUNDING_MIN:
            print(f"[WARN] Cau tra loi chat khong bam nguon (ty le {ratio:.2f}); dung trich dan nguyen van.")
            return extractive_answer(question, scored_list)

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

        # 2. Câu hỏi về một người nhưng mô hình không ghi mã nguồn và không có từ khóa
        #    khớp: nguồn chính là các lượt nói của người đó.
        if not citations and speaker_number is not None and max_score == 0:
            citations = [_citation(s) for s in target_segments[:MAX_OVERVIEW_CITATIONS]]

        # 3. Nếu LLM trả lời nhưng không ghi [seg_XXXX], chỉ lấy citations khi thực sự có keyword match (score > 0)
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
        "answer": strip_segment_tags(answer),
        "citations": citations,
        "insufficient_evidence": insufficient
    }


SEGMENT_TAG = re.compile(r"\s*[,;]?\s*[\[(]\s*seg_\d+(?:\s*[,;]\s*seg_\d+)*\s*[\])]|\s*\bseg_\d+\b", re.IGNORECASE)


def strip_segment_tags(answer: str) -> str:
    """Bỏ mã nguồn [seg_0003] khỏi câu trả lời; nguồn đã hiển thị ở phần trích dẫn."""
    text = SEGMENT_TAG.sub("", answer)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip() or answer.strip()
