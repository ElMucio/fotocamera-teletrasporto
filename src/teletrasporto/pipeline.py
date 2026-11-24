"""Elaborazione in tempo reale: webcam → gesti → funzioni → composizione → uscite."""
import logging
import queue
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .autorizzazione import Autorizzatore
from .cattura import Webcam
from .clip import ArchivioClip
from .composizione import effetti
from .composizione.sfondo import ModelloSfondo
from .funzioni.loop import FaseLoop, FunzioneLoop
from .funzioni.stato import Stato
from .funzioni.teletrasporto import Teletrasporto
from .impostazioni import Impostazioni
from .uscita.fotocamera_virtuale import ErroreFotocameraVirtuale, FotocameraVirtualeOBS
from .ui import sovrapposizioni as sv
from .visione import gesti
from .visione.rilevatori import Rilevatori
from .visione.tenuta import TimerTenuta

log = logging.getLogger(__name__)

_MEMORIA_VOLTO = 1.5      # s: il volto resta valido anche se la mano lo copre per un po'
_OGNI_N_MASCHERA = 6      # fotogrammi tra due aggiornamenti dello sfondo (~5 al secondo)
_CONTO_CATTURA_SFONDO = 5.0


def _analizza_mani(rilevatori: Rilevatori, rgb: np.ndarray, ts_ms: int, t: float):
    """Mani e, se ci sono mani, volti (servono per la posa sulla fronte e per l'autorizzazione)."""
    mani = rilevatori.mani(rgb, ts_ms)
    volti = rilevatori.volti(rgb, ts_ms) if mani else []
    return mani, volti, t


