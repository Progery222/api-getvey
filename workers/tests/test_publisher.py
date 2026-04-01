from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adb_controller import ADBController


def test_tap(tmp_path):
    ctrl = ADBController(serial="emulator-5554")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        ctrl.tap(540, 960)
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert "input" in called_args


def test_push_file(tmp_path):
    test_file = tmp_path / "video.mp4"
    test_file.write_bytes(b"fake")
    ctrl = ADBController(serial="emulator-5554")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        ctrl.push_file(str(test_file), "/sdcard/video.mp4")
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert "push" in called_args
