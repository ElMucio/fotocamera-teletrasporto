"""Scarica i modelli MediaPipe nella cartella models/ (solo quelli mancanti)."""
import sys
import urllib.request

from .percorsi import MODELLI

BASE = "https://storage.googleapis.com/mediapipe-models"
FILE = {
    "hand_landmarker.task": f"{BASE}/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "blaze_face_short_range.tflite": f"{BASE}/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
    "selfie_segmenter.tflite": f"{BASE}/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
}


def percorso(nome: str):
    return MODELLI / nome


def scarica_mancanti() -> None:
    MODELLI.mkdir(parents=True, exist_ok=True)
    for nome, url in FILE.items():
        dest = MODELLI / nome
        if dest.exists() and dest.stat().st_size > 0:
            continue
        print(f"Scarico il modello {nome}...")
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)


if __name__ == "__main__":
    try:
        scarica_mancanti()
    except OSError as e:
        print(f"Download dei modelli non riuscito: {e}", file=sys.stderr)
        sys.exit(1)
