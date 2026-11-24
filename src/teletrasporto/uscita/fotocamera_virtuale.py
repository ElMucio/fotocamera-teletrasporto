"""Invio dei fotogrammi alla OBS Virtual Camera, in puro Python.

La OBS Virtual Camera (filtro DirectShow registrato da OBS Studio) legge i fotogrammi da una
memoria condivisa chiamata "OBSVirtualCamVideo", con la stessa struttura di
obs-studio/plugins/win-dshow/shared-memory-queue.c. La scriviamo direttamente con mmap,
così non servono DLL native (che Smart App Control bloccherebbe) e OBS non deve essere aperto.
"""
import ctypes
import mmap
import time

import cv2
import numpy as np

NOME_MEMORIA = "OBSVirtualCamVideo"

# Stati della coda (enum queue_state di OBS)
_STATO_AVVIO = 1
_STATO_PRONTO = 2
_STATO_ARRESTO = 3

_DIM_INTESTAZIONE = 80  # sizeof(struct queue_header)
_DIM_INTESTAZIONE_FOTOGRAMMA = 32
_FILE_MAP_READ = 0x0004


def _allinea(n: int, a: int = 32) -> int:
    return (n + a - 1) & ~(a - 1)


def _memoria_esistente() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    h = kernel32.OpenFileMappingW(_FILE_MAP_READ, False, NOME_MEMORIA)
    if h:
        kernel32.CloseHandle(ctypes.c_void_p(h))
        return True
    return False


def obs_installata() -> bool:
    """True se il filtro OBS Virtual Camera è registrato nel sistema."""
    import winreg

    clsid = r"CLSID\{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, clsid))
        return True
    except OSError:
        return False


class ErroreFotocameraVirtuale(RuntimeError):
    pass


class FotocameraVirtualeOBS:
    """Scrittore della coda condivisa letta dalla OBS Virtual Camera."""

    def __init__(self, larghezza: int, altezza: int, fps: float):
        if larghezza % 2 or altezza % 2:
            raise ValueError("Larghezza e altezza devono essere pari (formato NV12)")
        if _memoria_esistente():
            raise ErroreFotocameraVirtuale(
                "La OBS Virtual Camera è già in uso (OBS o un altro programma la sta usando)"
            )
        self.larghezza, self.altezza = larghezza, altezza
        dim_fotogramma = larghezza * altezza * 3 // 2

        offset = []
        dim = _allinea(_DIM_INTESTAZIONE)
        for _ in range(3):
            offset.append(dim)
            dim = _allinea(dim + dim_fotogramma + _DIM_INTESTAZIONE_FOTOGRAMMA)

        self._mm = mmap.mmap(-1, dim, tagname=NOME_MEMORIA, access=mmap.ACCESS_WRITE)
        intest = np.ndarray((_DIM_INTESTAZIONE // 4,), dtype=np.uint32, buffer=self._mm)
        intest[:] = 0
        # write_idx, read_idx, state, offsets[3], type, cx, cy, interval (uint64), reserved[8]
        intest[2] = _STATO_AVVIO
        intest[3:6] = offset
        intest[6] = 0  # SHARED_QUEUE_TYPE_VIDEO
        intest[7] = larghezza
        intest[8] = altezza
        np.ndarray((1,), dtype=np.uint64, buffer=self._mm, offset=40)[0] = int(10_000_000 / fps)
        self._intest = intest

        self._ts = [np.ndarray((1,), dtype=np.uint64, buffer=self._mm, offset=o) for o in offset]
        self._fotogrammi = [
            np.ndarray((dim_fotogramma,), dtype=np.uint8, buffer=self._mm,
                       offset=o + _DIM_INTESTAZIONE_FOTOGRAMMA)
            for o in offset
        ]
        self._uv = np.empty((altezza // 2, larghezza), dtype=np.uint8)
        self._chiusa = False

    def invia(self, bgr: np.ndarray) -> None:
        """Invia un fotogramma BGR (viene ridimensionato se necessario)."""
        h, w = self.altezza, self.larghezza
        if bgr.shape[0] != h or bgr.shape[1] != w:
            bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
        i420 = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420).reshape(-1)
        dim_y, dim_c = w * h, (w // 2) * (h // 2)
        self._uv[:, 0::2] = i420[dim_y:dim_y + dim_c].reshape(h // 2, w // 2)
        self._uv[:, 1::2] = i420[dim_y + dim_c:].reshape(h // 2, w // 2)

        inc = int(self._intest[0]) + 1
        self._intest[0] = inc
        idx = inc % 3
        dest = self._fotogrammi[idx]
        dest[:dim_y] = i420[:dim_y]
        dest[dim_y:] = self._uv.reshape(-1)
        self._ts[idx][0] = time.perf_counter_ns()
        self._intest[1] = inc
        self._intest[2] = _STATO_PRONTO

    def chiudi(self) -> None:
        if self._chiusa:
            return
        self._chiusa = True
        self._intest[2] = _STATO_ARRESTO
        del self._intest, self._ts, self._fotogrammi
        self._mm.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.chiudi()
