"""Riconoscimento dei gesti con regole geometriche sui punti delle mani.

Indici MediaPipe: 0 polso; pollice 1-4; indice 5-8; medio 9-12; anulare 13-16; mignolo 17-20
(per ogni dito: base, articolazione intermedia, penultima, punta).
"""
from dataclasses import dataclass, field

import numpy as np

from ..autorizzazione import Autorizzatore
from .rilevatori import Mano, Volto

POLLICE, INDICE, MEDIO, ANULARE, MIGNOLO = range(5)
_BASE = {INDICE: 5, MEDIO: 9, ANULARE: 13, MIGNOLO: 17}


def _punti_dito(dito: int) -> tuple[int, int, int]:
    b = _BASE[dito]
    return b, b + 1, b + 3  # base, articolazione intermedia, punta


def dito_teso(m: Mano, dito: int) -> bool:
    """Dito dritto e con la punta più lontana dal polso dell'articolazione intermedia."""
    b, a, p = (m.punti[i] for i in _punti_dito(dito))
    polso = m.punti[0]
    v1, v2 = a - b, p - a
    coseno = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6))
    return coseno > 0.75 and np.linalg.norm(p - polso) > np.linalg.norm(a - polso) * 1.1


def dito_piegato(m: Mano, dito: int) -> bool:
    """Punta del dito vicina al palmo (non più lontana dal polso dell'articolazione intermedia)."""
    _, a, p = (m.punti[i] for i in _punti_dito(dito))
    polso = m.punti[0]
    return np.linalg.norm(p - polso) < np.linalg.norm(a - polso) * 1.1


def _segmenti_incrociati(p1, p2, q1, q2) -> bool:
    def orient(a, b, c):
        return np.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return (orient(p1, p2, q1) != orient(p1, p2, q2)) and (orient(q1, q2, p1) != orient(q1, q2, p2))


def _angolo_gradi(v1, v2) -> float:
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(c, -1, 1))))


def posa_goku(m: Mano, volto: Volto | None) -> bool:
    """Indice e medio tesi e uniti, appoggiati sulla fronte; anulare e mignolo piegati."""
    if volto is None:
        return False
    if not (dito_teso(m, INDICE) and dito_teso(m, MEDIO)):
        return False
    if not (dito_piegato(m, ANULARE) and dito_piegato(m, MIGNOLO)):
        return False
    punta_i, punta_m = m.punti[8, :2], m.punti[12, :2]
    if np.linalg.norm(punta_i - punta_m) > 0.5 * m.scala:
        return False
    punte = (punta_i + punta_m) / 2
    return np.linalg.norm(punte - volto.fronte) < 0.45 * volto.larghezza


def _indice_allungato(m: Mano) -> tuple[np.ndarray, np.ndarray]:
    """Segmento base → punta dell'indice, allungato del 15% per lato: tollera le imprecisioni
    del rilevamento quando le dita si sovrappongono."""
    p1, p2 = m.punti[5, :2], m.punti[8, :2]
    d = (p2 - p1) * 0.15
    return p1 - d, p2 + d


def indici_incrociati(a: Mano, b: Mano) -> bool:
    pa1, pa2 = _indice_allungato(a)
    pb1, pb2 = _indice_allungato(b)
    return _segmenti_incrociati(pa1, pa2, pb1, pb2)


def x_indici(a: Mano, b: Mano) -> bool:
    """Due indici tesi che si incrociano formando una X."""
    for m in (a, b):
        if not dito_teso(m, INDICE) or dito_teso(m, MEDIO):
            return False
    if not indici_incrociati(a, b):
        return False
    va = a.punti[8, :2] - a.punti[5, :2]
    vb = b.punti[8, :2] - b.punti[5, :2]
    return 30 <= _angolo_gradi(va, vb) <= 150


def w_mani(a: Mano, b: Mano) -> bool:
    """Pollici che si toccano in basso, indici tesi verso l'alto e separati: le mani formano una W.

    Gli indici non devono incrociarsi (altrimenti è una X) e i pollici puntano l'uno verso l'altro."""
    scala = (a.scala + b.scala) / 2
    for m, altra in ((a, b), (b, a)):
        if not dito_teso(m, INDICE):
            return False
        direzione = m.punti[8, :2] - m.punti[5, :2]
        # Indice verso l'alto (y dell'immagine cresce verso il basso), entro 55° dalla verticale.
        if _angolo_gradi(direzione, np.array([0.0, -1.0])) > 55:
            return False
        if m.punti[4, 1] <= m.punti[8, 1]:  # il pollice deve stare sotto la punta dell'indice
            return False
        verso_altra = altra.punti[0, :2] - m.punti[0, :2]
        if np.dot(m.punti[4, :2] - m.punti[2, :2], verso_altra) <= 0:  # pollice verso l'altra mano
            return False
    if indici_incrociati(a, b):
        return False
    if np.linalg.norm(a.punti[4, :2] - b.punti[4, :2]) > 0.6 * scala:
        return False
    return np.linalg.norm(a.punti[8, :2] - b.punti[8, :2]) > 1.2 * scala


@dataclass
class Gesti:
    goku: bool = False
    x: bool = False
    w: bool = False
    volti_mani: list = field(default_factory=list)  # volto associato a ogni mano (per il debug)


def volto_della_mano(m: Mano, volti: list[Volto]) -> Volto | None:
    """Il volto più vicino al polso, se abbastanza vicino da appartenere alla stessa persona."""
    migliore, distanza = None, float("inf")
    for v in volti:
        d = np.linalg.norm(m.punti[0, :2] - v.centro) / max(v.larghezza, 1.0)
        if d < distanza:
            migliore, distanza = v, d
    return migliore if distanza < 4.0 else None


def valuta(mani: list[Mano], volti: list[Volto], autorizzatore: Autorizzatore) -> Gesti:
    g = Gesti()
    volti_mani = [volto_della_mano(m, volti) for m in mani]
    g.volti_mani = volti_mani
    consentite = [m for m, v in zip(mani, volti_mani) if autorizzatore.consentito(v)]
    volto_di = {id(m): v for m, v in zip(mani, volti_mani)}

    g.goku = any(posa_goku(m, volto_di[id(m)]) for m in consentite)
    if len(consentite) >= 2:
        a, b = consentite[0], consentite[1]
        g.x = x_indici(a, b)
        g.w = not g.x and w_mani(a, b)
    return g
