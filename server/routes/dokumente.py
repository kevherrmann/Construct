"""API: Dokumente (Logik in server/dokumente/)."""
import asyncio
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from server import config as cfg
from server.dokumente import ablage, ocr, scanner

DATEI_MAX = 60 * 1024 * 1024
BILDER = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}


def _kachel_an():
    """Ist die Kachel aus, gibt es die Ablage nicht, auch nicht am Bildschirm vorbei."""
    if not cfg.load_settings()["tiles"].get("dokumente", False):
        raise HTTPException(status_code=404,
                            detail=cfg.L("Die Dokumente sind abgeschaltet", "Documents are switched off"))


router = APIRouter(prefix="/api/dokumente", dependencies=[Depends(_kachel_an)])


def _fehler(e: Exception):
    if isinstance(e, KeyError):
        return JSONResponse({"error": cfg.L("Gibt es nicht.", "Does not exist.")}, status_code=404)
    return JSONResponse({"error": str(e)}, status_code=400)


def _aufruf(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ablage.Fehler, KeyError) as e:
        return _fehler(e)


async def _body(req: Request) -> dict:
    try:
        b = await req.json()
    except Exception:
        return {}
    return b if isinstance(b, dict) else {}


def _zahl(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@router.get("/uebersicht")
def uebersicht():
    u = ablage.uebersicht()
    u["scanner"] = scanner.verfuegbar()
    return u


@router.get("")
def liste(q: str = "", jahr: str = "", absender: str = "", typ: str = "", tag: str = "",
          eingang: str = "", limit: int = 200, offset: int = 0):
    return ablage.liste(q=q, jahr=jahr, absender=_zahl(absender), typ=_zahl(typ), tag=_zahl(tag),
                        eingang=None if eingang == "" else eingang in ("1", "true"),
                        limit=limit, offset=offset)


@router.get("/namen/{tabelle}")
def namen(tabelle: str):
    return _aufruf(ablage.namen, tabelle)


@router.post("/namen/{tabelle}/{id_}")
async def namen_umbenennen(tabelle: str, id_: int, req: Request):
    b = await _body(req)
    return _aufruf(lambda: ablage.umbenennen(tabelle, id_, b.get("name", "")) or {"ok": True})


@router.delete("/namen/{tabelle}/{id_}")
def namen_entfernen(tabelle: str, id_: int):
    return _aufruf(lambda: ablage.entfernen(tabelle, id_) or {"ok": True})


@router.post("/hochladen")
async def hochladen(datei: UploadFile = File(...)):
    """PDF oder Foto. Jede Datei wird ein Dokument."""
    name = Path(datei.filename or "Dokument").name
    endung = Path(name).suffix.lower()
    if endung != ".pdf" and endung not in BILDER:
        return _fehler(ablage.Fehler(cfg.L("Nur PDF oder Bilder", "Only PDF or images")))
    inhalt = await datei.read(DATEI_MAX + 1)
    if len(inhalt) > DATEI_MAX:
        return _fehler(ablage.Fehler(cfg.L("Datei zu groß (max. 60 MB)", "File too large (max 60 MB)")))

    def aufnehmen():
        with tempfile.TemporaryDirectory() as tmp:
            roh = Path(tmp) / f"roh{endung}"
            roh.write_bytes(inhalt)
            pdf = Path(tmp) / "dok.pdf"
            if endung == ".pdf":
                roh.rename(pdf)
            else:
                ocr.bild_datei_zu_pdf(roh, pdf)
            return ablage.neu(pdf, titel=Path(name).stem, quelle="upload")
    try:
        return await asyncio.to_thread(aufnehmen)
    except (OSError, ValueError) as e:
        return _fehler(ablage.Fehler(str(e)))


# ---------- Scannen ----------

@router.get("/scan/geraete")
async def scan_geraete(frisch: int = 0):
    gs = await asyncio.to_thread(scanner.geraete, bool(frisch))
    return {"verfuegbar": scanner.verfuegbar(), "geraete": gs}


@router.post("/scan")
async def scan_start(req: Request):
    b = await _body(req)
    try:
        return await asyncio.to_thread(scanner.neu, str(b.get("geraet") or ""),
                                       str(b.get("quelle") or "auto"), bool(b.get("farbe")))
    except ablage.Fehler as e:
        return _fehler(e)


@router.get("/scan/{sid}")
def scan_stand(sid: str):
    try:
        return scanner.sitzung(sid).stand()
    except KeyError as e:
        return _fehler(e)


@router.post("/scan/{sid}/weiter")
async def scan_weiter(sid: str, req: Request):
    b = await _body(req)
    return _aufruf(scanner.weiter, sid, str(b.get("was") or ""))


@router.post("/scan/{sid}/fertig")
async def scan_fertig(sid: str, req: Request):
    b = await _body(req)
    try:
        z = b.get("zuordnung")
        zuordnung = [_zahl(x) or 0 for x in z] if isinstance(z, list) else None
        return {"dokumente": await asyncio.to_thread(scanner.abschliessen, sid, bool(b.get("einzeln")),
                                                     zuordnung)}
    except (ablage.Fehler, KeyError) as e:
        return _fehler(e)


@router.delete("/scan/{sid}")
def scan_abbrechen(sid: str):
    scanner.abbrechen(sid)
    return {"ok": True}


@router.get("/scan/{sid}/seite/{seite}/{n}")
def scan_seite(sid: str, seite: str, n: int):
    try:
        return Response(scanner.seitenbild(sid, seite, n), media_type="image/webp",
                        headers={"Cache-Control": "no-store"})
    except KeyError:
        raise HTTPException(status_code=404)


# ---------- Einzelnes Dokument (zuletzt: /{id_} würde sonst /scan und /hochladen schlucken) ----------

@router.get("/{id_}")
def dokument(id_: int):
    return _aufruf(ablage.dokument, id_)


@router.post("/{id_}")
async def aendern(id_: int, req: Request):
    return _aufruf(ablage.aendern, id_, await _body(req))


@router.post("/{id_}/teilen")
async def teilen(id_: int, req: Request):
    b = await _body(req)
    try:
        return {"dokumente": await asyncio.to_thread(ablage.teilen, id_, str(b.get("seiten") or ""))}
    except (ablage.Fehler, KeyError) as e:
        return _fehler(e)


@router.delete("/{id_}")
def loeschen(id_: int):
    return _aufruf(lambda: ablage.loeschen(id_) or {"ok": True})


@router.get("/{id_}/datei")
def datei(id_: int, download: int = 0):
    try:
        p = ablage.datei(id_)
    except KeyError:
        raise HTTPException(status_code=404)
    art = "attachment" if download else "inline"
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": f"{art}; filename*=UTF-8''{quote(p.name)}"})


@router.get("/{id_}/vorschau")
def vorschau(id_: int):
    p = ablage.vorschau(id_)
    if not p:
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type="image/webp")
