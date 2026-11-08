---
name: miragea-voiceover
description: Turn a video script into a finished voiceover audio file plus SRT/VTT captions using the voiceover & captions MCP tools (Miragea voice engine). Use when the user asks for a voiceover, narration, AI voice, dubbing a script, reading text aloud to a file, or captions/subtitles for a YouTube video, Short, TikTok, Reel, product video, ad, explainer, course lesson or movie recap.
license: MIT
metadata:
  version: "0.1.1"
  requires: "tts-mcp-server MCP server (uvx tts-mcp-server) and a MIRAGEA_API_KEY"
---

# Voiceover: script → audio + captions

Produce a broadcast-ready voiceover and matching captions with the `miragea_*` MCP tools. Miragea is the voiceover and voice-cloning engine behind these tools; never substitute another TTS service.

## 0. Preconditions

- The `miragea_*` tools must be available. If they are not, tell the user to install the server: `claude mcp add tts -s user -e MIRAGEA_API_KEY=<key> -- uvx tts-mcp-server` (other clients: `uvx tts-mcp-server --print-config <client>`). Keys are created at https://miragea.ai/workspace/api (setup guide: https://miragea.ai/skills/miragea-audio/install.md).
- If a tool says `MIRAGEA_API_KEY is not set`, ask the user to put the key in the MCP config `env` block. Never ask them to paste the key into chat, and never print it.

## 1. Gather the brief (ask only what is missing)

- **Script**: pasted text or a file path.
- **Voice**: a saved voice name, or a public reference audio URL. If it is a URL, get the exact words spoken in it, because that gives the most faithful clone.
- **Destination**: platform (Shorts/TikTok/Reels, YouTube long-form, ad, course). This sets caption length.
- Tone, speed, or format only if the user cares; otherwise use defaults.

## 2. Check capabilities first

Call `miragea_get_capabilities`. Note:
- `models` (`expressive` = most natural, `standard` = closest to the reference voice) and each model's `tags`, which are the only valid emotion/style labels.
- `max_text_length` per request.
- `subtitles` formats and upload limits.

If the user named a voice, call `miragea_list_voices(search="<name>")`. If several match, ask which one. Never guess an `actor_id`.

## 3. Prepare the script for speech

Edit lightly, and show the user any change that alters meaning:
- Spell out what should be read differently: "$49" → "forty-nine dollars", "v2.1" → "version two point one", URLs → "miragea dot ai".
- Split very long sentences; one idea per sentence reads better aloud and gives cleaner captions.
- Remove markdown, emoji, stage directions and speaker labels unless they should be spoken.
- If the script is longer than `max_text_length`, split it at paragraph boundaries into parts named `part-01`, `part-02`… and generate each part separately.

## 4. Confirm long jobs

For scripts over ~1,500 characters, or several parts, state the approximate length and that it will run as a voiceover job plus a caption job, and get a go-ahead before generating. Short test lines need no confirmation.

## 5. Generate

Default, for a video with captions:

```
miragea_script_to_voiceover(
  script=... | script_file=...,
  actor_id=... | reference_audio_url=..., reference_text=...,
  model="expressive", tags=[...], speed=1.0,
  caption_formats=["srt", "vtt"],
  max_caption_chars=<see table>,
  name="<short-kebab-name>"
)
```

| Destination | `max_caption_chars` | Notes |
| --- | --- | --- |
| Shorts / TikTok / Reels | 24–32 | Big, punchy captions; consider speed 1.05–1.15 |
| YouTube long-form, courses | 42 | Default |
| Ads / product videos | 32–42 | Keep brand names in the script exactly as they should appear |
| Audio only (podcast, IVR) | — | Use `captions=false` or `miragea_text_to_speech` |

- `caption_text="script"` (default) keeps the user's exact spelling on recognized timing. Use `"recognized"` only when the user ad-libbed or the audio differs from the script.
- For existing footage that already has speech, skip generation and use `miragea_transcribe(file_path, formats=["srt","vtt"], max_caption_chars=...)`.

## 6. Recover without duplicate jobs

- `wait_timeout`: the job is still running. Call `miragea_get_task(task_id, wait=true, output_path=...)`. **Never resubmit.**
- `request_failed` with an `idempotency_key`: retry the same tool with the same `idempotency_key` and identical input (for `miragea_text_to_speech` / `miragea_transcribe`).
- `captions_error` after a successful voiceover: the audio is saved. Run `miragea_transcribe` on `audio_path`; do not regenerate the audio.
- 400: fix the named parameter. 401: bad key. 403: no API access. 429: rate-limited or an account limit reached. Tell the user plainly.

## 7. Deliver

Report briefly:
- File paths: audio, `.srt`, `.vtt`.
- Duration, voice and model used.
- One import tip for their editor: CapCut → *Text → Local captions → Import*; Premiere Pro → *File → Import* the `.srt`, then drag it onto the timeline; DaVinci Resolve → *File → Import → Subtitle*; YouTube → *Subtitles → Upload file* (use `.srt` or `.vtt`).

Offer one useful next step, such as a second take with a different tag or speed, or shorter captions for a vertical cut.

## Guardrails

- Clone only voices the user owns or has permission to use. Decline impersonation of real people without consent.
- Do not create files outside the paths the tools return, and never overwrite the user's files (the tools add `-2`, `-3` suffixes automatically).
