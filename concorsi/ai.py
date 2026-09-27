"""Verifica con un modello AI: legge il testo del bando (anche il PDF) e dice se il candidato può partecipare.

Si usa solo sui bandi già passati dal filtro a parole chiave, quindi poche chiamate a settimana.
Provider:
  - gemini    (default, gratis entro i limiti del piano free)  -> secret GEMINI_API_KEY
  - anthropic (Claude, a pagamento, pochi centesimi a bando)   -> secret ANTHROPIC_API_KEY
Senza chiave la verifica viene saltata e tutto funziona come prima.
"""
from __future__ import annotations

import io
import json
import logging
import os
import time

from bs4 import BeautifulSoup

from .http import FonteError, Http
from .modelli import Bando

log = logging.getLogger("concorsi")

ESITI = ("si", "forse", "no")
CAMPI = ("esito", "laurea_richiesta", "classi_ammesse", "requisiti", "motivo")
SCHEMA = {
    "type": "object",
    "properties": {
        "esito": {"type": "string", "enum": list(ESITI)},
        "laurea_richiesta": {"type": "string"},
        "classi_ammesse": {"type": "string"},
        "requisiti": {"type": "string"},
        "motivo": {"type": "string"},
    },
    "required": list(CAMPI),
    "additionalProperties": False,
}
PROMPT = """Valuti bandi di concorso pubblico italiani per conto di un candidato.

CANDIDATO:
{candidato}
{esempi}
BANDO:
Titolo: {titolo}
Ente: {ente}
Scadenza: {scadenza}
Testo{troncato}:
{testo}

Rispondi solo con un oggetto JSON con questi campi:
- "esito": "si" se il candidato ha (o avrà entro la scadenza) i requisiti e il profilo riguarda informatica, dati, AI,
  cybersecurity o ammette qualsiasi laurea; "no" se non è ammissibile (titolo di studio non ammesso, esperienza
  pluriennale richiesta, riservato a interni, categorie protette o mobilità) o il profilo non c'entra;
  "forse" se il testo non basta per decidere.
- "laurea_richiesta": il titolo di studio richiesto, in poche parole.
- "classi_ammesse": le classi di laurea ammesse (es. "LM-32, LM-18"), oppure "".
- "requisiti": gli altri requisiti importanti (voto minimo, esperienza, età, lingue), max 25 parole.
- "motivo": una frase che spiega l'esito."""


class ErroreAI(Exception):
    pass


def testo_documento(http: Http, url: str, max_caratteri: int) -> str:
    """Scarica una pagina o un PDF e ne restituisce il testo."""
    r = http.get(url)
    if r.content[:5] == b"%PDF-" or "pdf" in r.headers.get("Content-Type", "").lower():
        from pypdf import PdfReader
        pagine, n = [], 0
        for p in PdfReader(io.BytesIO(r.content)).pages:
            t = p.extract_text() or ""
            pagine.append(t)
            n += len(t)
            if n > max_caratteri:
                break
        testo = "\n".join(pagine)
    else:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        testo = soup.get_text(" ")
    return " ".join(testo.split())


class Verificatore:
    def __init__(self, cfg: dict, http: Http, esempi: str = ""):
        self.cfg = cfg
        self.esempi = esempi
        self.http = http
        self.provider = cfg.get("provider", "gemini")
        self.modello = cfg.get("modello") or {"gemini": "gemini-flash-lite-latest",
                                               "anthropic": "claude-opus-5"}[self.provider]
        self.chiave = os.environ.get({"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[self.provider])
        self.max_caratteri = int(cfg.get("max_caratteri", 60000))
        self.pausa = float(cfg.get("pausa", 5))

    @property
    def attivo(self) -> bool:
        return bool(self.cfg.get("attiva", True) and self.chiave)

    def prompt(self, b: Bando, testo: str) -> str:
        return PROMPT.format(
            candidato=(os.environ.get("PROFILO_CANDIDATO") or self.cfg.get("candidato", "")).strip(),
            esempi=f"\nESEMPI DEI SUOI GUSTI (usali solo per decidere tra 'si' e 'forse'):\n{self.esempi}\n"
                   if self.esempi else "", titolo=b.titolo, ente=b.ente or "-",
            scadenza=b.scadenza or "-", testo=testo[:self.max_caratteri] or "(non disponibile: usa il titolo)",
            troncato=" (troncato)" if len(testo) > self.max_caratteri else "",
        )

    def verifica(self, b: Bando) -> dict:
        testo = b.testo
        try:
            testo = testo_documento(self.http, b.documento or b.url, self.max_caratteri) or testo
        except Exception as e:  # pagina o PDF illeggibile: si usa il testo che già abbiamo
            log.warning("AI: testo del bando non disponibile per %s: %s", b.id, e)
        risposta = self._chiama(self.prompt(b, testo))
        try:
            dati = json.loads(risposta)
        except json.JSONDecodeError as e:
            raise ErroreAI(f"risposta non in JSON: {risposta[:200]}") from e
        out = {k: str(dati.get(k, "")).strip() for k in CAMPI}
        if out["esito"] not in ESITI:
            out["esito"] = "forse"
        return out

    def _chiama(self, prompt: str) -> str:
        if self.pausa:
            time.sleep(self.pausa)
        return self._gemini(prompt) if self.provider == "gemini" else self._claude(prompt)

    def _gemini(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modello}:generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        try:
            dati = self.http.post_json(url, body, headers={"x-goog-api-key": self.chiave}).json()
            return dati["candidates"][0]["content"]["parts"][0]["text"]
        except FonteError as e:
            raise ErroreAI(f"Gemini non risponde ({e})") from e
        except (KeyError, IndexError, ValueError) as e:
            raise ErroreAI("risposta Gemini inattesa") from e

    def _claude(self, prompt: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.chiave)
        params = {"model": self.modello, "max_tokens": 16000,
                  "messages": [{"role": "user", "content": prompt}],
                  "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}}
        if not self.modello.startswith("claude-haiku"):
            params["output_config"]["effort"] = "low"   # estrazione semplice: basta poco ragionamento
        try:
            if self.modello in ("claude-opus-5", "claude-opus-5-5", "claude-fable-5-1"):
                # se il modello rifiuta la richiesta, l'API la ripete su un modello di riserva
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                   fallbacks="default", **params)
            else:
                resp = client.messages.create(**params)
        except anthropic.RateLimitError as e:
            raise ErroreAI("Claude: limite di richieste raggiunto") from e
        except anthropic.APIStatusError as e:
            raise ErroreAI(f"Claude: errore {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ErroreAI("Claude: errore di rete") from e
        if resp.stop_reason == "refusal":
            raise ErroreAI("Claude ha rifiutato la richiesta")
        return next(b.text for b in resp.content if b.type == "text")
