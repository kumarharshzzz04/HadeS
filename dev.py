# dev.py - HadeS one-command dev launcher
# =============================================================================
# Start the whole stack with a single command (Anaconda Prompt, any folder):
#
#     python dev.py
#
#   1. checks Ollama (starts `ollama serve` if it isn't running)
#   2. starts server.py (FastAPI :8000) with THIS Python interpreter
#   3. if a frontend/ folder exists (the private UI, checked out locally), starts
#      `npm run dev` in it and opens the browser; without it the launcher stops at
#      the API and says so
#
# Ctrl+C stops everything this script started. server.py, the frontend and the
# manual two-window workflow are all untouched.
#
# Safety rules this launcher follows (learned the hard way):
#   * every helper process is spawned with CREATE_NO_WINDOW, so nothing flashes;
#   * it never kills processes it did not start - a running backend, a frontend or
#     another app's dev server on :8000/:5173-5179 is reused, not killed;
#   * launching it again while HadeS is already up just opens the browser again;
#   * `taskkill /F /IM node.exe` is gone - that took down every Node process on
#     the machine, not just this project's Vite.
#
# Options:
#   python dev.py                 normal boot (warns if a leftover server
#                                 is already holding a port)
#   python dev.py --fresh         kill leftover HadeS servers (:8000, :5173-5179)
#                                 before starting, so this is always a clean boot
# =============================================================================
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
HOST = "127.0.0.1"
BACKEND_PORT = int(os.environ.get("HADES_PORT", "8000"))  # env override so the desktop shell can relocate the API
# Vite lands on 5173 and shifts if it's busy; probe the usual neighborhood.
CANDIDATE_PORTS = tuple(range(5173, 5180))

sys.path.insert(0, str(ROOT))
import config  # same folder; single source of truth for the model name and Ollama host
import ollama_locator  # shared Ollama discovery/status — lifted out of this file (Task 1.1)
MODEL = config.OLLAMA_MODEL_NAME           # no fallback literal — a missing config is a hard error
OLLAMA_TAGS_URL = config.OLLAMA_TAGS_URL   # derives from config.OLLAMA_HOST


# -- console output -----------------------------------------------------------

def _ansi_ok() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # VT processing
    except Exception:
        return False


_ANSI = _ansi_ok()
RESET = "\033[0m" if _ANSI else ""
DIM = "\033[2m" if _ANSI else ""
BOLD = "\033[1m" if _ANSI else ""
C_DEV = "\033[38;5;180m" if _ANSI else ""
C_API = "\033[38;5;111m" if _ANSI else ""
C_WEB = "\033[38;5;150m" if _ANSI else ""
C_WARN = "\033[38;5;221m" if _ANSI else ""
C_ERR = "\033[38;5;203m" if _ANSI else ""

_print_lock = threading.Lock()
_T0 = time.time()


def emit(text: str = "") -> None:
    with _print_lock:
        print(text, flush=True)


def dev(text: str) -> None:
    # elapsed seconds on every launcher line: makes it obvious which step is slow
    emit(f"{C_DEV}[dev]{RESET} {text} {DIM}(+{time.time() - _T0:.1f}s){RESET}")


def warn(text: str) -> None:
    emit(f"{C_WARN}[dev]{RESET} {text}")


def fail(text: str) -> None:
    emit(f"{C_ERR}[dev]{RESET} {text}")


# -- small helpers ------------------------------------------------------------

def _get_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _backend_up() -> bool:
    """True when HadeS answers /api/health.

    Raw socket gate first: urllib against a closed loopback port costs ~5s on
    Windows (proxy/DNS fallback), and on a cold boot that port is always closed.
    The 3s JSON timeout stays: /api/health itself waits up to 2s on Ollama, so a
    shorter one would report a healthy backend as down while Ollama starts.
    """
    if not _http_alive(BACKEND_PORT, timeout=1.0):
        return False
    try:
        return bool(_get_json(f"http://{HOST}:{BACKEND_PORT}/api/health", 3.0).get("ok"))
    except Exception:
        return False


def _port_busy(port: int) -> bool:
    # Check both loopback families: Vite (Node) may bind only ::1.
    for family, addr in ((socket.AF_INET, (HOST, port)), (socket.AF_INET6, ("::1", port))):
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            if sock.connect_ex(addr) == 0:
                return True
    return False


def _alive_ports(ports=CANDIDATE_PORTS) -> list[int]:
    """Candidate ports that answer HTTP, probed in parallel.

    A serial sweep is the single biggest startup cost: a closed loopback port
    costs ~0.4-0.8s here (urllib adds proxy/DNS fallback), so seven of them in
    sequence added 4-12s per sweep, twice per boot.
    """
    ports = list(ports)
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        return [p for p, ok in zip(ports, pool.map(_http_alive, ports)) if ok]


