"""Impostazioni del programma, salvate in config/impostazioni.json."""
import json
import logging
from dataclasses import asdict, dataclass, fields

from .percorsi import CONFIG

FILE = CONFIG / "impostazioni.json"
log = logging.getLogger(__name__)


@dataclass
class Impostazioni:
    # Webcam
    nome_webcam: str = ""          # vuoto = prima webcam reale disponibile
    larghezza: int = 1280
    altezza: int = 720
    fps: int = 30
    # Funzioni
    fotocamera_virtuale: bool = True
    gesti_attivi: bool = True
    teletrasporto_attivo: bool = True
    loop_attivo: bool = True
    # Tempi (secondi)
    tenuta_goku: float = 3.0
    tenuta_x: float = 0.6
    tenuta_w: float = 0.6
    conto_alla_rovescia: float = 2.0
    durata_clip: float = 10.0
    dissolvenza_loop: float = 0.5
    durata_effetto: float = 0.45
    clip_da_conservare: int = 3
    # Anteprima
    specchio_anteprima: bool = True
    anteprima_uscita: bool = True   # False = fotogramma grezzo della webcam
    mostra_punti_mani: bool = False
    anteprima_sfondo: bool = False  # mostra lo sfondo memorizzato (per controllarlo)
    # Scorciatoie globali (es. Ctrl+Alt+L)
    scorciatoie_attive: bool = True
    scorciatoia_live: str = "Ctrl+Alt+L"
    scorciatoia_gesti: str = "Ctrl+Alt+J"
    scorciatoia_sfondo: str = "Ctrl+Alt+B"

    @classmethod
    def carica(cls) -> "Impostazioni":
        imp = cls()
        if FILE.exists():
            try:
                dati = json.loads(FILE.read_text(encoding="utf-8"))
                for campo in fields(cls):
                    if campo.name in dati:
                        setattr(imp, campo.name, type(getattr(imp, campo.name))(dati[campo.name]))
            except (OSError, ValueError, TypeError) as e:
                log.warning("Impostazioni non leggibili, uso i valori predefiniti: %s", e)
        return imp

    def salva(self) -> None:
        CONFIG.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
