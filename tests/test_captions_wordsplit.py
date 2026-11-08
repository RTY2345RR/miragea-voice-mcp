from miragea_voice_mcp.captions import Segment, fix_word_splits, segments_from_result, to_srt

FULL = "He hoped there would be stew for dinner, turnips and carrots, and bruised potatoes and fat mutton pieces."


def _chunked():
    parts = ["He hoped there would be stew for", "dinner, turnips and carrots, an", "d bruised potatoes and fat mutto", "n pieces", "."]
    return [Segment(i * 2.0, i * 2.0 + 2.0, p) for i, p in enumerate(parts)]


def test_words_cut_across_cues_are_rejoined():
    out = fix_word_splits(_chunked(), FULL)
    texts = [s.text for s in out]
    assert texts[1].endswith("carrots, and")
    assert texts[2] == "bruised potatoes and fat mutton"
    assert texts[3] == "pieces."
    assert " ".join(texts).replace(" .", ".") == FULL or " ".join(texts) == FULL
    for a, b in zip(out, out[1:]):
        assert a.end == b.start and a.start <= a.end


def test_mismatch_with_transcript_leaves_cues_unchanged():
    segs = _chunked()
    assert [s.text for s in fix_word_splits(segs, "something else entirely")] == [s.text for s in segs]


def test_segments_from_result_uses_full_text():
    result = {"text": "ladled out in thick sauce", "segments": [
        {"start": 0, "end": 1, "text": "ladled out in thi"}, {"start": 1, "end": 2, "text": "ck sau"}, {"start": 2, "end": 2.2, "text": "ce"}]}
    srt = to_srt(segments_from_result(result))
    assert "thi\n" not in srt and "\nck" not in srt and "\nce" not in srt
    assert "thick" in srt and "sauce" in srt
