from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from miragea_voice_mcp import server
from miragea_voice_mcp.server import ToolError

from .conftest import API_KEY, AUDIO_BYTES, AUDIO_URL

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------ key / config
async def test_missing_key_gives_clear_error_without_network(monkeypatch, fake):
    monkeypatch.delenv("MIRAGEA_API_KEY")
    with pytest.raises(ToolError) as info:
        await server.miragea_get_capabilities()
    assert "MIRAGEA_API_KEY is not set" in str(info.value)
    assert "miragea.ai/workspace/api" in str(info.value)
    assert fake.requests == []


async def test_invalid_base_url_rejected(monkeypatch, fake):
    monkeypatch.setenv("MIRAGEA_BASE_URL", "https://user:pw@miragea.ai/v1")
    with pytest.raises(ToolError, match="MIRAGEA_BASE_URL"):
        await server.miragea_get_capabilities()


async def test_bad_key_is_explained_and_never_echoed(monkeypatch, fake):
    monkeypatch.setenv("MIRAGEA_API_KEY", "sk-wrong-KEY-should-not-leak")
    with pytest.raises(ToolError) as info:
        await server.miragea_get_capabilities()
    msg = str(info.value)
    assert "HTTP 401" in msg and "MIRAGEA_API_KEY" in msg
    assert "sk-wrong-KEY-should-not-leak" not in msg


# ------------------------------------------------------------------ read-only tools
async def test_capabilities_summary_and_headers(fake):
    caps = await server.miragea_get_capabilities()
    assert [m["id"] for m in caps["models"]] == ["expressive", "standard"]
    assert caps["models"][0]["tags"] == ["happy", "calm"]
    assert caps["max_text_length"] == 500
    assert "vtt" in caps["subtitles"]["extra_local_formats"]
    req = fake.requests[0]
    assert str(req.url) == "https://miragea.ai/v1/capabilities"
    assert req.headers["authorization"] == f"Bearer {API_KEY}"
    ua = req.headers["user-agent"]
    assert ua.startswith("miragea-voice-mcp/") and "urllib" not in ua.lower()


async def test_capabilities_raw_optional(fake):
    caps = await server.miragea_get_capabilities(include_raw=True)
    assert caps["raw"]["api_version"] == "1"


async def test_list_voices_page(fake):
    page = await server.miragea_list_voices(limit=20, offset=0)
    assert len(page["voices"]) == 20 and page["has_more"] is True and page["next_offset"] == 20


async def test_list_voices_search_walks_pages(fake):
    found = await server.miragea_list_voices(search="nova")
    assert found["voices"] == [{"actor_id": "a120", "name": "Narrator Nova", "language": "en"}]
    assert found["scanned"] == 150


async def test_list_voices_bad_limit(fake):
    with pytest.raises(ToolError, match="limit"):
        await server.miragea_list_voices(limit=0)


async def test_list_tasks(fake):
    data = await server.miragea_list_tasks(limit=5)
    assert data["tasks"][0]["task_id"] == "T-audio"
    assert fake.requests[-1].url.params["limit"] == "5"


# ------------------------------------------------------------------ text to speech
async def test_tts_end_to_end_saves_file(fake, tmp_path):
    out = await server.miragea_text_to_speech(
        text="Hello there, creators!", actor_id="a1", model="expressive", tags=["happy"], speed=1.1,
        output_path="hello.mp3",
    )
    path = Path(out["audio_path"])
    assert path == tmp_path / "out" / "hello.mp3"
    assert path.read_bytes() == AUDIO_BYTES
    assert out["status"] == "succeeded" and out["task_id"] == "T-audio"
    post = fake.posts("/v1/audio/generations")[0]
    assert fake.json_of(post) == {
        "text": "Hello there, creators!", "actor_id": "a1", "model": "expressive", "speed": 1.1, "tags": ["happy"],
    }
    assert post.headers["idempotency-key"] == out["idempotency_key"]
    # the bearer token must not be sent to the audio CDN
    cdn = [r for r in fake.requests if r.url.host == "cdn.miragea.test"][0]
    assert "authorization" not in cdn.headers


