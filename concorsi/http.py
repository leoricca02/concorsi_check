from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("concorsi")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 concorsi-check/1.0"
)


class FonteError(Exception):
    """Fonte non raggiungibile o con struttura cambiata: va segnalata nel report, non ignorata."""


class Http:
    """Client HTTP educato: pausa tra le richieste e qualche tentativo in caso di errore."""

    def __init__(self, pausa: float = 1.0, timeout: float = 30, tentativi: int = 3):
        self.pausa = pausa
        self.timeout = timeout
        self.tentativi = tentativi
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9"})

    def _richiesta(self, metodo: str, url: str, **kw) -> requests.Response:
        ultimo = ""
        for i in range(self.tentativi):
            if self.pausa:
                time.sleep(self.pausa if i == 0 else self.pausa * 2 * i)
            try:
                r = self.s.request(metodo, url, timeout=self.timeout, **kw)
                if r.status_code == 200:
                    return r
                ultimo = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                ultimo = type(e).__name__
            log.warning("%s %s -> %s (tentativo %d)", metodo, url, ultimo, i + 1)
        raise FonteError(f"impossibile leggere {url} ({ultimo})")

    def get(self, url: str, **kw) -> requests.Response:
        return self._richiesta("GET", url, **kw)

    def post_json(self, url: str, body: dict, **kw) -> requests.Response:
        return self._richiesta("POST", url, json=body, **kw)
