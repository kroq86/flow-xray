# flow-xray vs LangSmith

This is the short version.

## flow-xray

Best when you want:

- local-first debugging
- one HTML trace file
- no account
- no hosted tracing requirement
- a lightweight way to inspect Python agent runs

`flow-xray` is especially good for debugging:

- tool calls
- nested branches
- retries
- token and cost hotspots
- shareable local traces after redaction

## LangSmith

Best when you want:

- hosted trace storage
- team workflows
- production dashboards
- centralized evaluation and monitoring
- persistent cloud-based observability

## Practical difference

Use `flow-xray` when your question is:

> What actually happened in this run, locally, right now?

Use LangSmith when your question is:

> How do we monitor, compare, and manage traces across many runs and teammates over time?

## Why people use flow-xray even if they know LangSmith

Some developers want:

- local debugging first
- zero SaaS setup
- one artifact they can open immediately
- one file they can inspect before sharing

That is the niche `flow-xray` is built for.

## Not a replacement story

`flow-xray` is not trying to be a full hosted observability platform.

It is a focused local visual debugger for Python agents.
