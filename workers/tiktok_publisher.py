import time
import tempfile
import httpx
from adb_controller import ADBController


class TikTokPublisher:
    """Публикует видео на TikTok через UI телефона."""

    UPLOAD_BUTTON = (540, 1200)
    SELECT_VIDEO = (540, 800)
    NEXT_BUTTON = (950, 120)
    POST_BUTTON = (540, 900)
    CAPTION_FIELD = (540, 400)

    def __init__(self, adb: ADBController):
        self.adb = adb

    def _download_video(self, url: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            with httpx.stream("GET", url) as response:
                for chunk in response.iter_bytes():
                    f.write(chunk)
            return f.name

    def publish(self, file_url: str, caption: str, hashtags: list[str]) -> bool:
        local_path = self._download_video(file_url)
        self.adb.push_file(local_path, "/sdcard/Movies/upload.mp4")

        self.adb._run("shell", "am", "start", "-n", "com.zhiliaoapp.musically/.main.MainActivity")
        time.sleep(3)

        self.adb.tap(*self.UPLOAD_BUTTON)
        time.sleep(2)

        self.adb.tap(*self.SELECT_VIDEO)
        time.sleep(1)
        self.adb.tap(*self.NEXT_BUTTON)
        time.sleep(2)
        self.adb.tap(*self.NEXT_BUTTON)
        time.sleep(2)

        full_caption = caption + " " + " ".join(f"#{h}" for h in hashtags)
        self.adb.tap(*self.CAPTION_FIELD)
        self.adb._run("shell", "input", "text", full_caption.replace(" ", "%s"))
        time.sleep(1)

        self.adb.tap(*self.POST_BUTTON)
        time.sleep(3)

        return True
