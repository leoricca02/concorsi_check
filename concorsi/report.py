"""Testo del report: Markdown (file nel repo / issue GitHub), HTML (email), testo semplice (Telegram)."""
from __future__ import annotations

import html
from datetime import date

from .modelli import Bando

LAUREA = {"magistrale": "🎓 Magistrale", "triennale": "🎓 Triennale", "qualsiasi": "🎓 Qualsiasi laurea"}


def stelle(b: Bando) -> str:
    return "⭐⭐⭐" if b.punteggio >= 12 else "⭐⭐" if b.punteggio >= 8 else "⭐"


def ordina(bandi: list[Bando]) -> list[Bando]:
    return sorted(bandi, key=lambda b: (-b.punteggio, b.scadenza or "9999"))


def _dettagli(b: Bando) -> list[str]:
    parti = [b.ente] if b.ente else []
    if b.posti:
        parti.append(f"{b.posti} posti")
    if b.laurea:
        parti.append(LAUREA[b.laurea])
    if b.sede:
        parti.append(f"📍 {b.sede}")
    if b.scadenza:
        parti.append(f"⏰ scade il {_data(b.scadenza)}")
    return parti


AI = {"si": "✅ adatto", "forse": "❔ da verificare", "no": "❌ non adatto"}


def _ai(b: Bando) -> str:
    """Riga con il riassunto dell'AI, o '' se la verifica non è stata fatta."""
    if not b.ai:
        return ""
    parti = [f"🤖 {AI[b.ai['esito']]}: {b.ai['motivo']}"]
    for chiave, etichetta in (("laurea_richiesta", "Laurea"), ("classi_ammesse", "Classi"), ("requisiti", "Requisiti")):
        if b.ai.get(chiave):
            parti.append(f"{etichetta}: {b.ai[chiave]}")
    return " · ".join(parti)


def _md(t: str) -> str:
    """Evita che parentesi quadre o asterischi nel titolo rompano il Markdown."""
    return t.replace("[", "(").replace("]", ")").replace("*", "")


def _data(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def markdown(nuovi: list[Bando], aperti: list[Bando], errori: dict[str, str], oggi: date,
             letti: dict[str, int] | None = None, scartati: list[Bando] | None = None) -> str:
    righe = [f"# Concorsi — controllo del {oggi.strftime('%d/%m/%Y')}", ""]
    if nuovi:
        righe += [f"## 🆕 Nuovi concorsi rilevanti ({len(nuovi)})", ""]
        for b in ordina(nuovi):
            righe.append(f"- {stelle(b)} **[{_md(b.titolo)}]({b.url})**  ")
            righe.append(f"  {' · '.join(_dettagli(b))}  ")
            if b.ai:
                righe.append(f"  {_ai(b)}  ")
            righe.append(f"  <sub>fonte: {b.fonte} · punteggio {b.punteggio}: {', '.join(b.motivi)}</sub>")
        righe.append("")
    else:
        righe += ["Nessun nuovo concorso rilevante dall'ultimo controllo.", ""]
    if aperti:
        righe += [f"## 📌 Segnalati in precedenza e ancora aperti ({len(aperti)})", ""]
        for b in aperti:
            righe.append(f"- [{_md(b.titolo)}]({b.url}) — {' · '.join(_dettagli(b))}")
        righe.append("")
    if scartati:
        righe += [f"<details><summary>🤖 Scartati dopo la lettura del bando ({len(scartati)})</summary>", ""]
        righe += [f"- [{_md(b.titolo)}]({b.url}) — {b.ai['motivo']}" for b in scartati]
        righe += ["", "</details>", ""]
    if errori:
        righe += ["## ⚠️ Fonti con problemi", "",
                  "Queste fonti non sono state controllate: se l'errore si ripete, va aggiornato `config.yaml`.", ""]
        righe += [f"- **{nome}**: {msg}" for nome, msg in errori.items()]
        righe.append("")
    if letti:
        righe += ["<sub>Fonti controllate (voci lette): "
                  + ", ".join(f"{n} ({c})" for n, c in letti.items()) + "</sub>", ""]
    return "\n".join(righe)


def html_email(nuovi: list[Bando], aperti: list[Bando], errori: dict[str, str], oggi: date) -> str:
    e = html.escape
    parti = [f"<h2>Concorsi — controllo del {oggi.strftime('%d/%m/%Y')}</h2>"]
    if nuovi:
        parti.append(f"<h3>🆕 Nuovi concorsi rilevanti ({len(nuovi)})</h3><ul>")
        for b in ordina(nuovi):
            parti.append(f"<li>{stelle(b)} <a href=\"{e(b.url)}\"><b>{e(b.titolo)}</b></a><br>"
                         f"{e(' · '.join(_dettagli(b)))}<br>"
                         + (f"{e(_ai(b))}<br>" if b.ai else "") +
                         f"<small style='color:#666'>fonte: {e(b.fonte)} · {e(', '.join(b.motivi))}</small></li>")
        parti.append("</ul>")
    else:
        parti.append("<p>Nessun nuovo concorso rilevante dall'ultimo controllo.</p>")
    if aperti:
        parti.append(f"<h3>📌 Ancora aperti ({len(aperti)})</h3><ul>")
        parti += [f"<li><a href=\"{e(b.url)}\">{e(b.titolo)}</a> — {e(' · '.join(_dettagli(b)))}</li>" for b in aperti]
        parti.append("</ul>")
    if errori:
        parti.append("<h3>⚠️ Fonti con problemi</h3><ul>")
        parti += [f"<li><b>{e(n)}</b>: {e(m)}</li>" for n, m in errori.items()]
        parti.append("</ul>")
    return "\n".join(parti)


def testo_semplice(nuovi: list[Bando], errori: dict[str, str], oggi: date) -> str:
    righe = [f"Concorsi — {oggi.strftime('%d/%m/%Y')}: {len(nuovi)} nuovi rilevanti", ""]
    for b in ordina(nuovi):
        righe += [f"{stelle(b)} {b.titolo}", " · ".join(_dettagli(b)), *([_ai(b)] if b.ai else []), b.url, ""]
    if errori:
        righe.append("⚠️ Fonti con problemi: " + ", ".join(errori))
    return "\n".join(righe)
