"""Costruzione di mani e volti sintetici per i test dei gesti."""
import numpy as np

from teletrasporto.visione.rilevatori import Mano, Volto

# Lunghezze delle falangi (pixel) e posizione della base di ogni dito rispetto al polso,
# per una mano verticale con le dita verso l'alto.
_BASI = {1: (-35, -30), 5: (-25, -90), 9: (0, -95), 13: (22, -90), 17: (40, -80)}
_FALANGI = [40, 25, 20]


def mano(polso=(0.0, 0.0), tese=(), angolo_gradi=0.0, pollice_dir=None, specchiata=False) -> Mano:
    """Mano con polso in `polso`, dita in `tese` dritte (le altre piegate verso il palmo).

    Dita: "pollice", "indice", "medio", "anulare", "mignolo". `angolo_gradi` ruota la mano
    (0 = dita verso l'alto, positivo = in senso orario sull'immagine). `specchiata` = l'altra mano.
    """
    nomi = {"pollice": 1, "indice": 5, "medio": 9, "anulare": 13, "mignolo": 17}
    punti = np.zeros((21, 3), dtype=np.float32)
    for nome, base in nomi.items():
        bx, by = _BASI[base]
        punti[base, :2] = (bx, by)
        if nome in tese:
            direzione = np.array(pollice_dir if (nome == "pollice" and pollice_dir) else (0.0, -1.0))
            p = np.array([bx, by], dtype=np.float32)
            for k, lung in enumerate(_FALANGI, start=1):
                p = p + direzione * lung
                punti[base + k, :2] = p
        else:
            # Dito piegato: sale un po' e poi torna verso il palmo
            punti[base + 1, :2] = (bx, by - 30)
            punti[base + 2, :2] = (bx, by - 15)
            punti[base + 3, :2] = (bx, by + 5)
    if specchiata:
        punti[:, 0] *= -1
    a = np.radians(angolo_gradi)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]], dtype=np.float32)
    punti[:, :2] = punti[:, :2] @ rot.T + np.array(polso, dtype=np.float32)
    return Mano(punti, "Right", 0.99)


def volto(centro=(640.0, 300.0), larghezza=200.0) -> Volto:
    cx, cy = centro
    s = larghezza / 200
    punti = np.array([
        [cx - 40 * s, cy - 20 * s],   # occhio destro
        [cx + 40 * s, cy - 20 * s],   # occhio sinistro
        [cx, cy + 15 * s],            # naso
        [cx, cy + 55 * s],            # bocca
        [cx - 95 * s, cy],            # orecchio destro
        [cx + 95 * s, cy],            # orecchio sinistro
    ], dtype=np.float32)
    return Volto((cx - larghezza / 2, cy - larghezza * 0.6, larghezza, larghezza * 1.2), punti, 0.95)
