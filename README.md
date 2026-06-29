# VoxScribe

**Real-time speech transcription and translation overlay for Windows.**

VoxScribe captures system audio output through Windows loopback, or a microphone, transcribes it offline with Whisper, translates it in real time, and displays captions in a draggable always-on-top overlay. It is built for meetings, presentations, and multilingual conversations.

<p align="center">
  <img src="screenshots/demo.png" alt="VoxScribe Demo" width="600" />
  <br/>
  <em>Subtitle overlay in compact and full modes</em>
</p>

---

## Features

- **Always-on-top overlay** - draggable subtitle window with compact and full transcript modes
- **Offline speech recognition** - faster-whisper large-v3 for ASR
- **Disk-backed audio buffering** - slow CPU transcription can fall behind without silently dropping captured audio
- **Real-time translation** - Google Translate via `deep-translator`
- **Direct script conversion** - zh-cn <-> zh-tw uses OpenCC locally, not online translation
- **Technology glossary** - IT/engineering terms corrected after ASR
- **Hardware auto-tuning** - detects specs and picks a high/mid/low runtime profile
- **Hot-swap languages** - change input/output language mid-session
- **Persistent transcript** - view, save, and clear transcript history
- **Local integration API** - optional HTTP API for runtime state, caption, and transcript data
- **CJK-aware text wrapping** - better line-breaking for mixed Latin and CJK text

<p align="center">
  <img src="screenshots/setup.png" alt="VoxScribe Main Window" width="600" />
  <br/>
  <em>Main window: language selection, audio source, and status controls</em>
</p>

## Supported Languages

| Role | Languages |
|------|-----------|
| Input ASR | English, Mandarin Simplified (zh-cn), Mandarin Traditional (zh-tw), Indonesian |
| Output translation | English, Mandarin Simplified (zh-cn), Mandarin Traditional (zh-tw), Indonesian |

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.10+
- At least 8 GB RAM
- At least 6 GB free disk space for the Whisper model, plus extra room for temporary audio spool backlog

### Run

```bash
git clone https://github.com/T0MM11Y/voxscribe-live-caption.git
cd voxscribe-live-caption
python main.py
```

On first launch, VoxScribe checks dependencies, runs a PC spec check, downloads the Whisper model if needed, warms up audio capture, and opens the subtitle overlay.

### Build Standalone EXE

```bash
python build_exe.py
```

Output: `dist/VoxScribe.exe`.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F5` | Start / stop recognition |
| `Ctrl + S` | Save transcript to file |
| `Ctrl + Shift + C` | Toggle compact / full overlay mode |

## Architecture

```text
main.py                      # Entry point, DPI awareness, crash logging
app/
  controller.py              # AppController alias
  ui/
    main_window.py           # GUI orchestration, startup flow, state machine
    subtitle_overlay.py      # Always-on-top draggable overlay
    dialogs.py               # Custom themed dialog boxes
  audio/
    capture.py               # Windows loopback / microphone capture via soundcard
    spool.py                 # Disk-backed PCM audio spool for long ASR backlog
  recognition/
    whisper_engine.py        # faster-whisper ASR with VAD, filtering, chunking
    model_manager.py         # Model lifecycle, cache, validation
  translation/
    service.py               # Async priority queue, caching, OpenCC direct conversion
  services/
    transcript.py            # In-memory transcript storage and rendering
    glossary.py              # Source glossary normalization
    export.py                # Transcript file export
    language_switcher.py     # Hot-swap language facade
  core/
    config.py                # JSON config persisted to ~/.voxscribe/config.json
    languages.py             # Language registry and transform strategies
    state.py                 # Thread-safe observable state container
  integration/
    openapi.py               # Optional local HTTP API
  system/
    profiler.py              # Hardware probe, auto-tuner, spec checker
tests/                       # unittest coverage for major subsystems
```

## Audio Buffering

Audio capture uses a disk-backed spool by default at `~/.voxscribe/audio_spool`. Captured PCM frames are written to a temporary session directory and consumed by Whisper in order. This prevents silent drops when CPU transcription is slower than real time.

The spool is still bounded by disk availability. If free disk space falls below `audio_spool_min_free_mb`, capture stops with an explicit retryable error instead of dropping audio. Current session spool files are auto-deleted on stop/cleanup, and old orphan sessions are cleaned on the next start.

## Runtime Pipeline

1. Audio capture writes PCM frames to the disk-backed spool.
2. Whisper consumes queued audio in order and emits final source chunks.
3. Final ASR chunks accumulate in a stable translation buffer.
4. The buffer flushes on sentence punctuation, ideal chunk size plus short delay, max chars, or max timeout.
5. Translated output updates the overlay and transcript.

Default latency profile: `responsive`. Timing config lives in `app/core/config.py`.

## Testing

```bash
# Run all tests
python -m unittest discover -s tests

# Run one test file
python -m unittest discover -s tests -p "test_translation_service.py"
```

Current test coverage includes audio capture/spool, Whisper recognition, translation queue, glossary corrections, overlay layout, main window state, language config, OpenAPI integration, auto-tuner, and transcript service.

## Integration API

When `integration_api_enabled` is `true`, a local HTTP server starts on `http://127.0.0.1:8765`.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Server health check |
| `GET /openapi.json` | OpenAPI 3.1 specification |
| `GET /docs` | Swagger-style HTML docs |
| `GET /runtime/snapshot` | Full runtime state snapshot |
| `GET /runtime/state` | Current application state |
| `GET /runtime/caption` | Current caption text and translation |
| `GET /runtime/transcript` | Full transcript history |

## Configuration

All settings are stored in `~/.voxscribe/config.json`. Notable options:

| Key | Default | Description |
|-----|---------|-------------|
| `input_language` | `en` | Source language for ASR |
| `output_language` | `en` | Target language for translation |
| `compute_device` | `cpu` | `cpu` or `cuda` |
| `audio_source_type` | `loopback` | `loopback` or `microphone` |
| `audio_spool_enabled` | `true` | Use disk-backed audio buffering instead of memory-only queue |
| `audio_spool_min_free_mb` | `1024` | Stop capture before disk free space drops below this threshold |
| `audio_spool_stale_cleanup_hours` | `24` | Remove orphaned temporary spool sessions older than this |
| `overlay_font_size` | `16` | Caption font size |
| `overlay_compact` | `true` | Compact overlay mode default |
| `integration_api_enabled` | `false` | Enable local HTTP API |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Startup fails | Ensure Windows audio output is active and playing sound |
| NumPy 2.x error | Install `numpy<2` |
| Chinese Traditional issues | Install `opencc-python-reimplemented` |
| Translation empty | Check internet connection |
| Model download slow | Model is about 3 GB; wait for the one-time download |
| Audio spool disk space is low | Free disk space, or lower `audio_spool_min_free_mb` only if you understand the risk |

## Tech Stack

- **ASR**: faster-whisper / CTranslate2
- **Translation**: deep-translator / Google Translate
- **UI**: CustomTkinter
- **Audio capture**: soundcard
- **Script conversion**: opencc-python-reimplemented
- **Build**: PyInstaller, excluding torch/transformers/tensorflow from the bundled app

## License

MIT
