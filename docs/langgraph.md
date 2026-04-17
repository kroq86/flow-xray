# Using flow-xray with LangGraph

`flow-xray` works well when you want local tracing for LangGraph-style workflows without a hosted tracing dashboard.

## What flow-xray is good at

Use it when you want to inspect:

- which node ran
- which tool call happened
- where a branch split
- where an error or retry happened
- how many tokens or how much cost accumulated

## Minimal integration pattern

Decorate the functions that matter at the boundaries of your workflow:

```python
from flow_xray import trace

@trace
def planner(state):
    ...

@trace
def call_tool(tool_name, args):
    ...

@trace
def final_answer(state):
    ...
```

Then run your workflow inside `trace.run(...)`:

```python
result = trace.run(run_graph, initial_state)
result.to_html("langgraph_trace.html")
```

## What to trace first

If you do not want to decorate everything, start with:

- planner / router nodes
- tool gateway calls
- verifier or critic steps
- final answer generation

That usually gives enough structure to understand the run.

## Why use this instead of only logs?

Logs are fine for isolated events.

`flow-xray` is better when you need to understand the shape of the run:

- parent/child relationships
- nested steps
- branch depth
- slow nodes
- token-heavy nodes

## Local-first debugging

The main difference is that `flow-xray` exports one local HTML artifact instead of pushing traces to a hosted service.

That is useful when you want:

- no cloud dependency
- no account
- easy local inspection
- a single file to attach in issues or share after redaction

## Privacy controls

If your LangGraph state or tool payloads contain secrets, use:

```python
@trace(redact={"api_key", "authorization"}, capture_output=False)
```

That lets you keep the run structure while reducing risk in the exported HTML.
