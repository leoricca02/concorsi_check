import json
from datetime import date

from conftest import HttpFinto, leggi

from concorsi import main as m
from concorsi.duplicati import stesso_bando, stesso_ente, trova_su_inpa
from concorsi.modelli import Bando
from concorsi.stato import Stato

OGGI = date(2026, 9, 26)


def b(id_, titolo, ente, posti=None, **kw):
    return Bando(id=id_, fonte="f", titolo=titolo, url="u", ente=ente, posti=posti, **kw)


def test_stesso_ente():
    assert stesso_ente("AGENZIA PER LA CYBERSICUREZZA NAZIONALE", "Agenzia per la Cybersicurezza Nazionale")
    assert stesso_ente("Banca d'Italia", "BANCA D'ITALIA - Servizio Risorse umane")
    assert stesso_ente("Università di Roma «La Sapienza»", "Universita' di Roma La Sapienza")
    assert not stesso_ente("Comune di Roma", "Comune di Milano")
    assert not stesso_ente("", "Comune di Roma")


def test_stesso_bando():
    gu = b("gu:1", "Concorso pubblico, per esami, per la copertura di venti posti di funzionario informatico, "
                   "area dei funzionari, a tempo pieno ed indeterminato.",
           "Agenzia per la Cybersicurezza Nazionale", 20)
    inpa = b("inpa:1", "Concorso per 20 funzionari informatici - area dei funzionari",
             "AGENZIA PER LA CYBERSICUREZZA NAZIONALE", 20, profilo="Funzionario informatico")
    altro = b("inpa:2", "Concorso per 20 funzionari amministrativi contabili",
              "Agenzia per la Cybersicurezza Nazionale", 20)
    altri_posti = b("inpa:3", inpa.titolo, inpa.ente, 5, profilo=inpa.profilo)
    assert stesso_bando(gu, inpa)
    assert not stesso_bando(gu, altro)
    assert not stesso_bando(gu, altri_posti)
    assert trova_su_inpa(gu, [altro, inpa]) is inpa
    assert trova_su_inpa(inpa, [inpa]) is None  # un bando inPA non si confronta con sé stesso


def test_doppione_gazzetta_inpa_segnalato_una_volta(config, tmp_path):
    # su inPA c'è lo stesso concorso ACN che la Gazzetta pubblica
    pagina = json.loads(leggi("inpa_pagina1.json"))
    pagina["content"].append({
        "id": "acn20", "titolo": "Concorso per venti posti di funzionario informatico, area dei funzionari",
        "figuraRicercata": "Funzionario informatico", "dataScadenza": "2026-10-26T21:59:00Z",
        "entiRiferimento": ["Agenzia per la Cybersicurezza Nazionale"], "sedi": ["Lazio", "Roma"],
        "categorie": ["Concorso"], "allegatoMediaId": "pdf-acn"})
    http = HttpFinto(
        post={"page=0": leggi("inpa_pagina0.json"), "page=1": json.dumps(pagina)},
        get={"caricaDettaglio": leggi("gu_sommario.html"), "30giorni/concorsi": leggi("gu_30giorni.html")})
    config["fonti"] = {"inpa": {"tipo": "inpa"}, "gu": {"tipo": "gazzetta", "fascicoli_primo_run": 1}}
    ris = m.esegui(config, Stato(tmp_path / "s.json"), http, OGGI)
    ids = [x.id for x in ris.nuovi]
    assert "inpa:acn20" in ids and "gu:26E01234" not in ids


def test_gazzetta_prende_il_pdf_da_inpa_se_inpa_non_lo_segnala(config, tmp_path):
    config["fonti"] = {"gu": {"tipo": "gazzetta", "fascicoli_primo_run": 1}}
    stato = Stato(tmp_path / "s.json")
    http = HttpFinto(get={"caricaDettaglio": leggi("gu_sommario.html"), "30giorni/concorsi": leggi("gu_30giorni.html")})
    gemello = b("inpa:acn20", "Funzionario informatico: venti posti", "Agenzia per la Cybersicurezza Nazionale", 20,
                documento="https://portale.inpa.gov.it/api/media/pdf-acn", sede="Lazio, Roma")
    orig = m.trova_su_inpa
    m.trova_su_inpa = lambda x, pool: gemello if x.id == "gu:26E01234" else None
    try:
        ris = m.esegui(config, stato, http, OGGI)
    finally:
        m.trova_su_inpa = orig
    acn = next(x for x in ris.nuovi if x.id == "gu:26E01234")
    assert acn.documento.endswith("pdf-acn") and acn.sede == "Nazionale"
