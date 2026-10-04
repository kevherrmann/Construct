#!/usr/bin/env python3
"""
CONSTRUCT starten: Server hoch, dann ein eigenes Fenster im Browser.

Startet den FastAPI-Server (app.py) in einem Hintergrund-Thread auf 127.0.0.1
und öffnet die Oberfläche als App-Fenster eines Chromium-Browsers (Chrome,
Edge, Brave, Chromium, Vivaldi, Opera): eigenes Fenster ohne Tabs und
Adressleiste, eigener Eintrag in der Taskleiste. Der Standardbrowser hat
Vorrang, sofern er einer davon ist; sonst nimmt CONSTRUCT irgendeinen
installierten. Gibt es keinen, öffnet sich ein normaler Tab im Standardbrowser.

Früher war das ein eigenes WebKitGTK-Fenster (pywebview). Das war unter
Wayland + NVIDIA nur im Software-Rendering stabil und entsprechend zäh; im
Browser läuft dieselbe Oberfläche mit Grafikkarte flüssig.

Aufruf normalerweise über ./start.sh (kümmert sich um venv + Abhängigkeiten):

    ./start.sh              Server + Fenster
    ./start.sh --web        nur Server, kein Fenster (Autostart/Server)

Läuft auf dem Port schon eine Instanz, wird KEIN zweiter Server gestartet —
es öffnet sich nur das Fenster. Das Fenster zu schließen beendet den Server
nicht: der Telegram-Bot und geplante Aufgaben laufen weiter.

    CONSTRUCT_BROWSER=/pfad/zum/browser   bestimmten Chromium-Browser nehmen
    CONSTRUCT_FENSTER=0                   immer nur einen Tab öffnen
"""
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)                    # app.py legt Pfade relativ zu sich an
sys.path.insert(0, str(BASE_DIR))
sys.stdout.reconfigure(line_buffering=True)   # Meldungen sofort im journal/Log

HOST = os.environ.get("MATRIX_HOST", "127.0.0.1")
PORT = int(os.environ.get("MATRIX_PORT", "8765"))
URL = f"http://{HOST}:{PORT}/"

def port_busy() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def server_info() -> dict:
    """Was der Server auf dem Port über sich sagt ({} = keiner/erreichbar)."""
    try:
        with urllib.request.urlopen(URL + "api/version", timeout=2) as r:
            import json
            return json.load(r) if r.status == 200 else {}
    except urllib.error.HTTPError as e:
        return {"auth": True} if e.code == 401 else {}
    except Exception:
        return {}


def server_alive() -> bool:
    """Antwortet auf dem Port wirklich CONSTRUCT?"""
    return bool(server_info())


