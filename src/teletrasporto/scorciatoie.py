"""Scorciatoie da tastiera globali (funzionano anche con la finestra in secondo piano).

Usa RegisterHotKey di Windows: niente intercettazione della tastiera e niente permessi
di amministratore. Formato: "Ctrl+Alt+L", "Ctrl+Shift+F5", ...
"""
import ctypes
import logging
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

_MOD = {"ctrl": 0x2, "control": 0x2, "alt": 0x1, "shift": 0x4, "win": 0x8}
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_TASTI = {"space": 0x20, "spazio": 0x20, "esc": 0x1B, "pause": 0x13, "pausa": 0x13,
          "home": 0x24, "end": 0x23, "insert": 0x2D, "ins": 0x2D, "del": 0x2E, "canc": 0x2E}


def interpreta(combinazione: str) -> tuple[int, int]:
    """'Ctrl+Alt+L' → (modificatori, codice tasto). ValueError se non valida."""
    parti = [p.strip().lower().strip("<>") for p in combinazione.split("+") if p.strip()]
    if not parti:
        raise ValueError("combinazione vuota")
    mod = 0
    for p in parti[:-1]:
        if p not in _MOD:
            raise ValueError(f"modificatore sconosciuto: {p}")
        mod |= _MOD[p]
    t = parti[-1]
    if len(t) == 1 and t.isascii() and t.isalnum():
        vk = ord(t.upper())
    elif t.startswith("f") and t[1:].isdigit() and 1 <= int(t[1:]) <= 24:
        vk = 0x6F + int(t[1:])
    elif t in _TASTI:
        vk = _TASTI[t]
    else:
        raise ValueError(f"tasto sconosciuto: {t}")
    if mod == 0:
        raise ValueError("serve almeno un modificatore (Ctrl, Alt, Shift o Win)")
    return mod, vk


class Scorciatoie:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self.errori: list[str] = []

    def avvia(self, azioni: dict) -> list[str]:
        """azioni: {combinazione: funzione}. Restituisce gli errori (combinazioni non valide
        o già usate da un altro programma). Le funzioni vengono chiamate da un altro thread."""
        self.ferma()
        self.errori = []
        pronte = threading.Event()
        self._thread = threading.Thread(target=self._esegui, args=(azioni, pronte),
                                        name="scorciatoie", daemon=True)
        self._thread.start()
        pronte.wait(2)
        return self.errori

    def _esegui(self, azioni: dict, pronte: threading.Event) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._thread_id = ctypes.WinDLL("kernel32").GetCurrentThreadId()
        registrate = {}
        for i, (combinazione, funzione) in enumerate(azioni.items(), start=1):
            try:
                mod, vk = interpreta(combinazione)
            except ValueError as e:
                self.errori.append(f"{combinazione}: {e}")
                continue
            if user32.RegisterHotKey(None, i, mod | _MOD_NOREPEAT, vk):
                registrate[i] = funzione
            else:
                self.errori.append(f"{combinazione}: già usata da un altro programma")
        pronte.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY and msg.wParam in registrate:
                try:
                    registrate[msg.wParam]()
                except Exception:  # noqa: BLE001
                    log.exception("Errore nella scorciatoia")
        for i in registrate:
            user32.UnregisterHotKey(None, i)

    def ferma(self) -> None:
        if self._thread and self._thread.is_alive():
            ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
            self._thread.join(timeout=2)
        self._thread = None
