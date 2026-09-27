import pytest

from concorsi.modelli import Bando
from concorsi.valutazione import Valutatore


def bando(titolo, testo="", ente="", profilo="", sede="Lazio, Roma"):
    return Bando(id="x", fonte="t", titolo=titolo, url="u", ente=ente, testo=testo, profilo=profilo, sede=sede)


@pytest.fixture
def val(config):
    return Valutatore(config["profilo"])


@pytest.mark.parametrize("titolo,testo,ente", [
    ("Concorso per 30 Esperti con orientamento nelle discipline informatiche", "", "Banca d'Italia"),
    ("Concorso per 20 funzionari informatici, area dei funzionari, a tempo pieno ed indeterminato", "", ""),
    ("Concorso per 10 data scientist", "laurea magistrale in statistica o informatica", "CONSOB"),
    ("Concorso per 5 funzionari - area dei funzionari", "Laurea L-8 o LM-32", "Regione Lazio"),
    ("Concorso per 90 esperti tecnico-scientifici", "laurea magistrale", "Agenzia per la Cybersicurezza Nazionale"),
    ("Selezione per 4 laureati nelle discipline dell'ICT", "", "IVASS"),
])
def test_bandi_da_informatico_sono_segnalati(val, titolo, testo, ente):
    b = bando(titolo, testo, ente)
    assert val.valuta(b), (b.punteggio, b.motivi)


@pytest.mark.parametrize("titolo,testo", [
    # la frase standard sulle "applicazioni informatiche" non deve far scattare il profilo
    ("Concorso pubblico per n. 1 Funzionario Legale",
     "Laurea magistrale in giurisprudenza. Conoscenza dell'uso delle apparecchiature e delle "
     "applicazioni informatiche più diffuse. Domanda tramite piattaforma telematica inPA con SPID."),
    ("Concorso per 3 istruttori informatici - area degli istruttori", ""),
    ("Concorso per 1 funzionario tecnico ingegnere civile", "laurea magistrale LM-23"),
    ("Concorso per 10 infermieri", "laurea in scienze infermieristiche, competenze informatiche di base"),
    ("Avviso di mobilità esterna per funzionario informatico", ""),
    ("Concorso per collaboratore tecnico enti di ricerca (CTER) - supporto informatico", "diploma"),
])
def test_bandi_non_adatti_sono_scartati(val, titolo, testo):
    b = bando(titolo, testo)
    assert not val.valuta(b), (b.punteggio, b.motivi)


def test_esclusione_ha_la_precedenza(val):
    b = bando("Mobilità volontaria per data scientist")
    assert not val.valuta(b)
    assert b.punteggio == -99 and b.motivi[0].startswith("escluso")


def test_etichetta_laurea(val):
    b = bando("Concorso per 30 esperti informatici", "laurea magistrale LM-32")
    val.valuta(b)
    assert b.laurea == "magistrale"
    b = bando("Concorso per 5 funzionari informatici", "laurea triennale L-8 o laurea magistrale LM-32")
    val.valuta(b)
    assert b.laurea == "triennale"


def test_rivalutare_non_accumula(val):
    b = bando("Concorso per 30 esperti informatici", "laurea magistrale")
    val.valuta(b)
    primo = (b.punteggio, list(b.motivi), b.laurea)
    val.valuta(b)
    assert (b.punteggio, b.motivi, b.laurea) == primo


def test_richiesta_una_di_con_regola_inesistente():
    with pytest.raises(ValueError):
        Valutatore({"regole": [{"nome": "a", "peso": 1, "pattern": ["a"]}], "richiesta_una_di": ["b"]})


@pytest.mark.parametrize("titolo,ente,sede,atteso", [
    ("Concorso per 5 funzionari informatici", "Comune di Milano", "Lombardia, Milano", False),
    ("Concorso per 5 funzionari informatici", "Ministero dell'Interno", "Nazionale", True),
    ("Concorso per 5 funzionari informatici", "Roma Capitale", "", True),       # Gazzetta: niente sede, si guarda l'ente
    ("Concorso per 5 funzionari informatici", "Comune di Frosinone", "", False),
])
def test_solo_roma(val, titolo, ente, sede, atteso):
    assert val.valuta(bando(titolo, "laurea magistrale", ente, sede=sede)) is atteso


@pytest.mark.parametrize("titolo,ente", [
    ("Concorso per 2 posti di categoria D, area elaborazione dati, laureati in ingegneria informatica",
     "Universita' di Roma La Sapienza"),
    ("Concorso per 1 tecnologo informatico", "Università degli Studi di Roma Tor Vergata"),
    ("Concorso per 2 collaboratori tecnico-professionali informatici riservato alle categorie protette "
     "di cui all'art. 1 della legge n. 68/1999", "ASL Roma 1"),
])
def test_universita_e_categorie_protette_escluse(val, titolo, ente):
    b = bando(titolo, "laurea magistrale LM-32", ente)
    assert not val.valuta(b) and b.punteggio == -99


def test_motivo_esclusione_e_quasi_rilevanti(val):
    fuori = bando("Concorso per 5 funzionari informatici", "laurea magistrale", "Comune di Milano",
                  sede="Lombardia, Milano")
    assert not val.valuta(fuori) and fuori.esclusione == "sede" and not val.quasi_rilevante(fuori)
    lazio = bando("Concorso per 5 funzionari informatici", "laurea magistrale", "Comune di Latina",
                  sede="Lazio, Latina")
    assert not val.valuta(lazio) and lazio.esclusione == "sede" and val.quasi_rilevante(lazio)
    legale = bando("Concorso per 1 funzionario legale", "laurea magistrale in giurisprudenza")
    assert not val.valuta(legale) and legale.esclusione == "materia" and not val.quasi_rilevante(legale)
    mobilita = bando("Mobilità per funzionario informatico")
    val.valuta(mobilita)
    assert mobilita.esclusione == "mobilità/procedure interne" and not val.quasi_rilevante(mobilita)
    ok = bando("Concorso per 30 esperti informatici", "laurea magistrale")
    assert val.valuta(ok) and ok.esclusione == ""


def test_quasi_rilevante_per_soglia():
    v = Valutatore({"soglia": 5, "margine_quasi_rilevanti": 2, "richiesta_una_di": ["ict"],
                    "regole": [{"nome": "ict", "peso": 3, "pattern": ["ict"]}]})
    b = bando("Profilo ICT")
    assert not v.valuta(b) and b.esclusione == "soglia" and v.quasi_rilevante(b)