def code_version() -> str:
    """Version aus server/core.py auf der PLATTE — ohne sie zu importieren.

    Der Import würde Abhängigkeiten laden und dauert; hier reicht die eine
    Zeile. Findet sie sich nicht, wird eben nicht verglichen.
    """
    try:
        for line in (Path(__file__).parent / "server" / "core.py").read_text(
                encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VERSION"):
                return line.split("=", 1)[1].strip().strip('"\'')
    except Exception:
        pass
    return ""


def code_stamp() -> str:
    """Wie neu ist der Code auf der Platte? Gegenstück zu app.code_stamp().

    Bewusst hier nochmal ausgeschrieben statt aus app.py importiert: der Import
    zieht FastAPI und alles Weitere nach und kostet Sekunden — für eine Frage,
    die vor dem Start beantwortet sein muss.
    """
    try:
        base = Path(__file__).parent
        quellen = (list(base.glob("*.py")) + list((base / "server").rglob("*.py"))
                   + list((base / "static").rglob("*.[hjc]*")))
        return str(int(max(f.stat().st_mtime for f in quellen if f.exists())))
    except Exception:
        return ""


def stop_stale(info: dict) -> bool:
    """Beendet einen laufenden Server, der ÄLTER ist als der Code hier.

    Das ist kein Randfall: läuft noch eine Instanz von vorhin, hängt sich das
    Fenster wortlos an sie. Der Browser lädt dann die NEUE index.html von der
    Platte, der Server bringt aber die ALTEN Routen mit — und die Oberfläche
    ist halb kaputt, ohne dass irgendwo ein Fehler steht. Genau das ist
    passiert, und es hat wie drei verschiedene Bugs ausgesehen.

    Beendet wird nur, was aus DIESEM Ordner stammt — fremde Installationen
    auf demselben Port bleiben unangetastet.
    """
    running, mine = info.get("version", ""), code_version()
    # Zwei Merkmale, weil eines allein nicht reicht: die Version wandert nur bei
    # groesseren Spruengen, der Zeitstempel bei jeder Aenderung. Fehlt der
    # Zeitstempel in der Antwort, ist die laufende Instanz so alt, dass sie ihn
    # noch gar nicht kennt — auch das ist ein Grund, sie zu ersetzen.
    alt_version = bool(running and mine and running != mine)
    lauf_code, platte_code = info.get("code", ""), code_stamp()
    alt_code = bool(platte_code) and lauf_code != platte_code
    if not alt_version and not alt_code:
        return False
    if info.get("dir") and Path(info["dir"]).resolve() != Path(__file__).parent.resolve():
        print(f"⚠  Auf {URL} läuft CONSTRUCT {running} aus einem ANDEREN Ordner "
              f"({info['dir']}) — ich fasse es nicht an.")
        return False
    if alt_version:
        print(f"» Auf {URL} läuft noch die ältere Version {running} (hier: {mine}).")
    else:
        print(f"» Auf {URL} läuft CONSTRUCT mit älterem Code "
              f"(Stand {lauf_code or 'unbekannt'}, hier: {platte_code}).")
    print("  Sie wird beendet — sonst passt die Oberfläche nicht zum Server.")
    pid = _pid_on_port(PORT)
    if not pid:
        print("⚠  Konnte nicht feststellen, welcher Prozess auf dem Port sitzt.")
        print("     Von Hand beenden, dann neu starten.")
        return False
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"⚠  Beenden fehlgeschlagen: {e}")
        return False
    for _ in range(40):
        if not port_busy():
            return True
        time.sleep(0.25)
    print(f"⚠  Prozess {pid} reagiert nicht. Von Hand:  kill -9 {pid}")
    return False


def _pid_on_port(port: int):
    """PID des Prozesses, der auf dem Port lauscht — oder None.

    Gezielt über den Port, NICHT über Prozessnamen: ein Muster wie
    "desktop.py" trifft auch das eigene Fenster und jede zweite Instanz auf
    einem anderen Port. Beim ersten Versuch hat genau das die gesunde
    Instanz mit abgeräumt.
    """
    import subprocess
    for cmd in (["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                ["ss", "-ltnpH", f"sport = :{port}"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except Exception:
            continue
        if not out.strip():
            continue
        if cmd[0] == "lsof":
            for tok in out.split():
                if tok.isdigit() and int(tok) != os.getpid():
                    return int(tok)
        else:
            m = re.search(r"pid=(\d+)", out)
            if m and int(m.group(1)) != os.getpid():
                return int(m.group(1))
    return None


_SERVER = None
_THREAD = None


def serve() -> None:
    import uvicorn
    from app import app
    from server import core
    global _SERVER
    _SERVER = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    # ⏻ in der Oberfläche: sauber herunterfahren (app.lifespan räumt auf)
    core.beim_beenden(lambda: setattr(_SERVER, "should_exit", True))
    _SERVER.run()


def start_server() -> bool:
    """True, wenn wir den Server selbst gestartet haben."""
    if port_busy():
        info = server_info()
        if not info:
            sys.exit(
                f"!! Port {PORT} ist belegt, aber das ist nicht CONSTRUCT.\n"
                f"   Anderen Port nehmen:  MATRIX_PORT=8766 ./start.sh"
            )
        if not stop_stale(info):
            print(f"» CONSTRUCT läuft schon auf {URL} — hänge mich dran.")
            return False
        # Alte Instanz ist weg, Port frei — unten wird neu gestartet.

    global _THREAD
    _THREAD = threading.Thread(target=serve, daemon=True)
    _THREAD.start()
    for _ in range(150):              # bis 30 s — der erste Start liest Skills ein
        if server_alive():
            print(f"🟢 CONSTRUCT läuft auf {URL}")
            return True
        time.sleep(0.2)
    sys.exit("!! Server ist nicht hochgekommen. Details:  ./start.sh --web")


# ---------------------------------------------------------------------------
# Fenster: App-Modus eines Chromium-Browsers

# Woran ein Chromium-Browser zu erkennen ist (Name der .desktop-Datei, des
# Programms oder der Windows-ProgId).
CHROMIUM = re.compile(r"chrom|brave|edge|vivaldi|opera|thorium|yandex", re.I)

# Linux: .desktop-IDs in der Reihenfolge, in der sie ohne passenden
# Standardbrowser probiert werden.
LINUX_IDS = [
    "google-chrome", "com.google.Chrome", "chromium", "chromium-browser",
    "org.chromium.Chromium", "brave-browser", "com.brave.Browser",
    "microsoft-edge", "com.microsoft.Edge", "vivaldi-stable",
    "com.vivaldi.Vivaldi", "opera", "com.opera.Opera",
]
LINUX_PROGRAMME = [
    "google-chrome-stable", "google-chrome", "chromium", "chromium-browser",
    "brave-browser", "microsoft-edge-stable", "microsoft-edge", "vivaldi-stable",
    "vivaldi", "opera",
]


def _desktop_dirs() -> list[Path]:
    home = Path.home()
    dirs = [Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))]
    dirs += [Path(d) for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if d]
    dirs += [home / ".local/share/flatpak/exports/share", Path("/var/lib/flatpak/exports/share")]
    return [d / "applications" for d in dirs]


