from .gazzetta import Gazzetta
from .inpa import Inpa
from .pagina import Pagina

TIPI = {cls.tipo: cls for cls in (Inpa, Gazzetta, Pagina)}
