import json
from datetime import date

from concorsi import main as m
from concorsi.stato import Stato
from conftest import HttpFinto, leggi

OGGI = date(2026, 9, 26)


def cfg_prova(config):
    config["fonti"] = {
        "inpa": {"tipo": "inpa", "categorie_escluse": ["Avvisi di mobilità"]},
        "gu": {"tipo": "gazzetta", "fascicoli": 1, "fascicoli_primo_run": 1},
        "bdi": {"tipo": "pagina", "url": "https://www.bancaditalia.it/bandi/index.html", "ente": "Banca d'Italia",
                "sede": "Roma"},
        "rotta": {"tipo": "pagina", "url": "https://sito-rotto.example/"},
    }
    return config


def http_tutto():
    return HttpFinto(
        post={"page=0": leggi("inpa_pagina0.json"), "page=1": leggi("inpa_pagina1.json")},
        get={
            "concorso-public-area/eee555": leggi("inpa_dettaglio_eee555.json"),
            "caricaDettaglio": leggi("gu_sommario.html"),  # prima: anche il suo URL contiene "30giorni"
            "30giorni/concorsi": leggi("gu_30giorni.html"),
            "bancaditalia": leggi("pagina_bancaditalia.html"),
        },
    )


def test_primo_run(config, tmp_path):
    stato = Stato(tmp_path / "stato.json")
    ris = m.esegui(cfg_prova(config), stato, http_tutto(), OGGI)
    ids = {b.id for b in ris.nuovi}
    # inPA: Banca d'Italia (titolo) e Regione Lazio (requisiti dal dettaglio); scaduto e legale esclusi
    assert {"inpa:aaa111", "inpa:eee555"} <= ids
    assert not {"inpa:bbb222", "inpa:ddd444", "inpa:fff666"} & ids
    # GU: ACN (amministrazione centrale) sì; istruttore a Frosinone e università no
    assert "gu:26E01234" in ids and not {"gu:26E01240", "gu:26E01250"} & ids
    # pagina generica al primo run: memorizzata ma non segnalata
    assert not any(i.startswith("pagina:") for i in ids)
    assert stato.fonte_inizializzata("bdi")
    # la fonte rotta è segnalata, le altre vanno avanti comunque
    assert set(ris.errori) == {"rotta"}
    assert ris.letti["inpa"] == 5


def test_secondo_run_niente_di_nuovo_poi_nuovo_link(config, tmp_path):
    cfg = cfg_prova(config)
    percorso = tmp_path / "stato.json"
    stato = Stato(percorso)
    m.esegui(cfg, stato, http_tutto(), OGGI)
    stato.salva(OGGI)

    stato = Stato(percorso)
    ris = m.esegui(cfg, stato, http_tutto(), OGGI)
    assert ris.nuovi == []
    assert {"inpa:aaa111", "gu:26E01234"} <= {b.id for b in ris.aperti}

    # la pagina di Banca d'Italia pubblica un nuovo bando informatico
    http = http_tutto()
    http.get_map["bancaditalia"] = leggi("pagina_bancaditalia.html").replace(
        "</ul>", '<li><a href="/bandi/2026/bando-15-cyber/index.html">Concorso per 15 Esperti in cybersecurity</a></li></ul>')
    ris = m.esegui(cfg, Stato(percorso), http, OGGI)
    assert [b.titolo for b in ris.nuovi] == ["Concorso per 15 Esperti in cybersecurity"]


def test_segnala_al_primo_run(config, tmp_path):
    cfg = cfg_prova(config)
    cfg["fonti"] = {"bdi": {**cfg["fonti"]["bdi"], "segnala_al_primo_run": True}}
    ris = m.esegui(cfg, Stato(tmp_path / "s.json"), http_tutto(), OGGI)
    assert [b.titolo for b in ris.nuovi] == [
        "Concorso per l'assunzione di 30 Esperti con orientamento nelle discipline informatiche"]


def test_dettaglio_inpa_scaricato_una_volta_sola(config, tmp_path):
    cfg = cfg_prova(config)
    cfg["fonti"] = {"inpa": cfg["fonti"]["inpa"]}
    percorso = tmp_path / "s.json"
    http = http_tutto()
    stato = Stato(percorso)
    m.esegui(cfg, stato, http, OGGI)
    stato.salva(OGGI)
    primi = [u for u in http.chiamate if "search-better" not in u]
    http.chiamate.clear()
    m.esegui(cfg, Stato(percorso), http, OGGI)
    assert primi and [u for u in http.chiamate if "search-better" not in u] == []


def test_main_scrive_report_stato_e_output(config, tmp_path, monkeypatch):
    import yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg_prova(config), allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(m, "Http", lambda **kw: http_tutto())
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    for k in ("EMAIL_USER", "EMAIL_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    codice = m.main(["--config", str(cfg_path), "--stato", str(tmp_path / "stato.json"),
                     "--report", str(tmp_path / "r.md"), "--issue-file", str(tmp_path / "issue.md")])
    assert codice == 0
    md = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "Nuovi concorsi rilevanti" in md and "Fonti con problemi" in md and "rotta" in md
    assert (tmp_path / "issue.md").read_text(encoding="utf-8") == md
    stato = json.loads((tmp_path / "stato.json").read_text(encoding="utf-8"))
    assert stato["ultimo_run"] and "inpa:aaa111" in stato["segnalati"]
    out = (tmp_path / "out.txt").read_text()
    assert "nuovi=" in out and "errori=1" in out


def test_main_codice_errore_se_tutte_le_fonti_falliscono(config, tmp_path, monkeypatch):
    import yaml
    config["fonti"] = {"rotta": {"tipo": "pagina", "url": "https://sito-rotto.example/"}}
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(m, "Http", lambda **kw: HttpFinto())
    assert m.main(["--config", str(cfg_path), "--stato", str(tmp_path / "s.json"),
                   "--report", str(tmp_path / "r.md"), "--no-notifiche"]) == 1
