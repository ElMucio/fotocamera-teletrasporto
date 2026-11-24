"""Modello dello sfondo: serve a mostrare cosa c'è dietro la persona quando scompare.

Regola di base: nello sfondo entra solo ciò che è fermo e lontano dalla persona.
- Un pixel mai visto viene accettato solo dopo alcuni aggiornamenti in cui è rimasto uguale.
- Un pixel già noto si aggiorna piano se è simile (cambi di luce); se diventa diverso viene
  sostituito solo quando il nuovo valore resta stabile a lungo (es. un oggetto spostato).
Così una persona che il segmentatore non riconosce per qualche istante non lascia la sagoma.
"""
import cv2
import numpy as np

# Frazione di immagine mai vista oltre la quale lo sfondo è considerato incompleto.
_SOGLIA_BUCHI = 0.003
# Differenza massima (per canale, 0..255) perché due valori siano considerati "uguali".
_SOGLIA_SIMILE = 28
# Aggiornamenti consecutivi stabili richiesti (con circa 5 aggiornamenti al secondo).
_CONFERME_NUOVO = 5        # pixel mai visto: ~1 s
_CONFERME_CAMBIO = 40      # pixel noto ma cambiato: ~8 s
# Area minima (frazione dell'immagine) di una macchia per essere considerata una persona.
_AREA_MINIMA_PERSONA = 0.004
# Cattura manuale: campioni senza persona richiesti per ogni pixel, e tempo massimo.
_CAMPIONI_CATTURA = 12
_TEMPO_MAX_CATTURA = 20.0
# Se nessuno è visibile per questo tempo, la cattura si chiude anche se manca qualche pixel.
_TEMPO_SENZA_PERSONA = 1.0


def macchie_persona(maschera: np.ndarray) -> np.ndarray:
    """Zone (uint8 0/1) che appartengono davvero a una persona.

    Si tengono solo le macchie della maschera che hanno un nucleo sicuro (confidenza > 0.5)
    abbastanza grande: le piccole macchie a bassa confidenza su oggetti della stanza
    (cornici, sedie...) vengono ignorate. I bordi incerti della persona restano inclusi."""
    debole = (maschera > 0.15).astype(np.uint8)
    n, etichette, statistiche, _ = cv2.connectedComponentsWithStats(debole, connectivity=8)
    if n <= 1:
        return debole
    area_minima = maschera.size * _AREA_MINIMA_PERSONA
    nucleo_per_macchia = np.bincount(etichette[maschera > 0.5], minlength=n)
    valide = (statistiche[:, cv2.CC_STAT_AREA] >= area_minima) & (nucleo_per_macchia >= area_minima / 2)
    valide[0] = False  # etichetta 0 = fuori dalla maschera
    return valide[etichette].astype(np.uint8)


