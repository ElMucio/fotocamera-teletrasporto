"""Lettura della webcam in un thread: si tiene solo l'ultimo fotogramma (niente ritardi)."""
import logging
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)
_ESCLUSE = ("OBS Virtual Camera",)  # la nostra uscita: usarla come ingresso creerebbe un anello


def elenca_webcam() -> list[str]:
    """Nomi delle webcam DirectShow, nell'ordine degli indici di OpenCV (CAP_DSHOW)."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception:  # noqa: BLE001
        log.exception("Elenco delle webcam non disponibile")
        return []


def scegli_webcam(nome: str) -> tuple[int, str] | None:
    """Indice e nome della webcam richiesta, o della prima webcam reale se non c'è."""
    nomi = elenca_webcam()
    for i, n in enumerate(nomi):
        if n == nome and n not in _ESCLUSE:
            return i, n
    for i, n in enumerate(nomi):
        if n not in _ESCLUSE:
            return i, n
    return None


def webcam_selezionabili() -> list[str]:
    return [n for n in elenca_webcam() if n not in _ESCLUSE]


class Webcam:
    def __init__(self, indice: int, larghezza: int, altezza: int, fps: int):
        self.indice, self.larghezza, self.altezza, self.fps = indice, larghezza, altezza, fps
        self.errore: str | None = None
        self._cond = threading.Condition()
        self._img: np.ndarray | None = None
        self._numero = 0
        self._letto = 0
        self._ferma = threading.Event()
        self._thread = threading.Thread(target=self._esegui, name="webcam", daemon=True)

    def avvia(self) -> None:
        self._thread.start()

    def ferma(self) -> None:
        self._ferma.set()
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout=3)

    def leggi(self, timeout: float = 1.0) -> np.ndarray | None:
        """Attende un fotogramma nuovo e lo restituisce (None se non arriva in tempo)."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._numero > self._letto or self._ferma.is_set(),
                                       timeout):
                return None
            self._letto = self._numero
            return self._img

    def _apri(self) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(self.indice, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.larghezza)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altezza)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def _esegui(self) -> None:
        cap = None
        errori = 0
        while not self._ferma.is_set():
            if cap is None:
                cap = self._apri()
                if cap is None:
                    self.errore = "webcam non disponibile (usata da un altro programma?)"
                    self._ferma.wait(2.0)
                    continue
            ok, img = cap.read()
            if not ok or img is None:
                errori += 1
                if errori > 15:
                    self.errore = "webcam scollegata o bloccata"
                    cap.release()
                    cap = None
                    errori = 0
                time.sleep(0.02)
                continue
            errori = 0
            self.errore = None
            # Il formato della fotocamera virtuale (NV12) richiede dimensioni pari.
            h, w = img.shape[:2]
            if h % 2 or w % 2:
                img = img[: h - h % 2, : w - w % 2]
            with self._cond:
                self._img = img
                self._numero += 1
                self._cond.notify_all()
        if cap is not None:
            cap.release()