def _busy_ports(ports=CANDIDATE_PORTS) -> set[int]:
    """Candidate ports with any listener (not necessarily HTTP), probed in parallel."""
    ports = list(ports)
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        return {p for p, busy in zip(ports, pool.map(_port_busy, ports)) if busy}


def _frontend_url() -> str | None:
    """URL of a HadeS frontend that is already serving, if any."""
    for port in _alive_ports():
        if not _http_alive(port):
            continue
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/", timeout=2.0) as resp:
                body = resp.read(4000).decode("utf-8", "replace")
        except Exception:
            continue
        if "HadeS" in body:
            return f"http://localhost:{port}"
    return None


def _http_alive(port: int, timeout: float = 0.5) -> bool:
    """True when something answers HTTP on *port*. Raw socket first: a refused
    connect returns instantly, HTTP only happens once the port is open."""
    request = b"GET / HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n"
    for host in ("localhost", HOST):
        try:
            with socket.create_connection((host, port), timeout=0.25) as sock:
                sock.sendall(request)
                sock.settimeout(timeout)
                return sock.recv(64).startswith(b"HTTP/")
        except Exception:
            continue
    return False


# Keeps every helper process invisible: a console spawned without a window can
# never flash on screen, whatever this launcher was started from.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run_quiet(cmd, **kw):
    """Run a console helper (netstat/tasklist/taskkill) with no window and no
    inherited output. Never raises."""
    kw.setdefault("stdout", subprocess.DEVNULL)
    kw.setdefault("stderr", subprocess.DEVNULL)
    kw.setdefault("check", False)
    if os.name == "nt":
        kw.setdefault("creationflags", _NO_WINDOW)
    try:
        return subprocess.run(cmd, **kw)
    except Exception:
        return None


def _popen_extra() -> dict:
    # New process group: Ctrl+C is handled by this script only, then it kills
    # the whole tree itself (keeps shutdown deterministic on Windows).
    # CREATE_NO_WINDOW also means a child can never pop up a console of its own.
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {}


def _vite_port(vite_url) -> int:
    """Port Vite actually bound (G21) — the cleanup fallback used to hardcode :5173,
    which left our own Vite alive when it had shifted to 5174+."""
    try:
        return int(str(vite_url).rsplit(":", 1)[1])
    except Exception:  # noqa: BLE001
        return CANDIDATE_PORTS[0]


def _kill_tree(proc, port=None) -> None:
    """Stop a child process and everything it spawned (npm -> node, etc.).

    Only ever touches the process this launcher started. The port fallback runs
    solely when the tracked child survived ``taskkill /F /T`` — it is never used
    to kill a server this run did not start (that killed reused backends and
    other apps' dev servers on :8000/:5173).
    """
    if proc is None:
        return
    if proc.poll() is None:
        if os.name == "nt":
            _run_quiet(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
            time.sleep(0.3)
            if proc.poll() is None and port is not None:
                _kill_owner_of_port(port)
        else:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass


def _kill_owner_of_port(port: int) -> None:
    """Last-resort kill for a port whose owner we can prove is ours. Anything
    else is reported and left running."""
    owner = _listener_pid(port)
    if owner is None:
        return
    if not _owner_is_ours(owner):
        warn(f"something else holds :{port} (PID {owner}) - leaving it alone")
        return
    _force_tree_kill(owner)


# -- fresh start ---------------------------------------------------------------


def _listener_pid(port: int) -> int | None:
    """Return the Windows PID that has *port* in LISTEN state, or None."""
    proc = _run_quiet(["netstat", "-ano"], stdout=subprocess.PIPE, text=True)
    out = proc.stdout if proc is not None else None
    if not out:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].endswith(f":{port}") and parts[4].isdigit():
            return int(parts[4])
    return None


def _cmdline(pid: int) -> str:
    """Command line of *pid*, or "" when it can't be read. Best effort: wmic is
    gone from newer Windows builds, so PowerShell is the primary source."""
    if os.name != "nt":
        return ""
    ps = (
        "(Get-CimInstance Win32_Process -Filter \"ProcessId="
        + str(pid)
        + "\").CommandLine"
    )
    proc = _run_quiet(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        stdout=subprocess.PIPE,
        text=True,
    )
    return ((proc.stdout if proc is not None else "") or "").strip()


def _owner_is_ours(pid: int) -> bool:
    """True only when *pid*'s command line proves it belongs to this project.

    Anything unprovable counts as not ours, so a busy port never gets another
    app's server killed.
    """
    cmd = _cmdline(pid).lower()
    if not cmd:
        return False
    marks = ("server.py", "dev.py", str(ROOT).lower(), str(FRONTEND_DIR).lower())
    return any(m and m in cmd for m in marks)


