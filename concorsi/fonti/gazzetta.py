"""Gazzetta Ufficiale - 4ª Serie Speciale «Concorsi ed Esami» (esce il martedì e il venerdì).

  indice ultimi 30 giorni: {base}/30giorni/concorsi
     -> link ai fascicoli: /gazzetta/concorsi/caricaDettaglio?dataPubblicazioneGazzetta=YYYY-MM-DD&numeroGazzetta=NN
  sommario del fascicolo: sezioni in maiuscolo (AMMINISTRAZIONI CENTRALI, ENTI DI RICERCA, ...), poi il nome
     dell'ente in maiuscolo e per ogni atto DUE link allo stesso URL .../caricaDettaglioAtto/originario?...codiceRedazionale=X:
     il primo con il tipo ("CONCORSO (scad. 30 giugno 2026)", "MOBILITA'", "DIARIO", ...), il secondo col titolo.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from ..http import FonteError, Http
from ..modelli import Bando
from ..testo import data_italiana, indovina_posti, pulisci

log = logging.getLogger("concorsi")

BASE = "https://www.gazzettaufficiale.it"
RE_FASCICOLO = re.compile(r"caricaDettaglio\?.*dataPubblicazioneGazzetta=(\d{4}-\d{2}-\d{2})")
RE_ATTO = re.compile(r"caricaDettaglioAtto.*codiceRedazionale=(\w+)")
SEZIONI = {
    "AMMINISTRAZIONI CENTRALI", "ENTI PUBBLICI STATALI", "ENTI DI RICERCA", "REGIONI", "ENTI LOCALI",
    "UNIVERSITA' ED ALTRI ISTITUTI DI ISTRUZIONE", "UNIVERSITÀ ED ALTRI ISTITUTI DI ISTRUZIONE",
    "AZIENDE SANITARIE LOCALI ED ALTRE ISTITUZIONI SANITARIE", "ALTRI ENTI", "DIARI", "AVVISI", "SOMMARIO",
}
# per gli atti di queste sezioni la sede non è nel sommario: di solito è a livello nazionale (spesso Roma)
SEZIONI_NAZIONALI = {"AMMINISTRAZIONI CENTRALI", "ENTI PUBBLICI STATALI", "ENTI DI RICERCA"}
TIPI_ESCLUSI = ("DIARIO", "AVVISO", "RETTIFICA", "GRADUATORIA", "MOBILIT", "ERRATA")


class Gazzetta:
    tipo = "gazzetta"

    def __init__(self, nome: str, cfg: dict, http: Http):
        self.nome = nome
        self.cfg = cfg
        self.http = http
        self.base = cfg.get("base", BASE)

    def fascicoli(self, html: str, quanti: int) -> list[tuple[str, str]]:
        """[(url_sommario, data)] degli ultimi `quanti` fascicoli, dal più recente."""
        soup = BeautifulSoup(html, "html.parser")
        visti: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            m = RE_FASCICOLO.search(a["href"])
            if m and m.group(1) not in visti:
                visti[m.group(1)] = urljoin(self.base + "/", a["href"])
        if not visti:
            raise FonteError("nessun fascicolo nell'indice degli ultimi 30 giorni: pagina GU cambiata?")
        return [(visti[d], d) for d in sorted(visti, reverse=True)[:quanti]]

    def atti(self, html: str, data_pub: str) -> list[Bando]:
        soup = BeautifulSoup(html, "html.parser")
        ente, sezione = "", ""
        atti: dict[str, dict] = {}
        for el in soup.descendants:
            if isinstance(el, Tag) and el.name == "a":
                m = RE_ATTO.search(el.get("href", ""))
                if not m:
                    continue
                codice, txt = m.group(1), pulisci(el.get_text(" "))
                if codice not in atti:
                    atti[codice] = {"tipo": txt, "titolo": "", "ente": ente, "sezione": sezione, "url": urljoin(self.base + "/", el["href"])}
                elif not atti[codice]["titolo"]:
                    atti[codice]["titolo"] = txt
            elif (isinstance(el, NavigableString) and not isinstance(el, Comment)
                  and el.parent.name not in ("script", "style") and el.find_parent("a") is None):
                t = pulisci(str(el))
                if len(t) < 4 or not any(c.isalpha() for c in t):
                    continue
                if t.upper() in SEZIONI:
                    ente, sezione = "", t.upper()
                elif t.isupper():
                    ente = t
        if not atti:
            raise FonteError(f"nessun atto nel sommario del {data_pub}: pagina GU cambiata?")
        out = []
        for codice, a in atti.items():
            tipo = a["tipo"].upper()
            if tipo.startswith(TIPI_ESCLUSI) or not a["titolo"]:
                continue
            titolo = re.sub(r"\s*\(\w+\)\s*Pag\.\s*\d+\s*$", "", a["titolo"])
            out.append(Bando(
                id=f"gu:{codice}", fonte=self.nome, titolo=titolo, url=a["url"], ente=_ente_leggibile(a["ente"]),
                sede="Nazionale" if a["sezione"] in SEZIONI_NAZIONALI else "",
                pubblicazione=data_pub, scadenza=data_italiana(tipo.lower()) if "SCAD" in tipo else "",
                posti=indovina_posti(titolo),
            ))
        return out

    def cerca(self, primo_run: bool = False) -> list[Bando]:
        quanti = self.cfg.get("fascicoli_primo_run", 8) if primo_run else self.cfg.get("fascicoli", 2)
        indice = self.http.get(f"{self.base}/30giorni/concorsi").text
        out: list[Bando] = []
        for url, data_pub in self.fascicoli(indice, quanti):
            trovati = self.atti(self.http.get(url).text, data_pub)
            log.info("GU %s: %d atti", data_pub, len(trovati))
            out += trovati
        return out


MINUSCOLE = {"di", "del", "della", "dello", "dei", "degli", "delle", "e", "ed", "per", "la", "il", "a", "in", "al", "alla"}
SIGLE = {"asl", "aou", "irccs", "cnr", "inps", "inail", "istat", "enea", "infn", "asi", "ingv", "ispra", "crea", "inaf", "ats", "asst"}


def _ente_leggibile(s: str) -> str:
    """'AZIENDA SANITARIA LOCALE DI ROMA' -> 'Azienda Sanitaria Locale di Roma'."""
    if not s or not s.isupper():
        return s
    parole = []
    for i, w in enumerate(s.split()):
        lw = w.lower()
        parole.append(w.upper() if lw in SIGLE else lw if (lw in MINUSCOLE and i) else w.capitalize())
    return " ".join(parole)
