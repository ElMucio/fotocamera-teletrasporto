"""Timer di tenuta: un gesto scatta solo se mantenuto per un certo tempo."""


class TimerTenuta:
    """Scatta una volta quando il gesto è tenuto per `durata` secondi.

    - Brevi interruzioni del rilevamento (fino a `tolleranza`) non azzerano il conteggio.
    - Dopo lo scatto il gesto va rilasciato prima di poter scattare di nuovo,
      e per `attesa` secondi viene ignorato.
    """

    def __init__(self, durata: float, tolleranza: float = 0.25, attesa: float = 1.0):
        self.durata = durata
        self.tolleranza = tolleranza
        self.attesa = attesa
        self._inizio: float | None = None
        self._ultimo_visto = float("-inf")
        self._bloccato = False
        self._fine_attesa = float("-inf")
        self._t = 0.0

    def aggiorna(self, attivo: bool, t: float) -> bool:
        self._t = t
        if attivo:
            self._ultimo_visto = t
        if self._bloccato:
            if t - self._ultimo_visto > self.tolleranza:
                self._bloccato = False
            return False
        if t < self._fine_attesa:
            self._inizio = None
            return False
        if attivo:
            if self._inizio is None:
                self._inizio = t
            if t - self._inizio >= self.durata:
                self._inizio = None
                self._bloccato = True
                self._fine_attesa = t + self.attesa
                return True
        elif self._inizio is not None and t - self._ultimo_visto > self.tolleranza:
            self._inizio = None
        return False

    @property
    def progresso(self) -> float:
        """Avanzamento 0..1 della tenuta in corso."""
        if self._inizio is None or self.durata <= 0:
            return 0.0
        return min(1.0, (self._t - self._inizio) / self.durata)

    def blocca(self) -> None:
        """Annulla la tenuta in corso e richiede di rilasciare il gesto prima di ricontare
        (usato quando scatta un altro gesto)."""
        self._inizio = None
        self._bloccato = True
        self._ultimo_visto = self._t

    def azzera(self) -> None:
        self._inizio = None
        self._bloccato = False