def exec_aus_desktop(text: str) -> list[str]:
    """Befehl aus dem Exec= einer .desktop-Datei (Abschnitt [Desktop Entry]),
    ohne Platzhalter wie %U und die @@-Marken von Flatpak."""
    abschnitt = ""
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if zeile.startswith("["):
            abschnitt = zeile
        elif abschnitt == "[Desktop Entry]" and zeile.startswith("Exec="):
            teile = shlex.split(zeile[5:])
            return [t for t in teile if not t.startswith("%") and not t.startswith("@@")]
    return []


def _linux_desktop(desktop_id: str) -> list[str]:
    name = desktop_id if desktop_id.endswith(".desktop") else desktop_id + ".desktop"
    for d in _desktop_dirs():
        f = d / name
        if f.is_file():
            try:
                cmd = exec_aus_desktop(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if cmd and (shutil.which(cmd[0]) or Path(cmd[0]).exists()):
                return cmd
    return []


def _linux_browser() -> list[str]:
    try:
        std = subprocess.run(["xdg-settings", "get", "default-web-browser"],
                             capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        std = ""
    if std and CHROMIUM.search(std):
        cmd = _linux_desktop(std)
        if cmd:
            return cmd
    for prog in LINUX_PROGRAMME:
        if shutil.which(prog):
            return [prog]
    for did in LINUX_IDS:
        cmd = _linux_desktop(did)
        if cmd:
            return cmd
    return []


def _windows_browser() -> list[str]:
    env = os.environ
    orte = {
        "chrome": [r"Google\Chrome\Application\chrome.exe"],
        "edge": [r"Microsoft\Edge\Application\msedge.exe"],
        "brave": [r"BraveSoftware\Brave-Browser\Application\brave.exe"],
        "vivaldi": [r"Vivaldi\Application\vivaldi.exe"],
    }
    wurzeln = [env.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if env.get(k)]

    def finde(name: str) -> list[str]:
        for w in wurzeln:
            for rel in orte[name]:
                p = Path(w) / rel
                if p.is_file():
                    return [str(p)]
        return []

    reihe = ["chrome", "brave", "vivaldi", "edge"]   # Edge zuletzt: ist immer da
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell"
                            r"\Associations\UrlAssociations\https\UserChoice") as k:
            progid = str(winreg.QueryValueEx(k, "ProgId")[0]).lower()
        for name in list(reihe):
            if name in progid or (name == "edge" and "msedge" in progid):
                reihe.remove(name)
                reihe.insert(0, name)
    except Exception:
        pass
    for name in reihe:
        cmd = finde(name)
        if cmd:
            return cmd
    return []


def _mac_browser() -> list[str]:
    apps = ["Google Chrome", "Brave Browser", "Microsoft Edge", "Chromium", "Vivaldi", "Opera"]
    for basis in (Path("/Applications"), Path.home() / "Applications"):
        for app in apps:
            p = basis / f"{app}.app" / "Contents" / "MacOS" / app
            if p.is_file():
                return [str(p)]
    return []


def chromium_browser() -> list[str]:
    """Befehl eines Chromium-Browsers für das App-Fenster, [] = keiner da."""
    eigen = os.environ.get("CONSTRUCT_BROWSER", "").strip()
    if eigen:
        return shlex.split(eigen)
    if sys.platform.startswith("win"):
        return _windows_browser()
    if sys.platform == "darwin":
        return _mac_browser()
    return _linux_browser()


def _profil(cmd: list[str]) -> Path:
    """Eigenes Browser-Profil für das Fenster.

    Eigenes Profil heißt eigener Browser-Prozess: das Fenster bekommt so seine
    eigene Fensterklasse (Taskleiste zeigt CONSTRUCT, nicht den Browser) und
    hängt sich nicht in ein offenes Browserfenster mit 30 Tabs. Ein Flatpak-
    Browser darf meist nicht in den Projektordner schreiben — dort liegt das
    Profil in seinem eigenen Datenordner.
    """
    if cmd and "flatpak" in Path(cmd[0]).name:
        app_id = next((t for t in reversed(cmd) if re.fullmatch(r"[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}", t)), "")
        if app_id:
            return Path.home() / ".var" / "app" / app_id / "data" / "construct-fenster"
    return BASE_DIR / ".fenster"


def fenster_befehl(cmd: list[str], url: str) -> list[str]:
    return cmd + [
        f"--app={url}",
        f"--user-data-dir={_profil(cmd)}",
        "--class=construct",          # Fensterklasse = StartupWMClass der .desktop-Datei
        "--window-size=1440,920",
        "--no-first-run",
        "--no-default-browser-check",
    ]


def open_window() -> None:
    """Oberfläche öffnen: App-Fenster, sonst Tab im Standardbrowser."""
    url = URL + "?fenster=1"
    cmd = [] if os.environ.get("CONSTRUCT_FENSTER") == "0" else chromium_browser()
    if cmd:
        try:
            subprocess.Popen(fenster_befehl(cmd, url), start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            print(f"» Fenster geöffnet ({Path(cmd[0]).name}).")
            return
        except OSError as e:
            print(f"⚠  {cmd[0]} ließ sich nicht starten ({e}) — öffne einen Tab.")
    elif os.environ.get("CONSTRUCT_FENSTER") == "0":
        print("» Fenster abgeschaltet (CONSTRUCT_FENSTER=0) — öffne einen Tab.")
    else:
        print("» Kein Chromium-Browser gefunden (Chrome, Edge, Brave …) — öffne einen Tab.")
    webbrowser.open(URL)


def idle() -> None:
    """Warten, solange der Server läuft — bis ⏻ in der Oberfläche oder Strg+C."""
    try:
        while _THREAD is not None and _THREAD.is_alive():
            _THREAD.join(1)
    except KeyboardInterrupt:
        if _SERVER is not None:
            _SERVER.should_exit = True
        if _THREAD is not None:
            _THREAD.join(15)
    print("» CONSTRUCT beendet.")


def main() -> None:
    web_only = "--web" in sys.argv
    started = start_server()

    if not web_only:
        open_window()
    if started:
        # Der Server läuft in diesem Prozess: am Leben halten, auch wenn das
        # Fenster zugeht (Telegram-Bot, geplante Aufgaben). Beenden: Strg+C
        # bzw. Abmelden; ein erneuter Start öffnet nur das Fenster.
        idle()
    elif web_only:
        print("» Es lief schon eine Instanz — nichts zu tun.")


if __name__ == "__main__":
    main()
