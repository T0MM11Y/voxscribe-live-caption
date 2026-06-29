"""Optional local OpenAPI integration server for desktop runtime state."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


def _public_host(host: str) -> str:
    normalized = str(host or "").strip() or "127.0.0.1"
    if normalized in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return normalized


def build_openapi_spec(
    title: str,
    version: str,
    host: str,
    port: int,
    docs_enabled: bool = True,
) -> dict:
    server_url = f"http://{_public_host(host)}:{int(port)}"
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": version,
            "description": (
                "Local integration API for the VoxScribe desktop runtime. "
                "This API exposes read-only runtime snapshots so external tools "
                "can inspect recognition, caption, and transcript state."
            ),
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Check integration API health",
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "Integration API is available",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "Download the OpenAPI document",
                    "operationId": "getOpenApiDocument",
                    "responses": {
                        "200": {
                            "description": "OpenAPI document",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            },
                        }
                    },
                }
            },
            "/runtime/snapshot": {
                "get": {
                    "summary": "Read the complete runtime snapshot",
                    "operationId": "getRuntimeSnapshot",
                    "responses": {
                        "200": {
                            "description": "Full desktop runtime snapshot",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RuntimeSnapshot"}
                                }
                            },
                        }
                    },
                }
            },
            "/runtime/state": {
                "get": {
                    "summary": "Read compact runtime state",
                    "operationId": "getRuntimeState",
                    "responses": {
                        "200": {
                            "description": "Current recognition/runtime status",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RuntimeState"}
                                }
                            },
                        }
                    },
                }
            },
            "/runtime/caption": {
                "get": {
                    "summary": "Read current caption payload",
                    "operationId": "getRuntimeCaption",
                    "responses": {
                        "200": {
                            "description": "Current source preview and translated caption",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CaptionState"}
                                }
                            },
                        }
                    },
                }
            },
            "/runtime/transcript": {
                "get": {
                    "summary": "Read transcript payload",
                    "operationId": "getRuntimeTranscript",
                    "responses": {
                        "200": {
                            "description": "Rendered transcript and structured entries",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/TranscriptPayload"}
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "required": [
                        "status",
                        "service",
                        "version",
                        "generated_at",
                        "server_url",
                        "docs_enabled",
                    ],
                    "properties": {
                        "status": {"type": "string", "enum": ["ok"]},
                        "service": {"type": "string"},
                        "version": {"type": "string"},
                        "generated_at": {"type": "string", "format": "date-time"},
                        "server_url": {"type": "string", "format": "uri"},
                        "docs_enabled": {"type": "boolean"},
                    },
                },
                "RuntimeState": {
                    "type": "object",
                    "required": [
                        "status",
                        "status_message",
                        "is_recognizing",
                        "recognition_ready",
                        "input_language",
                        "output_language",
                        "availability",
                    ],
                    "properties": {
                        "status": {"type": "string"},
                        "status_message": {"type": "string"},
                        "is_recognizing": {"type": "boolean"},
                        "recognition_ready": {"type": "boolean"},
                        "stats": {"type": "string"},
                        "compute_backend_label": {"type": "string"},
                        "device_profile": {"type": "string"},
                        "input_language": {"$ref": "#/components/schemas/LanguageRef"},
                        "output_language": {"$ref": "#/components/schemas/LanguageRef"},
                        "availability": {
                            "type": "object",
                            "additionalProperties": {"type": "boolean"},
                        },
                    },
                },
                "LanguageRef": {
                    "type": "object",
                    "required": ["code", "label"],
                    "properties": {
                        "code": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
                "CaptionState": {
                    "type": "object",
                    "required": [
                        "source_text",
                        "translated_text",
                        "source_preview_text",
                        "translation_pending",
                        "translation_pending_source",
                        "current_translation_source",
                        "current_translation_source_language",
                        "current_translation_target",
                    ],
                    "properties": {
                        "source_text": {"type": "string"},
                        "translated_text": {"type": "string"},
                        "source_preview_text": {"type": "string"},
                        "translation_pending": {"type": "boolean"},
                        "translation_pending_source": {"type": "string"},
                        "current_translation_source": {"type": "string"},
                        "current_translation_source_language": {"type": "string"},
                        "current_translation_target": {"type": "string"},
                    },
                },
                "TranscriptEntry": {
                    "type": "object",
                    "required": [
                        "id",
                        "timestamp",
                        "text",
                        "target_language",
                        "target_label",
                        "pending_text",
                        "translation_pending",
                    ],
                    "properties": {
                        "id": {"type": "integer"},
                        "timestamp": {"type": "string"},
                        "text": {"type": "string"},
                        "target_language": {"type": "string"},
                        "target_label": {"type": "string"},
                        "pending_text": {"type": "string"},
                        "translation": {"type": ["string", "null"]},
                        "translation_pending": {"type": "boolean"},
                    },
                },
                "TranscriptPayload": {
                    "type": "object",
                    "required": ["entry_count", "entries", "rendered"],
                    "properties": {
                        "entry_count": {"type": "integer"},
                        "entries": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/TranscriptEntry"},
                        },
                        "rendered": {"type": "string"},
                    },
                },
                "RuntimeSnapshot": {
                    "type": "object",
                    "required": ["runtime", "caption", "transcript"],
                    "properties": {
                        "runtime": {"$ref": "#/components/schemas/RuntimeState"},
                        "caption": {"$ref": "#/components/schemas/CaptionState"},
                        "transcript": {"$ref": "#/components/schemas/TranscriptPayload"},
                    },
                },
            }
        },
    }

    if docs_enabled:
        spec["paths"]["/docs"] = {
            "get": {
                "summary": "Read the local documentation landing page",
                "operationId": "getLocalDocs",
                "responses": {
                    "200": {
                        "description": "Static HTML documentation page",
                        "content": {
                            "text/html": {"schema": {"type": "string"}}
                        },
                    }
                },
            }
        }

    return spec


def _docs_html(title: str, server_url: str, spec_url: str) -> str:
    escaped_title = escape(title)
    escaped_server_url = escape(server_url)
    escaped_spec_url = escape(spec_url)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f4f7fb;
      color: #16212f;
    }}
    main {{
      max-width: 950px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #d7e0ea;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 32px;
    }}
    code, pre {{
      font-family: Consolas, "Courier New", monospace;
    }}
    pre {{
      background: #0f172a;
      color: #dbeafe;
      padding: 16px;
      border-radius: 12px;
      overflow: auto;
      min-height: 160px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid #e2e8f0;
    }}
    a {{
      color: #0057d9;
      text-decoration: none;
    }}
    .pill {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: #dbeafe;
      color: #1d4ed8;
      font-size: 13px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main>
    <section class="card">
      <span class="pill">Local OpenAPI</span>
      <h1>{escaped_title}</h1>
      <p>Base URL: <code>{escaped_server_url}</code></p>
      <p>OpenAPI document: <a href="{escaped_spec_url}"><code>{escaped_spec_url}</code></a></p>
    </section>
    <section class="card">
      <h2>Endpoints</h2>
      <table>
        <thead>
          <tr><th>Method</th><th>Path</th><th>Purpose</th></tr>
        </thead>
        <tbody>
          <tr><td>GET</td><td><code>/health</code></td><td>Check the local integration server.</td></tr>
          <tr><td>GET</td><td><code>/openapi.json</code></td><td>Download the OpenAPI specification.</td></tr>
          <tr><td>GET</td><td><code>/runtime/snapshot</code></td><td>Read the full desktop runtime snapshot.</td></tr>
          <tr><td>GET</td><td><code>/runtime/state</code></td><td>Read compact runtime metadata.</td></tr>
          <tr><td>GET</td><td><code>/runtime/caption</code></td><td>Read current source and translated captions.</td></tr>
          <tr><td>GET</td><td><code>/runtime/transcript</code></td><td>Read rendered transcript and entry list.</td></tr>
        </tbody>
      </table>
    </section>
    <section class="card">
      <h2>Specification Preview</h2>
      <pre id="spec-output">Loading {escaped_spec_url} ...</pre>
    </section>
  </main>
  <script>
    fetch("{escaped_spec_url}")
      .then((response) => response.json())
      .then((spec) => {{
        document.getElementById("spec-output").textContent = JSON.stringify(spec, null, 2);
      }})
      .catch((error) => {{
        document.getElementById("spec-output").textContent = String(error);
      }});
  </script>
</body>
</html>
"""


