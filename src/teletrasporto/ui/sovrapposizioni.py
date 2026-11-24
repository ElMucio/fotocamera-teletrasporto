"""Disegni sull'anteprima (mai sulla fotocamera virtuale): spie, avanzamento, conti alla rovescia."""
from dataclasses import dataclass

import cv2
import numpy as np

from ..funzioni.stato import COLORE_SPIA, Stato
from ..visione.rilevatori import Mano, Volto

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_COLLEGAMENTI_MANO = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
                      (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
                      (17, 18), (18, 19), (19, 20)]


@dataclass
class Spia:
    etichetta: str
    stato: Stato
    progresso: float = 0.0  # tenuta del gesto in corso, 0..1


def _testo(img, testo, org, scala, colore=(255, 255, 255), spessore=2, ancora_destra=False):
    (tw, th), _ = cv2.getTextSize(testo, _FONT, scala, spessore)
    x, y = org
    if ancora_destra:
        x -= tw
    cv2.putText(img, testo, (x, y), _FONT, scala, (0, 0, 0), spessore + 3, cv2.LINE_AA)
    cv2.putText(img, testo, (x, y), _FONT, scala, colore, spessore, cv2.LINE_AA)
    return tw, th


def disegna_punti(img: np.ndarray, mani: list[Mano], volti: list[Volto]) -> None:
    """Punti delle mani e fronte dei volti (debug). Da chiamare prima dello specchio."""
    for m in mani:
        p = m.punti[:, :2].astype(int)
        for a, b in _COLLEGAMENTI_MANO:
            cv2.line(img, tuple(p[a]), tuple(p[b]), (255, 255, 255), 2, cv2.LINE_AA)
        for q in p:
            cv2.circle(img, tuple(q), 3, (0, 180, 255), -1, cv2.LINE_AA)
    for v in volti:
        x, y, w, h = (int(c) for c in v.riquadro)
        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 200, 0), 1)
        cv2.circle(img, tuple(v.fronte.astype(int)), int(0.45 * v.larghezza), (255, 200, 0), 1, cv2.LINE_AA)


def disegna_spie(img: np.ndarray, spie: list[Spia]) -> None:
    """Spie in alto a destra, una per funzione, con anello di avanzamento della tenuta."""
    h, w = img.shape[:2]
    s = max(0.6, w / 1280)
    r = int(13 * s)
    x = w - int(30 * s)
    y = int(32 * s)
    for spia in spie:
        colore = COLORE_SPIA[spia.stato]
        cv2.circle(img, (x, y), r + 3, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), r, colore, -1, cv2.LINE_AA)
        if spia.progresso > 0:
            cv2.ellipse(img, (x, y), (r + 7, r + 7), -90, 0, 360 * spia.progresso, (255, 255, 255),
                        max(2, int(3 * s)), cv2.LINE_AA)
        _testo(img, spia.etichetta, (x - r - int(14 * s), y + int(7 * s)), 0.6 * s,
               ancora_destra=True)
        y += int(42 * s)


def disegna_gesti(img: np.ndarray, nomi: list[str]) -> None:
    """Gesti riconosciuti in questo momento, sotto le spie (aiuta a capire cosa vede il programma)."""
    if not nomi:
        return
    w = img.shape[1]
    s = max(0.6, w / 1280)
    _testo(img, "gesto: " + " ".join(nomi), (w - int(16 * s), int(150 * s)), 0.7 * s,
           (255, 255, 0), ancora_destra=True)


def disegna_centro(img: np.ndarray, testo: str, sotto: str = "") -> None:
    """Testo grande al centro (conti alla rovescia)."""
    h, w = img.shape[:2]
    s = w / 1280
    (tw, th), _ = cv2.getTextSize(testo, _FONT, 5 * s, int(10 * s))
    _testo(img, testo, ((w - tw) // 2, (h + th) // 2), 5 * s, (0, 220, 255), max(2, int(10 * s)))
    if sotto:
        (sw, _), _ = cv2.getTextSize(sotto, _FONT, 1.0 * s, 2)
        _testo(img, sotto, ((w - sw) // 2, (h + th) // 2 + int(60 * s)), 1.0 * s)


def disegna_rec(img: np.ndarray, secondi: float) -> None:
    s = img.shape[1] / 1280
    c = (int(30 * s), int(34 * s))
    cv2.circle(img, c, int(11 * s), (0, 0, 230), -1, cv2.LINE_AA)
    _testo(img, f"REC {secondi:0.0f}s", (int(50 * s), int(44 * s)), 0.9 * s)


def disegna_messaggi(img: np.ndarray, messaggi: list[str]) -> None:
    h, w = img.shape[:2]
    s = max(0.6, w / 1280)
    y = h - int(16 * s)
    for m in reversed(messaggi):
        _testo(img, m, (int(16 * s), y), 0.65 * s, (0, 180, 255))
        y -= int(30 * s)
