"""
mail.py — E-Mail-Modul für Matrix Chat (Cody).

IMAP zum Abrufen / Löschen / Markieren, SMTP zum Senden:
  - GMX und Gmail per Passwort (Gmail: App-Passwort, 2FA nötig)
  - Hotmail/Outlook per OAuth2-Device-Flow, weil Microsoft Passwort-IMAP für
    Privatkonten im Sept. 2024 abgeschaltet hat.

Kategorien sind rein LOKAL (mail_meta.json) — die Mail-Server sehen davon
nichts. Löschen passiert dagegen RICHTIG auf dem Server (→ Papierkorb).

Zugangsdaten liegen in .mail-accounts.json (Dotfile, chmod 600) — Dotfiles
sind über /api/file ohnehin tabu.
"""
import base64
import email
import email.utils
import imaplib
import json
import mimetypes
import os
import re
import smtplib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path

# Liegt in server/ — Daten und Einstellungen bleiben im Projektordner darüber.
BASE_DIR = Path(__file__).resolve().parent.parent
ACC_FILE = BASE_DIR / ".mail-accounts.json"
META_FILE = BASE_DIR / "mail_meta.json"
ATTACH_DIR = BASE_DIR / "mail_attach"       # Anhänge zum VERSENDEN (nicht web-gemountet)
ATTACH_DIR.mkdir(exist_ok=True)

_LOCK = threading.Lock()


class MailError(Exception):
    pass


# ---------- Anbieter ----------
PROVIDERS = {
    "gmx": {
        "name": "GMX", "auth": "password",
        "imap": ("imap.gmx.net", 993), "smtp": ("mail.gmx.net", 587),
        "hint": "GMX-Webmail → Einstellungen → POP3/IMAP → „Zugriff erlauben“ aktivieren. Dann hier das normale GMX-Passwort eintragen.",
    },
    "gmail": {
        "name": "Gmail", "auth": "password",
        "imap": ("imap.gmail.com", 993), "smtp": ("smtp.gmail.com", 587),
        "hint": "Google-Konto → Sicherheit → 2-Faktor aktivieren → „App-Passwörter“ → neues App-Passwort (16 Zeichen) erzeugen und hier eintragen (NICHT das normale Passwort).",
    },
    "outlook": {
        "name": "Outlook/Hotmail", "auth": "oauth",
        "imap": ("outlook.office365.com", 993), "smtp": ("smtp-mail.outlook.com", 587),
        "hint": "Microsoft erlaubt kein Passwort-IMAP mehr — einfach auf MICROSOFT-LOGIN klicken und den angezeigten Code auf der Microsoft-Seite eingeben.",
    },
}
_DOMAINS = {
    "gmx.de": "gmx", "gmx.net": "gmx", "gmx.at": "gmx", "gmx.ch": "gmx",
    "gmail.com": "gmail", "googlemail.com": "gmail",
    "hotmail.com": "outlook", "hotmail.de": "outlook", "outlook.com": "outlook",
    "outlook.de": "outlook", "live.com": "outlook", "live.de": "outlook", "msn.com": "outlook",
}

# Beim ersten Start vorangelegte Konten. Leer: jede Installation traegt ihre
# eigenen Adressen ueber ⚙ → E-Mail-Konten ein (Passwoerter sowieso nur dort).
# Wer immer dieselben Konten will, kann sie hier eintragen — sie landen dann
# aber in der Datei, die mit anderen geteilt wird.
DEFAULT_ACCOUNTS = []


def provider_for(addr: str):
    dom = (addr or "").rsplit("@", 1)[-1].lower()
    key = _DOMAINS.get(dom)
    return PROVIDERS.get(key) if key else None


# ---------- Konten-Datei ----------
def load_accounts() -> list:
    with _LOCK:
        try:
            d = json.loads(ACC_FILE.read_text(encoding="utf-8"))
            accs = d.get("accounts") or []
        except Exception:
            accs = [{"email": e} for e in DEFAULT_ACCOUNTS]
            _write_accounts(accs)
        return accs


