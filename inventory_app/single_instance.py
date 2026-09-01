from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


class SingleInstanceGuard:
    """Own a Windows mutex for the lifetime of one A.C.E. process."""

    def __init__(self, handle: int | None, *, is_primary: bool) -> None:
        self._handle = handle
        self.is_primary = is_primary

    @classmethod
    def acquire(cls, name: str) -> "SingleInstanceGuard":
        if os.name != "nt":
            return cls(None, is_primary=True)

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        create_mutex.restype = wintypes.HANDLE

        ctypes.set_last_error(0)
        handle = create_mutex(None, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return cls(None, is_primary=False)
        return cls(int(handle), is_primary=True)

    @staticmethod
    def activate_existing_window(window_title: str) -> bool:
        """Restore the existing main window when it has finished loading."""
        if os.name != "nt":
            return False

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        find_window = user32.FindWindowW
        find_window.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
        find_window.restype = wintypes.HWND
        window = find_window(None, window_title)
        is_window_visible = user32.IsWindowVisible
        is_window_visible.argtypes = (wintypes.HWND,)
        is_window_visible.restype = wintypes.BOOL
        if not window or not is_window_visible(window):
            return False
        user32.ShowWindow(window, SW_RESTORE)
        return bool(user32.SetForegroundWindow(window))

    def close(self) -> None:
        if self._handle is None or os.name != "nt":
            self._handle = None
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(wintypes.HANDLE(self._handle))
        self._handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
