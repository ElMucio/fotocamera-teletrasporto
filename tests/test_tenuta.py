from teletrasporto.visione.tenuta import TimerTenuta


def _scorri(timer, attivo, da, a, passo=0.05):
    scatti = []
    for i in range(round((a - da) / passo) + 1):
        t = round(da + i * passo, 4)
        if timer.aggiorna(attivo(t) if callable(attivo) else attivo, t):
            scatti.append(round(t, 2))
    return scatti


def test_scatta_dopo_la_durata():
    assert _scorri(TimerTenuta(3.0), True, 0, 3.2) == [3.0]


def test_non_scatta_se_rilasciato_prima():
    assert _scorri(TimerTenuta(3.0), lambda t: t < 2.0, 0, 5) == []


def test_brevi_interruzioni_tollerate():
    # buco di 0.15 s a metà: il conteggio continua
    assert _scorri(TimerTenuta(1.0, tolleranza=0.25), lambda t: not (0.5 < t < 0.65), 0, 1.2) == [1.0]


def test_interruzione_lunga_azzera():
    assert _scorri(TimerTenuta(1.0, tolleranza=0.25), lambda t: not (0.5 < t < 1.0), 0, 1.4) == []


def test_serve_rilasciare_prima_di_riscattare():
    timer = TimerTenuta(1.0, attesa=0.5)
    assert _scorri(timer, True, 0, 5) == [1.0]  # tenuto fermo: scatta una volta sola
    assert _scorri(timer, False, 5.05, 6) == []
    assert _scorri(timer, True, 6.05, 7.1) == [7.05]


def test_progresso():
    timer = TimerTenuta(2.0)
    _scorri(timer, True, 0, 1.0)
    assert 0.45 < timer.progresso < 0.55


def test_blocca_richiede_il_rilascio():
    timer = TimerTenuta(0.5, tolleranza=0.2)
    _scorri(timer, True, 0, 0.3)
    timer.blocca()  # è scattato un altro gesto mentre questo era tenuto
    assert _scorri(timer, True, 0.35, 2.0) == []  # tenuto senza rilasciare: non scatta
    assert _scorri(timer, False, 2.05, 2.5) == []
    assert _scorri(timer, True, 2.55, 3.1) == [3.05]
