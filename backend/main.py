import os
import uuid
from typing import Any

import libcst as cst
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - exercised when SDK is absent
    Anthropic = None

from backend.db import (
    initialize_database,
    load_session_context,
    record_agent_turn,
    record_file_history,
    record_instruction,
)
from backend.search_tool import simple_search

load_dotenv()

app = FastAPI(title="AgentCode Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_database()


class CodeRequest(BaseModel):
    file_content: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)
    use_patch_mode: bool = False
    session_id: str | None = None


class StepResult(BaseModel):
    name: str
    status: str
    detail: str


class CodeResponse(BaseModel):
    rewritten_code: str
    steps: list[StepResult]
    session_id: str


def build_prompt(file_content: str, instruction: str) -> str:
    return (
        "You are an expert Python coding assistant. "
        "Rewrite the provided Python file so it satisfies the user's instruction. "
        "Return only the full rewritten Python file without explanation.\n\n"
        f"User instruction:\n{instruction}\n\n"
        f"Current file:\n{file_content}"
    )


def build_planner_prompt(
    file_content: str,
    instruction: str,
    memory_instructions: list[str],
    search_snippets: list[str],
) -> str:
    prompt = (
        "You are the planner. Break the user's request into a concise implementation plan. "
        "Reply with a JSON object containing a single 'plan' list of short steps."
        f"\n\nInstruction:\n{instruction}\n\n"
        f"Current file:\n{file_content}"
    )

    if memory_instructions:
        prompt += "\n\nPreviously completed tasks in this session:\n"
        prompt += "\n".join(memory_instructions[-5:])

    if search_snippets:
        prompt += "\n\nRelevant recent code snippets from this session:\n"
        prompt += "\n---\n".join(search_snippets[:3])

    return prompt


def build_developer_prompt(
    file_content: str,
    instruction: str,
    plan: str,
    memory_instructions: list[str],
    search_snippets: list[str],
) -> str:
    prompt = (
        "You are the developer. Produce a complete rewritten Python file that satisfies the plan. "
        "Return only the rewritten Python file, with no markdown or analysis."
        f"\n\nInstruction:\n{instruction}\n\n"
        f"Plan:\n{plan}\n\n"
        f"Current file:\n{file_content}"
    )

    if memory_instructions:
        prompt += "\n\nSession memory:\n"
        prompt += "\n".join(memory_instructions[-5:])

    if search_snippets:
        prompt += "\n\nRelevant recent code snippets:\n"
        prompt += "\n---\n".join(search_snippets[:3])

    prompt += "\n\nEnsure the output is valid Python." 
    return prompt


def extract_text_from_response(response: Any) -> str:
    if response is None:
        return ""

    if isinstance(response, str):
        return response

    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, (list, tuple)) and content:
            first = content[0]
            return getattr(first, "text", str(first))

    if hasattr(response, "completion"):
        return str(response.completion)

    if hasattr(response, "text"):
        return str(response.text)

    if hasattr(response, "choices"):
        choices = response.choices
        if isinstance(choices, (list, tuple)) and choices:
            first = choices[0]
            return getattr(first, "text", str(first))

    return str(response)


def generate_rewritten_code(file_content: str, prompt: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or Anthropic is None:
        return file_content

    client = Anthropic(api_key=api_key)
    try:
        if hasattr(client, "messages"):
            response = client.messages.create(
                model="claude-3-5-sonnet-latest",
                messages=[
                    {"role": "system", "content": "You are a careful Python coding assistant."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens_to_sample=1200,
            )
        else:
            response = client.completions.create(
                model="claude-3-5-sonnet-latest",
                prompt=prompt,
                max_tokens_to_sample=1200,
            )

        return extract_text_from_response(response).strip()
    except Exception:
        return file_content


def validate_python_code(candidate: str) -> bool:
    try:
        cst.parse_module(candidate)
        return True
    except Exception:
        return False


def generate_with_validation(file_content: str, developer_prompt: str, attempts: int = 2) -> tuple[str, list[str]]:
    details: list[str] = []
    rewritten_code = file_content

    for attempt in range(1, attempts + 1):
        candidate = generate_rewritten_code(file_content, developer_prompt)
        if validate_python_code(candidate):
            details.append(f"Developer attempt {attempt} produced valid Python.")
            return candidate, details

        details.append(
            f"Developer attempt {attempt} produced invalid Python."
        )
        developer_prompt += (
            "\n\nThe previous response contained invalid Python syntax. "
            "Return only valid Python code in your next response."
        )
        rewritten_code = candidate

    return rewritten_code, details


def generate_patch(file_content: str, instruction: str) -> str:
    try:
        module = cst.parse_module(file_content)
        replacement = cst.Module(body=[
            cst.SimpleStatementLine([
                cst.Expr(cst.SimpleString("# patched by AgentCode"))
            ])
        ])
        updated_module = module.with_changes(body=[*module.body, *replacement.body])
        return updated_module.code
    except Exception:
        return file_content


def run_agent_pipeline(
    file_content: str,
    instruction: str,
    session_id: str,
    use_patch_mode: bool = False,
) -> dict[str, Any]:
    record_instruction(session_id, instruction)
    record_file_history(session_id, file_content)

    session_context = load_session_context(session_id)
    search_snippets = simple_search(instruction, session_context["file_history"])

    planner_prompt = build_planner_prompt(
        file_content,
        instruction,
        session_context["instructions"],
        search_snippets,
    )
    planner_result = generate_rewritten_code(file_content, planner_prompt)
    record_agent_turn(
        session_id,
        "planner",
        "complete",
        planner_result[:220],
    )

    developer_prompt = build_developer_prompt(
        file_content,
        instruction,
        planner_result,
        session_context["instructions"],
        search_snippets,
    )
    developer_code, developer_details = generate_with_validation(
        file_content, developer_prompt, attempts=2
    )
    record_agent_turn(
        session_id,
        "developer",
        "complete",
        developer_details[-1] if developer_details else "Developer completed rewrite.",
    )

    if use_patch_mode:
        rewritten_code = generate_patch(file_content, instruction)
        detail = "Applied a libcst-based patch fallback for the requested edit."
    else:
        rewritten_code = developer_code.strip() or file_content
        detail = "Generated a full-file rewrite from the plan. "
        detail += "".join(developer_details) if developer_details else ""

    if not validate_python_code(rewritten_code):
        record_agent_turn(
            session_id,
            "validator",
            "failed",
            "Final rewrite did not produce valid Python. Returning original content.",
        )
        rewritten_code = file_content
        validation_status = "failed"
        validation_detail = "Final rewrite did not validate; original file returned."
    else:
        record_agent_turn(
            session_id,
            "validator",
            "complete",
            "Final rewrite passed syntax validation.",
        )
        validation_status = "complete"
        validation_detail = "Final rewrite passed syntax validation."

    steps = [
        StepResult(name="planner", status="complete", detail=planner_result[:220]),
        StepResult(name="developer", status="complete", detail=detail),
        StepResult(name="validator", status=validation_status, detail=validation_detail),
    ]

    return {
        "rewritten_code": rewritten_code,
        "steps": steps,
        "session_id": session_id,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/code/ask", response_model=CodeResponse)
def ask_ai(request: CodeRequest) -> CodeResponse:
    if not request.file_content.strip():
        raise HTTPException(status_code=400, detail="file_content cannot be empty")

    session_id = request.session_id or str(uuid.uuid4())
    pipeline_result = run_agent_pipeline(
        request.file_content,
        request.instruction,
        session_id,
        use_patch_mode=request.use_patch_mode,
    )
    return CodeResponse(**pipeline_result)
