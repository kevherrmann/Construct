"""Teile-Beschaffung: Stueckliste rein, optimierte Einkaufsliste raus.

Arbeitsteilung mit Cody (das ist der Punkt der ganzen Uebung):

  Cody sucht und entscheidet   -> welches Produkt ist das richtige Teil,
                                  was kostet es, wie viele sind in der Packung
  Python rechnet und merkt     -> Warenkorb-Aufteilung inkl. Versandkosten,
                                  Freigrenzen, Mindestbestellwerte; und die
                                  SQLite-DB, damit die Handarbeit genau einmal
                                  anfaellt

Der Optimizer ist formal ein Set-Cover mit Fixkosten pro Shop. Brute Force ueber
alle Shop-Teilmengen, 2^n bei n<=20, in Millisekunden. Der Trick ist nicht die
Suche, sondern die Kostenfunktion: bei Kleinteilen dominieren Versand und
Packungsgroessen den Gesamtpreis vollstaendig. Ein Teil fuer 2 EUR bei einem
siebten Haendler kostet real 8 EUR.

Shops werden NICHT vorkonfiguriert. Cody legt sie beim Suchen an; die
Konditionen (Versand, Freigrenze) traegt er ein, soweit er sie findet, und
Kevin korrigiert sie in der Oberflaeche.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

DB_PATH = Path(__file__).parent / "parts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id          INTEGER PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS part (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    raw         TEXT NOT NULL,          -- Originalzeile
    name        TEXT NOT NULL,
    spec        TEXT,                   -- Groesse, Material, Kennwerte
    qty         INTEGER NOT NULL DEFAULT 1,
    optional    INTEGER NOT NULL DEFAULT 0,
    note        TEXT,                   -- Codys Hinweis, z.B. "Welle pruefen!"
    pos         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (project_id, raw)
);

-- Konditionen je Shop. Die entscheiden den Vergleich staerker als Stueckpreise.
CREATE TABLE IF NOT EXISTS shop (
    id               INTEGER PRIMARY KEY,
    key              TEXT NOT NULL UNIQUE,   -- klein, ohne Leerzeichen
    name             TEXT NOT NULL,
    url              TEXT,
    shipping         REAL NOT NULL DEFAULT 0,
    free_shipping_at REAL,                   -- NULL = nie versandkostenfrei
    min_order        REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS offer (
    id          INTEGER PRIMARY KEY,
    part_id     INTEGER NOT NULL REFERENCES part(id) ON DELETE CASCADE,
    shop_id     INTEGER NOT NULL REFERENCES shop(id) ON DELETE CASCADE,
    sku         TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL,
    url         TEXT NOT NULL DEFAULT '',
    price       REAL NOT NULL,          -- pro Packung, brutto
    pack_size   INTEGER NOT NULL DEFAULT 1,
    note        TEXT,                   -- "39,6 mm statt 37 mm -- Halterung pruefen"
    available   INTEGER NOT NULL DEFAULT 1,  -- 0 = nicht lieferbar, zaehlt nicht
    stock_text  TEXT,                   -- "ab Lager, 1-2 Werktage" / "ausverkauft"
    confirmed   INTEGER NOT NULL DEFAULT 1,
    found_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (part_id, shop_id, sku, title)
);

CREATE INDEX IF NOT EXISTS idx_offer_part ON offer(part_id);
CREATE INDEX IF NOT EXISTS idx_part_proj  ON part(project_id);
"""


