from backend.main import build_prompt, generate_rewritten_code, run_agent_pipeline


def test_build_prompt_includes_context():
    prompt = build_prompt("print('hi')", "add a greeting")
    assert "add a greeting" in prompt
    assert "print('hi')" in prompt


def test_generate_rewritten_code_uses_fallback_when_api_missing(monkeypatch):
    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def messages_create(self, *args, **kwargs):
            raise RuntimeError("missing api key")

    monkeypatch.setattr("backend.main.Anthropic", DummyClient)
    result = generate_rewritten_code("print('hi')", "add a greeting")
    assert "print('hi')" in result


def test_run_agent_pipeline_returns_planning_and_development_steps():
    result = run_agent_pipeline("print('hi')", "add a greeting")
    assert result["rewritten_code"]
    assert len(result["steps"]) >= 2
    assert any(step.name == "planner" for step in result["steps"])
    assert any(step.name == "developer" for step in result["steps"])
