"""Invio delle notifiche. Ogni canale si attiva solo se le relative variabili d'ambiente sono impostate
(su GitHub: Settings -> Secrets and variables -> Actions)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import requests

log = logging.getLogger("concorsi")


def email(oggetto: str, testo: str, html: str) -> bool:
    """EMAIL_USER / EMAIL_PASSWORD (per Gmail: una "password per le app"), EMAIL_TO opzionale."""
    utente, password = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASSWORD")
    if not (utente and password):
        return False
    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = utente
    msg["To"] = os.environ.get("EMAIL_TO") or utente
    msg.set_content(testo)
    msg.add_alternative(html, subtype="html")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    porta = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, porta, timeout=30) as s:
        s.login(utente, password)
        s.send_message(msg)
    log.info("email inviata a %s", msg["To"])
    return True


def telegram(testo: str) -> bool:
    """TELEGRAM_BOT_TOKEN (da @BotFather) e TELEGRAM_CHAT_ID (il tuo id utente)."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    # Telegram accetta al massimo 4096 caratteri per messaggio
    blocchi, corrente = [], ""
    for riga in testo.splitlines(keepends=True):
        if len(corrente) + len(riga) > 4000:
            blocchi.append(corrente)
            corrente = ""
        corrente += riga[:4000]
    blocchi.append(corrente)
    for b in filter(str.strip, blocchi):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": b, "disable_web_page_preview": True}, timeout=30)
        r.raise_for_status()
    log.info("messaggio Telegram inviato")
    return True
