import json
from datetime import date

from conftest import HttpFinto, leggi

from concorsi import main as m
from concorsi.modelli import Bando
from concorsi.preferenze import Preferenze
from concorsi.stato import Stato
from concorsi.valutazione import Valutatore

OGGI = date(2026, 9, 26)


def scrivi(tmp_path, voti):
    p = tmp_path / "pref.json"
    p.write_text(json.dumps({"voti": voti}), encoding="utf-8")
    return p


def v(voto, titolo, ente, data="2026-09-20"):
    return {"voto": voto, "titolo": titolo, "ente": ente, "profilo": "", "data": data}


VOTI = {
    "a": v("like", "Concorso per 10 data scientist", "CONSOB"),
    "b": v("like", "Esperti in data science e intelligenza artificiale", "Banca d'Italia"),
    "c": v("candidato", "Funzionari data analyst", "Istat"),
    "d": v("dislike", "Collaboratore tecnico professionale informatico", "ASL Roma 2"),
    "e": v("dislike", "Tecnico informatico supporto sistemistico", "ASL Roma 1"),
}


def test_file_assente_o_pochi_voti(tmp_path):
    assert not Preferenze(tmp_path / "manca.json").attivo
    assert Preferenze().voti == {}
    pochi = Preferenze(scrivi(tmp_path, {k: VOTI[k] for k in "abd"}))
    assert not pochi.attivo and pochi.affinita(Bando(id="x", fonte="f", titolo="data scientist", url="u")) == 0
    solo_like = Preferenze(scrivi(tmp_path, {k: dict(VOTI[k], voto="like") for k in VOTI}))
    assert not solo_like.attivo


def test_affinita_segue_i_gusti(tmp_path):
    p = Preferenze(scrivi(tmp_path, VOTI))
    assert p.attivo and p.nascosti == {"d", "e"}
    simile = Bando(id="x", fonte="f", titolo="Concorso per 5 data scientist", url="u", ente="CONSOB")
    diverso = Bando(id="y", fonte="f", titolo="Collaboratore tecnico informatico", url="u", ente="ASL Roma 3")
    neutro = Bando(id="z", fonte="f", titolo="Ingegnere nucleare", url="u", ente="ENEA")
    assert p.affinita(simile) > 0 > p.affinita(diverso)
    assert p.affinita(neutro) == 0
    assert -4 <= p.affinita(diverso) and p.affinita(simile) <= 4


def test_bonus_nel_punteggio(tmp_path, config):
    p = Preferenze(scrivi(tmp_path, VOTI))
    b = Bando(id="x", fonte="f", titolo="Concorso per 5 data scientist", url="u", ente="CONSOB", sede="Roma")
    senza = Valutatore(config["profilo"])
    con = Valutatore(config["profilo"], affinita=p.affinita)
    senza.valuta(b)
    base = b.punteggio
    con.valuta(b)
    assert b.punteggio > base and "simile a bandi che ti sono piaciuti" in b.motivi[-1]


def test_esempi_per_ai(tmp_path):
    testo = Preferenze(scrivi(tmp_path, VOTI)).esempi()
    assert "Gli sono piaciuti:" in testo and "data scientist (CONSOB)" in testo
    assert "Non gli interessano:" in testo and "ASL Roma 1" in testo
    assert Preferenze().esempi() == ""


def test_dislike_nasconde_il_bando(tmp_path, config):
    config["fonti"] = {"inpa": {"tipo": "inpa"}}
    http = HttpFinto(post={"page=0": leggi("inpa_pagina0.json"), "page=1": leggi("inpa_pagina1.json")})
    pref = Preferenze(scrivi(tmp_path, {"inpa:aaa111": v("dislike", "BdI", "Banca d'Italia")}))
    stato = Stato(tmp_path / "s.json")
    ris = m.esegui(config, stato, http, OGGI, pref)
    assert "inpa:aaa111" not in {b.id for b in ris.nuovi}
    # anche se era stato segnalato prima, non compare più tra gli aperti
    stato.segna_segnalato(Bando(id="inpa:aaa111", fonte="f", titolo="t", url="u", scadenza="2026-12-01"), OGGI)
    ris = m.esegui(config, stato, http, OGGI, pref)
    assert "inpa:aaa111" not in {b.id for b in ris.aperti}


def test_profilo_dal_secret(monkeypatch):
    from concorsi.ai import Verificatore
    monkeypatch.setenv("PROFILO_CANDIDATO", "Profilo segreto LM-32")
    ver = Verificatore({"candidato": "profilo pubblico"}, HttpFinto(), esempi="Gli sono piaciuti:\n- X")
    prompt = ver.prompt(Bando(id="x", fonte="f", titolo="T", url="u"), "testo")
    assert "Profilo segreto LM-32" in prompt and "profilo pubblico" not in prompt
    assert "ESEMPI DEI SUOI GUSTI" in prompt and "- X" in prompt
