import numpy as np
import pytest

from teletrasporto.composizione import effetti
from teletrasporto.composizione.sfondo import ModelloSfondo
from teletrasporto.funzioni.stato import Stato
from teletrasporto.funzioni.teletrasporto import Teletrasporto
from teletrasporto.scorciatoie import interpreta


def test_teletrasporto_ciclo_completo():
    tp = Teletrasporto(0.5)
    tp.commuta(0.0)
    assert tp.stato == Stato.AVVIO and tp.scomparsa(0.25) == pytest.approx(0.5)
    tp.commuta(0.3)  # ignorato durante la transizione
    tp.aggiorna(0.6)
    assert tp.stato == Stato.ATTIVO and tp.scomparsa(0.6) == 1.0
    tp.commuta(1.0)
    assert tp.stato == Stato.SPEGNIMENTO and tp.scomparsa(1.25) == pytest.approx(0.5)
    tp.aggiorna(1.6)
    assert tp.stato == Stato.SPENTO


def test_spia_teletrasporto_arancione_con_problema():
    tp = Teletrasporto(0.0)
    tp.problema = "sfondo incompleto"
    assert tp.stato_spia == Stato.SPENTO
    tp.commuta(0.0)
    tp.aggiorna(0.1)
    assert tp.stato_spia == Stato.PROBLEMA


def test_effetto_estremi_e_dimensioni():
    rng = np.random.default_rng(0)
    img = np.full((120, 160, 3), 200, np.uint8)
    sfondo = np.zeros_like(img)
    m = np.zeros((120, 160), np.float32)
    m[30:110, 60:100] = 1.0
    assert effetti.teletrasporto(img, sfondo, m, 0.0, rng) is img
    vuoto = effetti.teletrasporto(img, sfondo, m, 1.0, rng)
    assert vuoto[70, 80].max() < 5 and vuoto[5, 5].min() > 195
    meta = effetti.teletrasporto(img, sfondo, m, 0.5, rng)
    assert meta.shape == img.shape and meta.dtype == np.uint8


def test_maschera_morbida_ingrandita_alla_dimensione_del_fotogramma():
    m = np.zeros((36, 64), np.float32)
    m[10:30, 20:40] = 1.0
    grande = effetti.maschera_morbida(m, (128, 72))
    assert grande.shape == (72, 128) and grande[40, 60] > 0.9 and grande[2, 2] < 0.05


def _scena(persona_x=None, colore_persona=200):
    """Muro uniforme (valore 50) con eventualmente una 'persona' larga 20 px in persona_x."""
    img = np.full((100, 200, 3), 50, np.uint8)
    m = np.zeros((100, 200), np.float32)
    if persona_x is not None:
        img[:, persona_x:persona_x + 20] = colore_persona
        m[:, persona_x:persona_x + 20] = 1.0
    return img, m


def test_sfondo_impara_solo_dove_non_c_e_la_persona_e_dopo_conferme():
    s = ModelloSfondo()
    img, m = _scena(90)
    s.aggiorna_auto(img, m)
    assert not s.visto.any()  # un solo fotogramma non basta
    for _ in range(5):
        s.aggiorna_auto(img, m)
    assert s.pronto and s.incompleto
    assert not s.visto[:, 100].any() and s.visto[:, 5].all()
    assert s.immagine().shape == img.shape


def test_persona_non_riconosciuta_per_un_attimo_non_lascia_la_sagoma():
    s = ModelloSfondo()
    vuoto, nessuno = _scena()
    for _ in range(6):
        s.aggiorna_auto(vuoto, nessuno)
    assert not s.incompleto
    # La persona entra ma il segmentatore non la vede per 3 aggiornamenti
    con_persona, _ = _scena(90)
    for _ in range(3):
        s.aggiorna_auto(con_persona, nessuno)
    assert abs(float(s.immagine()[50, 100].mean()) - 50) < 2


