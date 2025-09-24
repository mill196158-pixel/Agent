# agent/utils/watchdog.py
# -*- coding: utf-8 -*-
import time, threading
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

KEYWORDS = ["error", "ошибка", "warning", "license", "update", "доверяете", "save", "сохранить"]

def _try_close(win):
    title = (win.window_text() or "").lower()
    if any(k in title for k in KEYWORDS):
        for label in ["OK","Yes","Да","ОК","Close","Закрыть","Cancel","Отмена"]:
            try:
                btn = win.child_window(title=label, control_type="Button")
                if btn.exists(): btn.click_input(); return True
            except: pass
        send_keys("{ESC}"); return True
    return False

def start_watchdog(stop_event, reporter=print):
    def loop():
        desk = Desktop(backend="uia")
        while not stop_event.is_set():
            try:
                for w in desk.windows():
                    try:
                        if _try_close(w):
                            reporter(f"[watchdog] Закрыт диалог: {w.window_text()!r}")
                    except: pass
            except: pass
            time.sleep(0.5)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t
