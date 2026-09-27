import json

from concorsi import notifiche, telegram_voti as tv
from concorsi.preferenze import Preferenze


def cb(dati, chat=123, id_="c1"):
    return {"update_id": 1, "callback_query": {"id": id_, "data": dati, "from": {"id": chat},
                                                "message": {"message_id": 9, "chat": {"id": chat}}}}


def prepara(tmp_path, monkeypatch):
    chiamate = []
    monkeypatch.setattr(tv, "chiama_telegram", lambda metodo, **d: chiamate.append((metodo, d)) or {})
    pagina = tmp_path / "bandi.json"
    pagina.write_text(json.dumps({"bandi": [{"id": "inpa:a", "titolo": "Data scientist", "ente": "CONSOB",
                                            "profilo": "Esperto"}]}), encoding="utf-8")
    return chiamate, pagina


def test_voto_registrato_e_confermato(tmp_path, monkeypatch):
    chiamate, pagina = prepara(tmp_path, monkeypatch)
    pref = Preferenze(tmp_path / "pref.json")
    n = tv.elabora([cb("v:like:inpa:a")], "123", pref, pagina, tmp_path / "stato.json", "2026-09-27")
    assert n == 1 and pref.voti["inpa:a"] == {"voto": "like", "titolo": "Data scientist", "ente": "CONSOB",
                                              "profilo": "Esperto", "data": "2026-09-27"}
    assert chiamate[0] == ("answerCallbackQuery", {"callback_query_id": "c1", "text": "👍 salvato"})
    tastiera = chiamate[1][1]["reply_markup"]["inline_keyboard"][0]
    assert tastiera[0]["text"] == "✓ 👍" and tastiera[1]["text"] == "👎"
    pref.salva()
    assert Preferenze(tmp_path / "pref.json").voti["inpa:a"]["voto"] == "like"


def test_stesso_voto_due_volte_lo_toglie(tmp_path, monkeypatch):
    chiamate, pagina = prepara(tmp_path, monkeypatch)
    pref = Preferenze(tmp_path / "pref.json")
    tv.elabora([cb("v:dislike:inpa:a"), cb("v:dislike:inpa:a", id_="c2")], "123", pref, pagina,
               tmp_path / "s.json", "2026-09-27")
    assert "inpa:a" not in pref.voti
    assert chiamate[-2][1]["text"] == "Voto tolto"


def test_voti_di_altri_ignorati(tmp_path, monkeypatch):
    chiamate, pagina = prepara(tmp_path, monkeypatch)
    pref = Preferenze(tmp_path / "pref.json")
    n = tv.elabora([cb("v:like:inpa:a", chat=999), cb("x:like:inpa:a"), cb("v:boh:inpa:a"), {"update_id": 5}],
                   "123", pref, pagina, tmp_path / "s.json", "2026-09-27")
    assert n == 0 and pref.voti == {}
    assert all(c[1]["text"] == "Voto non valido" for c in chiamate)


def test_info_dal_stato_se_non_in_pagina(tmp_path):
    stato = tmp_path / "stato.json"
    stato.write_text(json.dumps({"segnalati": {"gu:1": {"titolo": "Vecchio", "ente": "ACN"}}}))
    assert tv.info_bando("gu:1", tmp_path / "manca.json", stato)["ente"] == "ACN"
    assert tv.info_bando("gu:2", tmp_path / "manca.json", stato) == {}


def test_invio_con_pulsanti(monkeypatch):
    inviati = []
    monkeypatch.setattr(notifiche, "chiama_telegram", lambda metodo, **d: inviati.append(d) or {})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    assert notifiche.telegram("Riepilogo", [("inpa:a", "⭐ Data scientist")])
    assert inviati[0]["text"] == "Riepilogo" and "reply_markup" not in inviati[0]
    pulsanti = inviati[1]["reply_markup"]["inline_keyboard"][0]
    assert [p["callback_data"] for p in pulsanti] == ["v:like:inpa:a", "v:dislike:inpa:a", "v:candidato:inpa:a"]


def test_main_senza_configurazione(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert tv.main([]) == 0


def test_prova(tmp_path, monkeypatch):
    inviati = []
    monkeypatch.setattr(tv, "telegram", lambda testo, bandi=None: inviati.append((testo, bandi)) or True)
    _, pagina = prepara(tmp_path, monkeypatch)
    tv.prova(pagina)
    assert inviati[0][1][0][0] == "inpa:a"
    tv.prova(tmp_path / "manca.json")
    assert inviati[1][1] is None
