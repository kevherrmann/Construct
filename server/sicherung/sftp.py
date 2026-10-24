"""Dateien auf einem Server ablegen und holen, per SFTP.

Benutzt das sftp-Programm von OpenSSH (Linux, Mac, Windows 10+ bringen es mit)
statt einer Python-Bibliothek: so gelten ~/.ssh/config, ssh-agent und
known_hosts wie im Terminal, und es kommt kein Paket dazu. Angemeldet wird nur
per Schlüssel (BatchMode): ein Passwort-Dialog würde im Hintergrund ewig warten.
Ein unbekannter Server wird beim ersten Kontakt in known_hosts aufgenommen,
danach muss sein Schlüssel gleich bleiben.

Geht auch mit reinen SFTP-Zugängen ohne Shell (Storage Box, NAS): alles läuft
über SFTP-Befehle, nichts über eine Shell auf dem Server.
"""
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from . import Fehler

ZEIT = 600
# Nur einfache Namen: Pfadteile oder Anführungszeichen hätten in den
# sftp-Befehlszeilen nichts verloren.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class Server:
    def __init__(self, host: str, benutzer: str = "", port: int = 0, ordner: str = "",
                 schluessel: str = ""):
        if not host or not re.fullmatch(r"[A-Za-z0-9._:\[\]-]+", host):
            raise Fehler("Servername fehlt oder enthält ungültige Zeichen.")
        if benutzer and not re.fullmatch(r"[A-Za-z0-9._-]+", benutzer):
            raise Fehler("Benutzername enthält ungültige Zeichen.")
        if '"' in (ordner or "") or "\n" in (ordner or ""):
            raise Fehler("Ordner enthält ungültige Zeichen.")
        self.host, self.benutzer, self.port = host, benutzer, int(port or 0)
        self.ordner = (ordner or "sicherungen").strip().rstrip("/") or "sicherungen"
        self.schluessel = schluessel

    def __str__(self):
        wer = f"{self.benutzer}@{self.host}" if self.benutzer else self.host
        return f"{wer}:{self.ordner}"

    def befehl(self) -> list:
        exe = shutil.which("sftp")
        if not exe:
            raise Fehler("Das Programm sftp (OpenSSH) fehlt auf diesem Rechner.")
        cmd = [exe, "-b", "-", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
               "-o", "StrictHostKeyChecking=accept-new"]
        if self.port:
            cmd += ["-P", str(self.port)]
        if self.schluessel:
            cmd += ["-i", str(Path(self.schluessel).expanduser()), "-o", "IdentitiesOnly=yes"]
        return cmd + [f"{self.benutzer}@{self.host}" if self.benutzer else self.host]

    def _sftp(self, zeilen: list) -> str:
        """Befehle im Stapelbetrieb; ein Befehl mit „-“ davor darf scheitern."""
        try:
            p = subprocess.run(self.befehl(), input="\n".join(zeilen) + "\n", capture_output=True,
                               text=True, timeout=ZEIT)
        except subprocess.TimeoutExpired:
            raise Fehler(f"Der Server {self.host} antwortet nicht (nach {ZEIT} s abgebrochen).") from None
        if p.returncode != 0:
            raise Fehler(f"Server {self.host}: {_meldung(p.stderr)}")
        return p.stdout

    def pfad(self, *teile: str) -> str:
        return str(PurePosixPath(self.ordner, *teile))

    def _anlegen(self, unterordner: str = "") -> list:
        teile = PurePosixPath(self.pfad(unterordner) if unterordner else self.ordner).parts
        return [f'-mkdir "{PurePosixPath(*teile[:i])}"' for i in range(1, len(teile) + 1)]

    def testen(self) -> None:
        """Verbinden und den Ordner anlegen. Wirft Fehler mit verständlicher Meldung."""
        self._sftp(self._anlegen())

    def liste(self, unterordner: str = "") -> set[str]:
        """Dateinamen in einem Ordner (fehlt er: leer)."""
        aus = self._sftp([f'-ls -1 "{self.pfad(unterordner) if unterordner else self.ordner}"'])
        return {PurePosixPath(z.strip()).name for z in aus.splitlines()
                if z.strip() and not z.startswith("sftp>")}

    def hochladen(self, dateien: list[tuple[Path, str]], unterordner: str = "") -> None:
        """Mehrere Dateien in einer Verbindung. Erst unter .tmp, dann umbenennen:
        eine halbe Datei trägt nie den richtigen Namen."""
        if not dateien:
            return
        zeilen = self._anlegen(unterordner)
        for datei, name in dateien:
            if not _NAME.match(name):
                raise Fehler(f"Ungültiger Name {name}.")
            ziel = self.pfad(unterordner, name) if unterordner else self.pfad(name)
            zeilen += [f'-rm "{ziel}.tmp"', f'put "{Path(datei).as_posix()}" "{ziel}.tmp"',
                       f'-rm "{ziel}"', f'rename "{ziel}.tmp" "{ziel}"', f'-chmod 600 "{ziel}"']
        self._sftp(zeilen)

    def holen(self, dateien: list[tuple[str, Path]], unterordner: str = "") -> None:
        if not dateien:
            return
        zeilen = []
        for name, ziel in dateien:
            if not _NAME.match(name):
                raise Fehler(f"Ungültiger Name {name}.")
            quelle = self.pfad(unterordner, name) if unterordner else self.pfad(name)
            zeilen.append(f'get "{quelle}" "{Path(ziel).as_posix()}"')
        self._sftp(zeilen)

    def loeschen(self, namen: list[str], unterordner: str = "") -> None:
        namen = [n for n in namen if _NAME.match(n)]
        if namen:
            self._sftp([f'rm "{self.pfad(unterordner, n) if unterordner else self.pfad(n)}"' for n in namen])


def _meldung(stderr: str) -> str:
    """Die letzte aussagekräftige Zeile von ssh/sftp, mit Hinweis bei den häufigen Fällen."""
    zeilen = [z.strip() for z in (stderr or "").splitlines() if z.strip()]
    letzte = zeilen[-1] if zeilen else "unbekannter Fehler"
    text = " ".join(zeilen).lower()
    if "permission denied" in text:
        return (f"{letzte} (Anmeldung abgelehnt: Ist der öffentliche Schlüssel auf dem Server "
                "hinterlegt? Schlüssel mit Passphrase gehen nur über ssh-agent.)")
    if "host key verification failed" in text or "remote host identification has changed" in text:
        return f"{letzte} (Der Schlüssel des Servers hat sich geändert. Bitte prüfen, ehe es weitergeht.)"
    if "could not resolve" in text or "name or service not known" in text:
        return f"{letzte} (Servername nicht gefunden.)"
    return letzte
