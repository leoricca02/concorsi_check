from __future__ import annotations

import html
import re

MESI = {m: i for i, m in enumerate(
    ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
     "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1)}


def pulisci(s: str | None) -> str:
    """Toglie tag HTML, entità e spazi multipli."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def data_iso(s: str | None) -> str:
    """'2026-10-11T21:59:00Z' -> '2026-10-11'; stringhe non riconosciute -> ''."""
    if not s:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s))
    return m.group(1) if m else ""


def data_italiana(s: str) -> str:
    """Trova la prima data tipo '30 giugno 2026' o '30/06/2026' e la restituisce in formato ISO."""
    m = re.search(r"(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})", s)
    if m and m.group(2).lower() in MESI:
        return f"{m.group(3)}-{MESI[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


NUMERI = {"un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6,
          "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "quindici": 15,
          "venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50, "cento": 100}


def indovina_posti(titolo: str) -> int | None:
    t = titolo.lower()
    m = re.search(r"\b(?:n\.?\s*)?(\d{1,4})\s+(?:posti|post[oi]|unit[àa]|figure|assunzioni|funzionari|esperti)", t)
    if m:
        return int(m.group(1))
    parole = "|".join(sorted(NUMERI, key=len, reverse=True))
    m = re.search(r"\b(" + parole + r")\s+(?:posti|posto|unit[àa])", t)
    return NUMERI.get(m.group(1)) if m else None
