"""Clip registrate: tenute in memoria come JPEG e salvate in clips/ (solo le ultime N)."""
import bisect
import logging
import threading
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)
_QUALITA_JPEG = [cv2.IMWRITE_JPEG_QUALITY, 90]


class Clip:
    def __init__(self, fotogrammi: list[bytes], tempi: list[float], percorso: Path | None = None):
        self.fotogrammi = fotogrammi
        self.tempi = tempi  # secondi dall'inizio, crescenti
        self.percorso = percorso
        self._cache_indice = -1
        self._cache_img: np.ndarray | None = None

    @property
    def durata(self) -> float:
        if len(self.tempi) < 2:
            return 0.0
        # Durata = ultimo istante + durata media di un fotogramma
        return self.tempi[-1] + self.tempi[-1] / (len(self.tempi) - 1)

    @property
    def fps(self) -> float:
        return len(self.tempi) / self.durata if self.durata > 0 else 30.0

    def _decodifica(self, i: int) -> np.ndarray:
        if i != self._cache_indice:
            self._cache_img = cv2.imdecode(np.frombuffer(self.fotogrammi[i], np.uint8), cv2.IMREAD_COLOR)
            self._cache_indice = i
        return self._cache_img

    def fotogramma_a(self, tau: float) -> np.ndarray:
        i = max(0, bisect.bisect_right(self.tempi, tau) - 1)
        return self._decodifica(min(i, len(self.fotogrammi) - 1))

    def fotogramma_loop(self, tau: float, dissolvenza: float) -> np.ndarray:
        """Fotogramma per la riproduzione in loop, con dissolvenza incrociata fine → inizio.

        Il periodo del loop è durata - dissolvenza: nei primi `dissolvenza` secondi di ogni giro
        la coda della clip sfuma nell'inizio, così il punto di ripartenza non si nota.
        """
        d = min(dissolvenza, self.durata / 3)
        periodo = self.durata - d
        if periodo <= 0:
            return self.fotogramma_a(0.0)
        tau %= periodo
        if d <= 0 or tau >= d:
            return self.fotogramma_a(tau)
        a = tau / d
        coda = self.fotogramma_a(periodo + tau).copy()
        testa = self.fotogramma_a(tau)
        return cv2.addWeighted(coda, 1 - a, testa, a, 0)


class Registratore:
    """Accumula fotogrammi compressi in JPEG durante la registrazione."""

    def __init__(self, t0: float):
        self.t0 = t0
        self.fotogrammi: list[bytes] = []
        self.tempi: list[float] = []

    def aggiungi(self, img: np.ndarray, t: float) -> None:
        ok, buf = cv2.imencode(".jpg", img, _QUALITA_JPEG)
        if ok:
            self.fotogrammi.append(buf.tobytes())
            self.tempi.append(t - self.t0)

    def clip(self) -> Clip | None:
        return Clip(self.fotogrammi, self.tempi) if len(self.fotogrammi) >= 2 else None


class ArchivioClip:
    """Le ultime `massimo` clip, dalla più recente; caricate all'avvio e salvate in mp4."""

    def __init__(self, cartella: Path, massimo: int = 3):
        self.cartella = cartella
        self.massimo = massimo
        self._clip: list[Clip] = []
        self._lock = threading.Lock()
        self.cartella.mkdir(parents=True, exist_ok=True)

    def __len__(self) -> int:
        with self._lock:
            return len(self._clip)

    def get(self, i: int) -> Clip | None:
        with self._lock:
            return self._clip[i] if 0 <= i < len(self._clip) else None

    def _file_su_disco(self) -> list[Path]:
        return sorted(self.cartella.glob("clip_*.mp4"), reverse=True)  # più recente prima

    def carica_in_background(self) -> threading.Thread:
        th = threading.Thread(target=self._carica, name="carica-clip", daemon=True)
        th.start()
        return th

    def _carica(self) -> None:
        caricate = []
        for p in self._file_su_disco()[: self.massimo]:
            clip = _leggi_mp4(p)
            if clip:
                caricate.append(clip)
        with self._lock:
            # Le clip registrate nel frattempo restano davanti.
            gia = {c.percorso for c in self._clip}
            self._clip += [c for c in caricate if c.percorso not in gia]
            del self._clip[self.massimo:]
        log.info("Clip caricate: %d", len(caricate))

    def aggiungi(self, clip: Clip) -> None:
        """Aggiunge una clip appena registrata e la salva su disco in un thread separato."""
        clip.percorso = self.cartella / f"clip_{datetime.now():%Y%m%d_%H%M%S_%f}.mp4"
        with self._lock:
            self._clip.insert(0, clip)
            del self._clip[self.massimo:]
        threading.Thread(target=self._salva, args=(clip,), name="salva-clip", daemon=True).start()

    def _salva(self, clip: Clip) -> None:
        try:
            _scrivi_mp4(clip)
        except Exception:  # noqa: BLE001 - un errore di salvataggio non deve fermare il programma
            log.exception("Salvataggio della clip non riuscito")
        with self._lock:
            tenere = {c.percorso for c in self._clip}
        for p in self._file_su_disco()[self.massimo:]:
            if p not in tenere:
                p.unlink(missing_ok=True)


def _scrivi_mp4(clip: Clip) -> None:
    # Decodifica indipendente: la cache della clip è usata dal thread di riproduzione.
    primo = cv2.imdecode(np.frombuffer(clip.fotogrammi[0], np.uint8), cv2.IMREAD_COLOR)
    h, w = primo.shape[:2]
    tmp = clip.percorso.with_suffix(".tmp.mp4")
    scrittore = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), clip.fps, (w, h))
    if not scrittore.isOpened():
        raise OSError(f"Impossibile scrivere {tmp}")
    for dati in clip.fotogrammi:
        scrittore.write(cv2.imdecode(np.frombuffer(dati, np.uint8), cv2.IMREAD_COLOR))
    scrittore.release()
    tmp.replace(clip.percorso)


def _leggi_mp4(percorso: Path) -> Clip | None:
    cap = cv2.VideoCapture(str(percorso))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    fotogrammi = []
    while True:
        ok, img = cap.read()
        if not ok:
            break
        ok, buf = cv2.imencode(".jpg", img, _QUALITA_JPEG)
        if ok:
            fotogrammi.append(buf.tobytes())
    cap.release()
    if len(fotogrammi) < 2:
        log.warning("Clip illeggibile o vuota: %s", percorso)
        return None
    return Clip(fotogrammi, [i / fps for i in range(len(fotogrammi))], percorso)