def _is_hades_child(pid: int) -> bool:
    """Backwards-compatible alias for the ownership check."""
    return _owner_is_ours(pid)


def _force_tree_kill(pid: int) -> None:
    """Kill *pid* and everything it spawned. It used to also run
    ``taskkill /F /IM node.exe``, which takes down every Node process on the
    machine (other agents, other projects) - never do that again."""
    _run_quiet(["taskkill", "/F", "/T", "/PID", str(pid)])


def _close_port_socket(port: int) -> None:
    """No-op placeholder: taskkill already released the listener, and a
    TIME_WAIT socket is short-lived (Uvicorn/Vite bind with SO_REUSEADDR)."""
    return


def _kill_leftovers() -> None:
    """Kill leftover HadeS servers (only ones provably from this project)."""
    killed = 0
    for port in (BACKEND_PORT, *CANDIDATE_PORTS):
        owner = _listener_pid(port)
        if owner is None:
            continue
        if _owner_is_ours(owner):
            _force_tree_kill(owner)
            killed += 1
        else:
            warn(f"port {port} is held by another app (PID {owner}) - leaving it alone")
    dev(f"cleared {killed} leftover HadeS process(es)")


# -- Ollama -------------------------------------------------------------------

def _ollama_catalog():
    return ollama_locator.tags(timeout=2.0)


def _ollama_exe() -> str | None:
    """Ollama binary — one implementation, shared with the app (ollama_locator.find_exe)."""
    return ollama_locator.find_exe()


def ensure_ollama() -> None:
    catalog = _ollama_catalog()
    if catalog is None:
        exe = _ollama_exe()
        if exe is None:
            fail("Ollama isn't installed or not on PATH - get it at https://ollama.com/download")
            fail(f"Answers will error until it runs: ollama serve  &&  ollama pull {MODEL}")
            return
        dev(f"Ollama not running - starting `ollama serve` ({exe})...")
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | _NO_WINDOW
            )
        else:
            extra["start_new_session"] = True
        try:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
        except Exception as e:  # noqa: BLE001
            fail(f"Could not start Ollama: {e}")
            return
        catalog = None
        deadline = time.time() + 30  # a cold Ollama load can take a while
        while time.time() < deadline:
            time.sleep(0.5)
            catalog = _ollama_catalog()
            if catalog is not None:
                break
        if catalog is None:
            fail("Ollama still isn't answering on :11434 - answers will error.")
            fail(f"Fix it in another window: ollama serve   (then)   ollama pull {MODEL}")
            return
        dev("Ollama answered - it was just slow to start")

    names = [m.get("name", "") for m in catalog.get("models", [])]
    if any(n == MODEL or n.startswith(MODEL) for n in names):
        dev(f"Ollama ready - {MODEL}")
    else:
        warn(f"Ollama is up, but model '{MODEL}' isn't pulled - run: ollama pull {MODEL}")


# -- child processes ----------------------------------------------------------

class _Pump(threading.Thread):
    """Copy a child's output line-by-line into our console, prefixed."""

    def __init__(self, proc, tag: str, color: str):
        super().__init__(daemon=True)
        self.proc = proc
        self.tag = tag
        self.color = color

    def run(self) -> None:
        try:
            for raw in self.proc.stdout:
                line = raw.rstrip("\r\n")
                emit(f"{self.color}[{self.tag}]{RESET} {line}")
        except Exception:  # noqa: BLE001
            pass


def start_backend():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["HADES_PORT"] = str(BACKEND_PORT)  # server.py binds what this launcher expects
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "server.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **_popen_extra(),
    )
    _Pump(proc, "api", C_API).start()
    return proc


def start_frontend():
    npm = shutil.which("npm")
    if npm is None:
        return None
    if os.name == "nt":
        # Through cmd.exe so the npm.cmd shim resolves reliably.
        cmd = ["cmd", "/d", "/s", "/c", "npm run dev"]
    else:
        cmd = [npm, "run", "dev"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **_popen_extra(),
    )
    _Pump(proc, "web", C_WEB).start()
    return proc


# -- main ---------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="dev.py", description="HadeS dev launcher (Ollama + backend, + frontend if present)")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Kill leftover HadeS servers (backend :8000, frontend :5173-5179) before starting, so this is a clean boot",
    )
    return parser.parse_args(argv)


