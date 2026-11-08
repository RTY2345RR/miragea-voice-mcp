"""MCP server exposing Miragea voiceover and subtitle tools over stdio."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Literal, Optional

import httpx

from . import __version__
from .captions import (
    CAPTION_FORMATS,
    Segment,
    align_script,
    render,
    segments_from_result,
    split_long,
)
from .client import MirageaClient, MirageaError, new_idempotency_key, write_new_text
from .config import MISSING_KEY_MESSAGE, ConfigError, Settings, load_settings

try:  # official MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # official MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]
from mcp.types import ToolAnnotations

log = logging.getLogger("miragea_voice_mcp")

INSTRUCTIONS = """\
Voiceover & captions tools for AI agents: turn text into voiceover audio files and audio/video into subtitles (SRT, VTT, TXT, JSON). Miragea is the voiceover and voice-cloning engine behind them.
Workflow:
1. Call miragea_get_capabilities first: it returns the live models (expressive / standard), emotion tags, formats, speed range and text-length limit for this account.
2. Pick a voice: an existing voice from miragea_list_voices (actor_id), or a public reference audio URL (reference_audio_url, ideally with its exact transcript in reference_text).
3. For a video voiceover with captions use miragea_script_to_voiceover; for audio only use miragea_text_to_speech; for subtitles of an existing file use miragea_transcribe.
Do not resubmit a job after a timeout (that would create a duplicate job); resume it with miragea_get_task.
"""

mcp = _Server(name="miragea-voice", instructions=INSTRUCTIONS)

# Test hooks: tests swap in an httpx.MockTransport and a no-op sleep.
_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None
_SLEEP: Any = None

AudioFormat = Literal["mp3", "wav", "flac", "opus", "aac", "pcm"]
CaptionFormat = Literal["srt", "vtt", "txt", "json"]


def _annotations(read_only: bool, idempotent: bool = True) -> ToolAnnotations:
    return ToolAnnotations.model_validate(
        {
            "readOnlyHint": read_only,
            "destructiveHint": False,
            "idempotentHint": idempotent,
            "openWorldHint": True,
        }
    )


# --------------------------------------------------------------- helpers
def _settings() -> Settings:
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise ToolError(str(exc)) from None
    if not settings.has_key:
        raise ToolError(MISSING_KEY_MESSAGE)
    return settings


def _client(settings: Settings) -> MirageaClient:
    kwargs: dict[str, Any] = {"transport": _TRANSPORT}
    if _SLEEP is not None:
        kwargs["sleep"] = _SLEEP
    return MirageaClient(settings, **kwargs)


def _fail(exc: Exception) -> ToolError:
    if isinstance(exc, MirageaError):
        return ToolError(str(exc))
    if isinstance(exc, FileNotFoundError):
        return ToolError(f"File not found: {exc.filename or exc}")
    if isinstance(exc, IsADirectoryError):
        return ToolError(f"Expected a file but got a directory: {exc.filename or exc}")
    if isinstance(exc, (ValueError, OSError, ConfigError)):
        return ToolError(str(exc))
    return ToolError(f"Unexpected error: {type(exc).__name__}: {exc}")


async def _progress(message: str) -> None:
    log.info(message)


def _slug(text: str, limit: int = 32) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)[:6]
    slug = "-".join(words).lower()[:limit].strip("-")
    return slug or "voiceover"


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _resolve(settings: Settings, path: Optional[str], default_name: str) -> Path:
    if path:
        p = Path(path).expanduser()
        return p if p.is_absolute() else settings.output_dir / p
    return settings.output_dir / default_name


def _with_suffix(path: Path, suffix: str) -> Path:
    return path.with_suffix("." + suffix) if path.suffix.lower() != "." + suffix else path


def _read_text(text: Optional[str], text_file: Optional[str], field: str) -> str:
    if bool(text) == bool(text_file):
        raise ToolError(f"Provide exactly one of `{field}` or `{field}_file`.")
    if text_file:
        try:
            value = Path(text_file).expanduser().read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _fail(exc) from None
    else:
        value = text or ""
    value = value.strip()
    if not value:
        raise ToolError(f"`{field}` is empty.")
    return value


def _summarize_capabilities(caps: dict[str, Any]) -> dict[str, Any]:
    audio = caps.get("audio") or {}
    subs = caps.get("subtitles") or {}
    models = []
    for m in audio.get("models") or []:
        if isinstance(m, dict):
            models.append(
                {
                    "id": m.get("id"),
                    "name": m.get("display_name") or m.get("name"),
                    "uses_reference_text": m.get("uses_reference_text"),
                    "tags": [t.get("label") for t in m.get("tags") or [] if isinstance(t, dict)],
                }
            )
    return {
        "models": models,
        "default_model": audio.get("default_model"),
        "voice_sources": audio.get("voice_sources"),
        "audio_formats": audio.get("formats"),
        "speed": audio.get("speed"),
        "max_text_length": audio.get("max_text_length"),
        "subtitles": {
            "max_upload_mb": subs.get("max_upload_mb"),
            "max_duration_minutes": subs.get("max_duration_minutes"),
            "formats": subs.get("formats"),
            "extra_local_formats": ["vtt"],
        },
    }


def _validate_tts(
    caps: dict[str, Any],
    text: str,
    actor_id: Optional[str],
    reference_audio_url: Optional[str],
    reference_text: Optional[str],
    model: Optional[str],
    audio_format: Optional[str],
    speed: Optional[float],
    tags: Optional[list[str]],
) -> None:
    """Catch mistakes before a job is submitted."""
    if bool(actor_id) == bool(reference_audio_url):
        raise ToolError(
            "Choose exactly one voice: `actor_id` (from miragea_list_voices) or `reference_audio_url` "
            "(a public http(s) audio URL)."
        )
    if reference_text and not reference_audio_url:
        raise ToolError("`reference_text` is only used together with `reference_audio_url`.")
    if reference_audio_url and not re.match(r"^https?://", reference_audio_url):
        raise ToolError("`reference_audio_url` must be a public http(s) URL the Miragea server can download.")
    audio = caps.get("audio") or {}
    limit = audio.get("max_text_length")
    if isinstance(limit, int) and limit > 0 and len(text) > limit:
        raise ToolError(
            f"Text is {len(text)} characters but this account allows {limit} per request. "
            "Split the script into shorter parts and generate them one by one."
        )
    models = [m for m in audio.get("models") or [] if isinstance(m, dict)]
    model_ids = [m.get("id") for m in models]
    if model and model_ids and model not in model_ids:
        raise ToolError(f"Unknown model {model!r}. Available: {', '.join(map(str, model_ids))}.")
    formats = audio.get("formats")
    if audio_format and isinstance(formats, list) and formats and audio_format not in formats:
        raise ToolError(f"Unsupported format {audio_format!r}. Available: {', '.join(formats)}.")
    rng = audio.get("speed") or {}
    lo, hi = rng.get("min", 0.25), rng.get("max", 4)
    if speed is not None and not (lo <= speed <= hi):
        raise ToolError(f"speed must be between {lo} and {hi}.")
    if tags:
        chosen = model or audio.get("default_model")
        spec = next((m for m in models if m.get("id") == chosen), None)
        if spec is not None and spec.get("tags") is not None:
            allowed = [t.get("label") for t in spec.get("tags") or [] if isinstance(t, dict)]
            bad = [t for t in tags if t not in allowed]
            if bad:
                raise ToolError(
                    f"Tag(s) {bad} are not available for model {chosen!r}. "
                    f"Allowed: {', '.join(map(str, allowed)) or 'none'}."
                )


def _tts_payload(
    text: str,
    actor_id: Optional[str],
    reference_audio_url: Optional[str],
    reference_text: Optional[str],
    model: Optional[str],
    audio_format: Optional[str],
    speed: Optional[float],
    tags: Optional[list[str]],
    language: Optional[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text}
    for key, value in (
        ("actor_id", actor_id),
        ("reference_audio_url", reference_audio_url),
        ("reference_text", reference_text),
        ("model", model),
        ("format", audio_format),
        ("speed", speed),
        ("tags", tags or None),
        ("language", language),
    ):
        if value is not None and value != "":
            payload[key] = value
    return payload


def _task_summary(task: dict[str, Any], key: Optional[str] = None) -> dict[str, Any]:
    out = {
        "task_id": task.get("task_id"),
        "kind": task.get("kind"),
        "status": task.get("status"),
    }
    if task.get("error"):
        out["error"] = task.get("error")
    if key:
        out["idempotency_key"] = key
    return out


def _task_failed(task: dict[str, Any], key: Optional[str]) -> ToolError:
    err = task.get("error") or {}
    msg = err.get("message") if isinstance(err, dict) else str(err)
    code = err.get("code") if isinstance(err, dict) else None
    return ToolError(
        f"Miragea task {task.get('task_id')} failed"
        + (f" [{code}]" if code else "")
        + f": {msg or 'no details'}."
        + (f" idempotency_key={key}" if key else "")
    )


def _write_captions(
    base: Path,
    result: dict[str, Any],
    segments: list[Segment],
    formats: list[str],
    native_ok: bool,
) -> dict[str, str]:
    saved: dict[str, str] = {}
    for fmt in dict.fromkeys(f.lower() for f in formats):
        if fmt not in CAPTION_FORMATS:
            raise ToolError(f"Unsupported caption format {fmt!r}; use {', '.join(CAPTION_FORMATS)}.")
        if native_ok and fmt in ("srt", "txt") and isinstance(result.get(fmt), str) and result.get(fmt).strip():
            text = result[fmt]
        elif fmt == "json" and native_ok:
            text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        else:
            if not segments:
                raise ToolError("Recognition returned no timed segments, so captions cannot be built.")
            text = render(segments, fmt, result)
        saved[fmt] = str(write_new_text(_with_suffix(base, fmt), text))
    return saved


async def _recognize(
    client: MirageaClient,
    file: Path,
    expected_rate: Optional[float],
    key: str,
    wait: bool,
    timeout: Optional[float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not file.is_file():
        raise ToolError(f"File not found: {file}")
    caps = await client.capabilities()
    subs = caps.get("subtitles") or {}
    rate = expected_rate if expected_rate is not None else subs.get("points_per_second")
    if rate is None:
        raise ToolError("The API capabilities are missing the subtitle settings; cannot submit recognition.")
    if isinstance(rate, float) and rate.is_integer():
        rate = int(rate)
    max_mb = subs.get("max_upload_mb")
    if isinstance(max_mb, (int, float)) and file.stat().st_size > max_mb * 1024 * 1024:
        raise ToolError(f"{file.name} is larger than the {max_mb} MB upload limit. Trim or compress it first.")
    task = await client.create_recognition(file, rate, key)
    if wait and task.get("status") not in ("succeeded", "failed"):
        task = await client.wait_for_task(task["task_id"], timeout, _progress)
    return task, {"max_duration_minutes": subs.get("max_duration_minutes")}


# ----------------------------------------------------------------- tools
@mcp.tool(
    name="miragea_get_capabilities",
    description=(
        "Get the live voice-engine capabilities for this API key: voice models (expressive, standard), "
        "emotion/style tags per model, voice sources, audio formats, speed range, max characters per request, "
        "and subtitle formats and upload limits. Read-only. Call this first."
    ),
    annotations=_annotations(read_only=True),
)
async def miragea_get_capabilities(include_raw: bool = False) -> dict[str, Any]:
    """Return a compact summary of what this account can do (set include_raw for the full response)."""
    settings = _settings()
    try:
        async with _client(settings) as client:
            caps = await client.capabilities()
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    summary = _summarize_capabilities(caps)
    if include_raw:
        summary["raw"] = caps
    return summary


@mcp.tool(
    name="miragea_list_voices",
    description=(
        "List the voices (actors) saved in the user's Miragea account, with actor_id, name and language. "
        "Use `search` to find a voice by name across pages. Pass the actor_id to the voiceover tools. Read-only."
    ),
    annotations=_annotations(read_only=True),
)
async def miragea_list_voices(
    search: Optional[str] = None, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    settings = _settings()
    try:
        async with _client(settings) as client:
            if not search:
                page = await client.list_actors(limit=limit, offset=offset)
                return {
                    "voices": page.get("items", []),
                    "has_more": bool(page.get("has_more")),
                    "next_offset": offset + len(page.get("items", [])) if page.get("has_more") else None,
                }
            needle = search.casefold().strip()
            matches: list[dict[str, Any]] = []
            cursor, scanned = offset, 0
            while scanned < 1000:
                page = await client.list_actors(limit=100, offset=cursor)
                items = page.get("items", []) or []
                scanned += len(items)
                matches += [a for a in items if needle in str(a.get("name", "")).casefold()]
                if not page.get("has_more") or not items:
                    break
                cursor += len(items)
            return {"voices": matches[: max(1, limit)], "match_count": len(matches), "scanned": scanned}
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None


@mcp.tool(
    name="miragea_text_to_speech",
    description=(
        "Generate a voiceover audio file from text (Miragea voice engine) and save it locally. Choose a voice with "
        "`actor_id` (from miragea_list_voices) OR `reference_audio_url` (public URL to clone from; add its exact "
        "transcript in `reference_text` for the most faithful clone). Optional: model "
        "('expressive' or 'standard'), tags (emotion/style labels from capabilities), speed 0.25-4, format. "
        "Returns the saved file path and task_id."
    ),
    annotations=_annotations(read_only=False, idempotent=False),
)
async def miragea_text_to_speech(
    text: Optional[str] = None,
    text_file: Optional[str] = None,
    actor_id: Optional[str] = None,
    reference_audio_url: Optional[str] = None,
    reference_text: Optional[str] = None,
    model: Optional[str] = None,
    format: Optional[AudioFormat] = None,  # noqa: A002 - mirrors the API field name
    speed: Optional[float] = None,
    tags: Optional[list[str]] = None,
    language: Optional[str] = None,
    output_path: Optional[str] = None,
    wait: bool = True,
    wait_timeout_seconds: Optional[float] = None,
    idempotency_key: Optional[str] = None,
) -> dict[str, Any]:
    body = _read_text(text, text_file, "text")
    settings = _settings()
    key = idempotency_key or new_idempotency_key()
    try:
        async with _client(settings) as client:
            caps = await client.capabilities()
            _validate_tts(caps, body, actor_id, reference_audio_url, reference_text, model, format, speed, tags)
            payload = _tts_payload(
                body, actor_id, reference_audio_url, reference_text, model, format, speed, tags, language
            )
            task = await client.create_audio(payload, key)
            if not wait:
                out = _task_summary(task, key)
                out["next_step"] = "Call miragea_get_task with this task_id (wait=true, output_path) to download."
                return out
            if task.get("status") not in ("succeeded", "failed"):
                task = await client.wait_for_task(task["task_id"], wait_timeout_seconds, _progress)
            if task.get("status") == "failed":
                raise _task_failed(task, key)
            result = task.get("result") or {}
            ext = result.get("format") or format or "mp3"
            dest = _with_suffix(_resolve(settings, output_path, f"miragea-{_slug(body)}-{_stamp()}.{ext}"), ext)
            saved = await client.download(result.get("audio_url", ""), dest)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, MirageaError) and not exc.idempotency_key:
            exc.idempotency_key = key
        raise _fail(exc) from None
    out = _task_summary(task, key)
    out.update({"audio_path": str(saved), "audio_url": result.get("audio_url"), "format": ext, "characters": len(body)})
    return out


@mcp.tool(
    name="miragea_transcribe",
    description=(
        "Create subtitles from a local audio or video file (mp3, wav, m4a, mp4, mov, ...) with Miragea speech "
        "recognition. Saves SRT by default; also VTT, TXT or JSON (text, language, timed segments). "
        "`max_caption_chars` splits long cues for short-form video (e.g. 32-42)."
    ),
    annotations=_annotations(read_only=False, idempotent=False),
)
async def miragea_transcribe(
    file_path: str,
    formats: Optional[list[CaptionFormat]] = None,
    output_path: Optional[str] = None,
    max_caption_chars: int = 0,
    expected_rate: Optional[float] = None,
    wait: bool = True,
    wait_timeout_seconds: Optional[float] = None,
    idempotency_key: Optional[str] = None,
) -> dict[str, Any]:
    settings = _settings()
    file = Path(file_path).expanduser()
    fmts = list(formats or ["srt"])
    key = idempotency_key or new_idempotency_key()
    try:
        async with _client(settings) as client:
            task, limits_info = await _recognize(client, file, expected_rate, key, wait, wait_timeout_seconds)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, MirageaError) and not exc.idempotency_key:
            exc.idempotency_key = key
        raise _fail(exc) from None
    if not wait:
        out = _task_summary(task, key)
        out["next_step"] = "Call miragea_get_task with this task_id (wait=true, output_path) to save subtitles."
        return out
    if task.get("status") == "failed":
        raise _task_failed(task, key)
    result = task.get("result") or {}
    segments = split_long(segments_from_result(result), max_caption_chars)
    base = _resolve(settings, output_path, f"{file.stem}-{_stamp()}")
    saved = _write_captions(base, result, segments, fmts, native_ok=not max_caption_chars)
    out = _task_summary(task, key)
    out.update(
        {
            "subtitle_paths": saved,
            "language": result.get("language"),
            "segments": len(segments),
            "text_preview": (result.get("text") or "")[:500],
            "limits": limits_info,
        }
    )
    return out


@mcp.tool(
    name="miragea_script_to_voiceover",
    description=(
        "One shot for video creators: turn a script into a voiceover audio file PLUS matching captions "
        "(SRT and VTT by default) ready for CapCut, Premiere, DaVinci Resolve, YouTube or Shorts/TikTok/Reels. "
        "Generates speech with Miragea, then times captions by running Miragea recognition on the new audio. "
        "caption_text='script' (default) keeps your exact script wording (brand names spelled right) on the "
        "recognized timing. Set captions=false for audio only."
    ),
    annotations=_annotations(read_only=False, idempotent=False),
)
async def miragea_script_to_voiceover(
    script: Optional[str] = None,
    script_file: Optional[str] = None,
    actor_id: Optional[str] = None,
    reference_audio_url: Optional[str] = None,
    reference_text: Optional[str] = None,
    model: Optional[str] = None,
    format: AudioFormat = "mp3",  # noqa: A002
    speed: Optional[float] = None,
    tags: Optional[list[str]] = None,
    language: Optional[str] = None,
    captions: bool = True,
    caption_formats: Optional[list[CaptionFormat]] = None,
    caption_text: Literal["script", "recognized"] = "script",
    max_caption_chars: int = 42,
    output_dir: Optional[str] = None,
    name: Optional[str] = None,
    wait_timeout_seconds: Optional[float] = None,
) -> dict[str, Any]:
    body = _read_text(script, script_file, "script")
    settings = _settings()
    folder = _resolve(settings, output_dir, "") if output_dir else settings.output_dir
    base_name = re.sub(r"[^\w-]+", "-", name).strip("-") if name else f"{_slug(body)}-{_stamp()}"
    base = folder / (base_name or "voiceover")
    tts_key, rec_key = new_idempotency_key(), new_idempotency_key()
    report: dict[str, Any] = {"characters": len(body)}
    try:
        async with _client(settings) as client:
            caps = await client.capabilities()
            _validate_tts(caps, body, actor_id, reference_audio_url, reference_text, model, format, speed, tags)
            payload = _tts_payload(
                body, actor_id, reference_audio_url, reference_text, model, format, speed, tags, language
            )
            task = await client.create_audio(payload, tts_key)
            if task.get("status") not in ("succeeded", "failed"):
                task = await client.wait_for_task(task["task_id"], wait_timeout_seconds, _progress)
            if task.get("status") == "failed":
                raise _task_failed(task, tts_key)
            result = task.get("result") or {}
            ext = result.get("format") or format
            audio_path = await client.download(result.get("audio_url", ""), _with_suffix(base, ext))
            report["voiceover"] = _task_summary(task, tts_key)
            report["audio_path"] = str(audio_path)
            report["audio_url"] = result.get("audio_url")
            if not captions:
                return report
            try:
                rec, _ = await _recognize(client, audio_path, None, rec_key, True, wait_timeout_seconds)
            except (MirageaError, ToolError) as exc:
                report["captions_error"] = str(exc)
                report["next_step"] = (
                    "Audio is saved. Retry captions only with miragea_transcribe on audio_path; "
                    "do not regenerate the voiceover."
                )
                return report
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    report["captions_task"] = _task_summary(rec, rec_key)
    if rec.get("status") == "failed":
        report["captions_error"] = str(_task_failed(rec, rec_key))
        return report
    rec_result = rec.get("result") or {}
    segments = segments_from_result(rec_result)
    if caption_text == "script":
        segments = align_script(body, segments)
    segments = split_long(segments, max_caption_chars)
    report["caption_paths"] = _write_captions(
        Path(audio_path).with_suffix(""), rec_result, segments, list(caption_formats or ["srt", "vtt"]), native_ok=False
    )
    report["caption_count"] = len(segments)
    report["duration_seconds"] = round(segments[-1].end, 3) if segments else None
    return report


@mcp.tool(
    name="miragea_get_task",
    description=(
        "Check a Miragea task by task_id and optionally wait for it and save its output (audio file, or "
        "subtitles in srt/vtt/txt/json). Use this to resume after a timeout instead of resubmitting."
    ),
    annotations=_annotations(read_only=False),
)
async def miragea_get_task(
    task_id: str,
    wait: bool = False,
    output_path: Optional[str] = None,
    caption_formats: Optional[list[CaptionFormat]] = None,
    wait_timeout_seconds: Optional[float] = None,
) -> dict[str, Any]:
    settings = _settings()
    try:
        async with _client(settings) as client:
            task = await client.get_task(task_id)
            if wait and task.get("status") not in ("succeeded", "failed"):
                task = await client.wait_for_task(task_id, wait_timeout_seconds, _progress)
            out = _task_summary(task)
            if task.get("status") != "succeeded":
                if task.get("status") == "failed":
                    raise _task_failed(task, None)
                out["next_step"] = "Still processing; call again with wait=true."
                return out
            result = task.get("result") or {}
            if task.get("kind") == "audio_generation":
                out["audio_url"] = result.get("audio_url")
                if output_path is not None or wait:
                    ext = result.get("format") or "mp3"
                    dest = _with_suffix(_resolve(settings, output_path, f"miragea-{task_id[:8]}.{ext}"), ext)
                    out["audio_path"] = str(await client.download(result.get("audio_url", ""), dest))
            else:
                out["language"] = result.get("language")
                out["text_preview"] = (result.get("text") or "")[:500]
                if output_path is not None or wait:
                    base = _resolve(settings, output_path, f"subtitles-{task_id[:8]}")
                    out["subtitle_paths"] = _write_captions(
                        base.with_suffix("") if base.suffix.lower() in (".srt", ".vtt", ".txt", ".json") else base,
                        result,
                        segments_from_result(result),
                        list(caption_formats or ["srt"]),
                        native_ok=True,
                    )
            return out
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None


@mcp.tool(
    name="miragea_list_tasks",
    description="List recent Miragea tasks (voiceovers and subtitle jobs) for this account, newest first.",
    annotations=_annotations(read_only=True),
)
async def miragea_list_tasks(limit: int = 20) -> dict[str, Any]:
    settings = _settings()
    try:
        async with _client(settings) as client:
            data = await client.list_tasks(limit)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"tasks": [_task_summary(t) for t in data.get("items", []) if isinstance(t, dict)]}


def run() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log.info("miragea-voice-mcp %s starting (stdio)", __version__)
    mcp.run("stdio")
