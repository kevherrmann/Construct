"""Anhänge in uploads/ wieder wegräumen.

Bilder und PDFs braucht man meist nur für eine Unterhaltung. Deshalb:
- Wird eine Session gelöscht, gehen ihre Anhänge mit — außer eine andere
  Session (z.B. eine abgezweigte) oder die Einstellungen nutzen sie noch.
- Einmal täglich fliegen Anhänge, die älter als ORPHAN_DAYS sind und nirgends
  mehr vorkommen (Telegram-Dateien, nie abgeschickte Uploads, Reste gelöschter
  Sessions von vor dieser Regel).

"Kommt vor" heißt: der Dateiname steht in irgendeinem Verlauf oder einer
JSON-Datei im Projektordner. Die Namen sind zufällige UUIDs, ein Treffer ist
also eindeutig — und der Abgleich über den Namen statt den vollen Pfad
überlebt ein Umbenennen des Projektordners.
"""
import threading
import time
from pathlib import Path

from server.core import BASE_DIR, PROJECTS_DIR, UPLOAD_DIR

ORPHAN_DAYS = 7
SWEEP_EVERY = 24 * 3600
SIDECAR = ".txt"   # PDF-Textauszug neben <name>.pdf


def _upload_names() -> list[str]:
    try:
        return [p.name for p in UPLOAD_DIR.iterdir()
                if p.is_file() and not p.name.endswith(".pdf" + SIDECAR)]
    except FileNotFoundError:
        return []


def _sources():
    """Alle Dateien, in denen ein Anhang noch erwähnt sein kann."""
    yield from PROJECTS_DIR.rglob("*.jsonl")
    yield from (BASE_DIR / "llm_sessions").glob("*.json")
    yield from BASE_DIR.glob("*.json")          # settings.json (Hintergrundbild) u.a.
    try:
        from server import hermes
        db = Path(hermes.hermes_home()) / "state.db"
        yield from (db, Path(str(db) + "-wal"))
    except Exception:
        pass


def referenced(names) -> set[str]:
    """Welche der Dateinamen noch irgendwo vorkommen."""
    left = {n: n.encode() for n in names}
    found = set()
    for src in _sources():
        if not left:
            break
        try:
            data = src.read_bytes()
        except OSError:
            continue
        for n, b in list(left.items()):
            if b in data:
                found.add(n)
                del left[n]
    return found


def _remove(name: str) -> None:
    for p in (UPLOAD_DIR / name, UPLOAD_DIR / (name + SIDECAR)):
        p.unlink(missing_ok=True)


def names_in(data: bytes | str) -> set[str]:
    """Welche vorhandenen Anhänge in diesem Verlauf vorkommen."""
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    return {n for n in _upload_names() if n.encode() in data}


def drop_unused(names) -> list[str]:
    """Anhänge löschen, die nirgends mehr vorkommen. Nach dem Löschen der
    Session aufrufen, sonst findet sie sich selbst."""
    names = set(names)
    gone = sorted(names - referenced(names))
    for n in gone:
        _remove(n)
    return gone


def sweep(max_age_days: float = ORPHAN_DAYS) -> list[str]:
    """Verwaiste Anhänge löschen, die älter als max_age_days sind."""
    cutoff = time.time() - max_age_days * 86400
    old = []
    for n in _upload_names():
        try:
            if (UPLOAD_DIR / n).stat().st_mtime < cutoff:
                old.append(n)
        except OSError:
            pass
    return drop_unused(old) if old else []


def drop_later(names) -> None:
    """drop_unused im Hintergrund — das Durchsuchen aller Verläufe dauert."""
    if names:
        threading.Thread(target=_safe, args=(drop_unused, names), daemon=True,
                         name="uploads-drop").start()


def _safe(fn, *a):
    try:
        gone = fn(*a)
        if gone:
            print(f"[uploads] {len(gone)} Anhang/Anhänge gelöscht", flush=True)
    except Exception as e:
        print(f"[uploads] Aufräumen fehlgeschlagen: {type(e).__name__}: {e}", flush=True)


def start() -> None:
    """Tägliches Aufräumen im Hintergrund (erster Lauf gleich beim Start)."""
    def loop():
        while True:
            _safe(sweep)
            time.sleep(SWEEP_EVERY)
    threading.Thread(target=loop, daemon=True, name="uploads-gc").start()
