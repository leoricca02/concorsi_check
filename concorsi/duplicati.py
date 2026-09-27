"""Riconosce lo stesso concorso pubblicato su più fonti (Gazzetta, sito dell'ente, inPA).

Si preferisce la versione inPA: ha sede, scadenza precisa e il PDF completo del bando, che serve
alla verifica AI (la Gazzetta pubblica solo un avviso di poche righe).
Il confronto è volutamente prudente: stesso ente e titoli con molte parole significative in comune.
"""
from __future__ import annotations

import re
import unicodedata

from .modelli import Bando

VUOTE = {
    "concorso", "pubblico", "pubblica", "selezione", "bando", "avviso", "esami", "titoli", "colloquio",
    "copertura", "posti", "posto", "unita", "tempo", "pieno", "parziale", "indeterminato", "determinato",
    "assunzione", "profilo", "professionale", "categoria", "area", "della", "delle", "degli", "dello",
    "nella", "nelle", "presso", "ruolo", "personale", "procedura", "comparativa", "anni", "durata",
}


def parole(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) >= 4 and w not in VUOTE}


def _simili(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def stesso_ente(a: str, b: str) -> bool:
    pa, pb = parole(a), parole(b)
    return bool(pa and pb) and (pa <= pb or pb <= pa or _simili(pa, pb) >= 0.6)


def stesso_bando(a: Bando, b: Bando, soglia: float = 0.4) -> bool:
    if not stesso_ente(a.ente, b.ente):
        return False
    if a.posti and b.posti and a.posti != b.posti:
        return False
    return _simili(parole(f"{a.titolo} {a.profilo}"), parole(f"{b.titolo} {b.profilo}")) >= soglia


def trova_su_inpa(b: Bando, inpa: list[Bando]) -> Bando | None:
    """Il bando inPA corrispondente a `b` (di Gazzetta o di una pagina), se c'è."""
    if b.id.startswith("inpa:"):
        return None
    return next((x for x in inpa if stesso_bando(b, x)), None)
