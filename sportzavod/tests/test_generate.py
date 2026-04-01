import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_generate_returns_task_id():
    with patch("app.routes.generate.generate_and_queue") as mock_gen:
        mock_gen.return_value = {"task_id": "abc-123", "status": "queued"}
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.post("/api/generate", json={
                "account_id": "550e8400-e29b-41d4-a716-446655440000",
                "sport": "basketball",
                "team": "Lakers",
                "event": "win",
            })
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "abc-123"
