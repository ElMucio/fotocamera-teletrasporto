"""Finestra principale: anteprima, comandi e impostazioni."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSizePolicy,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..cattura import scegli_webcam, webcam_selezionabili
from ..funzioni.stato import COLORE_SPIA, Stato
from ..impostazioni import Impostazioni
from ..pipeline import Pipeline
from ..scorciatoie import Scorciatoie

_RISOLUZIONI = [(640, 480), (1280, 720), (1920, 1080)]
_GUIDA = (
    "<b>Gesti</b><br>"
    "• <b>Teletrasporto</b>: indice e medio uniti sulla fronte per 3 s → sparisci; "
    "rifallo per ricomparire.<br>"
    "• <b>X</b> (due indici incrociati): dopo 2 s registra 10 s e va in loop; "
    "X durante il loop torna al live.<br>"
    "• <b>W</b> (pollici che si toccano, indici in su): va in loop l'ultima clip; "
    "durante il loop passa alla precedente.<br><br>"
    "Prima di usare il teletrasporto premi <b>Cattura sfondo</b> ed esci dall'inquadratura."
)


def _colore_css(stato: Stato) -> str:
    b, g, r = COLORE_SPIA[stato]
    return f"rgb({r},{g},{b})"


class Anteprima(QLabel):
    def __init__(self):
        super().__init__("Avvio in corso...")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#111; color:#aaa;")

    def mostra(self, img: QImage) -> None:
        self.setPixmap(QPixmap.fromImage(img).scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class Finestra(QMainWindow):
    # Le scorciatoie arrivano da un altro thread: passano da un segnale per l'interfaccia.
    _scorciatoia_premuta = Signal(str)

    def __init__(self, imp: Impostazioni, pipeline: Pipeline):
        super().__init__()
        self.imp, self.pipeline = imp, pipeline
        self.scorciatoie = Scorciatoie()
        self.setWindowTitle("Fotocamera Teletrasporto")
        self.resize(1320, 760)

        self.anteprima = Anteprima()
        schede = QTabWidget()
        schede.setFixedWidth(380)
        schede.addTab(self._scorrevole(self._scheda_comandi()), "Comandi")
        schede.addTab(self._scorrevole(self._scheda_impostazioni()), "Impostazioni")

        centrale = QWidget()
        lay = QHBoxLayout(centrale)
        lay.addWidget(self.anteprima, 1)
        lay.addWidget(schede)
        self.setCentralWidget(centrale)

        self._salvataggio = QTimer(self, singleShot=True, interval=600, timeout=self.imp.salva)
        pipeline.anteprima.connect(self.anteprima.mostra)
        pipeline.stato.connect(self._aggiorna_stato)
        self._scorciatoia_premuta.connect(self.pipeline.comando)
        self._applica_scorciatoie()
        QTimer.singleShot(0, self.avvia)

    # --- costruzione ------------------------------------------------------------------------

    @staticmethod
    def _scorrevole(contenuto: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidget(contenuto)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return area

    def _check(self, testo: str, campo: str) -> QCheckBox:
        c = QCheckBox(testo)
        c.setChecked(getattr(self.imp, campo))
        c.toggled.connect(lambda v: self._imposta(campo, v))
        return c

    def _decimale(self, campo: str, minimo: float, massimo: float, passo: float = 0.1) -> QDoubleSpinBox:
        s = QDoubleSpinBox(minimum=minimo, maximum=massimo, singleStep=passo, decimals=2, suffix=" s")
        s.setValue(getattr(self.imp, campo))
        s.valueChanged.connect(lambda v: self._imposta(campo, float(v)))
        return s

    def _scheda_comandi(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        stato = QGroupBox("Stato")
        f = QFormLayout(stato)
        self._spie: dict[str, QLabel] = {}
        for nome in ("TELETRASPORTO", "LOOP", "CAM VIRTUALE"):
            lab = QLabel("●  —")
            self._spie[nome] = lab
            f.addRow(nome.capitalize() + ":", lab)
        self._info = QLabel("")
        f.addRow("Info:", self._info)
        self._messaggi = QLabel("")
        self._messaggi.setWordWrap(True)
        self._messaggi.setStyleSheet("color:#d97706;")
        f.addRow(self._messaggi)
        v.addWidget(stato)

        comandi = QGroupBox("Comandi")
        g = QVBoxLayout(comandi)
        self._pulsante_avvio = QPushButton("Ferma")
        self._pulsante_avvio.clicked.connect(self._avvia_ferma)
        sfondo = QPushButton("Cattura sfondo (5 s per uscire)")
        sfondo.clicked.connect(lambda: self.pipeline.comando("sfondo"))
        live = QPushButton("Torna al live")
        live.clicked.connect(lambda: self.pipeline.comando("live"))
        prova = QHBoxLayout()
        for testo, cmd in (("Teletrasporto", "teletrasporto"), ("X", "x"), ("W", "w")):
            b = QPushButton(testo)
            b.setToolTip("Simula il gesto, utile per le prove")
            b.clicked.connect(lambda _=False, c=cmd: self.pipeline.comando(c))
            prova.addWidget(b)
        for widget in (self._pulsante_avvio, sfondo, live):
            g.addWidget(widget)
        g.addWidget(QLabel("Simula gesto:"))
        g.addLayout(prova)
        v.addWidget(comandi)

        funzioni = QGroupBox("Funzioni")
        g = QVBoxLayout(funzioni)
        self._check_gesti = self._check("Riconoscimento gesti", "gesti_attivi")
        for widget in (self._check_gesti, self._check("Teletrasporto", "teletrasporto_attivo"),
                       self._check("Loop (X / W)", "loop_attivo"),
                       self._check("Invia alla fotocamera virtuale", "fotocamera_virtuale")):
            g.addWidget(widget)
        v.addWidget(funzioni)

        anteprima = QGroupBox("Anteprima")
        g = QVBoxLayout(anteprima)
        for widget in (self._check("Effetto specchio", "specchio_anteprima"),
                       self._check("Mostra l'uscita (altrimenti la webcam grezza)", "anteprima_uscita"),
                       self._check("Mostra i punti delle mani", "mostra_punti_mani"),
                       self._check("Mostra lo sfondo memorizzato", "anteprima_sfondo")):
            g.addWidget(widget)
        v.addWidget(anteprima)

        guida = QLabel(_GUIDA)
        guida.setWordWrap(True)
        v.addWidget(guida)
        v.addStretch()
        return w

    def _scheda_impostazioni(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        webcam = QGroupBox("Webcam")
        f = QFormLayout(webcam)
        self._combo_webcam = QComboBox()
        self._combo_webcam.addItems(webcam_selezionabili())
        if self.imp.nome_webcam:
            self._combo_webcam.setCurrentText(self.imp.nome_webcam)
        self._combo_webcam.currentTextChanged.connect(self._cambia_webcam)
        self._combo_ris = QComboBox()
        for lw, lh in _RISOLUZIONI:
            self._combo_ris.addItem(f"{lw} × {lh}", (lw, lh))
        i = self._combo_ris.findData((self.imp.larghezza, self.imp.altezza))
        self._combo_ris.setCurrentIndex(i if i >= 0 else 1)
        self._combo_ris.currentIndexChanged.connect(self._cambia_risoluzione)
        fps = QSpinBox(minimum=10, maximum=60, value=self.imp.fps)
        fps.valueChanged.connect(lambda val: (self._imposta("fps", val), self._riavvia_presto()))
        f.addRow("Dispositivo:", self._combo_webcam)
        f.addRow("Risoluzione:", self._combo_ris)
        f.addRow("Fotogrammi/s:", fps)
        v.addWidget(webcam)

        tempi = QGroupBox("Tempi")
        f = QFormLayout(tempi)
        f.addRow("Tenuta posa Goku:", self._decimale("tenuta_goku", 0.5, 10))
        f.addRow("Tenuta X:", self._decimale("tenuta_x", 0.1, 5))
        f.addRow("Tenuta W:", self._decimale("tenuta_w", 0.1, 5))
        f.addRow("Durata effetto:", self._decimale("durata_effetto", 0.0, 3, 0.05))
        f.addRow("Attesa prima di registrare:", self._decimale("conto_alla_rovescia", 0, 10, 0.5))
        f.addRow("Durata clip:", self._decimale("durata_clip", 2, 60, 1))
        f.addRow("Dissolvenza del loop:", self._decimale("dissolvenza_loop", 0, 3, 0.1))
        n = QSpinBox(minimum=1, maximum=20, value=self.imp.clip_da_conservare)
        n.valueChanged.connect(lambda val: self._imposta("clip_da_conservare", val))
        f.addRow("Clip da conservare:", n)
        v.addWidget(tempi)

        scorciatoie = QGroupBox("Scorciatoie globali")
        f = QFormLayout(scorciatoie)
        f.addRow(self._check("Attive", "scorciatoie_attive"))
        self._campi_scorciatoie = {}
        for campo, testo in (("scorciatoia_live", "Torna al live:"),
                             ("scorciatoia_gesti", "Gesti on/off:"),
                             ("scorciatoia_sfondo", "Cattura sfondo:")):
            e = QLineEdit(getattr(self.imp, campo))
            self._campi_scorciatoie[campo] = e
            f.addRow(testo, e)
        applica = QPushButton("Applica scorciatoie")
        applica.clicked.connect(self._salva_scorciatoie)
        f.addRow(applica)
        self._errori_scorciatoie = QLabel("")
        self._errori_scorciatoie.setWordWrap(True)
        self._errori_scorciatoie.setStyleSheet("color:#d97706;")
        f.addRow(self._errori_scorciatoie)
        v.addWidget(scorciatoie)
        v.addStretch()
        return w

    # --- azioni -----------------------------------------------------------------------------

    def _imposta(self, campo: str, valore) -> None:
        setattr(self.imp, campo, valore)
        if campo == "scorciatoie_attive":
            self._applica_scorciatoie()
        self._salvataggio.start()

    def avvia(self) -> None:
        scelta = scegli_webcam(self.imp.nome_webcam)
        if scelta is None:
            self._messaggi.setText("Nessuna webcam trovata.")
            self._pulsante_avvio.setText("Avvia")
            return
        indice, nome = scelta
        self.pipeline.avvia(indice)
        self._pulsante_avvio.setText("Ferma")
        self.statusBar().showMessage(f"Webcam: {nome}")

    def _avvia_ferma(self) -> None:
        if self.pipeline.in_esecuzione:
            self.pipeline.ferma()
            self._pulsante_avvio.setText("Avvia")
            self.anteprima.setText("Fermo")
        else:
            self.avvia()

    def _riavvia_presto(self) -> None:
        if self.pipeline.in_esecuzione:
            QTimer.singleShot(300, self.avvia)

    def _cambia_webcam(self, nome: str) -> None:
        self._imposta("nome_webcam", nome)
        self._riavvia_presto()

    def _cambia_risoluzione(self, _i: int) -> None:
        lw, lh = self._combo_ris.currentData()
        self._imposta("larghezza", lw)
        self._imposta("altezza", lh)
        self._riavvia_presto()

    def _salva_scorciatoie(self) -> None:
        for campo, e in self._campi_scorciatoie.items():
            setattr(self.imp, campo, e.text().strip())
        self.imp.salva()
        self._applica_scorciatoie()

    def _applica_scorciatoie(self) -> None:
        self.scorciatoie.ferma()
        if not self.imp.scorciatoie_attive:
            self._errori_scorciatoie.setText("")
            return
        azioni = {
            self.imp.scorciatoia_live: lambda: self._scorciatoia_premuta.emit("live"),
            self.imp.scorciatoia_gesti: lambda: self._scorciatoia_premuta.emit("gesti"),
            self.imp.scorciatoia_sfondo: lambda: self._scorciatoia_premuta.emit("sfondo"),
        }
        errori = self.scorciatoie.avvia({k: f for k, f in azioni.items() if k})
        self._errori_scorciatoie.setText("\n".join(errori))

    def _aggiorna_stato(self, s: dict) -> None:
        if "errore" in s:
            self._messaggi.setText(s["errore"])
            self._pulsante_avvio.setText("Avvia")
            return
        for nome, stato in s.get("spie", {}).items():
            if nome in self._spie:
                self._spie[nome].setText(
                    f"<span style='color:{_colore_css(stato)}; font-size:16px'>●</span>  {stato.value}")
        self._info.setText(f"{s.get('fps', 0):.0f} fps · clip salvate: {s.get('clip', 0)}"
                           f" · sfondo noto: {s.get('sfondo', 0):.0%}")
        self._messaggi.setText("\n".join(s.get("messaggi", [])))
        if "gesti_attivi" in s and s["gesti_attivi"] != self._check_gesti.isChecked():
            self._check_gesti.blockSignals(True)
            self._check_gesti.setChecked(s["gesti_attivi"])
            self._check_gesti.blockSignals(False)
            self._salvataggio.start()

    def closeEvent(self, e) -> None:
        self.scorciatoie.ferma()
        self.pipeline.ferma()
        self.imp.salva()
        super().closeEvent(e)
