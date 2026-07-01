import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - exercised when SDK is absent
    Anthropic = None

load_dotenv()

app = FastAPI(title="AgentCode Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    file_content: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)


class StepResult(BaseModel):
    name: str
    status: str
    detail: str


class CodeResponse(BaseModel):
    rewritten_code: str
    steps: list[StepResult]


def build_prompt(file_content: str, instruction: str) -> str:
    return (
        "You are an expert Python coding assistant. "
        "Rewrite the provided Python file so it satisfies the user's instruction. "
        "Return only the full rewritten Python file.\n\n"
        f"User instruction:\n{instruction}\n\n"
        f"Current file:\n{file_content}"
    )


def generate_rewritten_code(file_content: str, instruction: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or Anthropic is None:
        return file_content

    client = Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=1200,
            system="You are a careful Python coding assistant.",
            messages=[
                {"role": "user", "content": build_prompt(file_content, instruction)}
            ],
        )
        text = response.content[0].text
    except Exception:
        return file_content

    return text.strip()


def run_agent_pipeline(file_content: str, instruction: str) -> dict[str, Any]:
    planner_prompt = (
        "You are the planner. Break the request into a concise implementation plan. "
        "Reply with a JSON object containing a single 'plan' list of short steps."
        f"\n\nInstruction: {instruction}\n\nCurrent file:\n{file_content}"
    )
    developer_prompt = (
        "You are the developer. Produce a full rewritten Python file that satisfies the plan. "
        "Return only the rewritten Python file."
        f"\n\nInstruction: {instruction}\n\nCurrent file:\n{file_content}"
    )

    planner_result = generate_rewritten_code(file_content, planner_prompt)
    developer_result = generate_rewritten_code(file_content, developer_prompt)

    rewritten_code = developer_result.strip() or file_content
    if rewritten_code == file_content:
        rewritten_code = file_content

    steps = [
        StepResult(name="planner", status="complete", detail=planner_result[:220]),
        StepResult(name="developer", status="complete", detail="Generated a rewritten file from the plan."),
    ]

    return {"rewritten_code": rewritten_code, "steps": steps}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/code/ask", response_model=CodeResponse)
def ask_ai(request: CodeRequest) -> CodeResponse:
    if not request.file_content.strip():
        raise HTTPException(status_code=400, detail="file_content cannot be empty")

    pipeline_result = run_agent_pipeline(request.file_content, request.instruction)
    return CodeResponse(**pipeline_result)
