"""Assegna a ogni bando un punteggio di rilevanza rispetto al profilo definito in config.yaml.

Ogni regola ha un peso e una lista di espressioni regolari (senza distinzione maiuscole/minuscole):
se almeno una corrisponde, il peso viene sommato UNA volta. Le regole con `campo: titolo` guardano
solo titolo, ente e profilo ricercato (utile per le penalità: "istruttore", "operatore"... nei
requisiti compaiono spesso anche in bandi che vanno bene). Le regole con `escludi: true` scartano
il bando. Un bando è segnalato solo se il punteggio raggiunge la soglia E corrisponde ad almeno
una delle regole elencate in `richiesta_una_di` (la "materia": senza, anche un concorso da
avvocato con laurea magistrale passerebbe la soglia).

Dal testo lungo (requisiti, descrizione) vengono prima tolte le `frasi_da_ignorare`: quasi ogni
bando chiede "la conoscenza delle applicazioni informatiche più diffuse", e non significa che
sia un concorso da informatico.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .modelli import Bando


@dataclass
class Regola:
    nome: str
    peso: int
    pattern: list[re.Pattern]
    campo: str = "tutto"          # "tutto" | "titolo"
    escludi: bool = False
    laurea: str = ""              # etichetta del titolo di studio richiesto, se la regola lo rileva

    @classmethod
    def da_config(cls, d: dict) -> "Regola":
        return cls(
            nome=d["nome"], peso=int(d.get("peso", 0)),
            pattern=[re.compile(p, re.I) for p in d["pattern"]],
            campo=d.get("campo", "tutto"), escludi=bool(d.get("escludi", False)), laurea=d.get("laurea", ""),
        )

    def corrisponde(self, titolo: str, tutto: str) -> bool:
        testo = titolo if self.campo == "titolo" else tutto
        return any(p.search(testo) for p in self.pattern)


class Valutatore:
    def __init__(self, profilo: dict):
        self.regole = [Regola.da_config(r) for r in profilo["regole"]]
        self.soglia = int(profilo.get("soglia", 5))
        self.richieste = set(profilo.get("richiesta_una_di", []))
        sconosciute = self.richieste - {r.nome for r in self.regole}
        if sconosciute:
            raise ValueError(f"richiesta_una_di cita regole inesistenti: {sorted(sconosciute)}")
        self.ignora = [re.compile(p, re.I) for p in profilo.get("frasi_da_ignorare", [])]
        self.sedi = [re.compile(p, re.I) for p in profilo.get("sedi_ammesse", [])]
        self.margine = int(profilo.get("margine_quasi_rilevanti", 2))
        self.sedi_quasi = [re.compile(p, re.I) for p in profilo.get("sedi_quasi_rilevanti", [])]

    def sede_ammessa(self, b: Bando) -> bool:
        """Senza sede esplicita (es. Gazzetta) si cerca la città nel titolo e nel nome dell'ente."""
        dove = b.sede or f"{b.titolo} {b.ente}"
        return not self.sedi or any(p.search(dove) for p in self.sedi)

    def valuta(self, b: Bando) -> bool:
        """Calcola punteggio, motivi ed eventuale `esclusione`; True se il bando va segnalato."""
        titolo = f"{b.titolo} {b.ente} {b.profilo}"
        testo = b.testo
        for p in self.ignora:
            testo = p.sub(" ", testo)
        tutto = f"{titolo} {testo} {b.sede}"
        b.punteggio, b.motivi, b.laurea, b.esclusione = 0, [], "", ""
        lauree, trovate = [], set()
        for r in self.regole:
            if not r.corrisponde(titolo, tutto):
                continue
            if r.escludi:
                b.punteggio, b.motivi, b.esclusione = -99, [f"escluso: {r.nome}"], r.nome
                return False
            trovate.add(r.nome)
            b.punteggio += r.peso
            b.motivi.append(f"{r.nome} ({r.peso:+d})")
            if r.laurea:
                lauree.append(r.laurea)
        # se il bando cita sia magistrale sia triennale, basta la triennale
        for l in ("triennale", "qualsiasi", "magistrale"):
            if l in lauree:
                b.laurea = l
                break
        if self.richieste and not (trovate & self.richieste):
            b.esclusione = "materia"
        elif not self.sede_ammessa(b):
            b.esclusione = "sede"
        elif b.punteggio < self.soglia:
            b.esclusione = "soglia"
        return not b.esclusione

    def quasi_rilevante(self, b: Bando) -> bool:
        """Bando in materia scartato solo per la sede o per pochi punti: utile per controllare i filtri."""
        dove = b.sede or f"{b.titolo} {b.ente}"
        vicino = any(p.search(dove) for p in self.sedi_quasi)
        return ((b.esclusione == "sede" and vicino and b.punteggio >= self.soglia)
                or (b.esclusione == "soglia" and b.punteggio >= self.soglia - self.margine))
