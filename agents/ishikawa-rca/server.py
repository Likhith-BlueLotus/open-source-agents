"""Web UI: live fishbone that fills in as the agents investigate.

    uvicorn server:app --port 8080
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse  # noqa: E402

from ishikawa.render import to_markdown  # noqa: E402
from ishikawa.runner import investigate, to_sse  # noqa: E402
from ishikawa.schema import RCAReport  # noqa: E402
from ishikawa.tools import list_incidents, load_incident  # noqa: E402

WEB = Path(__file__).parent / "web"
app = FastAPI(title="Ishikawa RCA")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/incidents")
def incidents() -> list[dict]:
    return list_incidents()


@app.get("/api/incidents/{incident_id}")
def incident(incident_id: str) -> dict:
    try:
        return load_incident(incident_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/investigate/{incident_id}")
async def run(incident_id: str) -> StreamingResponse:
    incident(incident_id)  # 404 early on unknown ids

    async def stream():
        try:
            async for ev in investigate(incident_id):
                yield to_sse(ev)
        except Exception as e:  # surface model/auth errors in the UI instead of a dead stream
            yield to_sse({"type": "error", "message": f"{type(e).__name__}: {e}"})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/markdown")
def markdown(report: RCAReport) -> PlainTextResponse:
    return PlainTextResponse(to_markdown(report), media_type="text/markdown")
