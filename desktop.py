#!/usr/bin/env python3
"""
CONSTRUCT als eigenes Desktop-Fenster — ohne Browser-Tab, ohne Docker.

Startet den FastAPI-Server (app.py) in einem Hintergrund-Thread auf 127.0.0.1
und legt ein natives Fenster darüber (pywebview -> WebKitGTK auf Linux,
WKWebView auf dem Mac). Damit taucht Cody als eigene App in der Taskleiste auf
statt als 27. Browser-Tab.

Aufruf normalerweise über ./start.sh (kümmert sich um venv + Abhängigkeiten):

    ./start.sh              Fenster
    ./start.sh --web        nur Server, kein Fenster (Autostart/Server)

Läuft auf Port 8765 schon eine Instanz, wird
KEIN zweiter Server gestartet — das Fenster hängt sich an die laufende an.
"""
import os
import re
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
ICON = BASE_DIR / "static" / "icon-256.png"

def _needs_software_render() -> bool:
    """Muss WebKit auf der CPU rastern statt auf der GPU?

    NVIDIAs GBM-Implementierung und WebKits DMA-BUF-Renderer vertragen sich
    unter Wayland nicht: "Failed to create GBM buffer of size ..." und das
    Fenster bleibt komplett leer. Betrifft nur die Kombination Wayland +
    NVIDIA-Treiber; überall sonst (Intel/AMD, X11, macOS) bleibt die GPU an.

    Erzwingen lässt sich beides:  CODY_GPU=1  /  CODY_SOFTWARE_RENDER=1
    """
    if os.environ.get("CODY_GPU") == "1":
        return False
    if os.environ.get("CODY_SOFTWARE_RENDER") == "1":
        return True
    return (sys.platform.startswith("linux")
            and os.environ.get("XDG_SESSION_TYPE") == "wayland"
            and Path("/proc/driver/nvidia/version").exists())


