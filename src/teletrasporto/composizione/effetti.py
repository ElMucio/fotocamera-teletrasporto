"""Composizione persona/sfondo ed effetto di teletrasporto stile Dragon Ball."""
import cv2
import numpy as np

_BIANCO_AZZURRO = (255, 245, 225)  # BGR


def _smoothstep(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def maschera_morbida(maschera: np.ndarray, dimensione: tuple[int, int]) -> np.ndarray:
    """Maschera della persona leggermente allargata e con bordi sfumati (float32 0..1).

    Si lavora alla risoluzione della maschera e solo alla fine si ingrandisce a `dimensione`
    (larghezza, altezza) del fotogramma.
    """
    w = maschera.shape[1]
    m = np.clip((maschera - 0.25) / 0.5, 0, 1).astype(np.float32)
    k = max(3, int(w * 0.012)) | 1
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    m = cv2.GaussianBlur(m, (0, 0), sigmaX=max(1.0, w * 0.005))
    if (m.shape[1], m.shape[0]) != dimensione:
        m = cv2.resize(m, dimensione, interpolation=cv2.INTER_LINEAR)
    return m


def nascondi(fotogramma: np.ndarray, sfondo: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Sostituisce la persona (maschera m) con lo sfondo."""
    return cv2.blendLinear(fotogramma, sfondo, 1.0 - m, m)


def teletrasporto(fotogramma: np.ndarray, sfondo: np.ndarray, m: np.ndarray, p: float,
                  rng: np.random.Generator) -> np.ndarray:
    """Effetto di scomparsa: p = 0 persona visibile, p = 1 persona sparita.

    La persona si comprime verso una linea verticale, si scompone in strisce verticali luminose
    e svanisce con un breve lampo. Per la ricomparsa si usa lo stesso effetto con p decrescente.
    Lo strato dell'effetto si calcola a metà risoluzione: dura meno di mezzo secondo.
    """
    if p <= 0.0:
        return fotogramma
    vuoto = nascondi(fotogramma, sfondo, m)
    if p >= 1.0:
        return vuoto
    H, W = fotogramma.shape[:2]
    w, h = W // 2, H // 2
    img = cv2.resize(fotogramma, (w, h), interpolation=cv2.INTER_AREA)
    ms = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)
    ys, xs = np.nonzero(ms > 0.5)
    if len(xs) == 0:
        return vuoto
    cx, cy = float(xs.mean()), float(ys.mean())

    # Compressione orizzontale verso il centro della persona, con un leggero allungamento verticale.
    q = _smoothstep(0.0, 0.75, p)
    sx, sy = max(0.02, 1.0 - 0.98 * q), 1.0 + 0.1 * q
    M = np.float32([[sx, 0, cx * (1 - sx)], [0, sy, cy * (1 - sy)]])
    persona = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    alfa = cv2.warpAffine(ms, M, (w, h), flags=cv2.INTER_LINEAR)

    # Strisce verticali: alcune colonne vengono "stirate" in verticale, sempre più numerose.
    lungo = max(3, int(h * (0.05 + 0.25 * p))) | 1
    colonne = rng.random(w) < (0.1 + 0.6 * p)
    persona_s = cv2.blur(persona, (1, lungo))
    alfa_s = cv2.blur(alfa, (1, lungo))
    persona[:, colonne] = persona_s[:, colonne]
    alfa[:, colonne] = np.minimum(1.0, np.maximum(alfa[:, colonne], alfa_s[:, colonne] * 1.5))

    # Bagliore: la persona diventa sempre più chiara.
    bagliore = min(1.0, p * 1.4) * 0.75
    persona = cv2.addWeighted(persona, 1 - bagliore, np.full_like(persona, _BIANCO_AZZURRO), bagliore, 0)
    alfa *= 1.0 - _smoothstep(0.7, 1.0, p)

    persona = cv2.resize(persona, (W, H), interpolation=cv2.INTER_LINEAR)
    alfa = cv2.resize(alfa, (W, H), interpolation=cv2.INTER_LINEAR)
    uscita = cv2.blendLinear(vuoto, persona, 1.0 - alfa, alfa)

    # Lampo breve verso la fine della compressione.
    lampo = 0.3 * float(np.exp(-((p - 0.65) / 0.08) ** 2))
    if lampo > 0.01:
        uscita = cv2.addWeighted(uscita, 1 - lampo, np.full_like(uscita, 255), lampo, 0)
    return uscita
