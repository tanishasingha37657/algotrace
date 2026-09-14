"""
main.py
-------
FastAPI app for the AlgoTrace AI Code Tracing Engine (Part 1 of the backend).

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload

Then POST to http://127.0.0.1:8000/trace with JSON body:
    {"code": "x = 1\\ny = 2\\nz = x + y\\nprint(z)"}
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from tracer import trace_code, MAX_STEPS_DEFAULT, TIMEOUT_SECONDS_DEFAULT

app = FastAPI(
    title="AlgoTrace AI - Code Tracing Engine",
    description="Executes submitted Python code and returns a step-by-step execution trace.",
    version="1.0.0",
)

# Enable CORS so the React frontend (running on a different origin) can call this API.
# For the hackathon/demo, "*" is simplest; tighten to your deployed frontend's
# exact origin before/at submission if you want it locked down.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TraceRequest(BaseModel):
    code: str = Field(..., description="Raw Python source code to execute and trace.")
    max_steps: int | None = Field(
        default=None, ge=1, le=MAX_STEPS_DEFAULT,
        description="Optional override for step cap (hard-capped at 50).",
    )


class TraceStep(BaseModel):
    step: int
    line: int
    event: str
    variables: dict


class TraceResponse(BaseModel):
    steps: list[TraceStep]
    truncated: bool
    error: str | None
    timed_out: bool


@app.get("/")
def health_check():
    return {"status": "ok", "service": "AlgoTrace AI - Code Tracing Engine"}


@app.post("/trace", response_model=TraceResponse)
def trace(request: TraceRequest):
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="`code` must not be empty.")

    step_cap = request.max_steps or MAX_STEPS_DEFAULT
    step_cap = min(step_cap, MAX_STEPS_DEFAULT)  # never allow exceeding the hard cap

    try:
        result = trace_code(
            code=request.code,
            max_steps=step_cap,
            timeout_seconds=TIMEOUT_SECONDS_DEFAULT,
        )
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"SyntaxError: {exc}")

    return result
