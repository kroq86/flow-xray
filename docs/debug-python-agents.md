# Debug Python agent runs locally

This is the main job `flow-xray` is built for.

## The problem

Your agent returns a reasonable final answer, but you still do not trust the run.

The real bug is often in the middle:

- the wrong tool call happened
- a branch went somewhere unexpected
- a retry silently changed the path
- one step burned too many tokens
- an error happened and then got hidden by later steps

## The goal

You want to inspect what actually happened inside the run without setting up a hosted tracing stack.

## What flow-xray gives you

`flow-xray` lets you:

- trace Python functions with `@trace`
- run once
- export one local HTML file
- inspect the run through overview, graph, timeline, and raw trace views

## Why local-first matters

For many debugging sessions, the fastest loop is:

1. run locally
2. open the trace immediately
3. inspect the structure
4. fix the bug

That is the niche `flow-xray` is designed for.

## Best-fit workflows

This works best for:

- LangGraph workflows
- LangChain flows
- OpenAI tool-calling code
- custom Python agents
- branchy or nested pipelines

## If you need sharing

Use:

- `redact={...}`
- `capture_output=False`

Then inspect the generated HTML once before sending it to anyone else.

## One-line summary

`flow-xray` helps you understand what happened inside a Python agent run by exporting one local HTML trace instead of making you debug the middle with logs alone.
