"""Lexical grounding is conservative; it cannot prove semantic entailment."""

import json
import re
import unicodedata

from .schema import Action, Extraction, Fact, SummaryData

NAMED_ASSIGNMENT = r"\b(?:anh|chị|ông|bà|bạn|em|cô|chú|bác)\s+[^\W\d_]+(?:\s+[^\W\d_]+){0,4}?\s+(?:sẽ|cần|phải|chịu trách nhiệm)\b"
SECTIONS = ("objectives", "results", "issues", "decisions", "actions")
ACTION_END = (
    r"[.!?](?:\s|$)|\bcuộc họp\b[^.!?]*\bkết thúc\b|"
    r"\bsau khi hoàn thành\s+mọi người\b|\bmọi người cập nhật\b"
)


def completed_json(raw: str) -> str | None:
    """Return all expected fully decoded fields, never repairing incomplete values.

    Used to stop generation once the requested object is complete instead of
    letting the model emit extra keys or repeat itself. All string values are
    preserved by JSON round-trip; grounding is checked separately.
    """
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), count=1)
    if not raw.startswith("{"):
        return None
    decoder, obj, pos = json.JSONDecoder(), {}, 1
    try:
        while len(obj) < len(SECTIONS):
            while pos < len(raw) and raw[pos].isspace():
                pos += 1
            key, pos = decoder.raw_decode(raw, pos)
            if not isinstance(key, str) or key not in SECTIONS or key in obj:
                return None
            while pos < len(raw) and raw[pos].isspace():
                pos += 1
            if pos >= len(raw) or raw[pos] != ":":
                return None
            pos += 1
            while pos < len(raw) and raw[pos].isspace():
                pos += 1
            value, pos = decoder.raw_decode(raw, pos)
            if not isinstance(value, list):
                return None
            obj[key] = value
            if len(obj) == len(SECTIONS):
                return json.dumps(obj, ensure_ascii=False)
            while pos < len(raw) and raw[pos].isspace():
                pos += 1
            if pos >= len(raw) or raw[pos] != ",":
                return None
            pos += 1
    except (ValueError, TypeError):
        return None
    return None


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def contains(source: str, excerpt: str) -> bool:
    # Word boundaries avoid matching Nam inside 'Việt Nam' partially or 15 in 115.
    source, excerpt = normalize(source), normalize(excerpt)
    return bool(excerpt) and re.search(r"(?<!\w)" + re.escape(excerpt) + r"(?!\w)", source) is not None


def locate(source: str, excerpt: str):
    return list(re.finditer(r"(?<!\w)" + re.escape(normalize(excerpt)) + r"(?!\w)", source))


def recover_evidence(action: Action, source: str, other_owners: list[str]) -> str | None:
    """Recover an omitted quote only when all fields align in one short clause.

    Never joins separate source spans or repairs an invented task/deadline.
    """
    source = normalize(source)
    for task in locate(source, action.task):
        start, end = task.span()
        if action.assignee:
            owners = [m for m in locate(source, action.assignee) if m.start() <= start and start - m.end() <= 40]
            if not owners:
                continue
            start = owners[-1].start()
        if action.deadline_text:
            deadlines = [m for m in locate(source, action.deadline_text) if m.start() >= task.start() and m.start() - end <= 40]
            if not deadlines:
                continue
            end = max(end, deadlines[0].end())
        quote = source[start:end]
        if re.search(r"[.!?]\s", quote):
            continue
        if any(normalize(name) != normalize(action.assignee or "") and contains(quote, name) for name in other_owners):
            continue
        return quote
    return None


