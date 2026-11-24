"""Loop: registra una clip e la ripete al posto del live.

X: inattivo → conto alla rovescia → registrazione → loop; X di nuovo annulla o torna al live.
W: va subito in loop l'ultima clip; durante il loop passa alla clip precedente.
"""
from enum import Enum

import numpy as np

from ..clip import ArchivioClip, Clip, Registratore
from .stato import Stato

_DURATA_AVVISO = 2.0  # secondi di spia arancione dopo un comando impossibile


class FaseLoop(Enum):
    INATTIVO = "inattivo"
    CONTO = "conto alla rovescia"
    REGISTRAZIONE = "registrazione"
    IN_LOOP = "in loop"


class FunzioneLoop:
    def __init__(self, archivio: ArchivioClip, conto_alla_rovescia: float = 2.0,
                 durata_clip: float = 10.0, dissolvenza: float = 0.5):
        self.archivio = archivio
        self.conto_alla_rovescia = conto_alla_rovescia
        self.durata_clip = durata_clip
        self.dissolvenza = dissolvenza
        self.fase = FaseLoop.INATTIVO
        self._t_fase = 0.0
        self._registratore: Registratore | None = None
        self._clip: Clip | None = None
        self.indice_clip = 0
        self._avviso_fino = float("-inf")
        self.avviso: str | None = None

    # --- comandi ------------------------------------------------------------------------------

    def gesto_x(self, t: float) -> None:
        if self.fase == FaseLoop.INATTIVO:
            self._vai(FaseLoop.CONTO, t)
        else:  # annulla conto/registrazione oppure torna al live
            self.torna_live()

    def gesto_w(self, t: float) -> None:
        if self.fase == FaseLoop.INATTIVO:
            self._riproduci(0, t)
        elif self.fase == FaseLoop.IN_LOOP:
            n = len(self.archivio)
            if n > 1:
                self._riproduci((self.indice_clip + 1) % n, t)

    def torna_live(self) -> None:
        self.fase = FaseLoop.INATTIVO
        self._registratore = None
        self._clip = None

    def _vai(self, fase: FaseLoop, t: float) -> None:
        self.fase, self._t_fase = fase, t

    def _riproduci(self, indice: int, t: float) -> None:
        clip = self.archivio.get(indice)
        if clip is None:
            self._avvisa("nessuna clip salvata: fai X per registrarne una", t)
            return
        self._clip, self.indice_clip = clip, indice
        self._vai(FaseLoop.IN_LOOP, t)

    def _avvisa(self, testo: str, t: float) -> None:
        self.avviso, self._avviso_fino = testo, t + _DURATA_AVVISO

    # --- a ogni fotogramma --------------------------------------------------------------------

    def aggiorna(self, t: float, pulito: np.ndarray) -> np.ndarray | None:
        """Riceve il fotogramma pulito in uscita; restituisce quello da mostrare al suo posto
        (None = mostra il live)."""
        trascorso = t - self._t_fase
        if self.fase == FaseLoop.CONTO and trascorso >= self.conto_alla_rovescia:
            self._registratore = Registratore(t)
            self._vai(FaseLoop.REGISTRAZIONE, t)
            trascorso = 0.0
        if self.fase == FaseLoop.REGISTRAZIONE:
            if trascorso < self.durata_clip:
                self._registratore.aggiungi(pulito, t)
            else:
                clip = self._registratore.clip()
                self._registratore = None
                if clip is None:
                    self._avvisa("registrazione non riuscita", t)
                    self.fase = FaseLoop.INATTIVO
                else:
                    self.archivio.aggiungi(clip)
                    self._clip, self.indice_clip = clip, 0
                    self._vai(FaseLoop.IN_LOOP, t)
        if self.fase == FaseLoop.IN_LOOP and self._clip is not None:
            return self._clip.fotogramma_loop(t - self._t_fase, self.dissolvenza)
        return None

    # --- per le spie --------------------------------------------------------------------------

    def secondi_rimanenti(self, t: float) -> float:
        trascorso = t - self._t_fase
        if self.fase == FaseLoop.CONTO:
            return max(0.0, self.conto_alla_rovescia - trascorso)
        if self.fase == FaseLoop.REGISTRAZIONE:
            return max(0.0, self.durata_clip - trascorso)
        return 0.0

    def stato_spia(self, t: float) -> Stato:
        if t < self._avviso_fino:
            return Stato.PROBLEMA
        self.avviso = None
        return {
            FaseLoop.INATTIVO: Stato.SPENTO,
            FaseLoop.CONTO: Stato.AVVIO,
            FaseLoop.REGISTRAZIONE: Stato.AVVIO,
            FaseLoop.IN_LOOP: Stato.ATTIVO,
        }[self.fase]
