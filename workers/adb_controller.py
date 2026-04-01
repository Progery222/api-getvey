import subprocess
from pathlib import Path


class ADBController:
    def __init__(self, serial: str):
        self.serial = serial

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["adb", "-s", self.serial, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ADB error: {result.stderr}")
        return result.stdout.strip()

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._run("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def push_file(self, local_path: str, remote_path: str) -> None:
        self._run("push", local_path, remote_path)

    def screenshot(self, local_path: str) -> None:
        self._run("shell", "screencap", "-p", "/sdcard/screen.png")
        self._run("pull", "/sdcard/screen.png", local_path)