def actions_from_quote(quote: str) -> list[Action]:
    """Parse Vietnamese assignment markers; keep unfamiliar grammar as a quote.

    These are source slices, not corrected or inferred facts. An unidentified
    owner/deadline stays unknown rather than triggering another model call.
    """
    if re.match(r"(?:(?:hôm nay|hiện tại|nhóm)\s+)?chưa\s+(?:phân công|chốt|thống nhất|giao)\b", quote.strip(), re.I):
        return []
    if not re.search(r"\s+(?:sẽ|cần|phải|chịu trách nhiệm)\s+", quote, re.I) and not re.match(
        r"(?:cần|phải|hãy|đề nghị|yêu cầu|kiểm tra|chuẩn bị|gửi|cập nhật|sửa|xử lý|rà soát|bổ sung|triển khai|thực hiện|hoàn thành)\b",
        quote.strip(), re.I,
    ):
        return []
    owners = list(re.finditer(NAMED_ASSIGNMENT, quote, re.I))
    starts = [m.start() for m in owners] or [0]
    actions = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(quote)
        evidence = quote[start:end].strip()
        boundary = re.search(ACTION_END, evidence, re.I)
        if boundary:
            evidence = evidence[:boundary.start()].strip()
        evidence = re.sub(r"\s+(?:còn|và)\s*$", "", evidence, flags=re.I).rstrip(" .;,")
        assignment = re.search(r"\s+(?:sẽ|cần|phải|chịu trách nhiệm)\s+", evidence, re.I)
        owner = evidence[:assignment.start()] if assignment and assignment.start() <= 60 else None
        task_start = assignment.end() if owner else 0
        if owner:
            # A repeated subject followed by deadline/status metadata starts a
            # new clause even if ASR corrupts the negation before 'chốt'. Do not
            # cut tasks about someone else's work or temporal conditions.
            subject = r"\bcông việc của\s+(?:(?:anh|chị|ông|bà|bạn)\s+)?"
            subject += r"\s+".join(re.escape(w) for w in owner_core(owner).split()) + r"\b"
            for marker in re.finditer(subject, evidence[task_start:], re.I):
                after = evidence[task_start + marker.end():]
                if re.match(r"\s+(?:trước|sau|để|và)\b", after, re.I):
                    continue
                if re.search(r"\b(?:chốt|thời hạn|deadline)\b", after[:50], re.I):
                    evidence = evidence[:task_start + marker.start()].rstrip()
                    break
        deadline = re.search(r"\b(?:trước|chậm nhất|hạn chót|vào ngày|trong (?:ngày|tuần|tháng))\b", evidence[task_start:], re.I)
        task_end = task_start + deadline.start() if deadline else len(evidence)
        task = evidence[task_start:task_end].strip(" ,;.")
        if not task or re.match(r"(?:không|chưa)\b", task, re.I):
            continue
        actions.append(Action(
            assignee=owner, task=task,
            deadline_text=evidence[task_end:] if deadline else None,
            evidence=evidence,
        ))
    return actions


def source_assignments(source: str, hints=()) -> list[Action]:
    """Locate full clauses, including source-verified names without a title."""
    named = list(re.finditer(NAMED_ASSIGNMENT, source, re.I))
    starts = {m.start() for m in named}
    for hint in hints:
        if not hint:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in hint.split())
        pattern += r"\s+(?:sẽ|cần|phải|chịu trách nhiệm)\b"
        for match in re.finditer(pattern, source, re.I):
            # 'lan sẽ' inside 'chị lan sẽ' is the same start, not another job.
            if not any(m.start() < match.start() < m.end() and match.end() <= m.end() for m in named):
                starts.add(match.start())
    starts = sorted(starts)
    result = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(source)
        result.extend(actions_from_quote(source[start:end]))
    return result


def owner_core(owner: str | None) -> str:
    return re.sub(r"^(?:anh|chị|ông|bà|bạn|em|cô|chú|bác)\s+", "", normalize(owner or ""))


def align_actions_to_source(actions: list[Action], source: str) -> list[Action]:
    """Extend truncated quotes only inside a matching, complete assignment.

    A longer source deadline replaces its prefix; distinct deadlines never
    overwrite one another. Unknown names are not corrected by this function.
    """
    canonical = source_assignments(source, [a.assignee for a in actions])
    aligned = []
    for action in actions:
        matches = []
        for candidate in canonical:
            if not action.assignee or owner_core(action.assignee) != owner_core(candidate.assignee):
                continue
            a_task, c_task = normalize(action.task), normalize(candidate.task)
            if not (a_task == c_task or a_task.startswith(c_task + " ") or c_task.startswith(a_task + " ")):
                continue
            a_date, c_date = normalize(action.deadline_text or ""), normalize(candidate.deadline_text or "")
            if a_date and c_date and not (a_date == c_date or a_date.startswith(c_date + " ") or c_date.startswith(a_date + " ")):
                continue
            # Do not combine incompatible honorifics (e.g. anh Nam vs chị Nam).
            a_owner, c_owner = normalize(action.assignee), normalize(candidate.assignee or "")
            if a_owner != owner_core(a_owner) and c_owner != owner_core(c_owner) and a_owner != c_owner:
                continue
            selected = candidate.model_copy(deep=True)
            selected.needs_confirmation |= action.needs_confirmation
            matches.append(selected)
        aligned.extend(matches or [action])
    return aligned


