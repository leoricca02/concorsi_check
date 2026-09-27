"""Punto d'ingresso: `python -m concorsi` legge le fonti, valuta i bandi, salva lo stato e notifica."""
from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml

from . import dashboard, notifiche, report
from .ai import ErroreAI, Verificatore
from .duplicati import trova_su_inpa
from .fonti import TIPI
from .http import FonteError, Http
from .modelli import Bando
from .preferenze import Preferenze
from .stato import Stato
from .valutazione import Valutatore

log = logging.getLogger("concorsi")


@dataclass
class Risultato:
    nuovi: list[Bando] = field(default_factory=list)
    aperti: list[Bando] = field(default_factory=list)
    errori: dict[str, str] = field(default_factory=dict)
    letti: dict[str, int] = field(default_factory=dict)
    scartati_ai: list[Bando] = field(default_factory=list)
    quasi: list[Bando] = field(default_factory=list)
    in_scadenza: list[Bando] = field(default_factory=list)


def controlla_quantita(nome: str, letti: int, stato: Stato, ris: Risultato) -> None:
    """Se una fonte restituisce molte meno voci del solito, probabilmente il sito è cambiato."""
    prima = stato.dati["letti"].get(nome)
    if prima and prima >= 20 and letti < prima * 0.3:
        ris.errori[nome] = (f"lette solo {letti} voci (la volta scorsa {prima}): "
                            "il sito potrebbe essere cambiato")
    stato.dati["letti"][nome] = letti


def esegui(cfg: dict, stato: Stato, http: Http, oggi: date, pref: Preferenze | None = None) -> Risultato:
    pref = pref or Preferenze()
    val = Valutatore(cfg["profilo"], affinita=pref.affinita if pref.attivo else None)
    nascosti = pref.nascosti
    soglia_dettaglio = int(cfg["profilo"].get("soglia_dettaglio", 2))
    ris = Risultato()
    inpa: list[Bando] = []   # bandi inPA letti in questo run, per riconoscere i doppioni (inPA va letta per prima)
    for nome, fcfg in cfg["fonti"].items():
        if not fcfg.get("attiva", True):
            continue
        try:
            fonte = TIPI[fcfg["tipo"]](nome, fcfg, http)
            bandi = fonte.cerca(primo_run=stato.primo_run) if fcfg["tipo"] == "gazzetta" else fonte.cerca()
        except (FonteError, ValueError, KeyError, requests.RequestException) as e:
            log.error("fonte %s: %s", nome, e)
            ris.errori[nome] = str(e) or type(e).__name__
            continue
        ris.letti[nome] = len(bandi)
        if fcfg["tipo"] == "inpa":
            inpa += bandi
        controlla_quantita(nome, len(bandi), stato, ris)
        # Le pagine generiche al primo controllo contengono anche bandi vecchi: di default
        # li memorizziamo senza segnalarli, e da lì in poi segnaliamo solo i link nuovi.
        silenzioso = (fcfg["tipo"] == "pagina" and not stato.fonte_inizializzata(nome)
                      and not fcfg.get("segnala_al_primo_run", False))
        for b in bandi:
            if (b.id in stato.dati["segnalati"] or b.id in nascosti
                    or (b.scadenza and b.scadenza < oggi.isoformat())):
                continue
            gemello = trova_su_inpa(b, inpa)
            if gemello:
                if gemello.id in stato.dati["segnalati"] or gemello.id in nascosti:
                    continue          # già segnalato (ora o in passato) nella versione inPA
                # stesso bando su inPA ma non segnalato lì: prendiamo i dati migliori da inPA
                b.documento = gemello.documento or b.documento
                b.sede = b.sede or gemello.sede
                b.scadenza = b.scadenza or gemello.scadenza
            rilevante = val.valuta(b)
            if (hasattr(fonte, "arricchisci") and b.punteggio >= soglia_dettaglio
                    and not stato.gia_visto(b.id)):
                fonte.arricchisci(b)
                rilevante = val.valuta(b)
                stato.segna_visto(b.id, oggi)
            if rilevante:
                stato.segna_segnalato(b, oggi)
                if not silenzioso:
                    ris.nuovi.append(b)
            elif val.quasi_rilevante(b) and b.id not in stato.dati["quasi"]:
                stato.dati["quasi"][b.id] = oggi.isoformat()
                if not silenzioso:
                    ris.quasi.append(b)
        stato.segna_fonte_inizializzata(nome)
    ris.aperti = stato.ancora_aperti(oggi, esclusi={b.id for b in ris.nuovi} | nascosti)
    verifica_ai(cfg.get("ai") or {}, http, stato, ris, oggi, pref.esempi())
    ris.in_scadenza = in_scadenza(ris.nuovi + ris.aperti, oggi,
                                  int((cfg.get("notifiche") or {}).get("giorni_scadenza", 7)))
    stato.pulisci(oggi)
    return ris


