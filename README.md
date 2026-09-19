# AlgoTrace AI

A small FastAPI service that runs a snippet of Python and returns a step-by-step trace: which line ran, what kind of event it was, and what the local variables looked like at that point. It's built to feed an algorithm visualizer, but the output is plain JSON so anything can use it.

This is not safe to expose to untrusted users. Read the [security note](#security) before deploying it anywhere public.

## Setup

Needs Python 3.10 or newer.

```bash
git clone https://github.com/tanishasingha37657/algotrace.git
cd algotrace
pip install -r requirements.txt
uvicorn main:app --reload
```

The server runs at http://127.0.0.1:8000, and FastAPI's interactive docs are at `/docs`.

## API

### `POST /trace`

Request:

| field | type | notes |
|---|---|---|
| `code` | string | Python source to run. Can't be empty. |
| `max_steps` | int, optional | 1 to 50. Defaults to 50, which is also the hard cap. |

Example:

```bash
curl -X POST http://127.0.0.1:8000/trace \
  -H "Content-Type: application/json" \
  -d '{"code": "a = 2\nb = a * 3"}'
```

Response:

```json
{
  "steps": [
    {"step": 1, "line": 0, "event": "call",   "variables": {}},
    {"step": 2, "line": 1, "event": "line",   "variables": {}},
    {"step": 3, "line": 2, "event": "line",   "variables": {"a": "2"}},
    {"step": 4, "line": 2, "event": "return", "variables": {"a": "2", "b": "6"}}
  ],
  "truncated": false,
  "error": null,
  "timed_out": false
}
```

- `event` is `line`, `call` or `return`.
- `variables` maps names to `repr()` strings, cut off at 200 characters. Callables and names starting with `__` are left out.
- `truncated` is true if the step cap was hit or the run timed out.
- `error` is `"ExceptionType: message"` if the submitted code raised. The request still returns 200 and `steps` holds everything traced before the exception.
- Code that doesn't compile returns 400 with the `SyntaxError` in `detail`.

Two things to know when rendering a trace:

- Step 1 is always the module itself being called, at line 0. You'll probably want to skip it.
- A `line` event fires before that line runs, so the variables are the state going into it. In the example, `b` only appears on the final `return` step.

`GET /` is a health check.

## Limits

- 50 traced steps. After that tracing stops and `truncated` is set.
- 5 second timeout, hardcoded.
- Only the submitted code is traced. Calls into builtins aren't stepped through.
- Builtins are whitelisted: `len`, `range`, `sorted`, `sum`, `enumerate`, `zip`, `print` and similar work. `import`, `open`, `eval` and `class` statements don't. Functions, loops, comprehensions and recursion are fine.
- `print` output goes to the server's stdout, not the response.

## Security

The builtins whitelist is not a sandbox. Something like `().__class__.__bases__[0].__subclasses__()` still runs, and from there it's possible to reach modules the whitelist was meant to block.

The timeout also doesn't stop anything. It just stops waiting for the worker thread, which keeps running in the background. Code stuck inside a single builtin call, such as `sum(range(10**12))`, never emits a line event, so the step cap doesn't catch it either.

CORS is set to allow all origins, which is fine for local work and not for production.

For anything public, run the tracer in a separate container or process with CPU, memory and time limits enforced by the OS.

## Project structure

```
main.py           FastAPI app and request/response models
tracer.py         tracing engine (sys.settrace)
requirements.txt  dependencies
```
