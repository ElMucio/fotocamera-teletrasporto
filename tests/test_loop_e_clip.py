import threading

import numpy as np
import pytest

from teletrasporto.clip import ArchivioClip, Registratore, _leggi_mp4, _scrivi_mp4
from teletrasporto.funzioni.loop import FaseLoop, FunzioneLoop
from teletrasporto.funzioni.stato import Stato


def _img(valore):
    return np.full((48, 64, 3), valore, np.uint8)


def _clip(n=30, fps=10.0, valore=None):
    r = Registratore(0.0)
    for i in range(n):
        r.aggiungi(_img(valore if valore is not None else i * 8), i / fps)
    return r.clip()


class ArchivioFinto(ArchivioClip):
    """Archivio in memoria, senza salvataggi su disco."""

    def __init__(self, clip=()):
        self.massimo, self._clip, self._lock = 3, list(clip), threading.Lock()

    def aggiungi(self, clip):
        self._clip.insert(0, clip)
        del self._clip[self.massimo:]


def _esegui(loop, da, a, passo=0.1, valore=100):
    uscita = None
    for i in range(round((a - da) / passo) + 1):
        uscita = loop.aggiorna(round(da + i * passo, 4), _img(valore))
    return uscita


def test_x_conto_registrazione_loop_e_ritorno_al_live():
    archivio = ArchivioFinto()
    loop = FunzioneLoop(archivio, conto_alla_rovescia=2.0, durata_clip=3.0, dissolvenza=0.0)
    loop.gesto_x(0.0)
    assert loop.fase == FaseLoop.CONTO and loop.stato_spia(0.0) == Stato.AVVIO
    _esegui(loop, 0.0, 1.9)
    assert loop.fase == FaseLoop.CONTO
    _esegui(loop, 2.0, 4.9)
    assert loop.fase == FaseLoop.REGISTRAZIONE
    uscita = _esegui(loop, 5.0, 5.3, valore=7)
    assert loop.fase == FaseLoop.IN_LOOP and loop.stato_spia(5.3) == Stato.ATTIVO
    assert uscita is not None and abs(int(uscita.mean()) - 100) <= 2  # mostra la clip, non il live
    assert len(archivio) == 1
    loop.gesto_x(6.0)
    assert loop.fase == FaseLoop.INATTIVO and loop.aggiorna(6.1, _img(7)) is None


def test_x_durante_il_conto_annulla():
    archivio = ArchivioFinto()
    loop = FunzioneLoop(archivio, 2.0, 3.0)
    loop.gesto_x(0.0)
    loop.gesto_x(1.0)
    assert loop.fase == FaseLoop.INATTIVO
    _esegui(loop, 1.0, 8.0)
    assert len(archivio) == 0


def test_w_senza_clip_segnala_problema():
    loop = FunzioneLoop(ArchivioFinto())
    loop.gesto_w(0.0)
    assert loop.fase == FaseLoop.INATTIVO and loop.stato_spia(0.5) == Stato.PROBLEMA
    assert loop.stato_spia(3.0) == Stato.SPENTO


def test_w_scorre_le_clip_dalla_piu_recente():
    clip = [_clip(valore=v) for v in (10, 20, 30)]
    loop = FunzioneLoop(ArchivioFinto(clip), dissolvenza=0.0)
    loop.gesto_w(0.0)
    assert loop.indice_clip == 0 and 8 <= int(loop.aggiorna(0.1, _img(0)).mean()) <= 12
    loop.gesto_w(1.0)
    assert loop.indice_clip == 1
    loop.gesto_w(2.0)
    loop.gesto_w(3.0)
    assert loop.indice_clip == 0  # torna alla più recente


def test_dissolvenza_del_loop_continua():
    c = _clip(n=30, fps=10.0)  # 3 s, valori crescenti 0..232
    fine = c.fotogramma_loop(c.durata - 0.5 - 0.01, 0.5).mean()
    inizio = c.fotogramma_loop(0.0, 0.5).mean()
    assert abs(fine - inizio) < 12  # nessun salto al punto di ripartenza


def test_archivio_su_disco_tiene_le_ultime_n(tmp_path):
    archivio = ArchivioClip(tmp_path, massimo=3)
    for v in range(5):
        archivio.aggiungi(_clip(n=12, valore=v * 40))
        for th in [t for t in threading.enumerate() if t.name == "salva-clip"]:
            th.join(timeout=10)
    assert len(archivio) == 3
    assert len(list(tmp_path.glob("clip_*.mp4"))) == 3
    nuovo = ArchivioClip(tmp_path, massimo=3)
    nuovo.carica_in_background().join(timeout=20)
    assert len(nuovo) == 3
    assert abs(nuovo.get(0).fotogramma_a(0).mean() - 160) < 6  # la più recente per prima


def test_mp4_andata_e_ritorno(tmp_path):
    c = _clip(n=20)
    c.percorso = tmp_path / "clip_x.mp4"
    _scrivi_mp4(c)
    letta = _leggi_mp4(c.percorso)
    assert len(letta.fotogrammi) == 20
    assert letta.fps == pytest.approx(10.0, rel=0.05)
