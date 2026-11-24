# Fotocamera Teletrasporto

> **EN** — Windows app that reads your webcam, recognizes hand gestures with MediaPipe and edits the image in real time:
> "teleport" out of the frame leaving only the background, or loop a recorded clip in place of the live feed.
> The output goes to the OBS Virtual Camera, so it works in Meet, Teams, Zoom. Python, OpenCV, MediaPipe, PySide6.

Programma per Windows che legge la webcam, riconosce dei gesti e modifica l'immagine in tempo reale.
Il risultato esce sulla **OBS Virtual Camera**, che si sceglie come fotocamera in Meet, Teams, Zoom ecc.

## Funzioni

| Gesto | Effetto |
|---|---|
| **Teletrasporto**: indice e medio uniti sulla fronte, tenuti per 3 s | Sparisci con un effetto stile Dragon Ball e resta solo lo sfondo. Rifai il gesto per 3 s per ricomparire. |
| **X**: due indici incrociati | Dopo 2 s registra 10 s, poi la clip va in loop al posto del live. X durante il conto alla rovescia o la registrazione annulla; X durante il loop torna al live. |
| **W**: due mani con i pollici che si toccano e gli indici in su | Va subito in loop l'ultima clip. W durante il loop passa alla clip precedente. |

Vengono conservate le ultime 3 clip nella cartella `clips/` (restano anche dopo un riavvio).

### Spie (solo nell'anteprima, chi ti guarda non le vede)
In alto a destra c'è una spia per ogni funzione:
- 🟢 verde: attiva
- 🔴 rosso: spenta
- 🟡 giallo: in avvio o in spegnimento (conto alla rovescia, registrazione, effetto)
- 🟠 arancione: problema (per esempio sfondo incompleto, nessuna clip salvata, fotocamera virtuale occupata)

L'anello bianco attorno alla spia mostra quanto manca prima che il gesto tenuto scatti.

### Scorciatoie globali (attive anche con la finestra in secondo piano)
- `Ctrl+Alt+L`: torna al live (ferma il loop e fa ricomparire)
- `Ctrl+Alt+J`: attiva/disattiva il riconoscimento dei gesti
- `Ctrl+Alt+B`: cattura lo sfondo

Si possono cambiare o disattivare nella scheda **Impostazioni**.

## Requisiti

- **Windows 10/11**
- **Python 3.12** dall'installatore ufficiale di [python.org](https://www.python.org/downloads/): viene usato solo come base, non ci viene installato niente.
- **[uv](https://docs.astral.sh/uv/)** per gestire i pacchetti (in alternativa basta mettere `uv.exe` in una cartella `strumenti/` dentro il progetto).
- **[OBS Studio](https://obsproject.com/)**: serve soltanto la sua OBS Virtual Camera. OBS non deve essere aperto; se lo apri, non avviare la sua fotocamera virtuale mentre usi questo programma.

## Avvio

Doppio clic su **`avvia.bat`**. La prima volta scarica i pacchetti e i modelli MediaPipe dentro la cartella del progetto (serve qualche minuto e circa 1 GB).

Tutto resta nella cartella: `.venv/` (pacchetti), `.uv-cache/` (cache dei download, si può cancellare), `models/`, `clips/`, `config/`.
**Per disinstallare basta cancellare la cartella.**

### Perché Python di python.org e non uno scaricato da uv
Con **Smart App Control** di Windows attivo, le librerie non firmate vengono bloccate. Il Python scaricato da uv non è firmato, quello ufficiale sì. Per lo stesso motivo:
- si usa `mediapipe` 0.10.14 (le versioni più recenti contengono una DLL che viene bloccata);
- l'uscita verso la fotocamera virtuale è scritta in Python puro (`uscita/fotocamera_virtuale.py`) invece di usare `pyvirtualcam`, la cui DLL viene bloccata.

## Primo utilizzo
1. Avvia il programma e controlla l'anteprima.
2. Premi **Cattura sfondo** ed esci dall'inquadratura. Dopo 5 secondi la cattura parte, ma raccoglie solo le zone in cui non ti vede: al centro dell'anteprima compare la percentuale e la scritta "ti vedo ancora" finché sei visibile. Quando arriva al 100% puoi rientrare (al massimo aspetta 20 s; le zone mai liberate restano da ricostruire e la spia diventa arancione).
   Senza questo passaggio il programma impara lo sfondo da solo, ma accetta un pixel solo quando è rimasto libero e fermo per circa 1 secondo, quindi ciò che c'è dietro di te resta sconosciuto finché non ti sposti.
   Con **Mostra lo sfondo memorizzato** vedi cosa ha imparato; in **Info** c'è la percentuale di sfondo nota.
3. In Meet: Impostazioni → Video → **OBS Virtual Camera**.
4. Per provare senza gesti ci sono i pulsanti **Simula gesto** (Teletrasporto, X, W). Con *Mostra i punti delle mani* vedi cosa riconosce il programma.

Consigli: luce frontale e sfondo fermo. Durante la registrazione del loop resta naturale e fermo, così la ripetizione si nota meno (c'è comunque una dissolvenza di 0,5 s nel punto in cui la clip ricomincia). Se qualcosa va storto in riunione, usa `Ctrl+Alt+L`.

## Privacy
Tutto viene elaborato in locale: nessuna immagine esce dal computer, se non verso la fotocamera virtuale. Le clip restano in `clips/` e le impostazioni in `config/`, entrambe escluse dal repository.

## Eseguibile
Dopo aver verificato tutto con `avvia.bat`, **`crea_exe.bat`** crea `dist\FotocameraTeletrasporto\FotocameraTeletrasporto.exe` con PyInstaller.
Attenzione: l'eseguibile non è firmato, quindi con Smart App Control attivo Windows potrebbe bloccarlo. In quel caso continua a usare `avvia.bat`.

## Test
```
.venv\Scripts\python -m pytest
```
I test usano mani sintetiche (`tests/mani_sintetiche.py`), quindi non serve la webcam.

## Struttura
```
src/teletrasporto/
  app.py, pipeline.py          avvio e ciclo di elaborazione
  cattura.py                   webcam
  visione/                     rilevatori MediaPipe, regole dei gesti, timer di tenuta
  funzioni/                    teletrasporto, loop, stati delle spie
  composizione/                modello dello sfondo, effetto
  clip.py                      registrazione e archivio delle clip
  uscita/fotocamera_virtuale.py   scrittura verso la OBS Virtual Camera
  scorciatoie.py               scorciatoie globali (RegisterHotKey di Windows)
  autorizzazione.py            punto di aggancio per i profili (fase 2)
  ui/                          finestra e disegni dell'anteprima
```

## Sviluppi futuri: profili
`autorizzazione.py` decide chi può comandare. Ogni mano è già associata al volto più vicino: basterà riconoscere quel volto (OpenCV YuNet + SFace, offline) e confrontarlo con i profili salvati.

---

Sviluppato da [Luca Sonno](https://lucasonno.com) con l'assistenza di Claude Code. Licenza [MIT](LICENSE).
I modelli MediaPipe vengono scaricati da Google al primo avvio e seguono la loro licenza (Apache 2.0).