# Muss VOR dem GTK-Import stehen, darum hier oben.
SOFTWARE_RENDER = _needs_software_render()
if SOFTWARE_RENDER:
    # NUR den DMA-BUF-Renderer abschalten. WEBKIT_DISABLE_COMPOSITING_MODE
    # gehört hier ausdrücklich NICHT hin: ohne Compositing legt WebKitGTK die
    # Klickflächen von `position: fixed`-Elementen woanders hin, als es sie
    # zeichnet — die Buttons sind dann sichtbar, aber nicht treffbar.
    os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"


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
    """Version aus app.py auf der PLATTE — ohne app.py zu importieren.

    Der Import würde Abhängigkeiten laden und dauert; hier reicht die eine
    Zeile. Findet sie sich nicht, wird eben nicht verglichen.
    """
    try:
        for line in (Path(__file__).parent / "app.py").read_text(
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
        quellen = list(base.glob("*.py")) + list((base / "static").rglob("*.[hjc]*"))
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


def serve() -> None:
    import uvicorn
    from app import app
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def start_server() -> bool:
    """True, wenn wir den Server selbst gestartet haben."""
    if port_busy():
        info = server_info()
        if info and stop_stale(info):
            info = {}                 # Port ist frei, unten wird neu gestartet
        elif info:
            print(f"» CONSTRUCT läuft schon auf {URL} — hänge mich dran.")
            return False
        sys.exit(
            f"!! Port {PORT} ist belegt, aber das ist nicht CONSTRUCT.\n"
            f"   Anderen Port nehmen:  MATRIX_PORT=8766 ./start.sh"
        )

    threading.Thread(target=serve, daemon=True).start()
    for _ in range(150):              # bis 30 s — der erste Start liest Skills ein
        if server_alive():
            print(f"🟢 CONSTRUCT läuft auf {URL}")
            return True
        time.sleep(0.2)
    sys.exit("!! Server ist nicht hochgekommen. Details:  ./start.sh --web")


def browser_fallback(grund: str) -> None:
    import webbrowser
    print(
        f"» Fenster-Modus geht nicht ({grund}) — öffne stattdessen den Browser.\n"
        f"  Was genau fehlt, sagt dir:  ./check-desktop.sh\n"
        f"  Der Chat funktioniert davon unabhängig."
    )
    webbrowser.open(URL)
    idle()


class _Bridge:
    """Wird dem Frontend als window.pywebview.api bereitgestellt.

    Die WebView hat keine Adress- und keine Zurueck-Leiste. Klickt man darin
    einen externen Link, navigiert das GANZE Fenster dorthin und es gibt keinen
    Weg zurueck zur App. Externe Links muessen deshalb an den Systembrowser.
    """

    def open_url(self, url: str) -> bool:
        # Nur echte Web-Links weiterreichen: file://, javascript: usw. haetten
        # hier nichts verloren.
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            return False
        webbrowser.open(url)
        return True


# Bilder, die von aussen ins Fenster gezogen werden (Dateimanager, Bildbetrachter).
# Im Browser reicht dafuer das drop-Ereignis in index.html. In WebKitGTK kommt
# eine hereingezogene Datei beim JavaScript aber nur als Name an, nicht als
# lesbare Datei - das Frontend laedt sie hoch und bekommt nichts. pywebview
# hat dafuer den eigenen Weg: der Python-Handler erhaelt den vollen Pfad
# (pywebviewFullPath), wir kopieren die Datei selbst in uploads/ und melden sie
# dem Frontend als Anhang - über dieselbe Ablage wie /api/upload (attach.py).
def _install_native_drop(window) -> None:
    import json
    import attach

    def on_drop(event):
        files = (event.get("dataTransfer") or {}).get("files") or []
        angenommen = []
        for f in files:
            src = f.get("pywebviewFullPath")
            if not src or not Path(src).is_file():
                continue
            try:
                angenommen.append(attach.store(Path(src).read_bytes(),
                                               Path(src).suffix, Path(src).name))
            except (OSError, ValueError) as e:
                print(f"!! Drop: {src} nicht übernommen ({e})")
        if angenommen:
            window.evaluate_js(
                f"window.__nativeDrop && window.__nativeDrop({json.dumps(angenommen)})")

    def register():
        try:
            window.dom.document.events.drop += on_drop
        except Exception as e:           # aeltere pywebview ohne DOM-API: Browserweg bleibt
            print(f"!! Drag-and-drop nativ nicht verfuegbar ({e})")

    window.events.loaded += register


def show_window() -> None:
    """Baut das Fenster und blockiert, bis es geschlossen wird.

    Läuft im KINDPROZESS (--window-only). Grund: GDK beendet den Prozess bei
    einem Wayland-Protokollfehler hart von innen heraus — das ist keine
    Python-Exception und mit try/except nicht auffangbar. Nur als eigener
    Prozess lässt sich so ein Absturz überhaupt bemerken und beantworten.
    """
    try:
        import webview
    except ImportError:
        print("!! pywebview ist nicht installiert.")
        raise SystemExit(2)          # 2 = aussichtslos, anderes Backend hilft nicht

    # Damit die Taskleiste das Fenster der .desktop-Datei zuordnet und unser
    # Icon zeigt (StartupWMClass=cody), statt es "python3" zu nennen.
    try:
        from gi.repository import GLib
        GLib.set_prgname("cody")
    except Exception:
        pass

    # Ohne GPU-Beschleunigung den Sparmodus anfordern: das Frontend lässt dann
    # den Vollbild-Canvas (Matrix-Regen) und die Scanlines weg. Auf 4K frisst
    # der Canvas sonst über die Hälfte eines Kerns und die Eingabe hakt.
    win_url = URL + "?fx=low" if SOFTWARE_RENDER else URL

    window = webview.create_window(
        "CONSTRUCT",
        win_url,
        width=1280,
        height=860,
        min_size=(900, 600),
        text_select=True,
        js_api=_Bridge(),
    )
    _install_native_drop(window)

    # GTK explizit: sonst fällt pywebview stillschweigend auf Qt zurück und der
    # Fehler lautet "kein Modul qtpy" — was mit der echten Ursache (fehlendes
    # WebKit-Typelib) nichts zu tun hat und beim Suchen nur in die Irre führt.
    gui = os.environ.get("CODY_GUI") or ("gtk" if sys.platform.startswith("linux") else None)
    # CODY_DEBUG=1 schaltet den Web-Inspector frei (Rechtsklick -> Element
    # untersuchen). Der einzige Weg, JS-Fehler im Fenster überhaupt zu sehen.
    debug = os.environ.get("CODY_DEBUG") == "1"

    # private_mode=False ist PFLICHT, nicht Komfort: pywebview startet sonst im
    # Private Mode, und darin existiert in WebKitGTK gar kein localStorage —
    # nicht leer, sondern nicht vorhanden. Das Frontend liest es auf Top-Level
    # (index.html: currentMode/currentModel), der ReferenceError bricht das
    # ganze Script ab und keine einzige Schaltfläche reagiert mehr.
    # storage_path liegt beim Projekt, damit Einstellungen auf dem USB-Stick
    # mitwandern statt am Rechner zu kleben.
    store = BASE_DIR / ".webview"
    store.mkdir(exist_ok=True)
    try:
        webview.start(gui=gui, debug=debug,       # blockiert, bis das Fenster zu ist
                      private_mode=False, storage_path=str(store))
    except TypeError:
        # Ältere pywebview-Versionen kennen storage_path noch nicht.
        webview.start(gui=gui, debug=debug, private_mode=False)


def window_attempts() -> list:
    """Welche GDK-Backends in welcher Reihenfolge probiert werden.

    Unter Wayland zuerst X11 (via XWayland): WebKitGTK wirft dort sonst gern
    "Error 71 (Protokollfehler)" und reißt den Prozess mit. XWayland ist der
    stabile Pfad; native Wayland-Darstellung ist bei HiDPI etwas schärfer,
    darum bleibt sie per CODY_WAYLAND=1 erreichbar.
    """
    if os.environ.get("GDK_BACKEND"):
        return [("", "GDK_BACKEND aus der Umgebung")]
    if not os.environ.get("WAYLAND_DISPLAY"):
        return [("", "System-Standard")]
    if os.environ.get("CODY_WAYLAND") == "1":
        return [("wayland", "Wayland"), ("x11", "X11/XWayland")]
    return [("x11", "X11/XWayland"), ("wayland", "Wayland")]


def spawn_window(backend: str) -> int:
    """Startet das Fenster als eigenen Prozess und gibt dessen Exit-Code zurück."""
    env = dict(os.environ)
    if backend:
        env["GDK_BACKEND"] = backend
    return subprocess.call(
        [sys.executable, str(Path(__file__).resolve()), "--window-only"], env=env
    )


def idle() -> None:
    """Server am Leben halten, wenn kein Fenster den Prozess blockiert."""
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n» beendet.")


def main() -> None:
    # Kindprozess: nur das Fenster, der Server läuft im Elternprozess.
    if "--window-only" in sys.argv:
        show_window()
        return

    web_only = "--web" in sys.argv
    started = start_server()

    if web_only:
        if started:
            idle()
        else:
            print("» Es lief schon eine Instanz — nichts zu tun.")
        return

    for backend, label in window_attempts():
        code = spawn_window(backend)
        if code == 0:
            print("» Fenster geschlossen, CONSTRUCT beendet.")
            return
        if code == 2:                 # pywebview fehlt — Backend-Wechsel zwecklos
            break
        print(f"   ⚠  Fenster über {label} abgestürzt (Code {code}) — nächster Versuch …")

    browser_fallback("kein Fenster-Backend hat durchgehalten")


if __name__ == "__main__":
    main()
