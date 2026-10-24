"""Wach halten: Sperre nur, solange ein Lauf arbeitet, und freigeben, wenn er fertig ist."""
import asyncio
import sys

from server import runs, wachhalten


class _Lauf:
    done = False


def test_sperre_folgt_den_laeufen(monkeypatch):
    # Statt kde-inhibit ein Prozess, der nur wartet
    monkeypatch.setattr(wachhalten, "befehl",
                        lambda: [sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(wachhalten, "PRUEF_TAKT", 0.1)
    monkeypatch.setattr(wachhalten, "_kaputt", False)
    monkeypatch.setattr(runs, "RUNS", {})
    monkeypatch.setattr(wachhalten, "RUNS", runs.RUNS)

    async def ablauf():
        lauf = _Lauf()
        wachhalten.RUNS["x"] = lauf
        t = asyncio.create_task(wachhalten.wach_loop())
        await asyncio.sleep(2.5)
        proc = wachhalten._proc
        assert proc and proc.returncode is None
        lauf.done = True
        await asyncio.sleep(0.5)
        assert wachhalten._proc is None
        assert await asyncio.wait_for(proc.wait(), 3) is not None
        t.cancel()

    asyncio.run(ablauf())


def test_abschaltbar(monkeypatch):
    monkeypatch.setenv("CODY_WACH_HALTEN", "0")
    asyncio.run(asyncio.wait_for(wachhalten.wach_loop(), 1))   # kehrt sofort zurück
