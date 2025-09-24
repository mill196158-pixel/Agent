import time
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

def focus_by_exe(exe_substr: str, timeout=20):
    desk = Desktop(backend="uia")
    t0 = time.time()
    exe_substr = exe_substr.lower()
    while time.time() - t0 < timeout:
        for w in desk.windows():
            try:
                pid = w.process_id()
                name = w.element_info.process_id  # dummy touch
                proc_name = w.app.process
            except:
                pass
        for w in desk.windows():
            try:
                if exe_substr in (w.app.process_module or "").lower():
                    w.set_focus()
                    return True
            except:
                pass
        time.sleep(0.5)
    return False

def type_text(text: str, delay: float = 0.03):
    for ch in text:
        send_keys(ch)
        time.sleep(delay)
    time.sleep(0.05)

def press_enter():
    send_keys("{ENTER}")
