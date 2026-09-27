"""I tuoi 👍/👎 (data/preferenze.json, scritto dalla pagina web) e un piccolo modello che ne impara i gusti.

Formato del file:
  {"voti": {"<id bando>": {"voto": "like" | "dislike" | "candidato", "titolo": ..., "ente": ...,
                           "profilo": ..., "data": "YYYY-MM-DD"}}}

Il modello è un Naive Bayes sulle parole di titolo, ente e profilo: per un bando nuovo confronta
quanto le sue parole compaiono nei bandi piaciuti rispetto a quelli scartati e restituisce un bonus
intero tra -max e +max punti. Resta spento finché non ci sono abbastanza voti.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from .duplicati import parole
from .modelli import Bando

POSITIVI = {"like", "candidato"}


class Preferenze:
    def __init__(self, percorso: str | Path | None = None, min_voti: int = 5, max_bonus: int = 4):
        self.percorso = Path(percorso) if percorso else None
        self.voti: dict[str, dict] = {}
        if self.percorso and self.percorso.is_file() and self.percorso.stat().st_size:
            self.voti = json.loads(self.percorso.read_text(encoding="utf-8")).get("voti", {})
        self.max_bonus = max_bonus
        self._conta = {True: Counter(), False: Counter()}
        n = {True: 0, False: 0}
        for v in self.voti.values():
            positivo = v.get("voto") in POSITIVI
            n[positivo] += 1
            self._conta[positivo].update(self._parole(v))
        self.attivo = len(self.voti) >= min_voti and n[True] > 0 and n[False] > 0
        self._vocabolario = set(self._conta[True]) | set(self._conta[False])

    @staticmethod
    def _parole(d) -> set[str]:
        get = d.get if isinstance(d, dict) else lambda k, _=None: getattr(d, k, "")
        return parole(f"{get('titolo', '')} {get('ente', '')} {get('profilo', '')}")

    def vota(self, id_: str, voto: str, bando: dict, oggi: str) -> None:
        """Registra un voto; lo stesso voto ripetuto lo toglie (come nella pagina web)."""
        if self.voti.get(id_, {}).get("voto") == voto:
            del self.voti[id_]
        else:
            self.voti[id_] = {"voto": voto, "titolo": bando.get("titolo", ""), "ente": bando.get("ente", ""),
                              "profilo": bando.get("profilo", ""), "data": oggi}

    def salva(self) -> None:
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        self.percorso.write_text(json.dumps({"voti": self.voti}, ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8")

    @property
    def nascosti(self) -> set[str]:
        return {i for i, v in self.voti.items() if v.get("voto") == "dislike"}

    def affinita(self, b: Bando) -> int:
        """Bonus (o malus) in punti per quanto il bando somiglia a quelli che ti sono piaciuti."""
        if not self.attivo:
            return 0
        tot = {k: sum(c.values()) + len(self._vocabolario) for k, c in self._conta.items()}
        log_rapporto = sum(
            math.log((self._conta[True][w] + 1) / tot[True]) - math.log((self._conta[False][w] + 1) / tot[False])
            for w in self._parole(b) if w in self._vocabolario
        )
        return max(-self.max_bonus, min(self.max_bonus, round(log_rapporto)))

    def esempi(self, n: int = 5) -> str:
        """Ultimi bandi votati, da dare all'AI come esempi dei tuoi gusti."""
        ordinati = sorted(self.voti.values(), key=lambda v: v.get("data", ""), reverse=True)
        righe = []
        for etichetta, positivo in (("Gli sono piaciuti", True), ("Non gli interessano", False)):
            titoli = [f"- {v.get('titolo', '')} ({v.get('ente', '')})"
                      for v in ordinati if (v.get("voto") in POSITIVI) == positivo][:n]
            if titoli:
                righe += [f"{etichetta}:", *titoli]
        return "\n".join(righe)