def explicit_source_facts(source: str) -> SummaryData:
    """Recover only explicit assignment/completion markers from original text.

    This improves recall when the small model omits a person or a completed
    result. No name, task or date is generated; validation still runs afterward.
    """
    data = SummaryData(objectives=[], results=[], issues=[], decisions=[], actions=[])
    data.actions.extend(source_assignments(source))
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", source):
        if re.match(r"(?:cần|phải|hãy)\b", sentence.strip(), re.I) and not re.search(NAMED_ASSIGNMENT, sentence, re.I):
            data.actions.extend(actions_from_quote(sentence))
        # Bound run-on ASR clauses by discourse markers, retaining exact slices.
        for clause in re.split(r"\b(?:nhìn chung|tuy nhiên|nhưng|nhóm thống nhất)\b", sentence, flags=re.I):
            if re.search(r"\bđã hoàn thành\b", clause, re.I) and not re.search(r"\b(?:không|chưa|nếu|liệu)\b", clause, re.I):
                data.results.extend(explicit_source_facts_for_result(clause))
    return validate_extraction(data, source)


def parse_extraction(raw: str) -> Extraction:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1)
        raw = re.sub(r"\s*```$", "", raw, count=1)
    repaired = False
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Bounded syntax repair: small models sometimes close the root object
        # with ']' instead of '}'. Do not repair strings or truncated content.
        if raw.startswith("{") and raw.endswith("]]"):
            obj = json.loads(raw[:-1] + "}")
            repaired = True
        else:
            raise
    sections = SECTIONS
    if not isinstance(obj, dict) or set(obj) != set(sections):
        raise ValueError("Missing or unexpected extraction sections")
    result = SummaryData(**{section: [] for section in sections})
    invalid = int(repaired)
    for section in sections:
        if not isinstance(obj[section], list):
            raise ValueError("Extraction sections must be arrays")
        for item in obj[section]:
            if isinstance(item, str) and section != "actions" and re.search(NAMED_ASSIGNMENT, item, re.I):
                result.actions.extend(actions_from_quote(item))
                continue
            if isinstance(item, str) and section == "actions":
                if not item.strip():
                    invalid += 1
                else:
                    result.actions.extend(actions_from_quote(item))
                continue
            if isinstance(item, str) and section != "actions":
                item = {"text": item, "evidence": item}
            # Small models sometimes put well-formed assignments in 'decisions'.
            # Recover their type without inventing or changing any field value.
            target = "actions" if isinstance(item, dict) and "task" in item else section
            try:
                value = (Action if target == "actions" else Fact).model_validate(item)
                getattr(result, target).append(value)
                invalid += target != section
            except ValueError:
                invalid += 1
    if invalid:
        result.warnings.append("Một số mục model trả sai cấu trúc; đã phục hồi mục hợp lệ và cần kiểm tra phần còn thiếu.")
    return result


def validate_extraction(data: Extraction, source: str) -> SummaryData:
    result = SummaryData(objectives=[], results=[], issues=[], decisions=[], actions=[])
    result.warnings.extend(getattr(data, "warnings", []))
    rejected = 0
    for section in ("objectives", "results", "issues", "decisions"):
        for fact in getattr(data, section):
            if contains(source, fact.evidence) and contains(fact.evidence, fact.text):
                if section == "results" and re.search(r"\bđã hoàn thành\b", fact.text, re.I):
                    # Run-on ASR often makes the model quote goals and problems
                    # as part of a result. Recover just the completion clause.
                    completions = explicit_source_facts_for_result(fact.text)
                    getattr(result, section).extend(completions or [fact])
                else:
                    getattr(result, section).append(fact)
            else:
                rejected += 1
    owners = [a.assignee for a in data.actions if a.assignee]
    for action in data.actions:
        action = action.model_copy(deep=True)
        if action.evidence is None:
            action.evidence = recover_evidence(action, source, owners)
        if not action.evidence or not contains(source, action.evidence) or not contains(action.evidence, action.task):
            rejected += 1
            continue
        for field in ("assignee", "deadline_text"):
            value = getattr(action, field)
            if value is not None and not contains(action.evidence, value):
                setattr(action, field, None)
                action.needs_confirmation = True
                rejected += 1
        # Common ASR corruption: never silently repair these spoken deadlines.
        if action.deadline_text and re.search(
            r"\b(thứ\s+tuần|tháng\s+tháng|ngày\s+thứ\s+tuần)\b", action.deadline_text, re.I
        ):
            action.needs_confirmation = True
        result.actions.append(action)
    result.actions = align_actions_to_source(result.actions, source)
    for action in result.actions:
        if action.deadline_text and re.search(r"\b(?:trước\s+từ|ngày\s+nay|thứ\s+tuần|tháng\s+tháng)\b", action.deadline_text, re.I):
            action.needs_confirmation = True
    if rejected:
        result.warnings.append("Đã loại hoặc đánh dấu dữ kiện không khớp trích dẫn; cần đối chiếu phiên âm.")
    return result