def _write_accounts(accs: list):
    tmp = ACC_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"accounts": accs}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(ACC_FILE)


def _update_account(addr: str, **fields):
    with _LOCK:
        try:
            accs = json.loads(ACC_FILE.read_text(encoding="utf-8")).get("accounts") or []
        except Exception:
            accs = []
        for a in accs:
            if a.get("email") == addr:
                a.update(fields)
                break
        else:
            accs.append(dict({"email": addr}, **fields))
        _write_accounts(accs)


def account(addr: str) -> dict:
    for a in load_accounts():
        if a.get("email") == addr:
            return a
    raise MailError(f"Unbekanntes Konto: {addr}")


def _configured(a: dict) -> bool:
    return bool(a.get("password") or a.get("ms_refresh"))


def public_accounts() -> list:
    """Konten OHNE Geheimnisse — fürs Frontend."""
    out = []
    for a in load_accounts():
        p = provider_for(a["email"]) or {}
        out.append({
            "email": a["email"],
            "provider": p.get("name", "?"),
            "auth": p.get("auth", "password"),
            "hint": p.get("hint", ""),
            "configured": _configured(a),
        })
    return out


def save_account(addr: str, password: str = "") -> dict:
    addr = addr.strip().lower()
    if "@" not in addr:
        raise MailError("Keine gültige E-Mail-Adresse")
    p = provider_for(addr)
    if not p:
        raise MailError(f"Unbekannter Anbieter für {addr} — ich kenne GMX, Gmail und Outlook/Hotmail.")
    fields = {}
    password = password.strip()     # Copy-Paste-Leerzeichen an den Rändern weg
    if password:                    # leer = altes Passwort behalten
        fields["password"] = password
    _update_account(addr, **fields)
    return {"ok": True}


def delete_account(addr: str) -> dict:
    with _LOCK:
        try:
            accs = json.loads(ACC_FILE.read_text(encoding="utf-8")).get("accounts") or []
        except Exception:
            accs = []
        accs = [a for a in accs if a.get("email") != addr]
        _write_accounts(accs)
    _LIST_CACHE.pop(addr, None)
    return {"ok": True}


# ---------- Microsoft OAuth2 (Device-Flow) ----------
# Öffentliche Client-ID von Thunderbird — bewährt für IMAP/SMTP-OAuth bei
# Privatkonten. Falls Microsoft die mal sperrt: eigene App unter
# portal.azure.com registrieren und hier eintragen.
MS_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
MS_SCOPE = ("https://outlook.office.com/IMAP.AccessAsUser.All "
            "https://outlook.office.com/SMTP.Send offline_access")
MS_DEVICE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"

_MS_FLOWS = {}    # email -> laufender Device-Flow
_MS_TOKENS = {}   # email -> (access_token, gültig_bis)


def _http_form(url: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)     # MS packt Fehlerdetails in den Body
        except Exception:
            raise MailError(f"HTTP {e.code} von Microsoft")


def ms_login_start(addr: str) -> dict:
    account(addr)                   # muss existieren
    j = _http_form(MS_DEVICE_URL, {"client_id": MS_CLIENT_ID, "scope": MS_SCOPE})
    if "device_code" not in j:
        raise MailError(j.get("error_description") or j.get("error") or "Device-Flow fehlgeschlagen")
    _MS_FLOWS[addr] = j
    return {"url": j.get("verification_uri") or "https://microsoft.com/devicelogin",
            "code": j.get("user_code", "?")}


def ms_poll(addr: str) -> dict:
    flow = _MS_FLOWS.get(addr)
    if not flow:
        return {"error": "Kein Login aktiv — nochmal auf MICROSOFT-LOGIN klicken."}
    j = _http_form(MS_TOKEN_URL, {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": MS_CLIENT_ID, "device_code": flow["device_code"],
    })
    err = j.get("error", "")
    if err in ("authorization_pending", "slow_down"):
        return {"pending": True}
    if j.get("refresh_token"):
        _update_account(addr, ms_refresh=j["refresh_token"])
        _MS_TOKENS[addr] = (j.get("access_token", ""), time.time() + int(j.get("expires_in") or 3600) - 60)
        _MS_FLOWS.pop(addr, None)
        return {"ok": True}
    _MS_FLOWS.pop(addr, None)
    return {"error": j.get("error_description") or err or "Login fehlgeschlagen"}


