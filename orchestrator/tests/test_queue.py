from app.schemas import QueueRequest
import uuid


def test_queue_request_schema():
    req = QueueRequest(
        account_id=uuid.uuid4(),
        file_url="http://minio:9000/content/test.mp4",
        caption="Test",
        hashtags=["test"],
        source_service="sportzavod",
    )
    assert req.platform == "tiktok"
