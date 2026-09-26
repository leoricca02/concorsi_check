"""Fonte generica: una pagina web (es. "Concorsi" di Banca d'Italia, CONSOB, ACN...).

Legge tutti i link della pagina (o solo quelli dentro `selettore`, se indicato) il cui testo
sembra un bando, e ogni link mai visto prima diventa un possibile nuovo concorso.
Va bene per qualunque sito senza API; se il sito cambia struttura, al peggio segnala
qualche link in più (o la fonte risulta "vuota" nel report).
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

from ..http import FonteError, Http
from ..modelli import Bando
from ..testo import indovina_posti, pulisci

# solo parole da bando: la materia (informatica, cyber...) la giudica poi la valutazione
FILTRO_LINK = (
    r"concors|selezion|\bband[oi]\b|avviso pubblico|assunzion|reclutament|interpello|"
    r"posizion[ei] (aperte|lavorativ)|manifestazione d.interesse|ricerca di personale"
)


class Pagina:
    tipo = "pagina"

    def __init__(self, nome: str, cfg: dict, http: Http):
        self.nome = nome
        self.cfg = cfg
        self.http = http
        if not cfg.get("url"):
            raise ValueError(f"fonte '{nome}': manca 'url'")
        self.filtro = re.compile(cfg.get("filtro_link", FILTRO_LINK), re.I)
        self.min_caratteri = cfg.get("min_caratteri", 20)

    def link(self, html: str) -> list[Bando]:
        soup = BeautifulSoup(html, "html.parser")
        radici = soup.select(self.cfg["selettore"]) if self.cfg.get("selettore") else [soup]
        ente = self.cfg.get("ente", self.nome)
        out: dict[str, Bando] = {}
        for radice in radici:
            for a in radice.find_all("a", href=True):
                href = urldefrag(urljoin(self.cfg["url"], a["href"].strip()))[0]
                if not href.startswith("http"):
                    continue
                testo = pulisci(a.get_text(" ") or a.get("title", ""))
                if len(testo) < self.min_caratteri or not self.filtro.search(testo):
                    continue
                chiave = hashlib.sha1(href.encode()).hexdigest()[:16]
                out.setdefault(chiave, Bando(
                    id=f"pagina:{self.nome}:{chiave}", fonte=self.nome, titolo=testo, url=href, ente=ente, sede=self.cfg.get("sede", ""),
                    posti=indovina_posti(testo),
                ))
        return list(out.values())

    def cerca(self) -> list[Bando]:
        trovati = self.link(self.http.get(self.cfg["url"]).text)
        if not trovati:
            raise FonteError("nessun link ai bandi trovato nella pagina: URL o struttura cambiati?")
        return trovati
