"""Teletrasporto: la persona scompare (e ricompare) con l'effetto stile DBZ."""
from .stato import Stato


class Teletrasporto:
    def __init__(self, durata_effetto: float = 0.45):
        self.durata_effetto = durata_effetto
        self.stato = Stato.SPENTO
        self._inizio_transizione = 0.0
        self.problema: str | None = None  # es. sfondo non ancora disponibile

    def commuta(self, t: float) -> None:
        """Chiamato dal gesto: fa sparire o ricomparire. Ignorato durante una transizione."""
        if self.stato == Stato.SPENTO:
            self.stato, self._inizio_transizione = Stato.AVVIO, t
        elif self.stato == Stato.ATTIVO:
            self.stato, self._inizio_transizione = Stato.SPEGNIMENTO, t

    def ricompari(self, t: float) -> None:
        if self.stato in (Stato.ATTIVO, Stato.AVVIO):
            self.stato, self._inizio_transizione = Stato.SPEGNIMENTO, t

    def aggiorna(self, t: float) -> None:
        if self.stato in (Stato.AVVIO, Stato.SPEGNIMENTO) and self.avanzamento(t) >= 1.0:
            self.stato = Stato.ATTIVO if self.stato == Stato.AVVIO else Stato.SPENTO

    def avanzamento(self, t: float) -> float:
        if self.durata_effetto <= 0:
            return 1.0
        return min(1.0, (t - self._inizio_transizione) / self.durata_effetto)

    def scomparsa(self, t: float) -> float:
        """Quanto la persona è scomparsa: 0 = visibile, 1 = sparita (con l'effetto in mezzo)."""
        if self.stato == Stato.SPENTO:
            return 0.0
        if self.stato == Stato.ATTIVO:
            return 1.0
        p = self.avanzamento(t)
        return p if self.stato == Stato.AVVIO else 1.0 - p

    @property
    def stato_spia(self) -> Stato:
        if self.problema and self.stato != Stato.SPENTO:
            return Stato.PROBLEMA
        return self.stato