class Pipeline(QObject):
    anteprima = Signal(QImage)
    stato = Signal(dict)

    def __init__(self, imp: Impostazioni, archivio: ArchivioClip):
        super().__init__()
        self.imp = imp
        self.archivio = archivio
        self._comandi: queue.Queue[str] = queue.Queue()
        self._ferma = threading.Event()
        self._thread: threading.Thread | None = None

    # --- controllo dal thread dell'interfaccia o delle scorciatoie -----------------------------

    def avvia(self, indice_webcam: int) -> None:
        self.ferma()
        self._ferma.clear()
        self._thread = threading.Thread(target=self._esegui_protetto, args=(indice_webcam,),
                                        name="pipeline", daemon=True)
        self._thread.start()

    def ferma(self) -> None:
        if self._thread and self._thread.is_alive():
            self._ferma.set()
            self._thread.join(timeout=5)
        self._thread = None

    @property
    def in_esecuzione(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def comando(self, nome: str) -> None:
        """'live', 'gesti', 'sfondo', 'teletrasporto', 'x', 'w' (thread-safe)."""
        self._comandi.put(nome)

    # --- ciclo di elaborazione ----------------------------------------------------------------

    def _esegui_protetto(self, indice_webcam: int) -> None:
        try:
            self._esegui(indice_webcam)
        except Exception as e:  # noqa: BLE001
            log.exception("Errore nell'elaborazione")
            self.stato.emit({"errore": f"Errore interno: {e}"})

    def _esegui(self, indice_webcam: int) -> None:
        imp = self.imp
        rilevatori = Rilevatori()
        webcam = Webcam(indice_webcam, imp.larghezza, imp.altezza, imp.fps)
        webcam.avvia()

        autorizzatore = Autorizzatore()
        sfondo = ModelloSfondo()
        tp = Teletrasporto(imp.durata_effetto)
        loop = FunzioneLoop(self.archivio, imp.conto_alla_rovescia, imp.durata_clip, imp.dissolvenza_loop)
        timer_goku, timer_x, timer_w = TimerTenuta(imp.tenuta_goku), TimerTenuta(imp.tenuta_x), TimerTenuta(imp.tenuta_w)
        rng = np.random.default_rng()
        esecutore = ThreadPoolExecutor(max_workers=1, thread_name_prefix="maschera")
        # Le mani si analizzano in un thread a parte, al loro ritmo: l'uscita video non le aspetta.
        esecutore_mani = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mani")
        futuro_mani = None
        mani: list = []
        g = gesti.Gesti()

        vcam: FotocameraVirtualeOBS | None = None
        errore_vcam: str | None = None
        prossimo_tentativo_vcam = 0.0
        volti, t_volti = [], -1e9
        maschera = None
        n = 0
        t_stato, fps, t_prec = 0.0, 0.0, time.monotonic()

        try:
            while not self._ferma.is_set():
                img = webcam.leggi(timeout=0.5)
                t = time.monotonic()
                ts_ms = int(t * 1000)

                # Comandi da pulsanti e scorciatoie
                while not self._comandi.empty():
                    c = self._comandi.get_nowait()
                    if c == "live":
                        loop.torna_live()
                        tp.ricompari(t)
                    elif c == "gesti":
                        imp.gesti_attivi = not imp.gesti_attivi
                    elif c == "sfondo":
                        sfondo.avvia_cattura(t, _CONTO_CATTURA_SFONDO)
                    elif c == "teletrasporto":
                        tp.commuta(t)
                    elif c == "x":
                        loop.gesto_x(t)
                    elif c == "w":
                        loop.gesto_w(t)

                if img is None:
                    self._senza_webcam(webcam.errore or "in attesa della webcam...", vcam)
                    continue
                n += 1

                # Parametri modificabili mentre il programma gira
                timer_goku.durata, timer_x.durata, timer_w.durata = imp.tenuta_goku, imp.tenuta_x, imp.tenuta_w
                tp.durata_effetto = imp.durata_effetto
                loop.conto_alla_rovescia, loop.durata_clip = imp.conto_alla_rovescia, imp.durata_clip
                loop.dissolvenza = imp.dissolvenza_loop
                if self.archivio.massimo != imp.clip_da_conservare:
                    self.archivio.massimo = imp.clip_da_conservare
                if not imp.teletrasporto_attivo and tp.stato in (Stato.ATTIVO, Stato.AVVIO):
                    tp.ricompari(t)
                if not imp.loop_attivo and loop.fase != FaseLoop.INATTIVO:
                    loop.torna_live()

                # La maschera della persona si calcola in parallelo al rilevamento delle mani
                # (MediaPipe rilascia il GIL). Serve a ogni fotogramma solo durante il teletrasporto.
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                aggiorna_sfondo = n % _OGNI_N_MASCHERA == 0
                serve_maschera = (tp.stato != Stato.SPENTO or timer_goku.progresso > 0.8
                                  or sfondo.in_cattura or aggiorna_sfondo)
                futuro = esecutore.submit(rilevatori.maschera_persona, rgb, ts_ms) if serve_maschera else None

                # --- gesti (sempre sul fotogramma reale della webcam) ---
                if futuro_mani is not None and futuro_mani.done():
                    mani, nuovi_volti, t_analisi = futuro_mani.result()
                    futuro_mani = None
                    if nuovi_volti:
                        volti, t_volti = nuovi_volti, t_analisi
                    if t - t_volti > _MEMORIA_VOLTO:
                        volti = []
                    g = gesti.valuta(mani, volti, autorizzatore) if imp.gesti_attivi else gesti.Gesti()
                if futuro_mani is None:
                    if imp.gesti_attivi or imp.mostra_punti_mani:
                        futuro_mani = esecutore_mani.submit(_analizza_mani, rilevatori, rgb, ts_ms, t)
                    else:
                        mani, g = [], gesti.Gesti()
                # Quando un gesto scatta gli altri si azzerano e vanno rilasciati: un gesto ambiguo
                # non può far scattare anche l'altro subito dopo.
                timer = {"goku": timer_goku, "x": timer_x, "w": timer_w}
                scattato = None
                if timer_goku.aggiorna(g.goku and imp.teletrasporto_attivo, t):
                    scattato = "goku"
                    tp.commuta(t)
                if timer_x.aggiorna(g.x and imp.loop_attivo, t) and scattato is None:
                    scattato = "x"
                    loop.gesto_x(t)
                if timer_w.aggiorna(g.w and imp.loop_attivo, t) and scattato is None:
                    scattato = "w"
                    loop.gesto_w(t)
                if scattato:
                    log.info("Gesto %s → teletrasporto %s, loop %s", scattato.upper(),
                             tp.stato.value, loop.fase.value)
                    for nome, altro in timer.items():
                        if nome != scattato:
                            altro.blocca()
                tp.aggiorna(t)

                # --- sfondo e maschera della persona ---
                if futuro is not None:
                    maschera = futuro.result()
                    if sfondo.in_cattura:
                        sfondo.aggiorna_cattura(img, maschera, t)
                    elif aggiorna_sfondo:
                        sfondo.aggiorna_auto(img, maschera)
                if not sfondo.pronto:
                    tp.problema = "sfondo non ancora pronto"
                elif sfondo.incompleto:
                    tp.problema = "sfondo incompleto: premi Cattura sfondo ed esci dall'inquadratura"
                else:
                    tp.problema = None

                # --- composizione ---
                pulito = img
                scomparsa = tp.scomparsa(t)
                if scomparsa > 0 and sfondo.pronto and maschera is not None:
                    m = effetti.maschera_morbida(maschera, (img.shape[1], img.shape[0]))
                    pulito = effetti.teletrasporto(img, sfondo.immagine(), m, scomparsa, rng)
                sostituto = loop.aggiorna(t, pulito)
                uscita = sostituto if sostituto is not None else pulito

                # --- fotocamera virtuale ---
                if imp.fotocamera_virtuale:
                    if vcam is None and t >= prossimo_tentativo_vcam:
                        try:
                            h, w = uscita.shape[:2]
                            vcam = FotocameraVirtualeOBS(w, h, imp.fps)
                            errore_vcam = None
                        except (ErroreFotocameraVirtuale, OSError, ValueError) as e:
                            errore_vcam = str(e)
                            prossimo_tentativo_vcam = t + 3.0
                    if vcam is not None:
                        vcam.invia(uscita)
                elif vcam is not None:
                    vcam.chiudi()
                    vcam = None

                # --- anteprima ---
                dt = t - t_prec
                t_prec = t
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if dt > 0 else fps
                spie = [
                    sv.Spia("TELETRASPORTO", tp.stato_spia if imp.teletrasporto_attivo else Stato.SPENTO,
                            timer_goku.progresso),
                    sv.Spia("LOOP", loop.stato_spia(t), max(timer_x.progresso, timer_w.progresso)),
                    sv.Spia("CAM VIRTUALE", Stato.PROBLEMA if errore_vcam else
                            (Stato.ATTIVO if vcam is not None else Stato.SPENTO)),
                ]
                self._emetti_anteprima(img, uscita, mani, volti, spie, loop, sfondo, tp, t, g)
                if t - t_stato > 0.25:
                    t_stato = t
                    self.stato.emit({
                        "spie": {s.etichetta: s.stato for s in spie},
                        "fps": fps,
                        "messaggi": self._messaggi(webcam, errore_vcam, loop, tp, imp),
                        "clip": len(self.archivio),
                        "sfondo": 1.0 - sfondo.frazione_buchi,
                        "gesti_attivi": imp.gesti_attivi,
                    })
        finally:
            esecutore.shutdown(wait=True)
            esecutore_mani.shutdown(wait=True)
            webcam.ferma()
            if vcam is not None:
                vcam.chiudi()
            rilevatori.chiudi()

    def _messaggi(self, webcam, errore_vcam, loop, tp, imp) -> list[str]:
        m = []
        if webcam.errore:
            m.append(webcam.errore)
        if errore_vcam and imp.fotocamera_virtuale:
            m.append(f"Fotocamera virtuale: {errore_vcam}")
        if loop.avviso:
            m.append(loop.avviso)
        if tp.problema and tp.stato != Stato.SPENTO:
            m.append(tp.problema)
        if not imp.gesti_attivi:
            m.append("gesti disattivati")
        return m

    def _emetti_anteprima(self, img, uscita, mani, volti, spie, loop, sfondo, tp, t, g) -> None:
        imp = self.imp
        if imp.anteprima_sfondo and sfondo.pronto:
            prev = sfondo.immagine().copy()
        else:
            prev = (uscita if imp.anteprima_uscita else img).copy()
        if imp.mostra_punti_mani:
            sv.disegna_punti(prev, mani, volti)
        if imp.specchio_anteprima:
            prev = cv2.flip(prev, 1)
        sv.disegna_spie(prev, spie)
        sv.disegna_gesti(prev, [n for n, attivo in (("GOKU", g.goku), ("X", g.x), ("W", g.w)) if attivo])
        if loop.fase == FaseLoop.CONTO:
            sv.disegna_centro(prev, f"{int(np.ceil(loop.secondi_rimanenti(t)))}", "abbassa le mani: registrazione in arrivo")
        elif loop.fase == FaseLoop.REGISTRAZIONE:
            sv.disegna_rec(prev, loop.secondi_rimanenti(t))
        if sfondo.in_cattura:
            sec = sfondo.secondi_alla_cattura(t)
            if sec > 0:
                sv.disegna_centro(prev, f"{int(np.ceil(sec))}", "esci dall'inquadratura: catturo lo sfondo")
            else:
                sv.disegna_centro(prev, f"{sfondo.avanzamento_cattura:.0%}",
                                  "ti vedo ancora: esci dall'inquadratura" if sfondo.persona_in_cattura
                                  else "catturo lo sfondo, resta fuori")
        messaggi = [loop.avviso] if loop.avviso else []
        if tp.problema and tp.stato != Stato.SPENTO:
            messaggi.append(tp.problema)
        sv.disegna_messaggi(prev, messaggi)
        rgb = cv2.cvtColor(prev, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        self.anteprima.emit(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())

    def _senza_webcam(self, testo: str, vcam) -> None:
        h, w = self.imp.altezza, self.imp.larghezza
        nero = np.zeros((h - h % 2, w - w % 2, 3), np.uint8)
        if vcam is not None:
            vcam.invia(nero)
        sv.disegna_messaggi(nero, [testo])
        rgb = cv2.cvtColor(nero, cv2.COLOR_BGR2RGB)
        self.anteprima.emit(QImage(rgb.data, rgb.shape[1], rgb.shape[0], 3 * rgb.shape[1],
                                   QImage.Format.Format_RGB888).copy())
        self.stato.emit({"messaggi": [testo], "spie": {}, "fps": 0.0})