async def test_tts_never_overwrites(fake, tmp_path):
    a = await server.miragea_text_to_speech(text="One", actor_id="a1", output_path="same.mp3")
    b = await server.miragea_text_to_speech(text="Two", actor_id="a1", output_path="same.mp3")
    assert a["audio_path"] != b["audio_path"] and b["audio_path"].endswith("same-2.mp3")


async def test_tts_reference_voice_and_text_file(fake, tmp_path):
    script = tmp_path / "line.txt"
    script.write_text("  Read me from a file.  \n", encoding="utf-8")
    out = await server.miragea_text_to_speech(
        text_file=str(script), reference_audio_url="https://example.com/ref.wav",
        reference_text="Exact words in the sample.", format="wav", output_path=str(tmp_path / "x"),
    )
    body = fake.json_of(fake.posts("/v1/audio/generations")[0])
    assert body["text"] == "Read me from a file."
    assert body["reference_audio_url"] == "https://example.com/ref.wav"
    assert body["reference_text"] == "Exact words in the sample."
    assert out["audio_path"].endswith("x.mp3")  # extension follows the API result format


async def test_tts_no_wait_returns_task(fake):
    out = await server.miragea_text_to_speech(text="Hi", actor_id="a1", wait=False)
    assert out["status"] == "queued" and "miragea_get_task" in out["next_step"]


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"text": "Hi"}, "exactly one voice"),
        ({"text": "Hi", "actor_id": "a1", "reference_audio_url": "https://x/y.wav"}, "exactly one voice"),
        ({"text": "Hi", "actor_id": "a1", "reference_text": "x"}, "only used together"),
        ({"text": "Hi", "reference_audio_url": "file:///etc/passwd"}, "public http"),
        ({"text": "x" * 501, "actor_id": "a1"}, "allows 500"),
        ({"text": "Hi", "actor_id": "a1", "model": "turbo"}, "Unknown model"),
        ({"text": "Hi", "actor_id": "a1", "speed": 9}, "speed must be"),
        ({"text": "Hi", "actor_id": "a1", "tags": ["angry"]}, "not available"),
        ({"text": "Hi", "actor_id": "a1", "model": "standard", "tags": ["happy"]}, "not available"),
        ({"actor_id": "a1"}, "exactly one of"),
        ({"text": "Hi", "text_file": "/tmp/a.txt", "actor_id": "a1"}, "exactly one of"),
        ({"text": "   ", "actor_id": "a1"}, "exactly one of|empty"),
    ],
)
async def test_tts_validation_blocks_before_submitting(fake, kwargs, match):
    with pytest.raises(ToolError, match=match):
        await server.miragea_text_to_speech(**kwargs)
    assert fake.posts("/v1/audio/generations") == []


async def test_tts_failed_task_reports_error(fake):
    fake.audio_fail = True
    with pytest.raises(ToolError) as info:
        await server.miragea_text_to_speech(text="Hi", actor_id="a1")
    msg = str(info.value)
    assert "T-audio" in msg and "synthesis_failed" in msg


async def test_tts_retries_503_with_same_idempotency_key(fake):
    calls = {"n": 0}

    def flaky(request: httpx.Request):
        if request.url.path == "/v1/audio/generations":
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, json={"error": {"code": "unavailable", "message": "busy", "type": "server_error", "retryable": True}})
        return None

    fake.overrides.append(flaky)
    out = await server.miragea_text_to_speech(text="Hi", actor_id="a1")
    posts = fake.posts("/v1/audio/generations")
    assert len(posts) == 2
    assert posts[0].headers["idempotency-key"] == posts[1].headers["idempotency-key"] == out["idempotency_key"]


