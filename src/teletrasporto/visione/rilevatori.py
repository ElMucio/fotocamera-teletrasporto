"""Rilevatori MediaPipe: mani, volti e separazione persona/sfondo."""
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from ..modelli import percorso

# Lato lungo dell'immagine su cui si calcola la maschera della persona.
LATO_MASCHERA = 640


@dataclass
class Mano:
    punti: np.ndarray   # (21, 3) in pixel: x, y, z (z nella stessa scala di x)
    lato: str           # "Left" / "Right" come visto da MediaPipe
    punteggio: float

    @property
    def scala(self) -> float:
        """Distanza polso → base del medio: misura della grandezza della mano."""
        return float(np.linalg.norm(self.punti[9, :2] - self.punti[0, :2])) or 1.0


@dataclass
class Volto:
    riquadro: tuple[float, float, float, float]  # x, y, larghezza, altezza in pixel
    punti: np.ndarray   # (6, 2): occhio dx, occhio sx, naso, bocca, orecchio dx, orecchio sx
    punteggio: float

    @property
    def centro(self) -> np.ndarray:
        x, y, w, h = self.riquadro
        return np.array([x + w / 2, y + h / 2])

    @property
    def larghezza(self) -> float:
        return self.riquadro[2]

    @property
    def fronte(self) -> np.ndarray:
        """Centro della fronte: sopra gli occhi, lungo l'asse bocca → occhi."""
        occhi = (self.punti[0] + self.punti[1]) / 2
        return occhi + (occhi - self.punti[3]) * 0.75


class Rilevatori:
    def __init__(self):
        self._mani = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(percorso("hand_landmarker.task"))),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        ))
        self._volti = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(percorso("blaze_face_short_range.tflite"))),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.5,
        ))
        self._segmentatore = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(percorso("selfie_segmenter.tflite"))),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        ))
        # Ogni task richiede tempi strettamente crescenti.
        self._ultimo_ts = {"mani": -1, "volti": -1, "maschera": -1}

    def _ts(self, chiave: str, ts_ms: int) -> int:
        ts = max(ts_ms, self._ultimo_ts[chiave] + 1)
        self._ultimo_ts[chiave] = ts
        return ts

    def mani(self, rgb: np.ndarray, ts_ms: int) -> list[Mano]:
        h, w = rgb.shape[:2]
        ris = self._mani.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                                          self._ts("mani", ts_ms))
        mani = []
        for punti, lato in zip(ris.hand_landmarks, ris.handedness):
            arr = np.array([[p.x * w, p.y * h, p.z * w] for p in punti], dtype=np.float32)
            mani.append(Mano(arr, lato[0].category_name, lato[0].score))
        return mani

    def volti(self, rgb: np.ndarray, ts_ms: int) -> list[Volto]:
        h, w = rgb.shape[:2]
        ris = self._volti.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                                           self._ts("volti", ts_ms))
        volti = []
        for d in ris.detections:
            b = d.bounding_box
            punti = np.array([[k.x * w, k.y * h] for k in d.keypoints], dtype=np.float32)
            volti.append(Volto((b.origin_x, b.origin_y, b.width, b.height), punti,
                               d.categories[0].score))
        return volti

    def maschera_persona(self, rgb: np.ndarray, ts_ms: int) -> np.ndarray:
        """Probabilità (0..1, float32) che ogni pixel appartenga a una persona.

        Per velocità la maschera è a risoluzione ridotta (lato lungo LATO_MASCHERA):
        chi la usa la ingrandisce quando serve.
        """
        h, w = rgb.shape[:2]
        f = LATO_MASCHERA / max(h, w)
        piccola = cv2.resize(rgb, (round(w * f), round(h * f)), interpolation=cv2.INTER_AREA) if f < 1 else rgb
        ris = self._segmentatore.segment_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(piccola)),
            self._ts("maschera", ts_ms))
        return np.squeeze(ris.confidence_masks[0].numpy_view()).astype(np.float32)

    def chiudi(self) -> None:
        self._mani.close()
        self._volti.close()
        self._segmentatore.close()
