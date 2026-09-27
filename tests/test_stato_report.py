from datetime import date

from concorsi import report
from concorsi.modelli import Bando
from concorsi.stato import Stato
from concorsi.testo import data_italiana, indovina_posti

OGGI = date(2026, 9, 26)


def test_stato_persistenza_e_aperti(tmp_path):
    p = tmp_path / "s.json"
    s = Stato(p)
    assert s.primo_run
    aperto = Bando(id="a", fonte="f", titolo="Aperto", url="u", scadenza="2026-10-10", punteggio=9)
    scaduto = Bando(id="b", fonte="f", titolo="Scaduto", url="u", scadenza="2026-09-01")
    s.segna_segnalato(aperto, OGGI)
    s.segna_segnalato(scaduto, OGGI)
    s.salva(OGGI)
    s2 = Stato(p)
    assert not s2.primo_run
    assert [b.id for b in s2.ancora_aperti(OGGI, esclusi=set())] == ["a"]
    assert s2.ancora_aperti(OGGI, esclusi={"a"}) == []


def test_stato_pulizia(tmp_path):
    s = Stato(tmp_path / "s.json")
    s.segna_visto("vecchio", date(2024, 1, 1))
    s.segna_visto("recente", OGGI)
    s.segna_segnalato(Bando(id="v", fonte="f", titolo="t", url="u", scadenza="2024-02-01"), date(2024, 1, 1))
    s.pulisci(OGGI)
    assert list(s.dati["visti"]) == ["recente"] and s.dati["segnalati"] == {}


def test_report_markdown_e_testo():
    b = Bando(id="a", fonte="inpa", titolo="Concorso [ICT] per 30 esperti", url="https://x", ente="Banca d'Italia",
              scadenza="2026-10-20", posti=30, punteggio=12, motivi=["profilo informatico/ICT (+6)"],
              laurea="magistrale", sede="Lazio, Roma")
    md = report.markdown([b], [], {"consob": "HTTP 403"}, OGGI, {"inpa": 1600})
    assert "⭐⭐⭐ **[Concorso (ICT) per 30 esperti](https://x)**" in md
    assert "scade il 20/10/2026" in md and "🎓 Magistrale" in md
    assert "**consob**: HTTP 403" in md and "inpa (1600)" in md
    assert "Nessun nuovo" in report.markdown([], [], {}, OGGI)
    txt = report.testo_semplice([b], {}, OGGI)
    assert "1 nuovi" in txt and "https://x" in txt
    assert "<a href=\"https://x\">" in report.html_email([b], [b], {}, OGGI)


def test_testo_helper():
    assert data_italiana("CONCORSO (scad. 5 novembre 2026)".lower()) == "2026-11-05"
    assert data_italiana("entro il 07/01/2027") == "2027-01-07"
    assert data_italiana("senza data") == ""
    assert indovina_posti("Concorso per n. 12 posti di funzionario") == 12
    assert indovina_posti("copertura di due posti di categoria D") == 2
    assert indovina_posti("Concorso per un posto di dirigente") == 1
    assert indovina_posti("Concorso pubblico per funzionario") is None


def test_in_scadenza_e_report():
    from concorsi.main import in_scadenza
    b = lambda i, s: Bando(id=i, fonte="f", titolo=f"T{i}", url="u", ente="E", scadenza=s)
    bandi = [b("tra3", "2026-09-29"), b("oggi", "2026-09-26"), b("lontano", "2026-10-20"), b("senza", ""),
             b("scaduto", "2026-09-25")]
    urgenti = in_scadenza(bandi, OGGI, 7)
    assert [x.id for x in urgenti] == ["oggi", "tra3"]
    md = report.markdown([], [], {}, OGGI, in_scadenza=urgenti)
    assert "## ⏰ In scadenza (2)" in md and "**oggi** (26/09/2026)" in md and "**tra 3 giorni**" in md
    assert report.titolo([], urgenti) == "2 in scadenza"
    assert report.titolo(urgenti[:1], urgenti) == "1 nuovi rilevanti, 2 in scadenza"
    assert report.titolo([], []) == "0 nuovi rilevanti"
    assert "⏰ domani" in report.testo_semplice([], {}, date(2026, 9, 28), urgenti[1:])
    assert "⏰ In scadenza" in report.html_email([], [], {}, OGGI, urgenti)


def test_notifica_anche_solo_per_scadenze(monkeypatch):
    from concorsi import main as m
    inviati = []
    monkeypatch.setattr(m.notifiche, "email", lambda ogg, t, h: inviati.append(ogg) or True)
    monkeypatch.setattr(m.notifiche, "telegram", lambda t: True)
    urg = [Bando(id="a", fonte="f", titolo="T", url="u", scadenza="2026-09-28")]
    m.notifica({}, m.Risultato(), OGGI)
    assert inviati == []
    m.notifica({}, m.Risultato(in_scadenza=urg), OGGI)
    assert inviati == ["Concorsi: 1 in scadenza (26/09/2026)"]
