<p align="center">
  <img src="https://raw.githubusercontent.com/kroq86/flow-xray/main/assets/banner.png" alt="flow-xray" width="100%">
</p>

<p align="center">
  <b>Local-first visual debugger for Python agents.</b><br>
  One HTML file. No cloud, no account. See LLM calls, tool calls, branches, errors, tokens, and cost.
</p>

<p align="center">
  <a href="https://pypi.org/project/flow-xray/"><img src="https://img.shields.io/pypi/v/flow-xray?color=blue&cacheSeconds=60" alt="PyPI"></a>
  <a href="https://github.com/kroq86/flow-xray/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
</p>

---

```python
from flow_xray import trace

@trace
def call_llm(prompt):
    return openai.chat(prompt)

@trace
def agent(query):
    plan = call_llm(f"plan: {query}")
    return call_llm(f"answer based on: {plan}")

result = trace.run(agent, "weather in Tokyo?")
result.to_html("trace.html")
```

<p align="center">
  <img src="https://raw.githubusercontent.com/kroq86/flow-xray/main/assets/demo.png" alt="flow-xray trace viewer" width="100%">
</p>

Open `trace.html` — you get a local debug artifact with:

- LLM calls
- tool calls
- branches and nested steps
- errors and retries
- tokens and estimated cost
- graph, timeline, overview, and raw trace views

No server, no account, no log viewer — one local HTML file.

## Install

```bash
pip install flow-xray
```

## 30-second quickstart

Create `demo_trace.py`:

```python
from flow_xray import trace

@trace
def fetch_profile(user_id):
    return {"id": user_id, "plan": "pro"}

@trace
def answer_question(user_id):
    profile = fetch_profile(user_id)
    return f"user {profile['id']} is on {profile['plan']}"

result = trace.run(answer_question, 42)
result.to_html("demo_trace.html")
```

Run it:

```bash
python demo_trace.py
```

Open `demo_trace.html` in your browser. You should see one root node (`answer_question`) and one child node (`fetch_profile`).

## When to use what

### Use `trace.run(...)` when

- you control the function call directly
- you want the clearest Python API
- you want full control over arguments and return values
- you are tracing inside tests, scripts, notebooks, or app code

```python
from flow_xray import trace

@trace
def pipeline(x):
    return x * 2

result = trace.run(pipeline, 5)
result.to_html("pipeline.html")
```

### Use `flow-xray run ...` when

- you already have a Python script on disk
- you want a quick local trace without editing much code
- the traced calls already happen at module scope when the file is executed

```bash
flow-xray run my_agent.py --html trace.html
```

## Usage

### Decorator + `trace.run`

```python
from flow_xray import trace

@trace
def step_a(x):
    return x + 1

@trace
def pipeline(x):
    return step_a(x) * 2

result = trace.run(pipeline, 5)
result.to_html("pipeline.html")
```

### CLI

```bash
flow-xray run my_agent.py --html trace.html
```

The script must use `@trace` on the functions you want captured.

### CLI onboarding

`flow-xray run` executes the file inside a trace session, but it does **not** enter `if __name__ == "__main__"` blocks.

That means:

- if your traced function call happens at module scope, `flow-xray run` can capture it directly
- if your traced function call only happens inside `main()` guarded by `if __name__ == "__main__"`, the CLI may produce `0 nodes`

If you hit `0 nodes`, use one of these fixes:

1. Move a traced demo call to module scope for local debugging.
2. Call `trace.run(...)` inside the script instead.
3. Keep using the Python API directly from a small wrapper script.

Example that works with `flow-xray run`:

```python
from flow_xray import trace

@trace
def step():
    return 1

step()
```

Example that will usually show `0 nodes` with `flow-xray run`:

```python
from flow_xray import trace

@trace
def step():
    return 1

if __name__ == "__main__":
    step()
```

### Async support

`@trace` works with `async def` out of the box — no extra config:

```python
from flow_xray import trace
import asyncio

@trace
async def call_api(query):
    await asyncio.sleep(0.1)  # simulate async I/O
    return {"answer": query}

@trace
async def agent(query):
    result = await call_api(query)
    return result["answer"]

result = trace.run(lambda: asyncio.run(agent("hello")))
result.to_html("async_trace.html")
```

### Token / cost tracking

Token usage and estimated cost are auto-extracted from OpenAI response objects, or you can set them manually:

```python
@trace
def call_llm(prompt):
    resp = openai.chat.completions.create(...)
    trace.meta(model=resp.model,
               prompt_tokens=resp.usage.prompt_tokens,
               completion_tokens=resp.usage.completion_tokens)
    return resp.choices[0].message.content
```

### Redaction and share-safe traces

Use decorator options when a trace may contain secrets or bulky payloads:

```python
from flow_xray import trace

@trace(redact={"api_key", "authorization"}, capture_output=False)
def call_service(api_key, payload):
    ...
```

- `redact={...}` masks matching argument names and nested dict keys as `[redacted]`
- `capture_output=False` keeps the real return value in Python, but stores `[redacted]` in the HTML trace

### Safety and sharing

`flow-xray` serializes trace data into the generated HTML file.

By default, that can include:

- function names
- bound inputs
- outputs
- exceptions
- attached `trace.meta(...)` fields
- token and cost metadata

Use the privacy controls when you want a trace that is safer to share:

- `redact={...}` hides matching input names and nested dict keys as `[redacted]`
- `capture_output=False` keeps the real Python return value, but writes `[redacted]` into the HTML trace

Treat trace files as local debugging artifacts unless you have explicitly reviewed or redacted their contents. A trace is generally safer to share when you have:

- redacted secrets, auth headers, API keys, or user data
- hidden sensitive outputs with `capture_output=False`
- checked the generated HTML once before posting it publicly

### What you see

- **Nodes** = function calls (name + latency + tokens)
- **Edges** = caller → callee
- **Green** = OK, **Red** = error, **Yellow** = slow (>1s)
- **Header** = total nodes, latency, tokens, estimated cost
- **Click a node** → side panel shows inputs, output, error, timing, model, tokens, cost

## Why this exists

Langfuse, Helicone, LangSmith — they give you **timelines and logs**.

But when your agent pipeline branches, retries, or chains 6 tools — you don't need another table. You need a **graph**.

flow-xray is **not** an agent framework. It's the layer **below** them — like Chrome DevTools is to browsers.

## Compatibility

- **Python** 3.10, 3.11, 3.12, 3.13, 3.14 — tested
- **Sync and async** functions — both supported
- **Any Python code** — not limited to LLM calls; works with any function you decorate
- **Frameworks** — works alongside LangGraph, CrewAI, OpenAI SDK, or plain Python

## How it works

`@trace` wraps functions (sync and async). When called inside a `trace.run()` session (or `flow-xray run` CLI), it records:
- function name
- bound arguments
- return value or exception
- wall-clock latency
- token usage and estimated cost (auto or manual)
- parent/child relationships (call stack → DAG)

`result.to_html()` embeds the trace as JSON in a self-contained HTML page that renders via WASM Graphviz (CDN, works offline after first load).

The trace viewer also includes search, zoom/reset controls, and copy-details for the currently selected node.

## Also included

Scalar autodiff core (micrograd-style `Value` graph with DOT/JSON export and stepping debugger) lives under `flow-xray dot` CLI and `from flow_xray import Value`. See `examples/` and `plan.md`.

## License

MIT
