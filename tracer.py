"""
tracer.py
----------
Core Code Tracing Engine for AlgoTrace AI.

Executes a user-submitted Python script under sys.settrace(), capturing the
line number and variable state after every executed line, up to a hard step
cap. Execution is sandboxed with a restricted builtins list and a wall-clock
timeout so a malicious or infinite-looping script can't hang or damage the
server.

This is a "best effort" sandbox suitable for a hackathon / student project
demo. It is NOT a substitute for real isolation (e.g. gVisor, Docker,
Firecracker) if you were putting this in front of untrusted users at scale.
"""

import sys
import threading
import traceback


class TraceLimitExceeded(Exception):
    """Raised internally when the step cap is hit, to unwind execution cleanly."""
    pass


class TraceTimeout(Exception):
    """Raised when the code runs longer than the allowed wall-clock time."""
    pass


MAX_STEPS_DEFAULT = 50
TIMEOUT_SECONDS_DEFAULT = 5
MAX_REPR_LENGTH = 200

# A conservative allow-list of builtins. Anything not listed here
# (open, eval, exec, __import__, compile, input, exit, ...) is unavailable
# to the traced script, which blocks file access, imports, and re-entrant
# code execution.
SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "chr": chr,
    "dict": dict, "divmod": divmod, "enumerate": enumerate, "filter": filter,
    "float": float, "frozenset": frozenset, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "len": len, "list": list, "map": map,
    "max": max, "min": min, "ord": ord, "pow": pow, "print": print,
    "range": range, "repr": repr, "reversed": reversed, "round": round,
    "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
    "zip": zip, "type": type,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "IndexError": IndexError, "KeyError": KeyError, "ZeroDivisionError": ZeroDivisionError,
    "StopIteration": StopIteration, "ArithmeticError": ArithmeticError,
    "RuntimeError": RuntimeError,
}


def _safe_repr(value):
    """Repr a value defensively so we never crash the tracer on a weird object."""
    try:
        r = repr(value)
    except Exception:
        r = f"<unrepresentable {type(value).__name__}>"
    if len(r) > MAX_REPR_LENGTH:
        r = r[:MAX_REPR_LENGTH] + "...(truncated)"
    return r


def _snapshot_locals(frame):
    """Capture a JSON-safe dict of the local variables in a frame."""
    snapshot = {}
    for name, value in frame.f_locals.items():
        # Skip dunder/internal names and module/function objects (noise, not state)
        if name.startswith("__") or callable(value):
            continue
        snapshot[name] = _safe_repr(value)
    return snapshot


def trace_code(code: str, max_steps: int = MAX_STEPS_DEFAULT,
               timeout_seconds: int = TIMEOUT_SECONDS_DEFAULT) -> dict:
    """
    Execute `code` under sys.settrace and return a dict:
    {
        "steps": [ {"step": int, "line": int, "event": str, "variables": {...}}, ... ],
        "truncated": bool,      # True if we hit max_steps before the script finished
        "error": str | None,    # exception message from the user's code, if any
        "timed_out": bool
    }
    """
    steps = []
    state = {"step_count": 0, "error": None, "timed_out": False}

    def tracer(frame, event, arg):
        # Only trace lines belonging to the executed script itself, not
        # library internals that might get called incidentally.
        if frame.f_code.co_filename != "<algotrace_user_code>":
            return None

        if event in ("line", "call", "return"):
            state["step_count"] += 1
            if state["step_count"] > max_steps:
                raise TraceLimitExceeded()

            steps.append({
                "step": state["step_count"],
                "line": frame.f_lineno,
                "event": event,
                "variables": _snapshot_locals(frame),
            })
        return tracer

    restricted_globals = {"__builtins__": SAFE_BUILTINS}
    compiled = compile(code, "<algotrace_user_code>", "exec")

    def run():
        sys.settrace(tracer)
        try:
            exec(compiled, restricted_globals)
        except TraceLimitExceeded:
            pass  # expected control-flow signal, not a real error
        except Exception as exc:  # noqa: BLE001 - we want to report ANY user-code error
            state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            sys.settrace(None)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive():
        # Thread is still running (infinite loop with no line events counted yet,
        # or stuck inside a single expensive line). We can't safely kill a thread
        # in Python, so we detach it (daemon=True) and report a timeout.
        state["timed_out"] = True
        sys.settrace(None)

    return {
        "steps": steps,
        "truncated": state["step_count"] > max_steps or state["timed_out"],
        "error": state["error"],
        "timed_out": state["timed_out"],
    }