def _ms_access_token(acc: dict) -> str:
    addr = acc["email"]
    tok, exp = _MS_TOKENS.get(addr, ("", 0))
    if tok and exp > time.time():
        return tok
    if not acc.get("ms_refresh"):
        raise MailError("Microsoft-Login nötig — unter ⚙ Konten verwalten anmelden.")
    j = _http_form(MS_TOKEN_URL, {
        "grant_type": "refresh_token", "client_id": MS_CLIENT_ID,
        "refresh_token": acc["ms_refresh"], "scope": MS_SCOPE,
    })
    if not j.get("access_token"):
        raise MailError("Microsoft-Token abgelaufen — bitte unter ⚙ Konten neu anmelden. "
                        + (j.get("error_description") or "")[:200])
    if j.get("refresh_token"):
        _update_account(addr, ms_refresh=j["refresh_token"])
    _MS_TOKENS[addr] = (j["access_token"], time.time() + int(j.get("expires_in") or 3600) - 60)
    return j["access_token"]


def _xoauth2(user: str, token: str) -> str:
    return f"user={user}\x01auth=Bearer {token}\x01\x01"


# ---------- Verbindungen ----------
def _imap(acc: dict) -> imaplib.IMAP4_SSL:
    p = provider_for(acc["email"])
    if not p:
        raise MailError("Unbekannter Anbieter")
    host, port = p["imap"]
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=25)
    except Exception as e:
        raise MailError(f"Keine Verbindung zu {host}: {e}")
    try:
        if p["auth"] == "oauth" and acc.get("ms_refresh"):
            tok = _ms_access_token(acc)
            conn.authenticate("XOAUTH2", lambda _: _xoauth2(acc["email"], tok).encode())
        elif acc.get("password"):
            conn.login(acc["email"], acc["password"])
        else:
            raise MailError("Konto nicht eingerichtet (⚙ Konten verwalten)")
    except MailError:
        conn.logout()
        raise
    except Exception as e:
        try:
            conn.logout()
        except Exception:
            pass
        raise MailError(f"Login fehlgeschlagen: {str(e)[:200]}")
    return conn


def _smtp(acc: dict) -> smtplib.SMTP:
    p = provider_for(acc["email"])
    host, port = p["smtp"]
    s = smtplib.SMTP(host, port, timeout=30)
    try:
        s.ehlo()
        s.starttls()
        s.ehlo()
        if p["auth"] == "oauth" and acc.get("ms_refresh"):
            tok = _ms_access_token(acc)
            auth = base64.b64encode(_xoauth2(acc["email"], tok).encode()).decode()
            code, resp = s.docmd("AUTH", "XOAUTH2 " + auth)
            if code != 235:
                raise MailError(f"SMTP-OAuth fehlgeschlagen: {resp.decode('utf-8', 'replace')[:200]}")
        elif acc.get("password"):
            s.login(acc["email"], acc["password"])
        else:
            raise MailError("Konto nicht eingerichtet")
    except MailError:
        s.close()
        raise
    except Exception as e:
        s.close()
        raise MailError(f"SMTP-Login fehlgeschlagen: {str(e)[:200]}")
    return s


def _q(folder: str) -> str:
    return '"' + folder.replace('"', '') + '"'


def _find_special(conn, want: str):
    """Ordner mit SPECIAL-USE-Flag (\\Trash, \\Sent) suchen — GMX/Gmail/Outlook
    liefern die Flags im normalen LIST mit."""
    try:
        typ, data = conn.list()
    except Exception:
        return None
    for line in data or []:
        if isinstance(line, bytes):
            s = line.decode("utf-8", "replace")
        else:
            continue
        m = re.match(r'\((?P<flags>[^)]*)\)\s+"?(?P<sep>[^"]*)"?\s+(?P<name>.+)$', s)
        if m and want.lower() in m.group("flags").lower():
            return m.group("name").strip().strip('"')
    return None


