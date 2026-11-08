"""Caption utilities: SRT/VTT rendering, script alignment and line splitting.

Miragea's subtitle recognition returns timed `segments` (seconds) plus ready
`srt`/`txt` strings. Everything here is pure formatting on top of that output;
no speech processing happens locally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

_CJK = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af"
_TOKEN_RE = re.compile(rf"[{_CJK}][\s]*|[^\s{_CJK}]+\s*")
_SENTENCE_END = re.compile(r"[.!?;:。！？；…]+[\"'”’)\]]*\s*$")
_TIME_RE = re.compile(
    r"(?P<a>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<b>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})"
)

CAPTION_FORMATS = ("srt", "vtt", "txt", "json")


@dataclass
class Segment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "text": self.text}


# ----------------------------------------------------------------- parsing
def _parse_time(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    if len(parts) == 2:
        parts.insert(0, "0")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def segments_from_result(result: dict[str, Any]) -> list[Segment]:
    """Read Miragea `result.segments`, falling back to parsing `result.srt`."""
    raw = result.get("segments")
    out: list[Segment] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                start, end = float(item["start"]), float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            text = str(item.get("text", "")).strip()
            if text:
                out.append(Segment(start, max(end, start), text))
    if not out and isinstance(result.get("srt"), str):
        out = parse_srt(result["srt"])
    full_text = result.get("text") or result.get("txt")
    if isinstance(full_text, str) and full_text.strip():
        out = fix_word_splits(out, full_text)
    return out


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() and not re.match(rf"[{_CJK}]", ch)


def fix_word_splits(segments: list[Segment], full_text: str) -> list[Segment]:
    """Re-join words that recognition cut across two cues ("an" | "d bruised").

    Some recognizers chunk the transcript every N characters, so a cue can end
    mid-word. The full transcript tells us where the real spaces are: we walk
    the cues along it and, wherever a boundary falls inside a word, move the
    smaller fragment to the cue holding the rest of the word, shifting the
    boundary time by the share of characters moved. Returns the input unchanged
    if the cues cannot be matched to the transcript.
    """
    if len(segments) < 2:
        return list(segments)
    text = full_text
    pos = 0
    spans: list[tuple[int, int]] = []
    for seg in segments:
        body = seg.text.strip()
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if text[pos : pos + len(body)] != body:
            return list(segments)
        spans.append((pos, pos + len(body)))
        pos += len(body)
    segs = [Segment(s.start, s.end, s.text.strip()) for s in segments]
    for i in range(len(segs) - 1):
        a, b = segs[i], segs[i + 1]
        end_a = spans[i][1]
        if not (0 < end_a < len(text) and spans[i + 1][0] == end_a):
            continue
        if b.text and not any(_is_word_char(c) for c in b.text) and len(b.text) <= 3:
            a.text, b.text = a.text + b.text, ""  # stray punctuation cue: attach it
            a.end = max(a.end, b.end)
            b.start = b.end = a.end
            continue
        if not (_is_word_char(text[end_a - 1]) and _is_word_char(text[end_a])):
            continue
        head = re.search(r"[^\s]*$", a.text).group(0)  # tail fragment of a
        tail = re.match(r"[^\s]*", b.text).group(0)  # head fragment of b
        if not head or not tail:
            continue
        a_rest, b_rest = a.text[: len(a.text) - len(head)].rstrip(), b.text[len(tail) :].lstrip()
        if len(head) <= len(tail) and a_rest:
            moved, a.text, b.text = head, a_rest, head + b.text
            share = len(moved) / max(1, len(a_rest) + len(moved))
            boundary = a.end - (a.end - a.start) * share
        elif b_rest:
            moved, a.text, b.text = tail, a.text + tail, b_rest
            share = len(moved) / max(1, len(b_rest) + len(moved))
            boundary = b.start + (b.end - b.start) * share
        else:  # b is only the end of a's last word: merge it into a
            a.text, b.text = a.text + tail, ""
            a.end = max(a.end, b.end)
            b.start = b.end = a.end
            continue
        a.end = b.start = max(a.start, min(boundary, b.end))
    return [s for s in segs if s.text]


def parse_srt(text: str) -> list[Segment]:
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        for i, line in enumerate(lines):
            match = _TIME_RE.search(line)
            if match:
                body = " ".join(lines[i + 1 :]).strip()
                if body:
                    segments.append(Segment(_parse_time(match["a"]), _parse_time(match["b"]), body))
                break
    return segments


# --------------------------------------------------------------- rendering
def _stamp(seconds: float, sep: str) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"


def to_srt(segments: Iterable[Segment]) -> str:
    blocks = [
        f"{i}\n{_stamp(s.start, ',')} --> {_stamp(s.end, ',')}\n{s.text}"
        for i, s in enumerate(segments, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(segments: Iterable[Segment]) -> str:
    body = "\n\n".join(
        f"{_stamp(s.start, '.')} --> {_stamp(s.end, '.')}\n{s.text.replace('-->', '->')}" for s in segments
    )
    return "WEBVTT\n\n" + body + ("\n" if body else "")


def to_txt(segments: Iterable[Segment]) -> str:
    return "\n".join(s.text for s in segments) + "\n"


# -------------------------------------------------------------- tokenizing
def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.strip())


def _weight(token: str) -> int:
    return max(1, len(token.strip()))


def _join(tokens: list[str]) -> str:
    return "".join(tokens).strip()


# ---------------------------------------------------------------- aligning
def align_script(script: str, segments: list[Segment], snap: int = 3) -> list[Segment]:
    """Keep recognized timing but use the exact script wording.

    Speech recognition can misspell brand names or jargon. When we generated the
    audio from a known script, the script is the ground truth for the words and
    recognition is the ground truth for the timing. Script tokens are spread
    over recognized segments in proportion to each segment's character count,
    and each boundary snaps to a nearby sentence end when one is within `snap`
    tokens.
    """
    tokens = _tokens(script)
    segs = [s for s in segments if s.text.strip()]
    if not tokens or not segs:
        return list(segs)
    if len(segs) == 1:
        return [Segment(segs[0].start, segs[0].end, _join(tokens))]

    seg_weights = [max(1, len(re.sub(r"\s", "", s.text))) for s in segs]
    total_seg = float(sum(seg_weights))
    tok_weights = [_weight(t) for t in tokens]
    total_tok = float(sum(tok_weights))

    # cumulative fraction at which each segment ends
    cum, ends = 0.0, []
    for w in seg_weights:
        cum += w
        ends.append(cum / total_seg)

    # proposed boundary index (exclusive) per segment
    boundaries: list[int] = []
    running, k = 0.0, 0
    for frac in ends[:-1]:
        while k < len(tokens) and (running + tok_weights[k] / 2) / total_tok <= frac:
            running += tok_weights[k]
            k += 1
        boundaries.append(k)
    boundaries.append(len(tokens))

    # snap to sentence ends, keep strictly increasing and non-empty where possible
    snapped: list[int] = []
    prev = 0
    for i, b in enumerate(boundaries):
        if i < len(boundaries) - 1:
            best = b
            for delta in sorted(range(-snap, snap + 1), key=abs):
                j = b + delta
                if prev < j < len(tokens) and _SENTENCE_END.search(tokens[j - 1]):
                    best = j
                    break
            b = max(best, prev + 1) if prev + 1 <= len(tokens) else best
            b = min(b, len(tokens))
        snapped.append(b)
        prev = b

    out: list[Segment] = []
    start_idx = 0
    for seg, end_idx in zip(segs, snapped):
        chunk = tokens[start_idx:end_idx]
        start_idx = max(start_idx, end_idx)
        if chunk:
            out.append(Segment(seg.start, seg.end, _join(chunk)))
        elif out:  # no words left for this segment: extend the previous cue
            out[-1].end = seg.end
    if start_idx < len(tokens) and out:
        out[-1].text = _join(_tokens(out[-1].text) + tokens[start_idx:])
    return out


# ---------------------------------------------------------------- splitting
def split_long(segments: list[Segment], max_chars: Optional[int]) -> list[Segment]:
    """Split cues longer than `max_chars` into shorter ones, sharing time by length."""
    if not max_chars or max_chars <= 0:
        return list(segments)
    out: list[Segment] = []
    for seg in segments:
        if len(seg.text) <= max_chars:
            out.append(seg)
            continue
        chunks: list[list[str]] = [[]]
        for tok in _tokens(seg.text):
            candidate = _join(chunks[-1] + [tok])
            if chunks[-1] and len(candidate) > max_chars:
                chunks.append([tok])
            else:
                chunks[-1].append(tok)
                if _SENTENCE_END.search(tok) and len(_join(chunks[-1])) >= max_chars * 0.5:
                    chunks.append([])
        texts = [_join(c) for c in chunks if c]
        weights = [max(1, len(t)) for t in texts]
        total = float(sum(weights))
        duration = max(0.0, seg.end - seg.start)
        cursor = seg.start
        for text, w in zip(texts, weights):
            nxt = cursor + duration * (w / total)
            out.append(Segment(cursor, nxt, text))
            cursor = nxt
        out[-1].end = seg.end
    return out


def render(segments: list[Segment], fmt: str, result: Optional[dict[str, Any]] = None) -> str:
    import json

    fmt = fmt.lower()
    if fmt == "srt":
        return to_srt(segments)
    if fmt == "vtt":
        return to_vtt(segments)
    if fmt == "txt":
        return to_txt(segments)
    if fmt == "json":
        data = dict(result or {})
        data["segments"] = [s.to_dict() for s in segments]
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    raise ValueError(f"Unsupported caption format {fmt!r}; use one of {', '.join(CAPTION_FORMATS)}.")
