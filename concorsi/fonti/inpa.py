"""inPA - Portale del reclutamento (www.inpa.gov.it).

È la fonte principale: dal 2023 le PA centrali e (quasi tutte) quelle locali devono pubblicare
qui i bandi. Il sito usa un'API REST pubblica, senza autenticazione:

  POST {api}/search-better?page=N&size=100    body: {"text": "", "status": ["OPEN"]}
       -> pagina Spring {content: [...], totalElements, totalPages, last}
       campi: id, codice, titolo, descrizioneBreve, figuraRicercata, dataPubblicazione,
              dataScadenza, numPosti, entiRiferimento[str], sedi[str], settori[str], categorie[str]
  GET  {api}/{id}  -> dettaglio: requisitiSpecifici, descrizione, company.name, linkSitoPA...

"status" deve essere una LISTA (con una stringa il server risponde 500).
"""
from __future__ import annotations

import logging

from ..http import FonteError, Http
from ..modelli import Bando
from ..testo import data_iso, indovina_posti, pulisci

log = logging.getLogger("concorsi")

API = "https://portale.inpa.gov.it/concorsi-smart/api/concorso-public-area"
MEDIA = "https://portale.inpa.gov.it/api/media/{id}"
PAGINA_BANDO = "https://www.inpa.gov.it/bandi-e-avvisi/dettaglio-bando-avviso/?concorso_id={id}"


class Inpa:
    tipo = "inpa"

    def __init__(self, nome: str, cfg: dict, http: Http):
        self.nome = nome
        self.cfg = cfg
        self.http = http
        self.api = cfg.get("api", API)

    def normalizza(self, raw: dict) -> Bando:
        enti = raw.get("entiRiferimento") or []
        sedi = raw.get("sedi") or []
        posti = raw.get("numPosti")
        titolo = pulisci(raw.get("titolo"))
        profilo = [pulisci(raw.get("figuraRicercata")), pulisci(" ".join(raw.get("settori") or []))]
        return Bando(
            id=f"inpa:{raw['id']}",
            fonte=self.nome,
            titolo=titolo,
            url=PAGINA_BANDO.format(id=raw["id"]),
            ente=pulisci(enti[0]) if enti else "",
            profilo=" · ".join(x for x in profilo if x),
            testo=pulisci(raw.get("descrizioneBreve")),
            sede=", ".join(sedi[:3]),
            pubblicazione=data_iso(raw.get("dataPubblicazione")),
            scadenza=data_iso(raw.get("dataScadenza")),
            posti=int(posti) if isinstance(posti, (int, float)) and posti > 0 else indovina_posti(titolo),
            documento=MEDIA.format(id=raw["allegatoMediaId"]) if raw.get("allegatoMediaId") else "",
        )

    def cerca(self) -> list[Bando]:
        escluse = {c.lower() for c in self.cfg.get("categorie_escluse", [])}
        dim = self.cfg.get("dimensione_pagina", 100)
        body = {"text": self.cfg.get("testo_ricerca", ""), "status": ["OPEN"]}
        out: list[Bando] = []
        for pagina in range(self.cfg.get("max_pagine", 40)):
            dati = self.http.post_json(f"{self.api}/search-better?page={pagina}&size={dim}", body).json()
            items = dati.get("content")
            if not isinstance(items, list):
                raise FonteError("risposta senza 'content': l'API inPA potrebbe essere cambiata")
            for raw in items:
                categorie = {c.lower() for c in raw.get("categorie") or []}
                if categorie & escluse:
                    continue
                try:
                    out.append(self.normalizza(raw))
                except (KeyError, TypeError, ValueError) as e:
                    log.warning("inPA: record scartato (%s): %s", raw.get("id"), e)
            if dati.get("last", True):
                break
        log.info("inPA: %d procedure aperte lette", len(out))
        return out

    def arricchisci(self, b: Bando) -> None:
        """Aggiunge requisiti e descrizione completa (una richiesta per bando: solo per i candidati)."""
        try:
            d = self.http.get(f"{self.api}/{b.id.split(':', 1)[1]}").json()
        except (FonteError, ValueError) as e:
            log.warning("inPA: dettaglio non disponibile per %s: %s", b.id, e)
            return
        nome_ente = (d.get("company") or {}).get("name")
        if nome_ente:
            b.ente = pulisci(nome_ente)
        allegati = sorted((a for a in d.get("allegati") or [] if a.get("mediaId")),
                          key=lambda a: (a.get("tipo") != "BANDO_CONCORSO", a.get("sequence") or 99))
        if allegati:
            b.documento = MEDIA.format(id=allegati[0]["mediaId"])
        dettagli = [pulisci(d.get("requisitiSpecifici")), pulisci(d.get("descrizione"))]
        b.testo = " ".join(x for x in [b.testo, *dettagli] if x)[:20000]