# ---------- Header-Helfer ----------
def dec(s) -> str:
    if not s:
        return ""
    out = ""
    try:
        for txt, enc in decode_header(str(s)):
            if isinstance(txt, bytes):
                out += txt.decode(enc or "utf-8", "replace")
            else:
                out += txt
    except Exception:
        out = str(s)
    return out.strip()


def _msg_ts(m) -> float:
    try:
        return email.utils.parsedate_to_datetime(m.get("Date")).timestamp()
    except Exception:
        return 0


def _msg_key(acc: dict, m, uid: str) -> str:
    """Stabiler Schlüssel für die lokale Kategorie-Zuordnung."""
    mid = (m.get("Message-ID") or "").strip()
    return acc["email"] + "|" + (mid or f"uid:{uid}")


# ---------- Abrufen ----------
_LIST_CACHE = {}          # email -> {"t":…, "msgs":[…]}
LIST_TTL = 120


def _fetch_headers(conn, uids):
    if not uids:
        return {}
    typ, data = conn.uid(
        "fetch", ",".join(uids),
        "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
    # imaplib liefert pro Nachricht ein Tupel (Meta, Header-Bytes), oft gefolgt
    # von losen b')'-Stücken — die Meta-Teile fürs FLAGS-Parsen zusammenkleben.
    records = []
    for item in data or []:
        if isinstance(item, tuple):
            records.append([item[0].decode("utf-8", "replace"), item[1]])
        elif isinstance(item, bytes) and records:
            records[-1][0] += " " + item.decode("utf-8", "replace")
    out = {}
    for meta, hdr in records:
        mu = re.search(r"UID (\d+)", meta)
        if not mu:
            continue
        mf = re.search(r"FLAGS \(([^)]*)\)", meta)
        out[mu.group(1)] = (mf.group(1) if mf else "", hdr or b"")
    return out


def list_messages(acc: dict, folder: str = "INBOX", limit: int = 50) -> list:
    conn = _imap(acc)
    try:
        typ, _ = conn.select(_q(folder), readonly=True)
        if typ != "OK":
            raise MailError(f"Ordner {folder} nicht lesbar")
        typ, data = conn.uid("search", None, "ALL")
        uids = [u.decode() for u in (data[0] or b"").split()]
        if limit > 0:
            uids = uids[-limit:]
        # In 500er-Häppchen fetchen — EIN Riesen-FETCH mit tausenden UIDs
        # sprengt sonst die Kommandozeilen-Länge mancher IMAP-Server.
        recs = {}
        for i in range(0, len(uids), 500):
            recs.update(_fetch_headers(conn, uids[i:i + 500]))
        msgs = []
        for uid in uids:
            flags, hdr = recs.get(uid, ("", b""))
            m = email.message_from_bytes(hdr)
            name, addr = email.utils.parseaddr(dec(m.get("From")))
            msgs.append({
                "account": acc["email"], "folder": folder, "uid": uid,
                "key": _msg_key(acc, m, uid),
                "from_name": name or addr, "from_addr": addr,
                "to": dec(m.get("To"))[:300],
                "subject": dec(m.get("Subject")),
                "ts": _msg_ts(m),
                "seen": "\\Seen" in flags,
            })
        return msgs
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _cached_list(acc: dict, limit: int, force: bool) -> list:
    """limit <= 0 heißt: ALLE Mails. Der Cache darf nur wiederverwendet werden,
    wenn er mindestens so viel abdeckt wie angefragt."""
    ent = _LIST_CACHE.get(acc["email"])
    covers = ent and (ent.get("limit", 50) <= 0 or (limit > 0 and ent.get("limit", 50) >= limit))
    if not force and ent and covers and time.time() - ent["t"] < LIST_TTL:
        return ent["msgs"]
    msgs = list_messages(acc, limit=limit)
    _LIST_CACHE[acc["email"]] = {"t": time.time(), "msgs": msgs, "limit": limit}
    return msgs


def list_all(account_filter: str = "", force: bool = False, limit: int = 50) -> dict:
    accs = [a for a in load_accounts() if _configured(a)]
    if account_filter:
        accs = [a for a in accs if a["email"] == account_filter]
    msgs, errors = [], {}
    if accs:
        with ThreadPoolExecutor(max_workers=min(5, len(accs))) as ex:
            futs = {ex.submit(_cached_list, a, limit, force): a for a in accs}
            for fut, a in futs.items():
                try:
                    msgs.extend(fut.result())
                except MailError as e:
                    errors[a["email"]] = str(e)
                except Exception as e:
                    errors[a["email"]] = f"{type(e).__name__}: {e}"
    assign = load_meta().get("assign", {})
    for m in msgs:
        m["category"] = assign.get(m["key"], "")
    msgs.sort(key=lambda m: m["ts"], reverse=True)
    return {"messages": msgs, "errors": errors}


def test_account(addr: str) -> dict:
    acc = account(addr)
    conn = _imap(acc)
    try:
        typ, data = conn.select('"INBOX"', readonly=True)
        n = int(data[0]) if typ == "OK" and data and data[0] else 0
        return {"ok": True, "inbox": n}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ---------- Einzelne Nachricht ----------
def _part_text(part) -> str:
    b = part.get_payload(decode=True) or b""
    return b.decode(part.get_content_charset() or "utf-8", "replace")


def _fetch_raw(conn, uid: str) -> bytes:
    typ, data = conn.uid("fetch", uid, "(BODY.PEEK[])")
    for item in data or []:
        if isinstance(item, tuple):
            return item[1]
    raise MailError("Nachricht nicht (mehr) gefunden")


def get_message(addr: str, uid: str, folder: str = "INBOX", mark_seen: bool = True) -> dict:
    acc = account(addr)
    conn = _imap(acc)
    try:
        typ, _ = conn.select(_q(folder), readonly=False)
        if typ != "OK":
            raise MailError(f"Ordner {folder} nicht lesbar")
        msg = email.message_from_bytes(_fetch_raw(conn, uid))
        text, html, atts, cids = "", "", [], {}
        for i, part in enumerate(msg.walk()):
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            fn = part.get_filename()
            disp = (part.get("Content-Disposition") or "").lower()
            cid = (part.get("Content-ID") or "").strip("<>")
            if fn or disp.startswith("attachment"):
                size = len(part.get_payload(decode=True) or b"")
                atts.append({"idx": i, "name": dec(fn) or f"anhang-{i}", "size": size, "mime": ctype})
                # angehängte Bilder mit Content-ID trotzdem inline anzeigen
                if cid and part.get_content_maintype() == "image":
                    b = part.get_payload(decode=True) or b""
                    cids[cid] = f"data:{ctype};base64,{base64.b64encode(b).decode()}"
                continue
            if ctype == "text/plain" and not text:
                text = _part_text(part)
            elif ctype == "text/html" and not html:
                html = _part_text(part)
            elif cid and part.get_content_maintype() == "image":
                b = part.get_payload(decode=True) or b""
                cids[cid] = f"data:{ctype};base64,{base64.b64encode(b).decode()}"
        for cid, uri in cids.items():
            html = html.replace(f"cid:{cid}", uri)
        if mark_seen:
            try:
                conn.uid("store", uid, "+FLAGS", r"(\Seen)")
            except Exception:
                pass
        name, from_addr = email.utils.parseaddr(dec(msg.get("From")))
        return {
            "account": addr, "folder": folder, "uid": uid,
            "key": _msg_key(acc, msg, uid),
            "message_id": (msg.get("Message-ID") or "").strip(),
            "from_name": name, "from_addr": from_addr,
            "to": dec(msg.get("To")), "cc": dec(msg.get("Cc")),
            "subject": dec(msg.get("Subject")), "ts": _msg_ts(msg),
            "text": text, "html": html, "attachments": atts,
        }
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def get_attachment(addr: str, uid: str, idx: int, folder: str = "INBOX"):
    acc = account(addr)
    conn = _imap(acc)
    try:
        typ, _ = conn.select(_q(folder), readonly=True)
        if typ != "OK":
            raise MailError(f"Ordner {folder} nicht lesbar")
        msg = email.message_from_bytes(_fetch_raw(conn, uid))
        for i, part in enumerate(msg.walk()):
            if i == idx:
                data = part.get_payload(decode=True) or b""
                name = dec(part.get_filename()) or f"anhang-{idx}"
                return data, name, part.get_content_type()
        raise MailError("Anhang nicht gefunden")
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ---------- Aktionen ----------
def set_seen(addr: str, uid: str, seen: bool, folder: str = "INBOX") -> dict:
    acc = account(addr)
    conn = _imap(acc)
    try:
        conn.select(_q(folder), readonly=False)
        conn.uid("store", uid, "+FLAGS" if seen else "-FLAGS", r"(\Seen)")
        _patch_cache(addr, uid, seen=seen)
        return {"ok": True}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def delete_message(addr: str, uid: str, folder: str = "INBOX") -> dict:
    """Echt löschen: in den Server-Papierkorb verschieben (falls auffindbar),
    sonst \\Deleted + EXPUNGE."""
    acc = account(addr)
    conn = _imap(acc)
    try:
        typ, _ = conn.select(_q(folder), readonly=False)
        if typ != "OK":
            raise MailError(f"Ordner {folder} nicht wählbar")
        trash = _find_special(conn, "\\Trash")
        if trash and trash != folder:
            try:
                conn.uid("copy", uid, _q(trash))
            except Exception:
                pass                # dann eben nur \Deleted + expunge
        conn.uid("store", uid, "+FLAGS", r"(\Deleted)")
        conn.expunge()
        ent = _LIST_CACHE.get(addr)
        if ent:
            ent["msgs"] = [m for m in ent["msgs"] if m["uid"] != uid]
        return {"ok": True}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def delete_many(items: list) -> dict:
    """Mehrere Mails löschen (→ Server-Papierkorb). items: [{account,uid,folder}].
    Pro Konto+Ordner EINE Verbindung, UIDs in 100er-Batches — sonst würde für
    jede Mail einzeln eingeloggt."""
    groups = {}
    for it in items or []:
        addr = (it.get("account") or "").strip()
        uid = str(it.get("uid") or "").strip()
        if not addr or not uid.isdigit():
            continue
        groups.setdefault((addr, it.get("folder") or "INBOX"), []).append(uid)
    deleted, errors = 0, {}
    for (addr, folder), uids in groups.items():
        try:
            acc = account(addr)
            conn = _imap(acc)
            try:
                typ, _ = conn.select(_q(folder), readonly=False)
                if typ != "OK":
                    raise MailError(f"Ordner {folder} nicht wählbar")
                trash = _find_special(conn, "\\Trash")
                for i in range(0, len(uids), 100):
                    batch = ",".join(uids[i:i + 100])
                    if trash and trash != folder:
                        try:
                            conn.uid("copy", batch, _q(trash))
                        except Exception:
                            pass            # dann eben nur \Deleted + expunge
                    conn.uid("store", batch, "+FLAGS", r"(\Deleted)")
                    conn.expunge()
                    deleted += len(uids[i:i + 100])
                if folder == "INBOX":
                    ent = _LIST_CACHE.get(addr)
                    if ent:
                        gone = set(uids)
                        ent["msgs"] = [m for m in ent["msgs"] if m["uid"] not in gone]
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except MailError as e:
            errors[addr] = str(e)
        except Exception as e:
            errors[addr] = f"{type(e).__name__}: {e}"
    return {"ok": not errors, "deleted": deleted, "errors": errors}


def _patch_cache(addr: str, uid: str, **fields):
    ent = _LIST_CACHE.get(addr)
    if ent:
        for m in ent["msgs"]:
            if m["uid"] == uid:
                m.update(fields)


# ---------- Senden ----------
def _safe_attachments(items) -> list:
    """Nur Dateien aus dem Anhang-/Upload-Ordner zulassen. items: [{path,name}]"""
    roots = [os.path.realpath(str(ATTACH_DIR)), os.path.realpath(str(BASE_DIR / "uploads"))]
    out = []
    for it in items or []:
        p = it.get("path") if isinstance(it, dict) else str(it)
        name = (it.get("name") if isinstance(it, dict) else "") or os.path.basename(p or "")
        rp = os.path.realpath(str(p or ""))
        if any(rp.startswith(r + os.sep) for r in roots) and os.path.isfile(rp):
            out.append((rp, re.sub(r"[\\/\x00-\x1f]", "_", name)[:180] or "anhang"))
    return out


def send_mail(addr: str, to: str, cc: str = "", bcc: str = "", subject: str = "",
              body: str = "", attachments=None, reply_to_id: str = "") -> dict:
    acc = account(addr)
    p = provider_for(addr)
    to, cc, bcc = (to or "").strip(), (cc or "").strip(), (bcc or "").strip()
    rcpt = [a for a in re.split(r"[,;\s]+", f"{to} {cc} {bcc}") if "@" in a]
    if not rcpt:
        raise MailError("Kein (gültiger) Empfänger")

    m = EmailMessage()
    m["From"] = addr
    m["To"] = to
    if cc:
        m["Cc"] = cc
    m["Subject"] = subject or "(kein Betreff)"
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = email.utils.make_msgid()
    if reply_to_id:
        m["In-Reply-To"] = reply_to_id
        m["References"] = reply_to_id
    m.set_content(body or "")
    for path, name in _safe_attachments(attachments):
        mt = mimetypes.guess_type(name)[0] or "application/octet-stream"
        main, sub = mt.split("/", 1)
        m.add_attachment(Path(path).read_bytes(), maintype=main, subtype=sub, filename=name)

    s = _smtp(acc)
    try:
        s.send_message(m, from_addr=addr, to_addrs=rcpt)
    finally:
        try:
            s.quit()
        except Exception:
            pass

    # Kopie in „Gesendet“ ablegen — Gmail macht das beim SMTP-Versand selbst
    if p["name"] != "Gmail":
        try:
            conn = _imap(acc)
            try:
                sent = _find_special(conn, "\\Sent")
                if sent:
                    conn.append(_q(sent), "\\Seen",
                                imaplib.Time2Internaldate(time.time()), m.as_bytes())
            finally:
                conn.logout()
        except Exception:
            pass
    return {"ok": True}


# ---------- Kategorien (rein lokal) ----------
DEFAULT_CATS = ["📌 Wichtig", "🧾 Rechnungen", "📰 Newsletter", "👨‍👩‍👧 Privat"]


def load_meta() -> dict:
    try:
        d = json.loads(META_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("categories", list(DEFAULT_CATS))
            d.setdefault("assign", {})
            return d
    except Exception:
        pass
    return {"categories": list(DEFAULT_CATS), "assign": {}}


def save_meta(d: dict):
    tmp = META_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(META_FILE)


def edit_categories(add: str = "", remove: str = "") -> dict:
    d = load_meta()
    if add:
        add = add.strip()[:40]
        if add and add not in d["categories"]:
            d["categories"].append(add)
    if remove:
        d["categories"] = [c for c in d["categories"] if c != remove]
        d["assign"] = {k: v for k, v in d["assign"].items() if v != remove}
    save_meta(d)
    return {"categories": d["categories"]}


def set_category(key: str, category: str) -> dict:
    d = load_meta()
    if category and category not in d["categories"]:
        raise MailError("Unbekannte Kategorie")
    if category:
        d["assign"][key] = category
    else:
        d["assign"].pop(key, None)
    save_meta(d)
    return {"ok": True}


def set_category_many(keys: list, category: str) -> dict:
    d = load_meta()
    if category and category not in d["categories"]:
        raise MailError("Unbekannte Kategorie")
    for key in keys:
        if not key:
            continue
        if category:
            d["assign"][key] = category
        else:
            d["assign"].pop(key, None)
    save_meta(d)
    return {"ok": True, "count": len([k for k in keys if k])}