async def test_tts_network_error_retried_then_reported_with_key(fake):
    def down(request: httpx.Request):
        if request.url.path == "/v1/audio/generations":
            raise httpx.ConnectError("boom", request=request)
        return None

    fake.overrides.append(down)
    with pytest.raises(ToolError) as info:
        await server.miragea_text_to_speech(text="Hi", actor_id="a1", idempotency_key="op-123")
    msg = str(info.value)
    assert "request_failed" in msg and "op-123" in msg and "same idempotency_key" in msg
    assert len(fake.posts("/v1/audio/generations")) == 3  # 1 try + 2 retries, all same key


async def test_tts_wait_timeout_returns_task_id(monkeypatch, fake):
    fake.never_finish = True
    monkeypatch.setenv("MIRAGEA_WAIT_TIMEOUT", "0.001")
    with pytest.raises(ToolError) as info:
        await server.miragea_text_to_speech(text="Hi", actor_id="a1")
    msg = str(info.value)
    assert "wait_timeout" in msg and "T-audio" in msg and "do not resubmit" in msg.lower()


async def test_api_error_payload_surfaces(fake):
    def reject(request: httpx.Request):
        if request.url.path == "/v1/audio/generations":
            return httpx.Response(429, json={"error": {"code": "insufficient_points", "message": "Not enough credits", "type": "rate_limit_error", "param": None, "retryable": False}})
        return None

    fake.overrides.append(reject)
    with pytest.raises(ToolError) as info:
        await server.miragea_text_to_speech(text="Hi", actor_id="a1")
    msg = str(info.value)
    assert "insufficient_points" in msg and "Check your Miragea account" in msg
    assert len(fake.posts("/v1/audio/generations")) == 1  # 429 is not retried automatically


async def test_redirects_are_not_followed_for_api(fake):
    def redirect(request: httpx.Request):
        if request.url.path == "/v1/capabilities":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        return None

    fake.overrides.append(redirect)
    with pytest.raises(ToolError, match="unexpected_redirect"):
        await server.miragea_get_capabilities()
    assert all(r.url.host != "evil.example" for r in fake.requests)


async def test_cloudflare_html_403_is_explained(fake):
    fake.overrides.append(
        lambda r: httpx.Response(403, text="<html>Just a moment...</html>") if r.url.path == "/v1/capabilities" else None
    )
    with pytest.raises(ToolError, match="cloudflare_blocked"):
        await server.miragea_get_capabilities()


# ------------------------------------------------------------------ transcription
async def test_transcribe_srt_and_vtt(fake, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"\x00\x00fake-video")
    out = await server.miragea_transcribe(file_path=str(media), formats=["srt", "vtt", "json"], output_path="clip-subs")
    srt = Path(out["subtitle_paths"]["srt"]).read_text()
    vtt = Path(out["subtitle_paths"]["vtt"]).read_text()
    data = json.loads(Path(out["subtitle_paths"]["json"]).read_text())
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,600")
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.600\nWelcome to Mirage ear.")
    assert data["language"] == "en" and len(data["segments"]) == 2
    post = fake.posts("/v1/subtitles/recognitions")[0]
    body = post.content
    assert b'name="expected_rate"\r\n\r\n2\r\n' in body
    assert b'filename="clip.mp4"' in body and b"fake-video" in body
    assert post.headers["idempotency-key"] == out["idempotency_key"]
    assert out["limits"]["max_duration_minutes"] == 60


async def test_transcribe_short_captions(fake, tmp_path):
    media = tmp_path / "a.mp3"
    media.write_bytes(b"x")
    out = await server.miragea_transcribe(file_path=str(media), formats=["srt"], max_caption_chars=12)
    assert out["segments"] > 2


async def test_transcribe_missing_file(fake, tmp_path):
    with pytest.raises(ToolError, match="File not found"):
        await server.miragea_transcribe(file_path=str(tmp_path / "nope.mp3"))
    assert fake.requests == []


async def test_transcribe_upload_limit(fake, tmp_path):
    big = tmp_path / "big.wav"
    big.write_bytes(b"0" * (1024 * 1024 + 1))
    with pytest.raises(ToolError, match="upload limit"):
        await server.miragea_transcribe(file_path=str(big))
    assert fake.posts("/v1/subtitles/recognitions") == []