# Spalten, die spaeter dazukamen. `CREATE TABLE IF NOT EXISTS` fasst bestehende
# Tabellen nicht an -- eine gewachsene DB muss sie trotzdem bekommen, ohne dass
# die muehsam recherchierten Angebote verloren gehen.
_MIGRATIONS = [
    ("offer", "available", "ALTER TABLE offer ADD COLUMN available INTEGER NOT NULL DEFAULT 1"),
    ("offer", "stock_text", "ALTER TABLE offer ADD COLUMN stock_text TEXT"),
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for table, column, ddl in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and column not in cols:
            conn.execute(ddl)
    conn.commit()
    return conn


# ---------------------------------------------------------------- Stueckliste

_QTY = re.compile(r"[x×]\s*(\d+)\b|\b(\d+)\s*[x×](?!\w)", re.I)
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s*")
_TRAIL = re.compile(r"[\s\-–—,;:]+$")


def _balance_parens(s: str) -> str:
    """Die Mengenangabe steht oft hinter einer Klammer -- beim Rausschneiden
    bleiben halbe Paare stehen. "M3 Bolt (10mm length" -> "...length)".
    """
    s = s.lstrip(") ").strip()
    if s.count("(") > s.count(")"):
        s += ")"
    while s.count(")") > s.count("(") and s.endswith(")"):
        s = s[:-1].strip()
    return s.strip()


def parse_bom(text: str) -> list[dict]:
    """Freitext-Stueckliste grob zerlegen.

    Bewusst duemmlich: Cody raeumt beim Suchen auf, was hier schiefgeht -- er
    liest die Originalzeile ja mit. Ein LLM-Aufruf schon an dieser Stelle waere
    ein zweiter Roundtrip fuer nichts.
    """
    items, seen = [], set()
    for line in text.splitlines():
        line = _BULLET.sub("", line).strip()
        if not line or line.startswith("#") or len(line) < 3:
            continue

        m = _QTY.search(line)
        qty = int(m.group(1) or m.group(2)) if m else 1
        name = _TRAIL.sub("", _QTY.sub("", line).strip())
        # "(optional)" markiert das Teil und fliegt aus dem Namen
        optional = bool(re.search(r"\boptional\b", name, re.I))
        name = _TRAIL.sub("", re.sub(r"\(?\s*optional\s*\)?", "", name, flags=re.I).strip())
        name = _balance_parens(name)
        if not name:
            continue
        if line in seen:
            continue
        seen.add(line)
        items.append({"raw": line, "name": name, "qty": max(qty, 1),
                      "optional": optional})
    return items


def create_project(conn, slug: str, name: str, text: str) -> dict:
    items = parse_bom(text)
    if not items:
        raise ValueError("Keine Teile erkannt. Eine Zeile pro Bauteil, "
                         "Menge z.B. als 'x14'.")

    conn.execute("INSERT OR IGNORE INTO project (slug, name) VALUES (?,?)",
                 (slug, name or slug))
    pid = conn.execute("SELECT id FROM project WHERE slug=?", (slug,)).fetchone()["id"]

    for i, it in enumerate(items):
        conn.execute(
            """INSERT INTO part (project_id, raw, name, spec, qty, optional, pos)
               VALUES (?,?,?,NULL,?,?,?)
               ON CONFLICT(project_id, raw) DO UPDATE SET
                 name=excluded.name, qty=excluded.qty, pos=excluded.pos""",
            (pid, it["raw"], it["name"], it["qty"], int(it["optional"]), i),
        )
    conn.commit()
    return {"slug": slug, "teile": len(items)}


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "shop"


def upsert_shop(conn, name: str, url: str = "", shipping: float = 0.0,
                free_shipping_at: float | None = None, min_order: float = 0.0,
                key: str | None = None) -> int:
    """Shop anlegen oder aktualisieren. -> shop_id

    Beim Aktualisieren gewinnen gesetzte Werte; 0/None laesst den Bestand
    stehen, damit ein spaeterer Fund die von Hand korrigierten Versandkosten
    nicht wieder plattmacht.
    """
    k = _slugify(key or name)
    row = conn.execute("SELECT * FROM shop WHERE key=?", (k,)).fetchone()
    if row is None:
        cur = conn.execute(
            """INSERT INTO shop (key, name, url, shipping, free_shipping_at, min_order)
               VALUES (?,?,?,?,?,?)""",
            (k, name or k, url, shipping or 0.0, free_shipping_at, min_order or 0.0),
        )
        conn.commit()
        return cur.lastrowid

    conn.execute(
        """UPDATE shop SET name=?, url=COALESCE(NULLIF(?,''), url),
             shipping=CASE WHEN ?>0 THEN ? ELSE shipping END,
             free_shipping_at=COALESCE(?, free_shipping_at),
             min_order=CASE WHEN ?>0 THEN ? ELSE min_order END
           WHERE id=?""",
        (name or row["name"], url, shipping, shipping, free_shipping_at,
         min_order, min_order, row["id"]),
    )
    conn.commit()
    return row["id"]


def add_offer(conn, part_id: int, shop_id: int, title: str, price: float,
              url: str = "", sku: str = "", pack_size: int = 1,
              note: str = "", available: bool = True, stock_text: str = "") -> int:
    if price is None or price <= 0:
        raise ValueError("Preis muss groesser als 0 sein.")
    cur = conn.execute(
        """INSERT INTO offer (part_id, shop_id, sku, title, url, price, pack_size,
                              note, available, stock_text)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(part_id, shop_id, sku, title) DO UPDATE SET
             url=excluded.url, price=excluded.price,
             pack_size=excluded.pack_size, note=excluded.note,
             available=excluded.available, stock_text=excluded.stock_text,
             found_at=datetime('now')""",
        (part_id, shop_id, sku or "", title, url or "", float(price),
         max(int(pack_size or 1), 1), note or "", int(bool(available)),
         stock_text or ""),
    )
    conn.commit()
    return cur.lastrowid


# ------------------------------------------------------------------ Optimizer

@dataclass(frozen=True)
class Part:
    id: int
    name: str
    qty: int
    optional: bool


@dataclass(frozen=True)
class Shop:
    id: int
    key: str
    name: str
    shipping: float
    free_shipping_at: float | None
    min_order: float


@dataclass(frozen=True)
class Offer:
    id: int
    part_id: int
    shop_id: int
    sku: str
    title: str
    url: str
    price: float
    pack_size: int
    note: str

    def packs_for(self, qty: int) -> int:
        return -(-qty // self.pack_size)          # ceil

    def cost_for(self, qty: int) -> float:
        return round(self.packs_for(qty) * self.price, 2)


@dataclass
class Line:
    part: Part
    offer: Offer
    packs: int
    cost: float


@dataclass
class Basket:
    shop: Shop
    lines: list[Line] = field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return round(sum(l.cost for l in self.lines), 2)

    @property
    def shipping(self) -> float:
        f = self.shop.free_shipping_at
        if f is not None and self.subtotal >= f:
            return 0.0
        return self.shop.shipping

    @property
    def total(self) -> float:
        return round(self.subtotal + self.shipping, 2)

    @property
    def below_min_order(self) -> bool:
        return self.subtotal < self.shop.min_order


@dataclass
class Solution:
    baskets: list[Basket]
    missing: list[Part]
    skipped: list[Part]        # optionale Teile, die nicht mitgekauft wurden

    @property
    def total(self) -> float:
        return round(sum(b.total for b in self.baskets), 2)

    @property
    def shipping_total(self) -> float:
        return round(sum(b.shipping for b in self.baskets), 2)


def _assign(parts, offers, shops, allowed, pflicht, skip_optional):
    """Jedes Teil dem guenstigsten Angebot innerhalb der erlaubten Shops zuordnen.

    Greedy ist hier exakt: bei fester Shop-Auswahl stehen die Versandkosten
    schon fest, also ist teilweise Minimierung global optimal.
    """
    baskets: dict[int, Basket] = {}
    missing: list[Part] = []

    for part in parts:
        if part.optional and skip_optional:
            continue
        cands = [o for o in offers.get(part.id, []) if o.shop_id in allowed]
        if not cands:
            if not part.optional or part.id in pflicht:
                missing.append(part)
            continue
        best = min(cands, key=lambda o: o.cost_for(part.qty))
        b = baskets.setdefault(best.shop_id, Basket(shop=shops[best.shop_id]))
        b.lines.append(Line(part=part, offer=best,
                            packs=best.packs_for(part.qty),
                            cost=best.cost_for(part.qty)))
    return baskets, missing


def optimize(parts: list[Part], offers: dict[int, list[Offer]], shops: list[Shop],
             max_shops: int | None = None, enforce_min_order: bool = True,
             include_optional: bool = True, top_n: int = 3) -> list[Solution]:
    """Beste `top_n` Loesungen, aufsteigend nach Gesamtpreis.

    `include_optional` kauft optionale Teile mit und laesst sie die Shop-Auswahl
    beeinflussen -- aber nur die, fuer die es ueberhaupt ein Angebot gibt.
    Ohne das verschwinden sie systematisch: eine Auswahl ohne den Kamera-
    Haendler ist immer billiger als eine mit, und billiger gewinnt.
    """
    shop_map = {s.id: s for s in shops}
    pflicht = ({p.id for p in parts if p.optional and offers.get(p.id)}
               if include_optional else set())
    skip_optional = not include_optional

    relevant = sorted({o.shop_id for lst in offers.values() for o in lst} & shop_map.keys())
    pflichtteile = [p for p in parts if not p.optional or p.id in pflicht]

    if not relevant:
        return [Solution(baskets=[], missing=pflichtteile, skipped=[])]
    if len(relevant) > 20:
        raise ValueError(f"{len(relevant)} Shops sind zu viele fuer Brute Force. "
                         "Erst ausduennen.")

    limit = min(max_shops or len(relevant), len(relevant))
    solutions: list[Solution] = []
    best_missing: list[Part] | None = None

    for k in range(1, limit + 1):
        for subset in combinations(relevant, k):
            allowed = set(subset)
            baskets, missing = _assign(parts, offers, shop_map, allowed,
                                       pflicht, skip_optional)
            if missing:
                if best_missing is None or len(missing) < len(best_missing):
                    best_missing = missing
                continue

            active = [b for b in baskets.values() if b.lines]
            if len(active) != k:
                continue      # gleicht einer kleineren Teilmenge, schon geprueft
            if enforce_min_order and any(b.below_min_order for b in active):
                continue

            gekauft = {l.part.id for b in active for l in b.lines}
            solutions.append(Solution(
                baskets=active, missing=[],
                skipped=[p for p in parts if p.optional and p.id not in gekauft],
            ))

    if not solutions:
        return [Solution(baskets=[], missing=best_missing or pflichtteile, skipped=[])]

    solutions.sort(key=lambda s: (s.total, len(s.baskets)))
    return solutions[:top_n]


# --------------------------------------------------------------------- Laden

def load_project(conn, slug: str) -> dict | None:
    proj = conn.execute("SELECT * FROM project WHERE slug=?", (slug,)).fetchone()
    if proj is None:
        return None

    parts = list(conn.execute(
        "SELECT * FROM part WHERE project_id=? ORDER BY pos, id", (proj["id"],)))
    shops = {s["id"]: dict(s) for s in conn.execute("SELECT * FROM shop")}

    by_part: dict[int, list[dict]] = {}
    if parts:
        ph = ",".join("?" * len(parts))
        for r in conn.execute(
                f"""SELECT * FROM offer WHERE part_id IN ({ph})
                    ORDER BY confirmed DESC, price ASC""",
                [p["id"] for p in parts]):
            o = dict(r)
            sh = shops.get(r["shop_id"], {})
            o["shop"] = sh.get("name", "?")
            o["shop_key"] = sh.get("key", "")
            qty = next(p["qty"] for p in parts if p["id"] == r["part_id"])
            o["available"] = bool(r["available"])
            o["packs"] = -(-qty // max(r["pack_size"], 1))
            o["cost"] = round(o["packs"] * r["price"], 2)
            by_part.setdefault(r["part_id"], []).append(o)

    # Nur Shops zeigen, die in DIESEM Projekt vorkommen. Die Shop-Tabelle ist
    # projektuebergreifend; ungefiltert stuenden dort irgendwann 20 Haendler,
    # von denen 18 mit dieser Stueckliste nichts zu tun haben.
    benutzt = {o["shop_id"] for lst in by_part.values() for o in lst}

    return {
        "slug": proj["slug"], "name": proj["name"],
        "parts": [{**dict(p), "optional": bool(p["optional"]),
                   "offers": by_part.get(p["id"], [])} for p in parts],
        "shops": sorted((s for sid, s in shops.items() if sid in benutzt),
                        key=lambda s: s["name"].lower()),
    }


def _rows_for_optimizer(conn, slug: str):
    proj = conn.execute("SELECT id FROM project WHERE slug=?", (slug,)).fetchone()
    if proj is None:
        return None, None, None

    parts = [Part(id=r["id"], name=r["name"], qty=r["qty"], optional=bool(r["optional"]))
             for r in conn.execute(
                 "SELECT * FROM part WHERE project_id=? ORDER BY pos, id", (proj["id"],))]
    shops = [Shop(id=r["id"], key=r["key"], name=r["name"], shipping=r["shipping"],
                  free_shipping_at=r["free_shipping_at"], min_order=r["min_order"])
             for r in conn.execute("SELECT * FROM shop")]

    offers: dict[int, list[Offer]] = {}
    if parts:
        ph = ",".join("?" * len(parts))
        # Nur lieferbare Angebote. Ein Link auf ein ausverkauftes Produkt ist
        # wertlos -- lieber "kein Angebot" melden als einen toten Warenkorb.
        for r in conn.execute(
                f"""SELECT * FROM offer WHERE part_id IN ({ph})
                    AND confirmed=1 AND available=1""",
                [p.id for p in parts]):
            offers.setdefault(r["part_id"], []).append(Offer(
                id=r["id"], part_id=r["part_id"], shop_id=r["shop_id"], sku=r["sku"],
                title=r["title"], url=r["url"], price=r["price"],
                pack_size=max(r["pack_size"], 1), note=r["note"] or ""))
    return parts, offers, shops


def plan(conn, slug: str, max_shops=None, include_optional=True,
         ignore_min_order=False, alternatives=3) -> dict | None:
    parts, offers, shops = _rows_for_optimizer(conn, slug)
    if parts is None:
        return None

    sols = optimize(parts, offers, shops, max_shops=max_shops,
                    enforce_min_order=not ignore_min_order,
                    include_optional=include_optional,
                    top_n=max(alternatives, 1))

    def js(sol: Solution) -> dict:
        return {
            "total": sol.total, "shipping_total": sol.shipping_total,
            "shop_count": len(sol.baskets),
            "baskets": [{
                "shop": b.shop.name, "shop_key": b.shop.key,
                "subtotal": b.subtotal, "shipping": b.shipping, "total": b.total,
                "fehlt_bis_frei": (round(b.shop.free_shipping_at - b.subtotal, 2)
                                   if b.shop.free_shipping_at
                                   and b.subtotal < b.shop.free_shipping_at else None),
                "lines": [{
                    "teil": l.part.name, "qty": l.part.qty, "packs": l.packs,
                    "cost": l.cost, "title": l.offer.title, "sku": l.offer.sku,
                    "url": l.offer.url, "pack_size": l.offer.pack_size,
                    "note": l.offer.note,
                } for l in sorted(b.lines, key=lambda x: -x.cost)],
            } for b in sorted(sol.baskets, key=lambda x: -x.total)],
            "missing": [{"name": p.name, "qty": p.qty} for p in sol.missing],
            "skipped": [{"name": p.name, "qty": p.qty} for p in sol.skipped],
        }

    return {"solutions": [js(s) for s in sols]}


def to_markdown(sol: dict, titel: str) -> str:
    out = [f"# {titel}", "",
           f"**Gesamt: {sol['total']:.2f} EUR** "
           f"({sol['shop_count']} Shops, davon {sol['shipping_total']:.2f} EUR Versand)", ""]
    for b in sol["baskets"]:
        out.append(f"## {b['shop']} — {b['total']:.2f} EUR")
        if b["shipping"]:
            zeile = f"*Versand {b['shipping']:.2f} EUR*"
            if b["fehlt_bis_frei"]:
                zeile += f" — noch {b['fehlt_bis_frei']:.2f} EUR bis versandkostenfrei"
            out.append(zeile)
        else:
            out.append("*Versandkostenfrei*")
        out += ["", "| Menge | Teil | Artikel | Preis |", "|---|---|---|---|"]
        for l in b["lines"]:
            art = f"[{l['title'][:55]}]({l['url']})" if l["url"] else l["title"][:55]
            out.append(f"| {l['packs']}× | {l['teil']} | {art} | {l['cost']:.2f} |")
        out.append("")
        for l in b["lines"]:
            if l["note"]:
                out.append(f"> ⚠ {l['teil']}: {l['note']}")
        out.append("")
    if sol["missing"]:
        out += ["## Nicht zuordenbar", ""]
        out += [f"- {m['qty']}× {m['name']}" for m in sol["missing"]] + [""]
    if sol["skipped"]:
        out += ["## Optional, nicht dabei", ""]
        out += [f"- {m['qty']}× {m['name']}" for m in sol["skipped"]] + [""]
    return "\n".join(out)
