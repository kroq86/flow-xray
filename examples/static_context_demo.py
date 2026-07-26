"""
Does "Show static context" answer a question a plain runtime trace can't?

Scenario: an agent routes to one of three tools. This run only takes the
database path, and it fails.

  agent -> choose_tool -> call_database   (raises: "customers" is a locked table)
                       -> call_search      (a live static branch -- never taken)
                       -> fallback         (another live branch -- never taken)
                       -> audit_log        (dispatched via globals()[...](...),
                                            so the static pass can't see it at all)

Without static context, the trace shows exactly one thing: chose "database",
it errored. It can't tell you whether that was the only option, or whether
anything else in the code depends on the function that just broke.

With static context (open the HTML this writes, click the toggle):
  - call_search and fallback appear as dashed ghost nodes -- reachable
    per the source, not taken this run. That answers "was database the only
    option, and what were the others?"
  - Click call_database -> the "Blast radius (static)" panel lists
    choose_tool and agent -- that answers "what depends on the node that
    just broke?"
  - The audit_log call renders as a plain orange edge (runtime-only): it
    ran, but no static reader would ever find that call site. That's the
    tool being honest about its own blind spot, not a bug to fix here.

Run:
    python examples/static_context_demo.py

Writes static_context_demo.html next to this file -- open it in a browser.
"""

from __future__ import annotations

from pathlib import Path

from flow_xray import trace
from flow_xray.static_index import build_index


@trace
def call_search(query: str) -> str:
    return f"search results for: {query!r}"


@trace
def call_database(query: str) -> str:
    if "customers" in query:
        raise RuntimeError(f"table locked: cannot query {query!r}")
    return f"db rows for: {query!r}"


@trace
def fallback(query: str) -> str:
    return f"no tool matched, echoing: {query!r}"


@trace
def audit_log(event: str) -> None:
    """A logging/observability hook wired up by name, the way a plugin
    registry or event bus would -- an honest example of what the static
    pass misses, not a hypothetical."""


@trace
def choose_tool(kind: str, query: str) -> str:
    globals()["audit_log"](f"dispatch:{kind}")  # dynamic call -> invisible to ast
    if kind == "search":
        return call_search(query)
    if kind == "database":
        return call_database(query)
    return fallback(query)


@trace
def agent(query: str) -> str:
    return choose_tool("database", query)


if __name__ == "__main__":
    result = trace.run(agent, "select * from customers")
    index = build_index([__file__])
    out = Path(__file__).with_name("static_context_demo.html")
    result.to_html(str(out), title="Static context demo: tool router", static_index=index)

    # agent -> choose_tool -> {audit_log, call_database}; the shape is fixed
    # by the scenario above, so a plain lookup beats a generic tree-walking
    # helper that build_index would otherwise pick up as one more function.
    error_node = next(c for c in result.roots[0].children[0].children if c.name == "call_database")
    known_callees = [c for c in index.callees("choose_tool") if c in index.functions]
    print(f"Result error: {result.error}")
    print(f"call_database node error: {error_node.error}")
    print(f"Static callees of choose_tool (known functions only): {known_callees}")
    print(f"Static blast radius of call_database: {index.blast_radius('call_database')}")
    print(f"Wrote {out} -- open it and click 'Show static context'.")
