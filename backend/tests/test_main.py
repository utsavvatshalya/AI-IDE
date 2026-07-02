import os
import tempfile

from fastapi.testclient import TestClient

from backend.db import initialize_database
from backend.main import app, build_prompt, run_agent_pipeline


client = TestClient(app)


def test_build_prompt_includes_context():
    prompt = build_prompt("print('hi')", "add a greeting")
    assert "add a greeting" in prompt
    assert "print('hi')" in prompt


def test_run_agent_pipeline_returns_steps_and_session_id(monkeypatch):
    os.environ.pop("ANTHROPIC_API_KEY", None)
    result = run_agent_pipeline("print('hi')", "add a greeting", session_id="test-session")
    assert result["rewritten_code"] == "print('hi')"
    assert result["session_id"] == "test-session"
    assert len(result["steps"]) >= 3
    assert any(step.name == "planner" for step in result["steps"])
    assert any(step.name == "developer" for step in result["steps"])
    assert any(step.name == "validator" for step in result["steps"])


def test_api_code_ask_creates_session_and_returns_payload():
    response = client.post(
        "/api/code/ask",
        json={
            "file_content": "print('hello')",
            "instruction": "do nothing",
        },
    )
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["rewritten_code"] == "print('hello')"
    assert json_data["session_id"]
    assert len(json_data["steps"]) == 3
