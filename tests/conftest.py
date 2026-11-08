"""Shared fixtures: a fake Miragea API served through httpx.MockTransport (no network)."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

import httpx
import pytest

from miragea_voice_mcp import server

API_KEY = "sk-test-SECRET-1234567890"
AUDIO_URL = "https://cdn.miragea.test/audio/abc.mp3"
AUDIO_BYTES = b"ID3\x04fake-mp3-bytes" * 64

CAPS: dict[str, Any] = {
    "api_version": "1",
    "capabilities": ["audio_generation", "subtitle_recognition"],
    "audio": {
        "models": [
            {
                "id": "expressive",
                "name": "expressive",
                "display_name": "Default",
                "uses_reference_text": True,
                "tags": [{"label": "happy"}, {"label": "calm"}],
            },
            {"id": "standard", "name": "standard", "display_name": "Closer", "uses_reference_text": False, "tags": []},
        ],
        "default_model": "expressive",
        "voice_sources": ["actor_id", "reference_audio_url"],
        "formats": ["mp3", "wav", "flac", "opus", "aac", "pcm"],
        "speed": {"min": 0.25, "max": 4},
        "max_text_length": 500,
        "pricing": {"expressive": {"with_reference_text_multiplier": 1, "without_reference_text_multiplier": 3}},
    },
    "subtitles": {"points_per_second": 2, "max_upload_mb": 1, "max_duration_minutes": 60, "formats": ["srt", "txt", "json"]},
    "task_poll_interval_seconds": 3,
    "skill_version": "1.1.0",
}

SUB_RESULT: dict[str, Any] = {
    "text": "Welcome to Mirage ear. Make videos faster today.",
    "language": "en",
    "segments": [
        {"start": 0.0, "end": 1.6, "text": "Welcome to Mirage ear."},
        {"start": 1.7, "end": 3.9, "text": "Make videos faster today."},
    ],
    "srt": "1\n00:00:00,000 --> 00:00:01,600\nWelcome to Mirage ear.\n\n2\n00:00:01,700 --> 00:00:03,900\nMake videos faster today.\n",
    "txt": "Welcome to Mirage ear. Make videos faster today.",
}


def task(task_id: str, kind: str, status: str, result: Optional[dict] = None, error: Optional[dict] = None) -> dict:
    return {
        "task_id": task_id,
        "kind": kind,
        "status": status,
        "status_path": f"/v1/tasks/{task_id}",
        "poll_after_seconds": 0 if status in ("succeeded", "failed") else 3,
        "result": result,
        "error": error,
        "usage": {"points": 12 if status == "succeeded" else 0, "estimated_points": 12},
        "created_at": "2026-11-08T00:00:00Z",
        "finished_at": None,
    }


class FakeMiragea:
    """Stateful fake of the documented Miragea endpoints."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.polls: dict[str, int] = {}
        self.audio_fail = False
        self.subs_fail = False
        self.never_finish = False
        self.actors = [{"actor_id": f"a{i}", "name": f"Voice {i}", "language": "en"} for i in range(150)]
        self.actors[120]["name"] = "Narrator Nova"
        self.overrides: list[Callable[[httpx.Request], Optional[httpx.Response]]] = []
        self.idempotency: dict[str, bytes] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for hook in list(self.overrides):
            resp = hook(request)
            if resp is not None:
                return resp
        url = request.url
        if url.host == "cdn.miragea.test":
            return httpx.Response(200, content=AUDIO_BYTES, headers={"content-type": "audio/mpeg"})
        if request.headers.get("authorization") != f"Bearer {API_KEY}":
            return httpx.Response(401, json={"error": {"code": "invalid_api_key", "message": "Invalid API key", "type": "authentication_error", "retryable": False}})
        path = url.path
        if path == "/v1/capabilities":
            return httpx.Response(200, json=CAPS)
        if path == "/v1/actors":
            limit, offset = int(url.params["limit"]), int(url.params["offset"])
            items = self.actors[offset : offset + limit]
            return httpx.Response(200, json={"items": items, "has_more": offset + limit < len(self.actors)})
        if path == "/v1/audio/generations" and request.method == "POST":
            return self._create(request, "T-audio", "audio_generation")
        if path == "/v1/subtitles/recognitions" and request.method == "POST":
            return self._create(request, "T-subs", "subtitle_recognition")
        if path == "/v1/tasks":
            return httpx.Response(200, json={"items": [task("T-audio", "audio_generation", "succeeded", {"audio_url": AUDIO_URL, "format": "mp3"})]})
        if path.startswith("/v1/tasks/"):
            tid = path.rsplit("/", 1)[1]
            self.polls[tid] = self.polls.get(tid, 0) + 1
            kind = "audio_generation" if tid == "T-audio" else "subtitle_recognition"
            if tid not in ("T-audio", "T-subs"):
                return httpx.Response(404, json={"error": {"code": "not_found", "message": "Task not found", "type": "invalid_request_error"}})
            if self.never_finish or self.polls[tid] < 2:
                return httpx.Response(200, json=task(tid, kind, "running"))
            if kind == "audio_generation":
                if self.audio_fail:
                    return httpx.Response(200, json=task(tid, kind, "failed", error={"code": "synthesis_failed", "message": "Engine error"}))
                return httpx.Response(200, json=task(tid, kind, "succeeded", {"audio_url": AUDIO_URL, "format": "mp3"}))
            if self.subs_fail:
                return httpx.Response(200, json=task(tid, kind, "failed", error={"code": "asr_failed", "message": "Bad media"}))
            return httpx.Response(200, json=task(tid, kind, "succeeded", SUB_RESULT))
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "no route", "type": "invalid_request_error"}})

    def _create(self, request: httpx.Request, tid: str, kind: str) -> httpx.Response:
        key = request.headers.get("idempotency-key")
        if not key:
            return httpx.Response(400, json={"error": {"code": "missing_idempotency_key", "message": "Idempotency-Key required", "type": "invalid_request_error"}})
        body = request.content
        if key in self.idempotency:
            if self.idempotency[key] != body and kind == "audio_generation":
                return httpx.Response(409, json={"error": {"code": "idempotency_conflict", "message": "conflict", "type": "invalid_request_error"}})
            return httpx.Response(200, json=task(tid, kind, "queued"))
        self.idempotency[key] = body
        return httpx.Response(202, json=task(tid, kind, "queued"))

    # helpers
    def posts(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST" and r.url.path == path]

    def json_of(self, request: httpx.Request) -> dict:
        return json.loads(request.content)


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path) -> FakeMiragea:
    api = FakeMiragea()
    monkeypatch.setenv("MIRAGEA_API_KEY", API_KEY)
    monkeypatch.setenv("MIRAGEA_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("MIRAGEA_BASE_URL", raising=False)
    monkeypatch.delenv("MIRAGEA_WAIT_TIMEOUT", raising=False)
    monkeypatch.setattr(server, "_TRANSPORT", httpx.MockTransport(api))
    monkeypatch.setattr(server, "_SLEEP", _no_sleep)
    return api
