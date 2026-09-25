"""API: E-Mail (IMAP/SMTP) — dünne Hülle um mail.py."""
import asyncio
import os
import re
import urllib.request
import uuid

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from server import attach
from server import mail as mailmod

router = APIRouter()


# ---------- E-Mail ----------
# IMAP/SMTP sind blockierend -> GET-Endpunkte als sync def (FastAPI-Threadpool),
# POST-Endpunkte (brauchen await req.json()) schieben die Arbeit per to_thread weg.
def _mail_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except mailmod.MailError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.get("/api/mail/accounts")
def mail_accounts():
    return {"accounts": mailmod.public_accounts()}


@router.post("/api/mail/accounts")
async def mail_accounts_save(req: Request):
    body = await req.json()
    return _mail_call(mailmod.save_account,
                      (body.get("email") or ""), body.get("password") or "")


@router.delete("/api/mail/accounts/{addr}")
def mail_accounts_del(addr: str):
    return _mail_call(mailmod.delete_account, addr)


@router.post("/api/mail/test")
async def mail_test(req: Request):
    body = await req.json()
    return await asyncio.to_thread(_mail_call, mailmod.test_account, body.get("email") or "")


@router.get("/api/mail/list")
def mail_list(account: str = "", force: int = 0, limit: int = 50):
    # limit=0 → ALLE Mails (fürs Aufräumen); sonst wie gehabt gedeckelt
    return _mail_call(mailmod.list_all, account, bool(force), max(0, min(limit, 10000)))


@router.get("/api/mail/msg")
def mail_msg(account: str, uid: str, folder: str = "INBOX"):
    return _mail_call(mailmod.get_message, account, uid, folder)


@router.get("/api/mail/att")
def mail_att(account: str, uid: str, idx: int, folder: str = "INBOX"):
    try:
        data, name, mime = mailmod.get_attachment(account, uid, idx, folder)
    except mailmod.MailError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)
    quoted = urllib.parse.quote(name)
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})


@router.post("/api/mail/delete")
async def mail_delete(req: Request):
    body = await req.json()
    return await asyncio.to_thread(
        _mail_call, mailmod.delete_message,
        body.get("account") or "", str(body.get("uid") or ""), body.get("folder") or "INBOX")


@router.post("/api/mail/delete_many")
async def mail_delete_many(req: Request):
    body = await req.json()
    items = body.get("items") or []
    if not isinstance(items, list) or len(items) > 5000:
        return JSONResponse({"error": "items: Liste mit max. 5000 Einträgen"}, status_code=400)
    return await asyncio.to_thread(_mail_call, mailmod.delete_many, items)


@router.post("/api/mail/flag")
async def mail_flag(req: Request):
    body = await req.json()
    return await asyncio.to_thread(
        _mail_call, mailmod.set_seen,
        body.get("account") or "", str(body.get("uid") or ""),
        bool(body.get("seen")), body.get("folder") or "INBOX")


@router.post("/api/mail/send")
async def mail_send(req: Request):
    body = await req.json()
    return await asyncio.to_thread(
        _mail_call, mailmod.send_mail,
        body.get("account") or "", body.get("to") or "", body.get("cc") or "",
        body.get("bcc") or "", body.get("subject") or "", body.get("body") or "",
        body.get("attachments") or [], body.get("reply") or "")


@router.post("/api/mail/attach")
async def mail_attach(file: UploadFile = File(...)):
    """Anhang für den VERSAND hochladen — jeder Dateityp, landet in mail_attach/
    (nicht web-gemountet) und wird nur von send_mail wieder angefasst."""
    data = await file.read()
    if len(data) > attach.MAX_UPLOAD:
        return JSONResponse({"error": "Datei zu groß (max. 25 MB)"}, status_code=400)
    name = re.sub(r"[\\/\x00-\x1f]", "_", os.path.basename(file.filename or "anhang"))[:180]
    sub = mailmod.ATTACH_DIR / uuid.uuid4().hex
    sub.mkdir(parents=True, exist_ok=True)
    dest = sub / (name or "anhang")
    dest.write_bytes(data)
    return {"path": str(dest), "name": name, "size": len(data)}


@router.get("/api/mail/categories")
def mail_categories():
    return {"categories": mailmod.load_meta()["categories"]}


@router.post("/api/mail/categories")
async def mail_categories_edit(req: Request):
    body = await req.json()
    return _mail_call(mailmod.edit_categories, body.get("add") or "", body.get("remove") or "")


@router.post("/api/mail/categorize")
async def mail_categorize(req: Request):
    body = await req.json()
    return _mail_call(mailmod.set_category, body.get("key") or "", body.get("category") or "")


@router.post("/api/mail/categorize_many")
async def mail_categorize_many(req: Request):
    body = await req.json()
    return _mail_call(mailmod.set_category_many, body.get("keys") or [], body.get("category") or "")


@router.post("/api/mail/ms_login")
async def mail_ms_login(req: Request):
    body = await req.json()
    return await asyncio.to_thread(_mail_call, mailmod.ms_login_start, body.get("email") or "")


@router.get("/api/mail/ms_poll")
def mail_ms_poll(email: str):
    return _mail_call(mailmod.ms_poll, email)
