# Decisions log — HadeS desktop app

Every non-obvious call made while building the installable app, with the options that
were on the table, the one chosen, and why. Numbers are measured on this machine unless
marked otherwise. Companion documents: `app plan/app-plan.md` (the execution plan) and
`TIMESTAMP_AUDIT.md` / `EVAL.md` (retrieval results).

---

## 1. Platform: Windows desktop app, not Android

| Option | Verdict |
|---|---|
| Android APK | **Rejected.** Ollama does not exist on Android, and llama3:8b (4.7 GB, 7–10 GB RAM) cannot run on a phone. An APK would have meant a second, weaker product. |
| Windows desktop app | **Chosen** — user's own clarification: "by app i mean like pc thing". |
| Both | Rejected as scope. The phone could later be a *client* of the PC brain, which is a different project. |

## 2. Desktop shell: the frozen exe opens the browser (no Tauri, no Electron)

| Option | Verdict |
|---|---|
| **Tauri** | Rejected for now. Needs the Rust toolchain (~1 GB download) and a compile step; adds nothing the payload needs, since the app is already a web UI. |
| **Electron** | Rejected for now. npm + Chromium (~200 MB) and electron-builder tooling, on top of a ~1 GB Python bundle. |
| **Frozen exe + default browser** | **Chosen.** PyInstaller output itself is the app: it picks a free port, serves the UI, opens the browser, and a console window is the quit affordance. Zero new toolchains. |
| Browser-only (manual `python server.py`) | Rejected: the user asked for an exe that installs. |

**Cost / ceiling:** no native window chrome, no tray icon, no single-click quit beyond
closing the console. Upgrade path stays open: the UI is same-origin HTTP, so wrapping the
same frozen sidecar in Tauri/Electron later is additive, not a rewrite.

## 3. Freezer: PyInstaller

| Option | Verdict |
|---|---|
| **PyInstaller 6.22.3** | **Chosen.** Supports Python 3.14 from 6.15.0 (this machine runs 3.14.7), and has maintained hooks for torch / transformers (pyinstaller-hooks-contrib 2026.8) — the two hardest packages here. |
| Nuitka | Rejected: slower builds, compiles rather than bundles, and the plan only wanted it as a fallback if PyInstaller refused the interpreter. It did not. |
| cx_Freeze | Rejected: weaker ecosystem support for torch/transformers. |

## 4. Bundle layout: onedir, not onefile

**Chosen: onedir.** Onefile re-extracts the whole payload into a temp dir at every
launch; at ~1 GB that is a slow start, double disk use, and leftover temp dirs when a
process is killed. onedir also lets the installer show real sizes and the user inspect
the folder. (Plan Task 2.1 and the PyInstaller research agree.)

## 5. Installer: Inno Setup 6.7.3, per-user

| Option | Verdict |
|---|---|
| **Inno Setup** | **Chosen.** Installed per-user with `winget --scope user` (no admin), and its `PrivilegesRequired=lowest` produces an installer that writes to `%LOCALAPPDATA%\Programs\HadeS` with Start-menu/desktop shortcuts, an uninstaller, and a licence page. |
| electron-builder NSIS | Rejected: drags Electron in for an installer only. |
| Standalone NSIS | Rejected: its own installer is machine-scope (needs admin), and the script would have to re-implement what Inno gives for free. |
| Zip + instructions | Rejected: the user explicitly wants an installer. |

**Publisher metadata** (file Properties → Details) carries `Kumar Harsh`, the app URL,
and the copyright. **It is not a code signature** — without an Authenticode certificate
Windows SmartScreen will still call the publisher unknown. Options were: buy a cert
(only real fix), self-sign (no trust gained, breaks on other machines), or ship unsigned
and document. **Chosen: unsigned + documented**, because no certificate exists and the
app is for local use.

## 6. First-run Ollama experience: in-app guide with a live flowchart

