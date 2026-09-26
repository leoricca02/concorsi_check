from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

RADICE = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


class Risposta:
    def __init__(self, testo: str):
        self.text = testo

    def json(self):
        return json.loads(self.text)


class HttpFinto:
    """Sostituisce Http: risponde con i file in tests/fixtures invece di andare in rete."""

    def __init__(self, get: dict[str, str] | None = None, post: dict[str, str] | None = None):
        self.get_map = get or {}
        self.post_map = post or {}
        self.chiamate: list[str] = []

    def _trova(self, mappa, url):
        from concorsi.http import FonteError
        self.chiamate.append(url)
        for chiave, valore in mappa.items():
            if chiave in url:
                if isinstance(valore, Exception):
                    raise valore
                return Risposta(valore)
        raise FonteError(f"impossibile leggere {url} (HTTP 404)")

    def get(self, url, **kw):
        return self._trova(self.get_map, url)

    def post_json(self, url, body, **kw):
        return self._trova(self.post_map, url)


def leggi(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


@pytest.fixture
def config() -> dict:
    return yaml.safe_load((RADICE / "config.yaml").read_text(encoding="utf-8"))
