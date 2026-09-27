"""Scrive docs/bandi.json: i bandi rilevanti ancora aperti, letti dalla pagina web (docs/index.html)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .preferenze import Preferenze

CAMPI = ("id", "titolo", "url", "ente", "sede", "scadenza", "pubblicazione", "posti", "laurea",
         "punteggio", "motivi", "ai", "fonte", "profilo")


def scrivi(percorso: str | Path, ris, oggi: date, pref: Preferenze) -> None:
    nuovi = {b.id for b in ris.nuovi}
    bandi = []
    for b in ris.nuovi + ris.aperti:
        d = {k: getattr(b, k) for k in CAMPI}
        d["nuovo"] = b.id in nuovi
        bandi.append(d)
    bandi.sort(key=lambda d: (d["scadenza"] or "9999", -d["punteggio"]))
    out = {"aggiornato": oggi.isoformat(), "bandi": bandi,
           "modello_attivo": pref.attivo, "voti_totali": len(pref.voti)}
    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    Path(percorso).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
