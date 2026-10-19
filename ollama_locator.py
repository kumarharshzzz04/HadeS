"""Ollama discovery, status, start and pull — shared by server.py and dev.py.

Lifted out of dev.py (plan Task 1.1) so the app and the launcher cannot drift.
Loopback HTTP + filesystem checks only; nothing here needs a shell.
"""
import json
import os
import shutil
import subprocess
import time

import requests

import config

# Documented install locations — used when PATH is stale (shortcut, double-clicked exe).
CANDIDATES = (
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
    r"C:\Program Files\Ollama\ollama.exe",
)


def find_exe() -> str | None:
    """$HADES_OLLAMA_EXE, then PATH, then the documented install dirs. None = not installed."""
    env = os.environ.get("HADES_OLLAMA_EXE")
    if env:
        return env if os.path.isfile(env) else None
    exe = shutil.which("ollama")
    if exe:
        return exe
    for cand in CANDIDATES:
        if cand and os.path.isfile(cand):
            return cand
    return None


def tags(timeout: float = 2.0) -> dict | None:
    """GET /api/tags. None = nothing answering, or it did not answer with JSON."""
    try:
        r = requests.get(config.OLLAMA_TAGS_URL, timeout=timeout)
        return r.json() if r.ok else None
    except Exception:  # noqa: BLE001
        return None


def port_conflict() -> bool:
    """Something IS answering on the Ollama port but isn't Ollama (plan review focus #1).

    `tags()` returning None means "not Ollama". This separates "down" from "occupied by
    a foreign service" so the guide can say which one it is."""
    try:
        r = requests.get(config.OLLAMA_TAGS_URL, timeout=2)
    except Exception:  # noqa: BLE001
        return False
    if not r.ok:
        return True
    try:
        body = r.json()
    except ValueError:
        return True
    return "version" not in body and "models" not in body


def model_names(catalog: dict | None) -> list[str]:
    return [m.get("name", "") for m in (catalog or {}).get("models", [])]


def has_model(name: str, catalog: dict | None) -> bool:
    """Exact tag match (plan review focus #3): a `:latest` tag must NOT count as the
    configured `:8b` tag just because the model name is a prefix."""
    return any(n == name for n in model_names(catalog))


def version(timeout: float = 2.0) -> str | None:
    """GET /api/version — `/api/tags` does not carry it."""
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/version", timeout=timeout)
        return (r.json() or {}).get("version") if r.ok else None
    except Exception:  # noqa: BLE001
        return None


def status() -> dict:
    catalog = tags()
    exe = find_exe()
    return {
        "ollama_running": catalog is not None,
        "ollama_installed": exe is not None,
        "exe": exe,
        "version": version() if catalog is not None else None,
        "model_present": has_model(config.OLLAMA_MODEL_NAME, catalog),
        "model_name": config.OLLAMA_MODEL_NAME,
        "models": model_names(catalog),
        "port_conflict": False if catalog is not None else port_conflict(),
    }


def start(timeout: float = 30.0) -> dict:
    """Spawn `ollama serve` detached when it isn't already running. Idempotent."""
    if tags() is not None:
        return {"started": False, "error": None, "already_running": True}
    exe = find_exe()
    if exe is None:
        return {"started": False, "error": "Ollama is not installed", "already_running": False}
    kwargs = {}
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — outlives this app, no console window.
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception as e:  # noqa: BLE001
        return {"started": False, "error": str(e), "already_running": False}

    deadline = time.time() + timeout
    while time.time() < deadline:
        if tags() is not None:
            return {"started": True, "error": None, "already_running": False}
        time.sleep(0.5)
    return {"started": False, "error": f"Ollama did not answer within {int(timeout)}s",
            "already_running": False}


def pull_events(model: str):
    """Stream Ollama's NDJSON pull progress as plain dicts (plan Task 1.2).

    Never buffers the whole body; upstream errors (bad model name, disk full) are
    surfaced as an `error` event instead of being swallowed."""
    url = f"{config.OLLAMA_HOST}/api/pull"
    try:
        r = requests.post(url, json={"model": model, "stream": True},
                          stream=True, timeout=(5, 120))
    except Exception as e:  # noqa: BLE001
        yield {"error": f"could not reach Ollama: {e}"}
        return
    with r:
        if not r.ok:
            yield {"error": f"Ollama replied {r.status_code} to the pull request"}
            return
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                evt = json.loads(line)
            except ValueError:
                continue
            if evt.get("error"):
                yield {"error": str(evt["error"])}
                return
            yield {
                "status": evt.get("status", ""),
                "completed": evt.get("completed"),
                "total": evt.get("total"),
            }
            if evt.get("status") == "success":
                yield {"done": True}
                return
    yield {"done": True}