def zona_persona(maschera: np.ndarray, dimensione: tuple[int, int]) -> np.ndarray:
    """Maschera bool (alla dimensione del fotogramma) della persona con un ampio margine.

    L'allargamento si calcola alla risoluzione della maschera (più veloce)."""
    persona = macchie_persona(maschera)
    k = max(3, int(persona.shape[1] * 0.06)) | 1
    persona = cv2.dilate(persona, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    w, h = dimensione
    if persona.shape != (h, w):
        persona = cv2.resize(persona, (w, h), interpolation=cv2.INTER_NEAREST)
    return persona.astype(bool)


def _simili(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return cv2.absdiff(a, b).max(axis=2) < _SOGLIA_SIMILE


class ModelloSfondo:
    def __init__(self, apprendimento: float = 0.05):
        self.apprendimento = apprendimento
        self.sfondo: np.ndarray | None = None   # float32 HxWx3
        self.visto: np.ndarray | None = None    # bool HxW: pixel noti senza persona davanti
        self.frazione_buchi = 1.0
        self._candidato: np.ndarray | None = None  # uint8: valore in prova per ogni pixel
        self._conferme: np.ndarray | None = None   # uint8: quante volte il candidato è rimasto uguale
        self._riempito: np.ndarray | None = None
        self._base: np.ndarray | None = None       # sfondo uint8, ricalcolato solo quando cambia
        self._chiamate_da_riempimento = 0
        # Cattura manuale
        self._fine_conto: float | None = None
        self._somma: np.ndarray | None = None
        self._somma_recente: np.ndarray | None = None
        self._campioni: np.ndarray | None = None
        self._n_recenti = 0
        self._t_ultima_persona = 0.0
        self.avanzamento_cattura = 0.0
        self.persona_in_cattura = False

    @property
    def pronto(self) -> bool:
        return self.sfondo is not None and bool(self.visto.any())

    @property
    def incompleto(self) -> bool:
        return self.frazione_buchi > _SOGLIA_BUCHI

    def reimposta(self) -> None:
        self.sfondo = self.visto = self._candidato = self._conferme = None
        self._riempito = self._base = None
        self.frazione_buchi = 1.0

    def _prepara(self, fotogramma: np.ndarray) -> None:
        h, w = fotogramma.shape[:2]
        if self.sfondo is not None and self.sfondo.shape[:2] != (h, w):
            self.reimposta()
        if self.sfondo is None:
            self.sfondo = fotogramma.astype(np.float32)
            self.visto = np.zeros((h, w), dtype=bool)
            self._candidato = fotogramma.copy()
            self._conferme = np.zeros((h, w), dtype=np.uint8)

    def _cambiato(self) -> None:
        self.frazione_buchi = 1.0 - float(np.count_nonzero(self.visto)) / self.visto.size
        self._chiamate_da_riempimento += 1
        self._base = None

    # --- apprendimento automatico -------------------------------------------------------------

    def aggiorna_auto(self, fotogramma: np.ndarray, maschera_persona: np.ndarray) -> None:
        """Aggiorna lo sfondo solo dove la persona non c'è e l'immagine è stabile.

        Va chiamato a ritmo regolare (circa 5 volte al secondo)."""
        if self.in_cattura:
            return
        self._prepara(fotogramma)
        h, w = fotogramma.shape[:2]
        libero = ~zona_persona(maschera_persona, (w, h))
        base = self._immagine_base()

        # 1. Pixel noti e simili allo sfondo: aggiornamento lento (cambi di luce).
        simile_sfondo = _simili(fotogramma, base)
        lento = libero & self.visto & simile_sfondo
        cv2.accumulateWeighted(fotogramma.astype(np.float32), self.sfondo, self.apprendimento,
                               mask=lento.astype(np.uint8))

        # 2. Pixel mai visti o cambiati: il nuovo valore deve restare stabile per un po'.
        in_prova = libero & ~lento
        stabile = in_prova & _simili(fotogramma, self._candidato)
        self._conferme[stabile] = np.minimum(self._conferme[stabile], 254) + 1
        ripartono = in_prova & ~stabile
        self._conferme[ripartono] = 1
        np.copyto(self._candidato, fotogramma, where=ripartono[..., None])
        self._conferme[~in_prova] = 0

        accetta = (stabile & ~self.visto & (self._conferme >= _CONFERME_NUOVO)) | \
                  (stabile & self.visto & (self._conferme >= _CONFERME_CAMBIO))
        if accetta.any():
            np.copyto(self.sfondo, self._candidato.astype(np.float32), where=accetta[..., None])
            self.visto |= accetta
            self._conferme[accetta] = 0
        self._cambiato()

    # --- cattura manuale ----------------------------------------------------------------------

    def avvia_cattura(self, t: float, conto_alla_rovescia: float = 5.0) -> None:
        self._fine_conto = t + conto_alla_rovescia
        self._somma = self._campioni = None
        self.avanzamento_cattura = 0.0
        self.persona_in_cattura = False

    @property
    def in_cattura(self) -> bool:
        return self._fine_conto is not None

    def secondi_alla_cattura(self, t: float) -> float:
        return max(0.0, (self._fine_conto or t) - t)

    def aggiorna_cattura(self, fotogramma: np.ndarray, maschera_persona: np.ndarray | None,
                         t: float) -> None:
        """Dopo il conto alla rovescia raccoglie solo i pixel in cui non c'è nessuno.

        Finisce quando ogni pixel ha abbastanza campioni puliti, oppure dopo un tempo massimo:
        in quel caso i pixel rimasti coperti restano "da ricostruire" (spia arancione)."""
        if self._fine_conto is None or t < self._fine_conto or maschera_persona is None:
            return
        h, w = fotogramma.shape[:2]
        libero = ~zona_persona(maschera_persona, (w, h))
        self.persona_in_cattura = not libero.all()
        if self._somma is None:
            self._somma = np.zeros((h, w, 3), np.float32)
            self._somma_recente = np.zeros((h, w, 3), np.float32)
            self._campioni = np.zeros((h, w), np.uint16)
            self._n_recenti = 0
            self._t_ultima_persona = t
        f = fotogramma.astype(np.float32)
        cv2.accumulate(f, self._somma, mask=libero.astype(np.uint8))
        self._campioni += libero
        # Media dei fotogrammi da quando nessuno è più visibile (serve a chiudere i pixel mancanti).
        if self.persona_in_cattura:
            self._t_ultima_persona = t
            self._somma_recente[:] = 0
            self._n_recenti = 0
        else:
            self._somma_recente += f
            self._n_recenti += 1
        pronti = self._campioni >= _CAMPIONI_CATTURA
        self.avanzamento_cattura = float(np.count_nonzero(pronti)) / pronti.size
        nessuno = not self.persona_in_cattura and t - self._t_ultima_persona >= _TEMPO_SENZA_PERSONA
        if pronti.all() or nessuno or t - self._fine_conto > _TEMPO_MAX_CATTURA:
            self._conclude_cattura(fotogramma)

    def _conclude_cattura(self, fotogramma: np.ndarray) -> None:
        self._prepara(fotogramma)
        validi = self._campioni >= 3
        media = self._somma / np.maximum(self._campioni, 1)[..., None]
        if self._n_recenti >= 3:
            # Nessuno visibile da un po': i pixel con pochi campioni prendono la media recente.
            recente = self._somma_recente / self._n_recenti
            np.copyto(media, recente, where=~validi[..., None])
            validi = np.ones_like(validi)
        np.copyto(self.sfondo, media, where=validi[..., None])
        # Dove la persona è rimasta sempre davanti non si può sapere cosa c'è: da ricostruire.
        self.visto = validi
        self._conferme[:] = 0
        self._riempito = None
        self._fine_conto = self._somma = self._somma_recente = self._campioni = None
        self._cambiato()

    def annulla_cattura(self) -> None:
        self._fine_conto = self._somma = self._campioni = None

    # --- uso nella composizione ---------------------------------------------------------------

    def _immagine_base(self) -> np.ndarray:
        if self._base is None:
            self._base = np.clip(self.sfondo, 0, 255).astype(np.uint8)
        return self._base

    def immagine(self) -> np.ndarray | None:
        """Sfondo uint8 con le zone mai viste riempite per interpolazione (inpainting)."""
        if self.sfondo is None:
            return None
        base = self._immagine_base()
        if self.frazione_buchi == 0.0:
            return base
        if self._riempito is None or self._chiamate_da_riempimento >= 3:
            self._chiamate_da_riempimento = 0
            h, w = base.shape[:2]
            piccola = cv2.resize(base, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
            buchi = cv2.resize((~self.visto).astype(np.uint8) * 255, (w // 4, h // 4),
                               interpolation=cv2.INTER_NEAREST)
            riempita = cv2.inpaint(piccola, buchi, 5, cv2.INPAINT_TELEA)
            grande = cv2.resize(riempita, (w, h), interpolation=cv2.INTER_LINEAR)
            self._riempito = np.where(self.visto[..., None], base, grande)
        return self._riempito
