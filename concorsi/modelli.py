from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Bando:
    """Un bando/concorso trovato su una fonte, già normalizzato."""

    id: str                      # univoco e stabile tra un run e l'altro (es. "inpa:<id>", "gu:<codice>")
    fonte: str                   # nome della fonte che l'ha trovato
    titolo: str
    url: str
    ente: str = ""
    profilo: str = ""            # figura ricercata / settore, se la fonte li fornisce
    testo: str = ""              # testo aggiuntivo usato solo per la valutazione (requisiti, descrizione...)
    sede: str = ""
    pubblicazione: str = ""      # YYYY-MM-DD
    scadenza: str = ""           # YYYY-MM-DD
    posti: int | None = None
    # compilati dalla valutazione
    punteggio: int = 0
    motivi: list[str] = field(default_factory=list)
    laurea: str = ""             # "magistrale" | "triennale" | "qualsiasi" | ""

    def per_stato(self) -> dict:
        d = asdict(self)
        d.pop("testo")
        return d
