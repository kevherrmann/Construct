"""Verschlüsselung für Sicherungen, die das Haus verlassen.

AES-256-GCM (Paket cryptography), der Schlüssel kommt per scrypt aus dem
Kennwort (hashlib, Standardbibliothek). GCM prüft beim Entschlüsseln mit, ob
die Datei verändert wurde: ein falsches Kennwort und eine beschädigte Datei
fallen beide auf, statt Datenmüll zu liefern.

Aufbau einer .enc-Datei: MAGIC | Salz (16) | Nonce (12) | Geheimtext mit Tag.

Ein Schluessel leitet einmal ab und verschlüsselt dann beliebig viele
Dateien (je mit eigener Nonce): scrypt kostet absichtlich Zeit, und eine
Sicherung mit tausend Dokumenten soll nicht tausendmal darauf warten.
"""
import hashlib
import os

from . import Fehler

MAGIC = b"CST-ENC1"
SALZ, NONCE = 16, 12
# scrypt: 32 MB Speicher je Ableitung, ein Bruchteil einer Sekunde, für Raten aber teuer.
N, R, P = 2 ** 15, 8, 1
KENNWORT_MIN = 10


def _aesgcm(schluessel: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise Fehler("Zum Verschlüsseln fehlt das Paket „cryptography“. CONSTRUCT einmal neu starten "
                     "(start.sh installiert es) oder: pip install cryptography") from None
    return AESGCM(schluessel)


def _ableiten(kennwort: str, salz: bytes) -> bytes:
    return hashlib.scrypt(kennwort.encode("utf-8"), salt=salz, n=N, r=R, p=P,
                          maxmem=64 * 1024 * 1024, dklen=32)


def kennwort_pruefen(kennwort: str) -> None:
    if len(kennwort or "") < KENNWORT_MIN:
        raise Fehler(f"Das Kennwort braucht mindestens {KENNWORT_MIN} Zeichen.")


class Schluessel:
    def __init__(self, kennwort: str):
        kennwort_pruefen(kennwort)
        self.kennwort = kennwort
        self.salz = os.urandom(SALZ)
        self._aes = _aesgcm(_ableiten(kennwort, self.salz))
        self._fremd: dict[bytes, object] = {}     # Salz → AES fürs Entschlüsseln

    def verschluesseln(self, daten: bytes) -> bytes:
        nonce = os.urandom(NONCE)
        kopf = MAGIC + self.salz
        return kopf + nonce + self._aes.encrypt(nonce, daten, kopf)

    def entschluesseln(self, daten: bytes) -> bytes:
        if not daten.startswith(MAGIC) or len(daten) < len(MAGIC) + SALZ + NONCE + 16:
            raise Fehler("Das ist keine verschlüsselte CONSTRUCT-Sicherung.")
        salz = daten[len(MAGIC):len(MAGIC) + SALZ]
        nonce = daten[len(MAGIC) + SALZ:len(MAGIC) + SALZ + NONCE]
        if salz == self.salz:
            aes = self._aes
        else:
            aes = self._fremd.get(salz)
            if aes is None:
                aes = self._fremd[salz] = _aesgcm(_ableiten(self.kennwort, salz))
        try:
            return aes.decrypt(nonce, daten[len(MAGIC) + SALZ + NONCE:], MAGIC + salz)
        except Exception:
            raise Fehler("Entschlüsseln fehlgeschlagen: Kennwort falsch oder Datei beschädigt.") from None
