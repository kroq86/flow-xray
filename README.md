<p align="center">
  <img src="https://raw.githubusercontent.com/kroq86/flow-xray/main/assets/banner.png" alt="flow-xray" width="100%">
</p>

<p align="center">
  <b>See what your agent actually does.</b><br>
  One decorator, one HTML file — a visual execution graph instead of logs.
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

Open `trace.html` — you get a **DAG** of every traced step with inputs, outputs, latency, tokens, cost, and errors. Click a node to inspect. No server, no account, no log viewer — one local file.

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

The script must use `@trace` on the functions you want captured. The CLI provides the session and executes the file without entering `if __name__ == "__main__"` blocks, so put a traced demo call at module scope if you want `flow-xray run` to capture it directly.

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

### Safety note

`flow-xray` serializes function inputs, outputs, errors, and attached metadata into the generated HTML file. Treat trace files as local debugging artifacts: avoid tracing secrets or redact sensitive payloads before sharing the HTML with others.

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
