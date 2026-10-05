"""Wo die Firma dieser Installation liegt.

Normalerweise `firma/` im Projektordner. CONSTRUCT_FIRMA_DIR verlegt sie — gebraucht
vom Prüfstand (scripts/pruefstand.py), der gegen eine Kopie der Belegschaft misst,
ohne die echte anzufassen. Eine verlegte Firma bringt ihre eigene USER.md mit; die
Firma des Normalbetriebs teilt sich die des Assistenten (eine Person, eine Datei).
"""
import os
from pathlib import Path

from server import config as cfg
from server.core import BASE_DIR

_EIGENE = os.environ.get("CONSTRUCT_FIRMA_DIR", "").strip()

FIRMA_DIR = Path(_EIGENE).expanduser().resolve() if _EIGENE else BASE_DIR / "firma"
USER_FILE = FIRMA_DIR / "USER.md" if _EIGENE else cfg.PERSONA_FILES["user"][0]
