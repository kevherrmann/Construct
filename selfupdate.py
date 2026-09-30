"""CONSTRUCT selbst aktuell halten — beim Start, vor allem anderen.

Läuft mit dem System-Python, BEVOR start.sh/start.bat das venv anfassen: kommt
mit dem Update eine neue requirements.txt, installiert der Start sie gleich mit.
Darum nur Standardbibliothek.

Vorsichtig statt clever:
  - nur ein Fast-Forward (`merge --ff-only`) — nie mergen, nie etwas verwerfen
  - lokal geänderte Dateien (Entwickler-Rechner) bleiben, wie sie sind; das
    Update läuft trotzdem, solange es keine davon ändert
  - eine lokale Änderung, die auf GitHub schon GENAU SO steht (auf dem anderen
    Rechner gemacht und gepusht), wird vorher zurückgesetzt — sonst blockt git,
    obwohl nichts verloren ginge
  - ändert das Update eine Datei, die lokal ANDERS geändert ist -> überspringen,
    nichts anfassen
  - Netz weg / GitHub hängt -> nach wenigen Sekunden aufgeben und normal starten
  - Nutzerdaten (USER.md, settings.json, …) stehen in .gitignore, git rührt sie nicht an

Exit-Code 10 = es wurde aktualisiert (der Starter startet sich dann neu, weil er
selbst eine der neuen Dateien sein kann). Alles andere = normal weiterstarten.

Abschalten: in settings.json `"updates": {"construct": false}` oder
Umgebungsvariable CONSTRUCT_NO_UPDATE=1.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
UPDATED = 10
NET_TIMEOUT = 20


def git(*args, timeout=10, raw=False):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"          # nie nach Passwort fragen
    # SSH ohne Schlüssel darf nicht hängen oder fragen, sondern schnell scheitern
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=5")
    try:
        p = subprocess.run(["git", "-C", str(BASE_DIR), *args], env=env,
                           capture_output=True, text=True, timeout=timeout)
        if raw:                               # -z-Ausgaben: nichts abschneiden
            return p.returncode, p.stdout
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def enabled() -> bool:
    if os.environ.get("CONSTRUCT_NO_UPDATE"):
        return False
    try:
        s = json.loads((BASE_DIR / "settings.json").read_text(encoding="utf-8"))
        return (s.get("updates") or {}).get("construct", True) is not False
    except Exception:
        return True


def fetch(branch: str) -> bool:
    code, out = git("fetch", "--quiet", "origin", timeout=NET_TIMEOUT)
    if code == 0:
        return True
    # Per SSH geklont, aber kein Schlüssel auf diesem Rechner: das Repository
    # ist öffentlich, also über HTTPS nachladen und origin/<branch> nachziehen.
    _, url = git("remote", "get-url", "origin")
    m = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if m:
        code, out = git("fetch", "--quiet", f"https://github.com/{m.group(1)}.git",
                        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
                        timeout=NET_TIMEOUT)
        if code == 0:
            return True
    print("   (Update-Prüfung übersprungen — kein Netz oder kein Zugriff)")
    return False


def local_conflicts():
    """Lokale Änderungen an Dateien, die das Update auch ändert.

    Rückgabe: (gleich, anders). `gleich` steht auf GitHub schon genau so und
    darf weichen; `anders` würde verloren gehen -> dann kein Update.
    """
    code, st = git("status", "--porcelain", "-z", "-uall", raw=True)
    if code:
        return [], ["(git status fehlgeschlagen)"]
    code, changed = git("diff", "--name-only", "-z", "HEAD", "@{u}", raw=True)
    if code:
        return [], ["(git diff fehlgeschlagen)"]
    changed = set(changed.split("\0"))
    same, other = [], []
    entries = iter(st.split("\0"))
    for e in entries:
        if len(e) < 4:
            continue
        path = e[3:]
        if e[0] in "RC":
            next(entries, None)           # Umbenennung: alter Name folgt extra
        if path not in changed:
            continue                      # Update fasst die Datei nicht an
        c1, local = git("hash-object", "--", path)
        c2, remote = git("rev-parse", f"@{{u}}:{path}")
        (same if not c1 and not c2 and local == remote else other).append(path)
    return same, other


def main() -> int:
    if not enabled() or not (BASE_DIR / ".git").exists() or not shutil.which("git"):
        return 0
    code, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if code or branch == "HEAD":
        return 0
    code, upstream = git("rev-parse", "--abbrev-ref", "@{u}")
    if code:
        return 0                                  # Zweig ohne Gegenstück auf GitHub
    if not fetch(branch):
        return 0
    code, behind = git("rev-list", "--count", "HEAD..@{u}")
    if code or behind.strip() in ("", "0"):
        return 0
    if git("merge-base", "--is-ancestor", "HEAD", "@{u}")[0]:
        print("   (CONSTRUCT-Update übersprungen — eigene Commits, bitte selbst mergen)")
        return 0
    same, other = local_conflicts()
    if other:
        print("   (CONSTRUCT-Update übersprungen — lokal anders geändert: "
              + ", ".join(other[:5]) + ")")
        return 0
    for path in same:
        if git("ls-files", "--error-unmatch", "--", path)[0] == 0:
            git("checkout", "HEAD", "--", path)
        else:
            (BASE_DIR / path).unlink(missing_ok=True)
    _, log = git("log", "--oneline", "--no-decorate", "HEAD..@{u}")
    code, out = git("merge", "--ff-only", "--quiet", "@{u}", timeout=60)
    if code:
        print("   ⚠  CONSTRUCT-Update fehlgeschlagen:\n" + out)
        return 0
    print(f"» CONSTRUCT aktualisiert ({behind.strip()} neue Änderung(en)):")
    for line in log.splitlines()[:10]:
        print("     " + line)
    return UPDATED


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
