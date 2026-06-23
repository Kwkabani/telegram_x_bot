"""
Windows Named Mutex singleton — prevents duplicate bot instances via kernel-level mutex.
Auto-released by the OS on crash or exit.
"""
import sys
import ctypes
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BotSingleton:
    MUTEX_PREFIX = "Global\\PTB_"

    def __init__(self, bot_token: str):
        token_id = abs(hash(bot_token)) & 0x7FFFFFFF
        self._mutex_name = f"{self.MUTEX_PREFIX}{token_id}"
        self._mutex_handle: Optional[int] = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def try_acquire(self) -> bool:
        self._mutex_handle = self._kernel32.CreateMutexW(None, True, self._mutex_name)
        if not self._mutex_handle:
            logger.critical(f"Failed to create mutex (error {ctypes.get_last_error()})")
            return False
        if ctypes.get_last_error() == 183:
            logger.warning("Another bot instance is already running. Exiting.")
            self._kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None
            return False
        return True

    def release(self):
        if self._mutex_handle:
            self._kernel32.ReleaseMutex(self._mutex_handle)
            self._kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None

    def __enter__(self):
        if not self.try_acquire():
            sys.exit(0)
        return self

    def __exit__(self, *args):
        self.release()
