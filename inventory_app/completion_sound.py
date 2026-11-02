"""Original A.C.E. feedback sounds, synthesized locally with the standard library."""
from array import array
from functools import lru_cache
import io
import math
import sys
import wave

from .config import DEVICE_SETTINGS_DIR, load_device_settings, _save_device_settings


def enabled(kind: str = 'completion') -> bool:
    return bool(load_device_settings().get(kind + '_sound_enabled', True))


def save_enabled(value: bool, kind: str = 'completion') -> bool:
    settings = load_device_settings()
    settings[kind + '_sound_enabled'] = bool(value)
    return _save_device_settings(settings)


@lru_cache(maxsize=2)
def chime_bytes(kind: str = 'completion') -> bytes:
    rate = 44100
    samples = array('h')
    notes = ((0.00, 659.255), (0.085, 830.609), (0.17, 987.767))
    duration = 0.52
    if kind == 'error':
        notes = ((0.00, 440.0), (0.12, 329.628))
        duration = 0.46
    for index in range(int(rate * duration)):
        time = index / rate
        value = 0.0
        for start, frequency in notes:
            elapsed = time - start
            if not 0 <= elapsed < 0.32:
                continue
            attack = min(1.0, elapsed / 0.009)
            release = min(1.0, (0.32 - elapsed) / 0.055)
            envelope = attack * release * math.exp(-9 * elapsed)
            tone = math.sin(2 * math.pi * frequency * elapsed)
            tone += 0.12 * math.sin(4 * math.pi * frequency * elapsed)
            value += 0.19 * envelope * tone
        samples.append(round(max(-1.0, min(1.0, value)) * 32767))
    if sys.byteorder != 'little':
        samples.byteswap()
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes())
    return output.getvalue()


def play(*, preview: bool = False, kind: str = 'completion') -> None:
    """Never block an inventory action or fall back to a Windows system sound."""
    try:
        if kind not in ('completion', 'error'):
            return
        if not preview and not enabled(kind):
            return
        import winsound
        folder = DEVICE_SETTINGS_DIR / 'sounds'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('ace_error_v1.wav' if kind == 'error' else 'ace_complete_v1.wav')
        audio = chime_bytes(kind)
        if not path.exists() or path.read_bytes() != audio:
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(audio)
            temporary.replace(path)
        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if kind == 'completion':
            flags |= winsound.SND_NOSTOP
        winsound.PlaySound(str(path), flags)
    except (ImportError, OSError, RuntimeError, ValueError):
        pass


def show_completion(app, message: str) -> None:
    """Use an A.C.E. success popup so Windows does not play its message-box beep."""
    import tkinter as tk
    from tkinter import ttk
    window = getattr(app, '_completion_window', None)
    if window is None or not window.winfo_exists():
        window = tk.Toplevel(app)
        app._completion_window = window
        window.title('A.C.E. - Completed')
        window.transient(app)
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Completed', style='Title.TLabel').pack(anchor='w', pady=(0, 10))
        window.completion_message = tk.StringVar(window)
        ttk.Label(frame, textvariable=window.completion_message, wraplength=480,
                  justify='left').pack(anchor='w', pady=(0, 18))
        ttk.Button(frame, text='OK', command=window.destroy).pack(anchor='e')
        window.bind('<Escape>', lambda _event: window.destroy())
        window.bind('<Return>', lambda _event: window.destroy())
    window.completion_message.set(message)
    window.update_idletasks()
    if app.winfo_viewable():
        x = app.winfo_rootx() + max(0, (app.winfo_width() - window.winfo_reqwidth()) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - window.winfo_reqheight()) // 2)
        window.geometry(f'+{x}+{y}')
    play()


def show_error(title: str, message: str, *, parent=None) -> str:
    """Acknowledge errors without the Windows message-box sound; preserve dialog grabs."""
    import tkinter as tk
    from tkinter import ttk
    owner = parent or tk._default_root
    temporary_owner = owner is None
    if temporary_owner:
        owner = tk.Tk()
        owner.withdraw()
    previous_grab = owner.grab_current()
    previous_focus = owner.focus_get()
    window = tk.Toplevel(owner)
    window.title(title)
    window.resizable(False, False)
    if owner.winfo_viewable():
        window.transient(owner)
    frame = ttk.Frame(window, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Action needs attention', font=('Segoe UI', 13, 'bold'),
              foreground='#a12626').pack(anchor='w', pady=(0, 10))
    ttk.Label(frame, text=message, wraplength=520, justify='left').pack(anchor='w', pady=(0, 18))
    button = ttk.Button(frame, text='OK', command=window.destroy)
    button.pack(anchor='e')
    window.bind('<Escape>', lambda _event: window.destroy())
    window.bind('<Return>', lambda _event: window.destroy())
    try:
        window.wait_visibility()
        window.grab_set()
        button.focus_set()
        play(kind='error')
        window.wait_window()
    finally:
        if window.winfo_exists():
            window.destroy()
        if temporary_owner:
            owner.destroy()
        else:
            try:
                if previous_grab is not None and previous_grab.winfo_exists():
                    previous_grab.grab_set()
                if previous_focus is not None and previous_focus.winfo_exists():
                    previous_focus.focus_set()
            except tk.TclError:
                pass
    return 'ok'
