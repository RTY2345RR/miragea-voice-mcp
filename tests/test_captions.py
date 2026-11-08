from miragea_voice_mcp.captions import (
    Segment,
    align_script,
    parse_srt,
    render,
    segments_from_result,
    split_long,
    to_srt,
    to_vtt,
)


def test_srt_and_vtt_timestamps():
    segs = [Segment(0, 1.5, "Hi"), Segment(3661.25, 3662.0, "Later")]
    assert to_srt(segs) == "1\n00:00:00,000 --> 00:00:01,500\nHi\n\n2\n01:01:01,250 --> 01:01:02,000\nLater\n"
    assert to_vtt(segs).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHi\n\n01:01:01.250")


def test_parse_srt_roundtrip_and_crlf():
    segs = [Segment(0.1, 0.9, "One"), Segment(1.0, 2.0, "Two words")]
    again = parse_srt(to_srt(segs).replace("\n", "\r\n"))
    assert [(s.start, s.end, s.text) for s in again] == [(0.1, 0.9, "One"), (1.0, 2.0, "Two words")]


def test_segments_fallback_to_srt():
    res = {"srt": "1\n00:00:01,000 --> 00:00:02,000\nHello\n"}
    assert segments_from_result(res)[0].text == "Hello"


def test_segments_skip_bad_items():
    res = {"segments": [{"start": 0, "end": 1, "text": "ok"}, {"start": "x"}, "junk", {"start": 1, "end": 2, "text": " "}]}
    assert [s.text for s in segments_from_result(res)] == ["ok"]


def test_align_script_preserves_wording_and_timing():
    segs = [Segment(0, 2, "welcome to mirage ear"), Segment(2, 4, "we make shorts fast")]
    out = align_script("Welcome to Miragea. We make Shorts fast!", segs)
    assert [s.text for s in out] == ["Welcome to Miragea.", "We make Shorts fast!"]
    assert [(s.start, s.end) for s in out] == [(0, 2), (2, 4)]


def test_align_script_cjk():
    segs = [Segment(0, 1, "你好世界"), Segment(1, 2, "欢迎回来")]
    out = align_script("你好，世界。欢迎回来！", segs)
    assert "".join(s.text for s in out) == "你好，世界。欢迎回来！"
    assert out[0].text.endswith("。")


def test_align_more_segments_than_words():
    segs = [Segment(0, 1, "a"), Segment(1, 2, "b"), Segment(2, 3, "c")]
    out = align_script("Hello", segs)
    assert " ".join(s.text for s in out) == "Hello"
    assert out[-1].end == 3


def test_align_empty_inputs():
    assert align_script("", [Segment(0, 1, "x")])[0].text == "x"
    assert align_script("hi", []) == []


def test_split_long_shares_time():
    seg = Segment(0, 10, "This sentence is quite long. And here is another one that keeps going on.")
    out = split_long([seg], 30)
    assert all(len(s.text) <= 30 for s in out)
    assert out[0].start == 0 and out[-1].end == 10
    assert all(a.end <= b.start + 1e-9 for a, b in zip(out, out[1:]))
    assert " ".join(s.text for s in out) == seg.text


def test_split_disabled():
    seg = Segment(0, 1, "x" * 100)
    assert split_long([seg], 0) == [seg]


def test_render_txt_json():
    segs = [Segment(0, 1, "A"), Segment(1, 2, "B")]
    assert render(segs, "txt") == "A\nB\n"
    assert '"segments"' in render(segs, "json", {"language": "en"})