def test_persona_che_si_muove_non_entra_mai_nello_sfondo():
    s = ModelloSfondo()
    for i in range(60):
        img, _ = _scena(20 + (i % 8) * 20)
        s.aggiorna_auto(img, np.zeros((100, 200), np.float32))  # segmentatore sempre cieco
    # Il muro viene imparato negli istanti in cui è libero, la persona mai.
    assert s.visto.mean() > 0.9
    assert (s.immagine()[s.visto] == 50).all()


def test_cambio_stabile_viene_accettato_dopo_molto_tempo():
    s = ModelloSfondo()
    vuoto, nessuno = _scena()
    for _ in range(6):
        s.aggiorna_auto(vuoto, nessuno)
    spostato = vuoto.copy()
    spostato[:, :50] = 150  # oggetto spostato: cambia stabilmente
    for _ in range(39):
        s.aggiorna_auto(spostato, nessuno)
    assert s.immagine()[50, 10].mean() < 60
    s.aggiorna_auto(spostato, nessuno)
    assert s.immagine()[50, 10].mean() == 150


def test_cattura_aspetta_che_la_persona_esca():
    s = ModelloSfondo()
    s.avvia_cattura(0.0, 1.0)
    con_persona, m = _scena(90)
    vuoto, nessuno = _scena()
    t = 1.0
    for _ in range(20):  # la persona è ancora lì: quella zona non viene raccolta
        s.aggiorna_cattura(con_persona, m, t)
        t += 0.03
    assert s.in_cattura and s.persona_in_cattura and s.avanzamento_cattura < 1.0
    for _ in range(12):
        s.aggiorna_cattura(vuoto, nessuno, t)
        t += 0.03
    assert not s.in_cattura and not s.incompleto
    assert (s.immagine() == 50).all()  # nessuna traccia della persona


def test_cattura_con_persona_sempre_presente_lascia_il_buco():
    s = ModelloSfondo()
    s.avvia_cattura(0.0, 0.0)
    con_persona, m = _scena(90)
    for i in range(40):
        s.aggiorna_cattura(con_persona, m, i * 0.6)  # supera il tempo massimo
    assert not s.in_cattura and s.incompleto and not s.visto[:, 100].any()


@pytest.mark.parametrize("testo,atteso", [
    ("Ctrl+Alt+L", (0x3, ord("L"))),
    ("ctrl+shift+f5", (0x6, 0x74)),
    ("<ctrl>+<alt>+b", (0x3, ord("B"))),
])
def test_interpreta_scorciatoie(testo, atteso):
    assert interpreta(testo) == atteso


@pytest.mark.parametrize("testo", ["L", "Ctrl+Pippo+L", "Ctrl+", "Ctrl+è"])
def test_scorciatoie_non_valide(testo):
    with pytest.raises(ValueError):
        interpreta(testo)


def test_macchie_piccole_e_incerte_non_sono_persone():
    from teletrasporto.composizione.sfondo import macchie_persona
    m = np.zeros((360, 640), np.float32)
    m[100:300, 250:400] = 0.9   # persona
    m[20:60, 560:600] = 0.3     # cornice vista con poca confidenza
    m[300:305, 10:15] = 0.9     # puntino
    p = macchie_persona(m)
    assert p[200, 300] == 1 and p[40, 580] == 0 and p[302, 12] == 0
    assert macchie_persona(np.zeros((36, 64), np.float32)).sum() == 0


def test_cattura_finisce_anche_con_una_falsa_macchia_di_persona():
    s = ModelloSfondo()
    s.avvia_cattura(0.0, 0.0)
    vuoto, _ = _scena()
    falsa = np.zeros((100, 200), np.float32)
    falsa[5:10, 5:10] = 0.3  # il segmentatore vede "qualcosa" in un angolo
    t = 0.1
    while s.in_cattura and t < 5:
        s.aggiorna_cattura(vuoto, falsa, t)
        t += 0.03
    assert not s.in_cattura and t < 2 and not s.incompleto
    assert (s.immagine() == 50).all()
