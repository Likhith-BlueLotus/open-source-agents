"""Run an investigation and stream progress events (used by both the CLI and the web UI)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from google.adk.runners import InMemoryRunner
from google.genai import types

from .agent import build_root_agent
from .schema import RCAReport

APP_NAME = "ishikawa"


def _stage(author: str) -> str:
    if author.endswith("_investigator"):
        return author.removesuffix("_investigator")
    return author


async def investigate(incident_id: str, repo_path: str | None = None, model: str | None = None) -> AsyncIterator[dict]:
    """Yield dict events: tool_call, finding, report, done."""
    agent = build_root_agent(model) if model else build_root_agent()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    state = {"incident_id": incident_id}
    if repo_path:
        state["repo_path"] = repo_path
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id="oncall", session_id=str(uuid.uuid4()), state=state
    )
    started = time.monotonic()
    message = types.Content(role="user", parts=[types.Part(text=f"Investigate incident {incident_id}.")])

    async for event in runner.run_async(user_id="oncall", session_id=session.id, new_message=message):
        stage = _stage(event.author)
        for call in event.get_function_calls():
            yield {"type": "tool_call", "stage": stage, "tool": call.name, "args": dict(call.args or {})}
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts if not p.thought).strip()
            if not text:
                continue
            if stage == "scribe":
                continue  # the validated report is read from session state below
            else:
                yield {"type": "finding", "stage": stage, "text": text, "t": round(time.monotonic() - started, 1)}

    final = await runner.session_service.get_session(app_name=APP_NAME, user_id="oncall", session_id=session.id)
    raw = final.state.get("report")
    if raw:
        report = RCAReport.model_validate(raw) if isinstance(raw, dict) else RCAReport.model_validate_json(_strip_fences(raw))
        yield {"type": "report", "report": report.model_dump(), "t": round(time.monotonic() - started, 1)}
    yield {"type": "done", "elapsed_s": round(time.monotonic() - started, 1)}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


def to_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
