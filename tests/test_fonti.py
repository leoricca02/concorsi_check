import pytest

from concorsi.fonti import Gazzetta, Inpa, Pagina
from concorsi.http import FonteError
from conftest import HttpFinto, leggi

INPA_CFG = {"categorie_escluse": ["Avvisi di mobilità"]}


def http_inpa():
    return HttpFinto(
        post={"page=0": leggi("inpa_pagina0.json"), "page=1": leggi("inpa_pagina1.json")},
        get={"concorso-public-area/eee555": leggi("inpa_dettaglio_eee555.json")},
    )


def test_inpa_legge_tutte_le_pagine_e_salta_categorie_escluse():
    http = http_inpa()
    bandi = Inpa("inpa", INPA_CFG, http).cerca()
    ids = [b.id for b in bandi]
    assert ids == ["inpa:aaa111", "inpa:bbb222", "inpa:ddd444", "inpa:eee555", "inpa:fff666"]
    assert len([u for u in http.chiamate if "search-better" in u]) == 2


def test_inpa_normalizza_campi():
    b = Inpa("inpa", INPA_CFG, http_inpa()).cerca()[0]
    assert b.ente == "Banca d'Italia"
    assert b.scadenza == "2026-10-20"
    assert b.pubblicazione == "2026-09-20"
    assert b.posti == 30
    assert b.sede == "Lazio, Roma"
    assert "Esperto informatico" in b.profilo and "Informatica" in b.profilo
    assert b.url.endswith("concorso_id=aaa111")


def test_inpa_arricchisci_aggiunge_requisiti_e_ente():
    fonte = Inpa("inpa", INPA_CFG, http_inpa())
    b = [x for x in fonte.cerca() if x.id == "inpa:eee555"][0]
    fonte.arricchisci(b)
    assert "L-8" in b.testo and "<b>" not in b.testo
    assert b.ente.startswith("Regione Lazio")


def test_inpa_dettaglio_mancante_non_blocca():
    fonte = Inpa("inpa", INPA_CFG, http_inpa())
    b = fonte.cerca()[0]
    fonte.arricchisci(b)  # nessun dettaglio per aaa111: solo un warning
    assert b.ente == "Banca d'Italia"


def test_inpa_risposta_strana_e_un_errore_della_fonte():
    http = HttpFinto(post={"page=0": '{"errore": "manutenzione"}'})
    with pytest.raises(FonteError):
        Inpa("inpa", {}, http).cerca()


def test_gazzetta_fascicoli_piu_recenti_senza_duplicati():
    g = Gazzetta("gu", {}, HttpFinto())
    fasc = g.fascicoli(leggi("gu_30giorni.html"), 2)
    assert [d for _, d in fasc] == ["2026-09-25", "2026-09-22"]
    assert fasc[0][0].startswith("https://www.gazzettaufficiale.it/gazzetta/concorsi/caricaDettaglio?")
    assert "&amp;" not in fasc[0][0]


def test_gazzetta_atti_con_ente_scadenza_e_filtro_tipi():
    g = Gazzetta("gu", {}, HttpFinto())
    atti = {b.id: b for b in g.atti(leggi("gu_sommario.html"), "2026-09-25")}
    # DIARIO e MOBILITA' esclusi
    assert set(atti) == {"gu:26E01234", "gu:26E01240", "gu:26E01250"}
    acn = atti["gu:26E01234"]
    assert acn.ente == "Agenzia per la Cybersicurezza Nazionale"
    assert acn.scadenza == "2026-10-26"
    assert acn.posti == 20
    assert acn.titolo.endswith("indeterminato.")  # tolto "(26E01234) Pag. 1"
    assert atti["gu:26E01240"].ente == "Comune di Frosinone"
    assert atti["gu:26E01250"].ente.startswith("Universita' di Roma")
    assert atti["gu:26E01250"].posti == 2


def test_gazzetta_cerca_usa_piu_fascicoli_al_primo_run():
    http = HttpFinto(get={"caricaDettaglio": leggi("gu_sommario.html"), "30giorni/concorsi": leggi("gu_30giorni.html")})
    Gazzetta("gu", {"fascicoli": 1, "fascicoli_primo_run": 3}, http).cerca(primo_run=True)
    assert len([u for u in http.chiamate if "caricaDettaglio?" in u]) == 3


def test_gazzetta_pagina_cambiata_segnala_errore():
    g = Gazzetta("gu", {}, HttpFinto())
    with pytest.raises(FonteError):
        g.fascicoli("<html><body>Manutenzione</body></html>", 2)
    with pytest.raises(FonteError):
        g.atti("<html><body>nessun atto</body></html>", "2026-09-25")


def test_pagina_estrae_solo_i_link_ai_bandi():
    cfg = {"url": "https://www.bancaditalia.it/chi-siamo/lavorare-bi/informazioni-concorsi/bandi/index.html",
           "ente": "Banca d'Italia"}
    bandi = Pagina("bdi", cfg, HttpFinto()).link(leggi("pagina_bancaditalia.html"))
    assert len(bandi) == 2
    assert bandi[0].url == ("https://www.bancaditalia.it/chi-siamo/lavorare-bi/informazioni-concorsi/"
                            "2026/bando-30-esperti-informatici/index.html")
    assert bandi[1].url.endswith("bando-20-giuristi/index.html")  # senza "#top"
    assert bandi[0].posti == 30 and bandi[0].ente == "Banca d'Italia"
    # id stabile: stesso link -> stesso id
    assert bandi[0].id == Pagina("bdi", cfg, HttpFinto()).link(leggi("pagina_bancaditalia.html"))[0].id


def test_pagina_selettore_css():
    cfg = {"url": "https://example.org/", "selettore": "nav"}
    assert Pagina("x", cfg, HttpFinto()).link(leggi("pagina_bancaditalia.html")) == []


def test_pagina_senza_link_e_un_errore():
    http = HttpFinto(get={"example.org": "<html><body><p>Nessun concorso</p></body></html>"})
    with pytest.raises(FonteError):
        Pagina("x", {"url": "https://example.org/"}, http).cerca()
