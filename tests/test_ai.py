import json
from datetime import date
from types import SimpleNamespace

import pytest
from conftest import HttpFinto

from concorsi import ai, report
from concorsi import main as m
from concorsi.ai import ErroreAI, Verificatore
from concorsi.modelli import Bando
from concorsi.stato import Stato

OGGI = date(2026, 9, 26)
GEMINI = "generativelanguage.googleapis.com"


def pdf_minimo(testo: str) -> bytes:
    """Un PDF di una pagina con del testo, costruito a mano (niente librerie extra nei test)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({testo}) Tj ET".encode()
    oggetti = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offset = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(oggetti, 1):
        offset.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(oggetti) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offset)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(oggetti) + 1, xref)
    return bytes(out)


def risposta_gemini(**campi) -> str:
    dati = {"esito": "si", "laurea_richiesta": "Laurea magistrale", "classi_ammesse": "LM-32",
            "requisiti": "voto minimo 105/110", "motivo": "Profilo informatico, requisiti posseduti", **campi}
    return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(dati)}]}}]})


@pytest.fixture
def chiave(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chiave-finta")


def cfg_ai(**extra):
    return {"provider": "gemini", "pausa": 0, "candidato": "Laureato LM-32", **extra}


def test_testo_da_pdf_e_da_html():
    http = HttpFinto(get={"bando.pdf": pdf_minimo("Requisiti: laurea magistrale LM-32"),
                          "pagina": "<html><script>x()</script><body><p>Laurea   L-8</p></body></html>"})
    assert "LM-32" in ai.testo_documento(http, "https://x/bando.pdf", 1000)
    assert ai.testo_documento(http, "https://x/pagina", 1000) == "Laurea L-8"


def test_senza_chiave_non_attivo(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert not Verificatore(cfg_ai(), HttpFinto()).attivo


def test_verifica_gemini_legge_il_pdf(chiave):
    http = HttpFinto(get={"media/123": pdf_minimo("Laurea magistrale LM-32 voto 105")},
                     post={GEMINI: risposta_gemini()})
    b = Bando(id="inpa:a", fonte="inpa", titolo="30 esperti informatici", url="https://pagina",
              documento="https://portale.inpa.gov.it/api/media/123")
    esito = Verificatore(cfg_ai(), http).verifica(b)
    assert esito["esito"] == "si" and esito["classi_ammesse"] == "LM-32"
    prompt = http.corpi[0]["contents"][0]["parts"][0]["text"]
    assert "LM-32 voto 105" in prompt and "Laureato LM-32" in prompt
    assert "gemini-flash-lite-latest:generateContent" in http.chiamate[-1]


def test_verifica_senza_documento_usa_il_testo_noto(chiave):
    http = HttpFinto(post={GEMINI: risposta_gemini(esito="boh")})
    b = Bando(id="x", fonte="f", titolo="T", url="https://non-raggiungibile", testo="requisiti noti")
    esito = Verificatore(cfg_ai(), http).verifica(b)
    assert esito["esito"] == "forse"  # valore non valido -> "forse"
    assert "requisiti noti" in http.corpi[0]["contents"][0]["parts"][0]["text"]


def test_risposta_non_json_e_un_errore(chiave):
    rotta = json.dumps({"candidates": [{"content": {"parts": [{"text": "non so"}]}}]})
    http = HttpFinto(post={GEMINI: rotta})
    with pytest.raises(ErroreAI):
        Verificatore(cfg_ai(), http).verifica(Bando(id="x", fonte="f", titolo="T", url="u"))


def test_integrazione_scarta_i_non_adatti(chiave, config, tmp_path):
    config["fonti"] = {}
    config["ai"] = cfg_ai()
    buono = Bando(id="a", fonte="f", titolo="Buono", url="https://a", scadenza="2026-12-01", punteggio=10)
    cattivo = Bando(id="b", fonte="f", titolo="Cattivo", url="https://b", scadenza="2026-12-01", punteggio=9)
    risposte = iter([risposta_gemini(), risposta_gemini(esito="no", motivo="serve LM-56")])

    class HttpAI(HttpFinto):
        def post_json(self, url, body, **kw):
            return SimpleNamespace(json=lambda: json.loads(next(risposte)))

    stato = Stato(tmp_path / "s.json")
    ris = m.Risultato(nuovi=[buono, cattivo])
    m.verifica_ai(config["ai"], HttpAI(), stato, ris, OGGI)
    assert [b.id for b in ris.nuovi] == ["a"] and [b.id for b in ris.scartati_ai] == ["b"]
    assert stato.dati["segnalati"]["b"]["ai"]["esito"] == "no"
    # lo scartato non ricompare tra gli "ancora aperti"
    assert [b.id for b in stato.ancora_aperti(OGGI, esclusi=set())] == ["a"]
    md = report.markdown(ris.nuovi, [], {}, OGGI, scartati=ris.scartati_ai)
    assert "🤖 ✅ adatto" in md and "Classi: LM-32" in md and "serve LM-56" in md


def test_errore_ai_non_blocca_il_report(chiave, config, tmp_path):
    config["ai"] = cfg_ai()
    b = Bando(id="a", fonte="f", titolo="T", url="https://a")
    ris = m.Risultato(nuovi=[b])
    m.verifica_ai(config["ai"], HttpFinto(), Stato(tmp_path / "s.json"), ris, OGGI)
    assert ris.nuovi == [b] and b.ai is None and "verifica AI" in ris.errori


def test_max_bandi_per_run(chiave, tmp_path):
    http = HttpFinto(post={GEMINI: risposta_gemini()})
    bandi = [Bando(id=str(i), fonte="f", titolo=f"T{i}", url="u", punteggio=i) for i in range(5)]
    ris = m.Risultato(nuovi=bandi)
    m.verifica_ai(cfg_ai(max_bandi_per_run=2), http, Stato(tmp_path / "s.json"), ris, OGGI)
    assert sorted(b.id for b in bandi if b.ai) == ["3", "4"]  # i due col punteggio più alto


@pytest.mark.parametrize("modello,beta,effort", [("claude-opus-5", True, True), ("claude-haiku-4-5", False, False)])
def test_verifica_claude_parametri(monkeypatch, modello, beta, effort):
    import anthropic
    chiamate = []

    def crea(**kw):
        chiamate.append(kw)
        testo = json.dumps({"esito": "si", "laurea_richiesta": "LM", "classi_ammesse": "", "requisiti": "",
                            "motivo": "ok"})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=testo)])

    messaggi = SimpleNamespace(create=crea)
    finto = SimpleNamespace(messages=messaggi, beta=SimpleNamespace(messages=messaggi))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: finto)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    v = Verificatore(cfg_ai(provider="anthropic", modello=modello), HttpFinto())
    assert v.verifica(Bando(id="x", fonte="f", titolo="T", url="https://u"))["esito"] == "si"
    kw = chiamate[0]
    assert kw["model"] == modello and kw["output_config"]["format"]["type"] == "json_schema"
    assert ("fallbacks" in kw) is beta and ("effort" in kw["output_config"]) is effort


def test_claude_rifiuto_e_un_errore(monkeypatch):
    import anthropic
    risposta = SimpleNamespace(stop_reason="refusal", content=[])
    finto = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: risposta)))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: finto)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with pytest.raises(ErroreAI):
        Verificatore(cfg_ai(provider="anthropic"), HttpFinto()).verifica(Bando(id="x", fonte="f", titolo="T", url="u"))


def test_ritenta_i_segnalati_senza_verifica(chiave, tmp_path):
    http = HttpFinto(post={GEMINI: risposta_gemini(esito="no", motivo="serve LM-56")})
    stato = Stato(tmp_path / "s.json")
    vecchio = Bando(id="v", fonte="f", titolo="Vecchio", url="https://v", scadenza="2026-12-01")
    stato.segna_segnalato(vecchio, OGGI)
    ris = m.Risultato(aperti=stato.ancora_aperti(OGGI, set()))
    m.verifica_ai(cfg_ai(), http, stato, ris, OGGI)
    assert ris.aperti == [] and [b.id for b in ris.scartati_ai] == ["v"]
    assert stato.dati["segnalati"]["v"]["ai"]["esito"] == "no"
    # al giro dopo è già verificato: nessuna nuova chiamata
    n = len(http.corpi)
    ris = m.Risultato(aperti=stato.ancora_aperti(OGGI, set()))
    m.verifica_ai(cfg_ai(), http, stato, ris, OGGI)
    assert len(http.corpi) == n
