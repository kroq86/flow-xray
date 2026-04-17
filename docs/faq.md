# FAQ

## What is flow-xray?

`flow-xray` is a local-first visual debugger for Python agents.

It captures traced function calls and exports one HTML file with:

- graph view
- timeline view
- overview cards
- raw trace JSON
- tokens, cost, errors, and nested steps

## Who is it for?

`flow-xray` is useful for people debugging:

- Python agents
- LangGraph workflows
- LangChain flows
- OpenAI tool-calling code
- branchy or nested function pipelines

## When should I use `trace.run(...)`?

Use `trace.run(...)` when you control the Python call directly and want the clearest API.

It is the best option for:

- scripts
- notebooks
- tests
- small wrappers around existing agent code

## When should I use `flow-xray run`?

Use `flow-xray run my_script.py --html trace.html` when you already have a Python script on disk and want a quick local trace.

## Why do I get `0 nodes` with `flow-xray run`?

`flow-xray run` executes the file inside a trace session, but it does not enter `if __name__ == "__main__"` blocks.

If your traced call only happens inside `main()`, the CLI can finish with `0 nodes`.

Use one of these fixes:

- move a traced demo call to module scope
- call `trace.run(...)` inside the script
- create a small wrapper script that imports and runs the traced function directly

## Does it work with async code?

Yes.

`@trace` works with sync and async functions, and concurrent coroutine branches are tracked with task-local context.

## What gets serialized into the HTML trace?

By default, the HTML file can include:

- function names
- inputs
- outputs
- exceptions
- `trace.meta(...)` fields
- token and cost metadata

## How do I hide secrets?

Use:

```python
@trace(redact={"api_key", "authorization"})
```

This masks matching argument names and nested dict keys as `[redacted]`.

## What does `capture_output=False` do?

It keeps the real Python return value in your code, but writes `[redacted]` into the HTML trace output field.

Use it when output data is sensitive but you still want to inspect the run structure.

## Is it safe to share a trace publicly?

Only after review.

A trace is safer to share when you have:

- redacted sensitive inputs
- hidden sensitive outputs
- inspected the generated HTML once yourself

## Does flow-xray replace LangSmith?

No.

`flow-xray` is best for local-first debugging and shareable one-file traces.

Hosted observability tools still make sense for production monitoring, team dashboards, and long-term trace storage.