def run() -> int:
    args = parse_args()
    emit(f"{BOLD}HadeS dev launcher{RESET} {DIM}- Ollama + backend (+ frontend when present){RESET}")
    if args.fresh:
        dev("--fresh: killing leftover servers before starting...")
        _kill_leftovers()
    dev(f"Project: {ROOT}")

    backend_proc = None
    web_proc = None
    vite_url = None
    reused_backend = False

    try:
        ensure_ollama()

        # Re-launch guard: double-clicking the .bat again used to start a second
        # backend + a second Vite (on the next port), and the two runs then killed
        # each other's processes on exit. If the stack is already up, just show it.
        backend_running = _backend_up()
        already_url = _frontend_url() if backend_running else None
        if backend_running and already_url:
            dev(f"HadeS is already running - backend :{BACKEND_PORT}, frontend {already_url}")
            dev("Reusing both; nothing new was started.")
            try:
                webbrowser.open(already_url)
            except Exception:  # noqa: BLE001
                pass
            return 0

        if _backend_up():
            reused_backend = True
            dev(f"Backend already running on :{BACKEND_PORT} - reusing it (Ctrl+C won't stop that one)")
        else:
            if _port_busy(BACKEND_PORT):
                warn(f"Port {BACKEND_PORT} is busy with something that isn't HadeS - starting anyway; check [api] if requests fail")
            dev(f"Starting backend  ->  http://localhost:{BACKEND_PORT}")
            backend_proc = start_backend()

            ready = False
            deadline = time.time() + 30
            while time.time() < deadline:
                if _backend_up():
                    ready = True
                    break
                if backend_proc.poll() is not None:
                    break
                time.sleep(0.4)
            if ready:
                dev("Backend is healthy")
            elif backend_proc.poll() is not None:
                fail("Backend exited during startup - see the [api] lines above")
            else:
                warn("Backend hasn't answered /api/health after 30s - continuing; check [api] if requests fail")

        # The React UI is not published with this repo. Without frontend/ the launcher
        # still brings up Ollama + the API and says where to point a client.
        have_frontend = FRONTEND_DIR.is_dir()
        vite_url = None
        if not have_frontend:
            warn("No frontend/ folder - this repo ships the engine and the API only")
            dev(f"API: http://localhost:{BACKEND_PORT}/api  (health check: /api/health)")

        if have_frontend and _frontend_url():
            vite_url = _frontend_url()
            dev(f"Frontend already serving at {vite_url} - reusing it")
        elif have_frontend:
            busy_before = _busy_ports()
            dev("Starting frontend ->  npm run dev")
            web_proc = start_frontend()
            if web_proc is None:
                fail("npm not found on PATH - install Node.js, then re-run")
                return 1

            # Vite hides its "Local: http://localhost:..." lines when its output
            # is piped, so detect the live URL by probing the ports that came up.
            deadline = time.time() + 40
            while time.time() < deadline:
                if web_proc.poll() is not None:
                    break
                for port in CANDIDATE_PORTS:
                    if port not in busy_before and _http_alive(port):
                        vite_url = f"http://localhost:{port}"
                        break
                if vite_url:
                    break
                time.sleep(0.3)

        if vite_url:
            dev(f"Opening {vite_url}")
            try:
                webbrowser.open(vite_url)
            except Exception:  # noqa: BLE001
                pass
        elif web_proc is not None and web_proc.poll() is not None:
            fail("Frontend exited during startup - see the [web] lines above")
        elif have_frontend:
            warn("Couldn't find the Vite URL - open the [web] URL above manually")
        else:
            dev("API only - browsers have nothing to open until the private UI is checked out")

        dev(f"{BOLD}Ready.{RESET} The model preloads in the background, so the first answer starts streaming in seconds. Ctrl+C stops everything.")

        backend_gone = False
        web_gone = False
        while True:
            time.sleep(0.3)
            if backend_proc is not None and backend_proc.poll() is not None and not backend_gone:
                backend_gone = True
                fail("Backend process exited - frontend is still up; Ctrl+C to stop")
            if web_proc is not None and web_proc.poll() is not None and not web_gone:
                web_gone = True
                fail("Frontend process exited - backend is still up; Ctrl+C to stop")
            backend_dead = backend_proc is None or backend_proc.poll() is not None
            web_dead = web_proc is None or web_proc.poll() is not None
            if backend_dead and web_dead:
                break
    except KeyboardInterrupt:
        pass
    finally:
        # only touch what this run started - a reused backend/frontend keeps running
        if backend_proc is not None or web_proc is not None:
            emit()
            dev("Stopping...")
            _kill_tree(web_proc, port=_vite_port(vite_url))
            _kill_tree(backend_proc, port=BACKEND_PORT)
            if reused_backend:
                dev(f"Left the backend on :{BACKEND_PORT} running (dev.py didn't start it)")
            dev("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