| Option | Verdict |
|---|---|
| **In-app guide that mirrors the steps** | **Chosen** (the user asked for "a flowchart or graph, easiest to understand, like how fitgirl repack works"). Three nodes — installed → running → model — tick themselves from `/api/setup/status` polling; below them is exactly one action card. |
| Bundle Ollama in the installer | Deferred (plan Batch 4). It is a separate install with its own licence and auto-updates; bundling risks version drift for no first-run gain. |
| README instructions only | Rejected: the first-run failure mode is a user staring at an error. |

Model download is streamed (`/api/setup/pull`, SSE with `completed`/`total`) so the user
sees a progress bar instead of a frozen screen, and the chosen model is remembered in
`%LOCALAPPDATA%\HadeS\settings.json`.

## 7. Where writable state lives: `%LOCALAPPDATA%\HadeS`

The install dir must be treated as read-only (Program Files installs, antivirus, updates).
Settings and future bookkeeping go to `config.state_dir()` — `%LOCALAPPDATA%\HadeS`,
overridable with `HADES_STATE_DIR`. Chat history stays in browser localStorage per dataset.

## 8. UI served by the API (same origin)

`server.py` mounts `frontend/dist` at `/` — so one process is the whole app. CORS and the
Vite proxy are now dev-only. `HADES_REQUIRE_UI=1` makes a missing build a hard error, used
by the packaged entry point so a UI-less package can never ship silently.

## 9. Curator LLM: off by default

Measured this session (`.freebuff/curator_bench.py`, llama3:8b warm, hades_demo):
mean **2.62 s** per retrieval with the curator on vs **1.14 s** off (+1.47 s), and the
main-lesson pick was identical on all three sampled questions. `TIMESTAMP_AUDIT.md`'s
152-run sweep has it a wash on hades_demo and *worse* on quantum (7/10 vs 8/10 first-MAIN).
**Decision: `LLM_CURATOR_ENABLED = False`**, switch kept for anyone who wants it back.

## 10. Grounding validation: computed but not shipped

The `validation` field was never rendered by any frontend version, and a low score sitting
next to a good answer is a liability in a demo. **Off by default** (`GROUNDING_VALIDATION
= False`); the function stays for audit tooling.

## 11. Default dataset: `hades_demo`

`og` is the estimated-timestamp 18 h set with no source video, so its citations cannot be
clicked. First run now opens the dataset that demonstrates the product correctly.

## 12. Frontend payload

Three.js moved to a lazy chunk (main JS 1,836,798 → 925,297 bytes) and the dead
`@fontsource-variable/geist` package was removed. The hero globe still renders; the
three.js chunk loads only when the landing hero mounts.

## 13. Python version: keep 3.14

The plan worried PyInstaller might not accept 3.14 and proposed freezing on 3.12.
Research settled it: PyInstaller has supported 3.14 since 6.15.0, and every dependency
here ships 3.14 wheels — so the app builds on the interpreter the project already runs on.

## 14. App window: a native WebView2 window, console retired

`console=True` used to make the console *the* app window ("close this window to quit"). It
worked and looked amateurish — the one thing worth fixing. The exe is now `console=False`
and the UI opens in a real window: pywebview over the WebView2 runtime that ships with
Windows 10/11, titled *HadeS — Teaching Assistant*, carrying the HadeS mark, with ordinary
minimize/maximize/close. Closing the window quits the app (uvicorn runs in a daemon thread,
so the process dies with the window).

Rejected: Tauri/Electron (§2) — a second toolchain and a rebundle of the same ~1 GB purely
for window chrome; a tkinter shell — chrome wrapped around something that still cannot
render the app; keeping the console — the status quo being fixed.

