"""Stato delle funzioni e colore della spia corrispondente."""
from enum import Enum


class Stato(Enum):
    SPENTO = "spento"
    AVVIO = "in avvio"
    ATTIVO = "attivo"
    SPEGNIMENTO = "in spegnimento"
    PROBLEMA = "problema"


# Colori BGR delle spie: verde attivo, rosso spento, giallo in avvio/spegnimento, arancio problema.
COLORE_SPIA = {
    Stato.SPENTO: (40, 40, 220),
    Stato.AVVIO: (0, 220, 255),
    Stato.ATTIVO: (60, 200, 60),
    Stato.SPEGNIMENTO: (0, 220, 255),
    Stato.PROBLEMA: (0, 140, 255),
}