def explicit_source_facts_for_result(text: str) -> list[Fact]:
    """Trim a completion quote without calling the full extraction pipeline."""
    facts = []
    for clause in re.split(r"\b(?:nhìn chung|tuy nhiên|nhưng|nhóm thống nhất)\b", text, flags=re.I):
        if not re.search(r"\bđã hoàn thành\b", clause, re.I):
            continue
        context = list(re.finditer(r"\btrong tuần qua\b", clause, re.I))
        if context:
            clause = clause[context[-1].start():]
        completed = re.search(r"\bđã hoàn thành\b", clause, re.I)
        if completed and re.search(r"\b(?:chào|họp|học để|để đánh giá|mục tiêu)\b", clause[:completed.start()], re.I):
            subjects = list(re.finditer(
                r"\b(?:nhóm|đội|bộ phận|phòng|chúng tôi|chúng ta)\b(?:(?!\bđã hoàn thành\b)[^.!?]){0,40}\bđã hoàn thành\b",
                clause, re.I,
            ))
            clause = clause[subjects[-1].start() if subjects else completed.start():]
        quote = clause.strip(" .;,")
        facts.append(Fact(text=quote, evidence=quote))
    return facts


def merge_results(parts: list[SummaryData]) -> SummaryData:
    merged = SummaryData(objectives=[], results=[], issues=[], decisions=[], actions=[])
    aliases = {}
    for part in parts:
        for action in part.actions:
            owner = normalize(action.assignee or "")
            title = re.match(r"(?:anh|chị|ông|bà|bạn|em|cô|chú|bác)\s+", owner)
            if title:
                aliases.setdefault(owner[title.end():], set()).add(owner)

    def owner_key(action):
        owner = normalize(action.assignee or "")
        choices = aliases.get(owner, set())
        return next(iter(choices)) if len(choices) == 1 else owner

    for section in ("objectives", "results", "issues", "decisions", "actions", "warnings"):
        positions = {}
        for part in parts:
            for item in getattr(part, section):
                if section == "warnings":
                    key = item
                elif section == "actions":
                    key = (owner_key(item), normalize(item.task), normalize(item.deadline_text or ""))
                else:
                    key = normalize(item.text)
                if key not in positions:
                    positions[key] = len(getattr(merged, section))
                    getattr(merged, section).append(item.model_copy(deep=True) if section != "warnings" else item)
                elif section == "actions":
                    index = positions[key]
                    prior = merged.actions[index]
                    confirm = prior.needs_confirmation or item.needs_confirmation
                    if len(item.assignee or "") > len(prior.assignee or ""):
                        merged.actions[index] = item.model_copy(deep=True)
                    merged.actions[index].needs_confirmation = confirm
    deadlines = {}
    for action in merged.actions:
        key = (owner_key(action), normalize(action.task))
        if action.deadline_text:
            deadlines.setdefault(key, set()).add(normalize(action.deadline_text))
    for action in merged.actions:
        key = (owner_key(action), normalize(action.task))
        if len(deadlines.get(key, set())) > 1:
            action.needs_confirmation = True
            warning = "Có công việc trùng người/nội dung nhưng khác thời hạn; giữ các phiên bản để xác nhận."
            if warning not in merged.warnings:
                merged.warnings.append(warning)
    return merged
