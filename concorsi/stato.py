"""Memoria tra un run e l'altro: quali bandi sono già stati visti/segnalati (data/stato.json)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .modelli import Bando


class Stato:
    def __init__(self, percorso: str | Path):
        self.percorso = Path(percorso)
        self.dati = {"ultimo_run": None, "fonti_inizializzate": [], "visti": {}, "segnalati": {},
                     "quasi": {}, "letti": {}}
        if self.percorso.exists():
            self.dati.update(json.loads(self.percorso.read_text(encoding="utf-8")))

    @property
    def primo_run(self) -> bool:
        return self.dati["ultimo_run"] is None

    def fonte_inizializzata(self, nome: str) -> bool:
        return nome in self.dati["fonti_inizializzate"]

    def segna_fonte_inizializzata(self, nome: str) -> None:
        if nome not in self.dati["fonti_inizializzate"]:
            self.dati["fonti_inizializzate"].append(nome)

    def gia_visto(self, id_: str) -> bool:
        return id_ in self.dati["visti"]

    def segna_visto(self, id_: str, oggi: date) -> None:
        self.dati["visti"].setdefault(id_, oggi.isoformat())

    def segna_segnalato(self, b: Bando, oggi: date) -> None:
        self.dati["segnalati"][b.id] = {**b.per_stato(), "segnalato_il": oggi.isoformat()}

    def ancora_aperti(self, oggi: date, esclusi: set[str]) -> list[Bando]:
        """Bandi segnalati nei run precedenti con scadenza non ancora passata."""
        out = []
        for id_, d in self.dati["segnalati"].items():
            if id_ in esclusi or (d.get("ai") or {}).get("esito") == "no":
                continue
            if d.get("scadenza") and d["scadenza"] >= oggi.isoformat():
                campi = {k: v for k, v in d.items() if k in Bando.__dataclass_fields__}
                out.append(Bando(**campi))
        return sorted(out, key=lambda b: b.scadenza)

    def pulisci(self, oggi: date, giorni: int = 400) -> None:
        """Dimentica le cose vecchie per non far crescere il file all'infinito."""
        limite = (oggi - timedelta(days=giorni)).isoformat()
        self.dati["visti"] = {k: v for k, v in self.dati["visti"].items() if v >= limite}
        self.dati["quasi"] = {k: v for k, v in self.dati["quasi"].items() if v >= limite}
        self.dati["segnalati"] = {
            k: v for k, v in self.dati["segnalati"].items()
            if (v.get("scadenza") or v.get("segnalato_il", "")) >= limite
        }

    def salva(self, oggi: date) -> None:
        self.dati["ultimo_run"] = oggi.isoformat()
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        self.percorso.write_text(json.dumps(self.dati, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                 encoding="utf-8")
