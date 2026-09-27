"""Legge i 👍/👎 dati dai pulsanti dei messaggi Telegram e li salva in data/preferenze.json.

Gira ogni ora (.github/workflows/telegram-voti.yml): Telegram conserva i tocchi per 24 ore.
Accetta solo i voti che arrivano dalla chat TELEGRAM_CHAT_ID.
Uso: python -m concorsi.telegram_voti [--prova]   (--prova manda un bando di prova con i pulsanti)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

from .notifiche import PULSANTI, chiama_telegram, telegram
from .preferenze import Preferenze

log = logging.getLogger("concorsi")
CONFERMA = {"like": "👍 salvato", "dislike": "👎 salvato: non lo vedrai più", "candidato": "✉️ segnato come candidato"}


def info_bando(id_: str, pagina: Path, stato: Path) -> dict:
    """Titolo, ente e profilo del bando (servono al punteggio personale)."""
    if pagina.is_file():
        for b in json.loads(pagina.read_text(encoding="utf-8")).get("bandi", []):
            if b["id"] == id_:
                return b
    if stato.is_file():
        return json.loads(stato.read_text(encoding="utf-8")).get("segnalati", {}).get(id_, {})
    return {}


def elabora(aggiornamenti: list[dict], chat: str, pref: Preferenze, pagina: Path, stato: Path,
            oggi: str) -> int:
    """Applica i voti; restituisce quanti ne ha registrati."""
    n = 0
    for agg in aggiornamenti:
        cb = agg.get("callback_query")
        if not cb:
            continue
        mittente = str((cb.get("message") or {}).get("chat", {}).get("id") or cb.get("from", {}).get("id"))
        parti = (cb.get("data") or "").split(":", 2)
        if mittente != str(chat) or len(parti) != 3 or parti[0] != "v" or parti[1] not in CONFERMA:
            _rispondi(cb, "Voto non valido")
            continue
        _, voto, id_ = parti
        pref.vota(id_, voto, info_bando(id_, pagina, stato), oggi)
        n += 1
        tolto = id_ not in pref.voti
        _rispondi(cb, "Voto tolto" if tolto else CONFERMA[voto])
        _segna_pulsante(cb, None if tolto else voto)
    return n


def _rispondi(cb: dict, testo: str) -> None:
    try:
        chiama_telegram("answerCallbackQuery", callback_query_id=cb["id"], text=testo)
    except Exception as e:  # la risposta è solo cortesia: il voto è comunque registrato
        log.warning("answerCallbackQuery fallita: %s", e)


def _segna_pulsante(cb: dict, voto: str | None) -> None:
    """Mette un ✓ sul pulsante scelto, così nel messaggio si vede il voto."""
    msg = cb.get("message") or {}
    id_ = cb["data"].split(":", 2)[2]
    tastiera = [[{"text": ("✓ " if v == voto else "") + t, "callback_data": f"v:{v}:{id_}"} for t, v in PULSANTI]]
    try:
        chiama_telegram("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                        reply_markup={"inline_keyboard": tastiera})
    except Exception as e:
        log.warning("editMessageReplyMarkup fallita: %s", e)


def prova(pagina: Path) -> None:
    bandi = json.loads(pagina.read_text(encoding="utf-8")).get("bandi", []) if pagina.is_file() else []
    if not bandi:
        telegram("Prova: Telegram funziona, ma non ci sono ancora bandi aperti da votare.")
        return
    b = bandi[0]
    telegram("Prova: ecco un bando con i pulsanti. Tocca 👍 o 👎: il voto viene salvato entro un'ora.",
             [(b["id"], f"{b['titolo']}\n{b.get('ente', '')}\n{b.get('url', '')}")])


def main(argv: list[str] | None = None) -> int:
    import sys
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and chat):
        log.info("Telegram non configurato")
        return 0
    if "--prova" in argv:
        prova(Path("docs/bandi.json"))
    offset_file = Path("data/telegram.json")
    offset = json.loads(offset_file.read_text())["offset"] if offset_file.is_file() else 0
    aggiornamenti = chiama_telegram("getUpdates", offset=offset, timeout=0,
                                    allowed_updates=["callback_query"])["result"]
    if not aggiornamenti:
        log.info("nessun voto nuovo")
        return 0
    pref = Preferenze("data/preferenze.json")
    n = elabora(aggiornamenti, chat, pref, Path("docs/bandi.json"), Path("data/stato.json"),
                date.today().isoformat())
    if n:
        pref.salva()
    offset_file.parent.mkdir(parents=True, exist_ok=True)
    offset_file.write_text(json.dumps({"offset": aggiornamenti[-1]["update_id"] + 1}) + "\n")
    log.info("voti registrati: %d", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
