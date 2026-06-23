"""
Cross-platform singleton — uses Windows Named Mutex on Windows,
PID file on Linux/macOS. Prevents duplicate bot instances.
"""
import sys
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"


class BotSingleton:
    MUTEX_PREFIX = "Global\\PTB_"

    def __init__(self, bot_token: str):
        self._token_id = abs(hash(bot_token)) & 0x7FFFFFFF
        self._mutex_handle: Optional[int] = None
        self._pid_file: Optional[str] = None
        self._released = False

    def try_acquire(self) -> bool:
        if _IS_WINDOWS:
            return self._try_acquire_windows()
        return self._try_acquire_posix()

    def _try_acquire_windows(self) -> bool:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = f"{self.MUTEX_PREFIX}{self._token_id}"
        self._mutex_handle = kernel32.CreateMutexW(None, True, mutex_name)
        if not self._mutex_handle:
            logger.critical(f"Failed to create mutex (error {ctypes.get_last_error()})")
            return False
        if ctypes.get_last_error() == 183:
            logger.warning("Another bot instance is already running. Exiting.")
            kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None
            return False
        return True

    def _try_acquire_posix(self) -> bool:
        pid_dir = os.path.join(os.path.dirname(__file__), "temp")
        os.makedirs(pid_dir, exist_ok=True)
        self._pid_file = os.path.join(pid_dir, f"bot_{self._token_id}.pid")
        try:
            with open(self._pid_file, "x") as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            with open(self._pid_file) as f:
                old_pid = f.read().strip()
            logger.warning(
                f"Another bot instance may be running (PID {old_pid}). Exiting."
            )
            return False

    def release(self):
        if self._released:
            return
        self._released = True
        if _IS_WINDOWS and self._mutex_handle:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.ReleaseMutex(self._mutex_handle)
            kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None
        elif not _IS_WINDOWS and self._pid_file:
            try:
                os.unlink(self._pid_file)
            except OSError:
                pass
            self._pid_file = None

    def __enter__(self):
        if not self.try_acquire():
            sys.exit(0)
        return self

    def __exit__(self, *args):
        self.release()
