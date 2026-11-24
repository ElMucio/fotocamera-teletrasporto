import numpy as np

from mani_sintetiche import mano, volto
from teletrasporto.autorizzazione import Autorizzatore
from teletrasporto.visione import gesti

V = volto()
# Polso posizionato in modo che le punte di indice e medio cadano sulla fronte
POLSO_FRONTE = tuple(V.fronte - np.array([-12.5, -177.5]))


def test_goku_due_dita_sulla_fronte():
    m = mano(POLSO_FRONTE, tese=("indice", "medio"))
    assert gesti.posa_goku(m, V)


def test_goku_falso_se_la_mano_e_lontana_dalla_fronte():
    m = mano((POLSO_FRONTE[0] + 300, POLSO_FRONTE[1] + 200), tese=("indice", "medio"))
    assert not gesti.posa_goku(m, V)


def test_goku_falso_con_mano_aperta():
    m = mano(POLSO_FRONTE, tese=("indice", "medio", "anulare", "mignolo"))
    assert not gesti.posa_goku(m, V)


def test_goku_falso_con_un_solo_dito():
    m = mano(POLSO_FRONTE, tese=("indice",))
    assert not gesti.posa_goku(m, V)


def test_goku_falso_senza_volto():
    assert not gesti.posa_goku(mano(POLSO_FRONTE, tese=("indice", "medio")), None)


def _x():
    a = mano((600, 500), tese=("indice",), angolo_gradi=40)
    b = mano((680, 500), tese=("indice",), angolo_gradi=-40, specchiata=True)
    return a, b


def test_x_indici_incrociati():
    assert gesti.x_indici(*_x())


def test_x_falso_con_indici_paralleli():
    a = mano((560, 500), tese=("indice",))
    b = mano((720, 500), tese=("indice",), specchiata=True)
    assert not gesti.x_indici(a, b)


def test_x_falso_con_mani_aperte():
    a = mano((600, 500), tese=("indice", "medio", "anulare"), angolo_gradi=40)
    b = mano((680, 500), tese=("indice", "medio", "anulare"), angolo_gradi=-40, specchiata=True)
    assert not gesti.x_indici(a, b)


def _w():
    a = mano((570, 500), tese=("indice", "pollice"), pollice_dir=(1.0, 0.0))
    b = mano((710, 500), tese=("indice", "pollice"), pollice_dir=(1.0, 0.0), specchiata=True)
    return a, b


def test_w_pollici_uniti_indici_in_su():
    assert gesti.w_mani(*_w())


def test_w_falso_con_pollici_lontani():
    a = mano((450, 500), tese=("indice", "pollice"), pollice_dir=(1.0, 0.0))
    b = mano((830, 500), tese=("indice", "pollice"), pollice_dir=(1.0, 0.0), specchiata=True)
    assert not gesti.w_mani(a, b)


def test_w_falso_con_indici_in_giu():
    a = mano((570, 300), tese=("indice", "pollice"), angolo_gradi=180, pollice_dir=(1.0, 0.0))
    b = mano((710, 300), tese=("indice", "pollice"), angolo_gradi=180, pollice_dir=(1.0, 0.0),
             specchiata=True)
    assert not gesti.w_mani(a, b)


def test_valuta_distingue_x_e_w():
    g = gesti.valuta(list(_x()), [], Autorizzatore())
    assert g.x and not g.w and not g.goku
    g = gesti.valuta(list(_w()), [], Autorizzatore())
    assert g.w and not g.x


def test_valuta_rispetta_l_autorizzazione():
    class Nessuno(Autorizzatore):
        def consentito(self, volto):
            return False
    m = mano(POLSO_FRONTE, tese=("indice", "medio"))
    assert gesti.valuta([m], [V], Autorizzatore()).goku
    assert not gesti.valuta([m], [V], Nessuno()).goku


def test_x_non_viene_mai_letto_come_w():
    a, b = _x()
    assert not gesti.w_mani(a, b)
    # anche con i pollici tesi e vicini
    a = mano((600, 500), tese=("indice", "pollice"), angolo_gradi=40, pollice_dir=(1.0, 0.0))
    b = mano((680, 500), tese=("indice", "pollice"), angolo_gradi=-40, pollice_dir=(1.0, 0.0),
             specchiata=True)
    assert gesti.x_indici(a, b) and not gesti.w_mani(a, b)


def test_x_tollera_punte_che_si_sfiorano_appena():
    # mani un po' più distanti: i segmenti base-punta si fermano poco prima di incrociarsi
    a = mano((585, 500), tese=("indice",), angolo_gradi=40)
    b = mano((780, 500), tese=("indice",), angolo_gradi=-40, specchiata=True)
    pa1, pa2 = a.punti[5, :2], a.punti[8, :2]
    pb1, pb2 = b.punti[5, :2], b.punti[8, :2]
    assert not gesti._segmenti_incrociati(pa1, pa2, pb1, pb2)
    assert gesti.x_indici(a, b)


def test_w_falso_con_pollici_verso_l_esterno():
    a = mano((570, 500), tese=("indice", "pollice"), pollice_dir=(-1.0, 0.0))
    b = mano((650, 500), tese=("indice", "pollice"), pollice_dir=(-1.0, 0.0), specchiata=True)
    assert not gesti.w_mani(a, b)
