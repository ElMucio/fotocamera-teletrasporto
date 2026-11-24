"""Chi può comandare con i gesti.

Fase 1: chiunque. Fase 2: qui si confronterà il volto associato alla mano con i profili
autorizzati (riconoscimento del volto offline con OpenCV YuNet + SFace).
"""


class Autorizzatore:
    def consentito(self, volto) -> bool:
        return True