def in_scadenza(bandi: list[Bando], oggi: date, giorni: int) -> list[Bando]:
    """Bandi rilevanti che scadono entro `giorni` giorni, dal più urgente."""
    limite = (oggi + timedelta(days=giorni)).isoformat()
    return sorted((b for b in bandi if b.scadenza and oggi.isoformat() <= b.scadenza <= limite),
                  key=lambda b: b.scadenza)


def verifica_ai(cfg: dict, http: Http, stato: Stato, ris: Risultato, oggi: date, esempi: str = "") -> None:
    """Fa leggere il bando completo a un modello AI e toglie quelli a cui il candidato non può partecipare."""
    ver = Verificatore(cfg, http, esempi) if cfg else None
    if not (ver and ver.attivo):
        return
    # prima i nuovi, poi quelli segnalati in passato rimasti senza verifica (errore o limite raggiunto)
    candidati = report.ordina(ris.nuovi) + [b for b in ris.aperti if b.ai is None]
    for b in candidati[: int(cfg.get("max_bandi_per_run", 40))]:
        try:
            b.ai = ver.verifica(b)
        except ErroreAI as e:
            log.error("verifica AI interrotta: %s", e)
            ris.errori["verifica AI"] = str(e)
            break
        stato.segna_segnalato(b, oggi)
    no = lambda b: bool(b.ai and b.ai["esito"] == "no")
    ris.scartati_ai = [b for b in ris.nuovi + ris.aperti if no(b)]
    ris.nuovi = [b for b in ris.nuovi if not no(b)]
    ris.aperti = [b for b in ris.aperti if not no(b)]


def notifica(cfg: dict, ris: Risultato, oggi: date) -> None:
    ncfg = cfg.get("notifiche", {})
    if not ris.nuovi and not ris.in_scadenza and not (ris.errori and ncfg.get("segnala_errori", True)) \
            and not ncfg.get("anche_senza_novita", False):
        log.info("niente di nuovo: nessuna notifica")
        return
    oggetto = f"Concorsi: {report.titolo(ris.nuovi, ris.in_scadenza)} ({oggi.strftime('%d/%m/%Y')})"
    testo = report.testo_semplice(ris.nuovi, ris.errori, oggi, ris.in_scadenza)
    for nome, invia in (("email", lambda: notifiche.email(oggetto, testo, report.html_email(
            ris.nuovi, ris.aperti, ris.errori, oggi, ris.in_scadenza))), ("telegram", lambda: notifiche.telegram(
                report.riepilogo_telegram(ris.nuovi, ris.errori, oggi, ris.in_scadenza),
                [(b.id, report.messaggio_bando(b)) for b in report.ordina(ris.nuovi)[:20]]))):
        try:
            if not invia():
                log.info("%s non configurato", nome)
        except Exception as e:  # una notifica fallita non deve far perdere lo stato
            log.error("invio %s fallito: %s", nome, e)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="concorsi", description="Controlla i nuovi concorsi pubblici.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--stato", default="data/stato.json")
    ap.add_argument("--report", default="reports/ultimo.md", help="dove scrivere il report Markdown")
    ap.add_argument("--preferenze", default="data/preferenze.json", help="i tuoi 👍/👎, scritti dalla pagina web")
    ap.add_argument("--pagina", default="docs/bandi.json", help="dati per la pagina web (GitHub Pages)")
    ap.add_argument("--issue-file", help="scrive qui un report accorciato per il corpo di una issue GitHub")
    ap.add_argument("--no-notifiche", action="store_true", help="non inviare email/Telegram")
    ap.add_argument("--prova", action="store_true", help="non salvare lo stato (i nuovi restano nuovi)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    stato = Stato(args.stato)
    oggi = date.today()
    pref = Preferenze(args.preferenze)
    ris = esegui(cfg, stato, Http(pausa=float(cfg.get("pausa_tra_richieste", 1.0))), oggi, pref)
    dashboard.scrivi(args.pagina, ris, oggi, pref)

    md = report.markdown(ris.nuovi, ris.aperti, ris.errori, oggi, ris.letti, ris.scartati_ai,
                         ris.quasi, ris.in_scadenza)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(md, encoding="utf-8")
    if args.issue_file:
        corpo = md if len(md) < 60000 else md[:60000] + "\n\n…(troncato, vedi reports/ultimo.md)"
        Path(args.issue_file).write_text(corpo, encoding="utf-8")
    if not args.no_notifiche:
        notifica(cfg, ris, oggi)
    if not args.prova:
        stato.salva(oggi)

    log.info("nuovi rilevanti: %d · ancora aperti: %d · fonti in errore: %d",
             len(ris.nuovi), len(ris.aperti), len(ris.errori))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"nuovi={len(ris.nuovi)}\nerrori={len(ris.errori)}\nin_scadenza={len(ris.in_scadenza)}\n"
                    f"titolo={report.titolo(ris.nuovi, ris.in_scadenza)}\n")
    # errore solo se TUTTE le fonti sono fallite: così il workflow diventa rosso e GitHub ti avvisa
    return 1 if ris.errori and not ris.letti else 0
