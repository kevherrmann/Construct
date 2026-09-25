"""API: externe KI-Anbieter, Bonsai und Ollama."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import bonsai as bonsaimod
import llm as llmmod

router = APIRouter()


# ---------- Externe KI-Anbieter (ChatGPT, Gemini, DeepSeek, Ollama) ----------
@router.get("/api/llm/providers")
def llm_providers(refresh: int = 0):
    """Anbieter + verfügbare Modelle (live abgefragt, gecacht) — ohne Keys."""
    return llmmod.public_providers(bool(refresh))


@router.post("/api/llm/providers")
async def llm_providers_save(req: Request):
    """Key/URL speichern bzw. Anbieter (de)aktivieren; testet direkt die Verbindung."""
    body = await req.json()
    pid = (body.get("id") or "").strip()
    if pid not in llmmod.PROVIDERS:
        return JSONResponse({"error": "unbekannter Anbieter"}, status_code=400)
    llmmod.save_provider(pid, api_key=body.get("api_key"),
                         base_url=body.get("base_url"), enabled=body.get("enabled"))
    if body.get("enabled") is False or not llmmod.is_configured(pid):
        return {"ok": True, "models": 0, "error": ""}
    models, err = await asyncio.to_thread(llmmod.list_remote_models, pid, True)
    return {"ok": not err, "models": len(models), "error": err}


# ---------- Bonsai: läuft der lokale Server gerade (= VRAM belegt)? ----------
@router.get("/api/bonsai/status")
def bonsai_status():
    return bonsaimod.status()


@router.post("/api/bonsai/stop")
def bonsai_stop():
    """VRAM sofort freigeben, ohne auf den Leerlauf-Wächter zu warten."""
    bonsaimod.stop()
    return bonsaimod.status()


# ---------- Ollama: lokale Modelle ansehen / laden / löschen ----------
@router.get("/api/ollama/models")
def ollama_models():
    """Installierte Modelle + Katalog + laufende Downloads + Install-Status."""
    out = {"installed": [], "catalog": llmmod.OLLAMA_CATALOG,
           "pulls": llmmod.ollama_pulls(), "error": ""}
    out.update(llmmod.ollama_install_status())   # bin (vorhanden?) + install (Fortschritt)
    try:
        out["installed"] = llmmod.ollama_installed()
        out["reachable"] = True
    except Exception as e:
        out["error"] = llmmod.friendly_error("ollama", e)
        out["reachable"] = False
    return out


@router.post("/api/ollama/install")
async def ollama_install():
    """Ollama herunterladen (offizielles Linux-Paket), entpacken und starten —
    bzw. nur starten, wenn es schon installiert ist. Läuft im Hintergrund."""
    return llmmod.ollama_install_start()


@router.post("/api/ollama/pull")
async def ollama_pull(req: Request):
    """Download starten — läuft server-seitig im Hintergrund weiter."""
    body = await req.json()
    try:
        return llmmod.ollama_pull_start(body.get("model") or "")
    except llmmod.LLMError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/api/ollama/pull_cancel")
async def ollama_pull_cancel(req: Request):
    body = await req.json()
    return {"cancelled": llmmod.ollama_pull_cancel(body.get("model") or "")}


@router.post("/api/ollama/delete")
async def ollama_delete(req: Request):
    body = await req.json()
    model = (body.get("model") or "").strip()
    try:
        await asyncio.to_thread(llmmod.ollama_delete, model)
    except llmmod.LLMError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": llmmod.friendly_error("ollama", e)}, status_code=400)
    return {"deleted": True, "model": model}
