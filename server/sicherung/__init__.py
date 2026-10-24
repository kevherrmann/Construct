"""Bausteine für Sicherungen, die mehrere Kacheln brauchen.

krypto.py  Verschlüsseln mit Kennwort (AES-256-GCM, Schlüssel per scrypt)
sftp.py    Dateien auf einen Server legen und holen (OpenSSH-sftp)
"""


class Fehler(Exception):
    """Meldung, die so in der Oberfläche stehen kann."""
