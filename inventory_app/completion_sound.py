"""Original A.C.E. completion chime, synthesized locally with the standard library."""
from array import array
from functools import lru_cache
import io
import math
import sys
import wave

from .config import DEVICE_SETTINGS_DIR, load_device_settings, _save_device_settings


def enabled() -> bool:
    return bool(load_device_settings().get('completion_sound_enabled', True))


def save_enabled(value: bool) -> bool:
    settings = load_device_settings()
    settings['completion_sound_enabled'] = bool(value)
    return _save_device_settings(settings)


@lru_cache(maxsize=1)
def chime_bytes() -> bytes:
    rate = 44100
    samples = array('h')
    notes = ((0.00, 659.255), (0.085, 830.609), (0.17, 987.767))
    for index in range(int(rate * 0.52)):
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


def play(*, preview: bool = False) -> None:
    """Never block an inventory action or fall back to a Windows system sound."""
    try:
        if not preview and not enabled():
            return
        import winsound
        folder = DEVICE_SETTINGS_DIR / 'sounds'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'ace_complete_v1.wav'
        audio = chime_bytes()
        if not path.exists() or path.read_bytes() != audio:
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(audio)
            temporary.replace(path)
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC |
                           winsound.SND_NODEFAULT | winsound.SND_NOSTOP)
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