class _SnapshotStore:
    def __init__(self):
        self._snapshot = {
            "runtime": {
                "status": "starting",
                "status_message": "",
                "is_recognizing": False,
                "recognition_ready": False,
                "stats": "",
                "compute_backend_label": "",
                "device_profile": "",
                "input_language": {"code": "en", "label": "English"},
                "output_language": {"code": "en", "label": "English"},
                "availability": {},
            },
            "caption": {
                "source_text": "",
                "translated_text": "",
                "source_preview_text": "",
                "translation_pending": False,
                "translation_pending_source": "",
                "current_translation_source": "",
                "current_translation_source_language": "",
                "current_translation_target": "",
            },
            "transcript": {
                "entry_count": 0,
                "entries": [],
                "rendered": "",
            },
        }
        self._lock = threading.RLock()

    def set(self, snapshot: dict):
        with self._lock:
            self._snapshot = deepcopy(snapshot or self._snapshot)

    def get(self) -> dict:
        with self._lock:
            return deepcopy(self._snapshot)


class _VoxScribeThreadingServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class VoxScribeOpenApiServer:
    """Serve a small local OpenAPI document and runtime snapshot."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        title: str = "VoxScribe Local API",
        version: str = "1.0.0",
        docs_enabled: bool = True,
        logger=None,
    ):
        self.host = str(host or "127.0.0.1").strip() or "127.0.0.1"
        self.port = int(port)
        self.title = title
        self.version = version
        self.docs_enabled = bool(docs_enabled)
        self.logger = logger
        self._snapshot_store = _SnapshotStore()
        self._httpd = None
        self._thread = None
        self._lock = threading.RLock()
        self.spec = build_openapi_spec(
            self.title, self.version, self.host, self.port, self.docs_enabled
        )

    @property
    def server_url(self) -> str:
        return f"http://{_public_host(self.host)}:{int(self.port)}"

    def publish_snapshot(self, snapshot: dict):
        self._snapshot_store.set(snapshot)

    def get_snapshot(self) -> dict:
        return self._snapshot_store.get()

    def start(self):
        with self._lock:
            if self._httpd is not None:
                return

            self._httpd = _VoxScribeThreadingServer(
                (self.host, self.port), self._make_handler()
            )
            self.port = int(self._httpd.server_address[1])
            self.spec = build_openapi_spec(
                self.title, self.version, self.host, self.port, self.docs_enabled
            )
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                name="voxscribe-openapi",
                daemon=True,
            )
            self._thread.start()
            if self.logger:
                self.logger.info(
                    f"Integration API started at {self.server_url} "
                    f"(docs={'on' if self.docs_enabled else 'off'})"
                )

    def stop(self, timeout: float = 2.0):
        with self._lock:
            if self._httpd is None:
                return
            httpd = self._httpd
            thread = self._thread
            self._httpd = None
            self._thread = None

        httpd.shutdown()
        httpd.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=max(0.0, timeout))
        if self.logger:
            self.logger.info("Integration API stopped")

    def _make_handler(self):
        api_server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "VoxScribeOpenAPI/1.0"

            def do_OPTIONS(self):
                self.send_response(HTTPStatus.NO_CONTENT)
                self._write_common_headers("text/plain; charset=utf-8")
                self.end_headers()

            def do_GET(self):
                path = urlsplit(self.path).path.rstrip("/") or "/"
                if path == "/health":
                    self._write_json(api_server._health_payload())
                    return
                if path == "/openapi.json":
                    self._write_json(api_server.spec)
                    return
                if path == "/runtime/snapshot":
                    self._write_json(api_server.get_snapshot())
                    return
                if path == "/runtime/state":
                    self._write_json(api_server.get_snapshot().get("runtime", {}))
                    return
                if path == "/runtime/caption":
                    self._write_json(api_server.get_snapshot().get("caption", {}))
                    return
                if path == "/runtime/transcript":
                    self._write_json(api_server.get_snapshot().get("transcript", {}))
                    return
                if path == "/docs" and api_server.docs_enabled:
                    self._write_html(
                        _docs_html(
                            api_server.title,
                            api_server.server_url,
                            f"{api_server.server_url}/openapi.json",
                        )
                    )
                    return
                self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

            def log_message(self, _format: str, *_args):
                return

            def _write_common_headers(self, content_type: str):
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def _write_json(self, payload: Any):
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self._write_common_headers("application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _write_html(self, payload: str):
                body = payload.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self._write_common_headers("text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _health_payload(self) -> dict:
        return {
            "status": "ok",
            "service": "voxscribe-openapi",
            "version": self.version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "server_url": self.server_url,
            "docs_enabled": self.docs_enabled,
        }