async def test_transcribe_rejects_unknown_format(fake, tmp_path):
    media = tmp_path / "a.mp3"
    media.write_bytes(b"x")
    with pytest.raises(ToolError, match="Unsupported caption format"):
        await server.miragea_transcribe(file_path=str(media), formats=["ass"])  # type: ignore[list-item]


# ------------------------------------------------------------------ one-shot
async def test_script_to_voiceover_uses_script_wording(fake, tmp_path):
    script = "Welcome to Miragea. Make videos faster today."
    out = await server.miragea_script_to_voiceover(script=script, actor_id="a1", name="promo")
    audio = Path(out["audio_path"])
    assert audio.name == "promo.mp3" and audio.read_bytes() == AUDIO_BYTES
    srt = Path(out["caption_paths"]["srt"]).read_text()
    vtt = Path(out["caption_paths"]["vtt"]).read_text()
    assert "Welcome to Miragea." in srt and "Mirage ear" not in srt
    assert "Make videos faster today." in vtt
    assert Path(out["caption_paths"]["srt"]).name == "promo.srt"
    assert out["duration_seconds"] == 3.9
    # recognition ran on the audio we just generated
    rec = fake.posts("/v1/subtitles/recognitions")[0]
    assert AUDIO_BYTES[:20] in rec.content


async def test_script_to_voiceover_recognized_text_option(fake):
    out = await server.miragea_script_to_voiceover(
        script="Welcome to Miragea. Make videos faster today.", actor_id="a1", caption_text="recognized",
        caption_formats=["srt"], max_caption_chars=0,
    )
    assert "Mirage ear" in Path(out["caption_paths"]["srt"]).read_text()


async def test_script_to_voiceover_audio_only(fake):
    out = await server.miragea_script_to_voiceover(script="Short line.", actor_id="a1", captions=False)
    assert "caption_paths" not in out and fake.posts("/v1/subtitles/recognitions") == []


async def test_script_to_voiceover_keeps_audio_when_captions_fail(fake):
    fake.subs_fail = True
    out = await server.miragea_script_to_voiceover(script="Short line.", actor_id="a1")
    assert Path(out["audio_path"]).exists()
    assert "asr_failed" in out["captions_error"]


# ------------------------------------------------------------------ resume
async def test_get_task_resume_and_download(fake, tmp_path):
    out = await server.miragea_get_task("T-audio", wait=True, output_path="resumed.mp3")
    assert Path(out["audio_path"]).read_bytes() == AUDIO_BYTES
    assert out["audio_url"] == AUDIO_URL


async def test_get_task_subtitles_vtt(fake):
    out = await server.miragea_get_task("T-subs", wait=True, caption_formats=["vtt", "srt"])
    assert Path(out["subtitle_paths"]["vtt"]).read_text().startswith("WEBVTT")


async def test_get_task_not_found(fake):
    with pytest.raises(ToolError, match="Task not found"):
        await server.miragea_get_task("T-missing")


async def test_get_task_pending_without_wait(fake):
    out = await server.miragea_get_task("T-audio")
    assert out["status"] == "running" and "wait=true" in out["next_step"]


# ------------------------------------------------------------------ secrecy
async def test_key_never_appears_in_any_result(fake, tmp_path):
    media = tmp_path / "a.mp3"
    media.write_bytes(b"x")
    results = [
        await server.miragea_get_capabilities(include_raw=True),
        await server.miragea_list_voices(),
        await server.miragea_text_to_speech(text="Hi", actor_id="a1"),
        await server.miragea_transcribe(file_path=str(media)),
        await server.miragea_script_to_voiceover(script="Hi there.", actor_id="a1"),
        await server.miragea_list_tasks(),
    ]
    assert API_KEY not in json.dumps(results)
    from miragea_voice_mcp.config import load_settings

    assert API_KEY not in repr(load_settings())