Guarantees kept: pywebview, pythonnet and WebView2 are all optional at runtime. If any is
missing the app logs the reason, prints the URL, opens the browser and behaves exactly as
before — degraded, never broken. (`private_mode=False` + a storage dir is deliberate:
pywebview's default private mode discards localStorage, and chat history lives there.)

Measured on the installed app: window class `WindowsForms10.Window…`, `showCmd=1`, restored
size 1600x1050 physical = 1280x840 logical at 125 % DPI, title-bar style `0x16CF0000`
(caption + min/max/close), and both window icons (32x32 and 16x16) pixel-identical to the
logo (mean |diff| 0.2 / 0.4 out of 255).

## 15. The frozen-torch DLL trap (two separate bugs, both measured)

The first frozen build **started, served the UI, answered `/api/health`, and then failed
every single question**: `Retrieval failed: [WinError 1114] ... Error loading
"...\_internal\torch\lib\c10.dll" or one of its dependencies.` A build that only gets
smoke-tested with `/api/health` looks perfectly healthy while being useless. Two distinct
causes, found by bisecting the bundle instead of rebuilding blindly:

| # | Cause | Fix |
|---|---|---|
| 1 | A wheel in the dependency tree ships its own **old `msvcp140.dll`**; PyInstaller hoists it into `_internal`, which Windows searches *before* `AddDllDirectory` paths — so the stale CRT loads first and `c10.dll`'s DllMain returns FALSE. Proven by renaming the bundled `msvcp140.dll` out of the way: retrieval passed immediately. | `packaging/refresh_crt.py` copies the whole CRT set (`msvcp140`, `msvcp140_1`, `vcruntime140`, `vcruntime140_1`, `concrt140`, `vcomp140`) from `System32` into the bundle in one consistent version. Chosen over deleting them (which would leave the app dependent on the target machine having the redist) and over a runtime-hook PATH fix (`AddDllDirectory` cannot outrank the app directory). |
| 2 | `torch.distributed` was in the spec's `excludes` to save space — but `torch/__init__.py` imports it unconditionally, so **every** retrieval died with `No module named 'torch.distributed'`. | Removed from `excludes`; the spec now carries the measurement in a comment so nobody re-adds it. |

Also kept from the first build: `packaging/rthook_torch_dlls.py` puts `torch/lib` on the
search path (needed for the CUDA-less CPU wheels to find `libiomp5md.dll`).

**Lesson recorded for the installer:** the acceptance test for a package is a real
question with a real timestamp, not a 200 from `/api/health`.

## 16. Installer size budget

The bundle is **943 MB on disk** (down from 2458 MB on the first build) after excluding
`polars` (168 MB), `cv2` (112 MB), `numba`+`llvmlite` (102 MB), `pyarrow`, whisper/ingest
tooling and the dev/notebook stack. That is inside the plan's <1.5 GB budget with room to
spare, and the installer's own lzma2 compression brings the download well below it.

## 17. Measured, end to end (Task 3.5)

| Step | Measured |
|---|---|
| PyInstaller freeze (onedir) | ~8.6 min wall clock, 943 MB dist |
| Inno compile (`lzma2/max`, solid) | 347 s → **`HadeS-Setup.exe`, 374,410,006 bytes (357 MB)** |
| Silent per-user install | ~2 min, no UAC prompt, `%LOCALAPPDATA%\Programs\HadeS` + uninstaller registered |
| Installed-app launch | binds a free loopback port, prints `HADES_PORT=54830`, browser opens on it |
| `/api/health` | `{"ok":true,"ollama":true,"model":"llama3:8b"}` |
| `/api/setup/status` | Ollama 0.40.4 found at its per-user path, `model_present: true`, `port_conflict: false` |
| `/api/setup/select` | writes `%LOCALAPPDATA%\HadeS\settings.json` (state dir verified) |
| Real question, installed app | *"What is a Hadamard gate?"* on `quantum` → **257 tokens in 14 s**, `quantum — 00:32:28 – 00:34:55 (3 chunks)` |
| Second profile, installed app | *"What are functions?"* on `hades_demo` → 220 tokens in 12 s |
| Bundled data | `og` 1328 / `hades_demo` 611 / `quantum` 138 chunks, all `ready` |

**One environment trap worth remembering** (cost an hour): in Git Bash, `/VERYSILENT` is
rewritten into a Windows path, so the installer opened its GUI wizard invisibly and looked
*hung* for the whole timeout. Pass `//VERYSILENT`. The installer was never broken — the
invocation was. Diagnosed by reading the stuck process's `MainWindowTitle`
(`"Select Setup Install Mode"`) instead of guessing.

**Second pass — native window + logo (§14, §18, §19), same machine:**

| Step | Measured |
|---|---|
| Icon build (`make_icon.py`) | 512 px render → `hades.ico` with 16/24/32/48/64/128/256 frames, 43,497 bytes |
| PyInstaller freeze (with pywebview/pythonnet) | 455 s → **954 MB** dist (was 943 MB: +11 MB for the window backend) |
| `verify_artifacts.py` | 8/8 checks pass: GUI subsystem (no console), exe icon = logo (mean |diff| 0.1/255), setup icon = logo, WebView2 assemblies + `ClrLoader.dll` + `Python.Runtime.dll` + `hades.ico` all bundled |
| Inno compile | 276.9 s → **`HadeS-Setup.exe`, 376,034,988 bytes (359 MB)** |
| Silent per-user install | succeeded, no UAC; log ends `Installation process succeeded.` |
| Installed app | opens its own window on a free port (`HADES_PORT=61994` in the log), `showCmd=1`, 1600x1050 physical = 1280x840 logical @125 % DPI, taskbar icon pixel-matches the logo |
| Real question, installed app | *"What is a Hadamard gate?"* → 255 words in 18.7 s, `quantum — 00:32:28 – 00:34:55 (3 chunks)` |
| Setup guide, installed app | header **Setup** button opens *Set up HadeS*; all three nodes ticked, "Everything is ready — Ollama v0.40.4 · model llama3:8b" |
| Window storage | `%LOCALAPPDATA%\HadeS\webview\EBWebView` — localStorage (chat history) persists across runs because `private_mode=False` |

**Still open:** the build is unsigned and the exe carries no version resource (Explorer's
Details tab is blank; the installer's is not). Both need a rebuild to change.

## 18. Icon: one logo, rendered once, used everywhere

`frontend/public/favicon.svg` stays the single source. `packaging/make_icon.py` rasterises
it at 512 px through Edge's headless renderer (Pillow cannot read SVG) and writes
`packaging/assets/hades.ico` with 16/24/32/48/64/128/256 frames, plus a 512 px PNG to look
at. That one file feeds PyInstaller's `icon=` (exe, so taskbar/Explorer/alt-tab), the native
window (`webview.start(icon=…)`) and Inno's `SetupIconFile` + `UninstallDisplayIcon`.

Rejected: hand-drawing the hexagon in Pillow — a second copy of the mark that silently goes
stale; a committed binary `.ico` or an online converter — unreviewable and unreproducible
when the SVG is three lines of geometry.

Checked, not assumed: the render has transparent corners, an opaque mark (27.7 % of pixels
light-plate) and all seven frames present; both window icon sizes match the source PNG.

## 19. The setup guide is re-openable

§6's guide appeared **only** when a step was missing — right for a first run, useless the
moment someone asks "where is the Ollama setup?" afterwards. It is now reachable two ways:
a `Setup` button in the app header, and `?setup=1` in the URL. First-run behaviour is
unchanged (the guide still opens by itself when `/api/setup/status` reports a missing step,
and still only then). Verified through the built UI: the button opens "Set up HadeS" with all
three nodes ticked — *Ollama installed · Ollama running · Model llama3:8b* — and
"Everything is ready. Ollama v0.40.4 · model llama3:8b".

---

## Still open (deliberately)

- **Code signing** — needs a certificate; until then SmartScreen warns on the installer. (§5)
- **Bundling Ollama (plan Batch 4)** — only if first-run testing shows people still fail
  at the Ollama step.
- **Clean-machine test** — every number here comes from this one Windows 11 box; a friend's
  PC is still the real proof.
