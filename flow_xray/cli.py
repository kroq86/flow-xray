"""
CLI entry points.

``flow-xray run``   — execute a script with @trace, export HTML execution graph.
``flow-xray dot``   — scalar-Value DOT/HTML export (demo / from script).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# flow-xray run  (execution tracing)
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    from flow_xray.trace import TraceResult, _TraceSession, _count_all

    path = Path(args.script)
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    # Use a non-__main__ name so scripts' `if __name__ == "__main__"` blocks
    # are skipped; @trace-decorated functions are captured by the CLI session.
    ns: dict[str, Any] = {"__name__": "__flow_xray_run__", "__file__": str(path)}
    session = _TraceSession()
    with session:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns, ns)
    result = TraceResult(session.roots)
    html_path = args.html or path.stem + "_trace.html"
    result.to_html(html_path, title=args.title or f"Trace: {path.name}")
    total, errs = _count_all(result.roots)
    if total == 0:
        print(
            "Wrote "
            f"{html_path} (0 nodes).\n"
            "No traced calls ran. `flow-xray run` executes the file without entering "
            "`if __name__ == \"__main__\"` blocks, so move a traced demo call to module scope "
            "or call `trace.run(...)` inside the script.",
            file=sys.stderr,
        )
        return 0
    print(
        f"Wrote {html_path} ({total} nodes, {errs} errors). "
        "Open the HTML file in your browser to inspect the trace.",
        file=sys.stderr,
    )
    return 0


# ---------------------------------------------------------------------------
# flow-xray dot  (scalar Value graph — legacy)
# ---------------------------------------------------------------------------

def _demo_root() -> Any:
    from flow_xray.value import Value
    a = Value(2.0, label="a")
    b = Value(-3.0, label="b")
    c = Value(10.0, label="c")
    L = ((a * b) + c).relu().tanh()
    L.label = "L"
    return L


def cmd_demo(args: argparse.Namespace) -> int:
    from flow_xray.export_dot import value_graph_to_dot, write_dot
    from flow_xray.export_html import write_standalone_viewer_html
    root = _demo_root()
    forward = value_graph_to_dot(root, show_grad=False)
    root.backward()
    backward = value_graph_to_dot(root, show_grad=True)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_dot(str(out / "forward.dot"), forward)
        write_dot(str(out / "backward.dot"), backward)
        print(f"Wrote {out / 'forward.dot'} and {out / 'backward.dot'}", file=sys.stderr)
        return 0
    if args.html:
        dot = backward if args.which == "backward" else forward
        title = f"flow-xray demo ({args.which})"
        write_standalone_viewer_html(args.html, dot, title=title)
        print(f"Wrote {args.html} — open in browser (no dot/PNG).", file=sys.stderr)
        return 0
    if args.which == "backward":
        sys.stdout.write(backward)
    else:
        sys.stdout.write(forward)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from flow_xray.export_dot import value_graph_to_dot, write_dot
    from flow_xray.export_html import write_standalone_viewer_html
    from flow_xray.value import Value
    path = Path(args.script)
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    ns: dict[str, Any] = {"__name__": "__main__", "__file__": str(path)}
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns, ns)
    except Exception as exc:
        print(f"error: script execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    root = ns.get("root")
    if root is None:
        print("error: script must define variable `root` (a Value)", file=sys.stderr)
        return 2
    if not isinstance(root, Value):
        print("error: `root` must be a flow_xray.Value", file=sys.stderr)
        return 2
    forward = value_graph_to_dot(root, show_grad=False)
    if args.backward:
        root.backward()
        dot = value_graph_to_dot(root, show_grad=True)
    else:
        dot = forward
    if args.html:
        title = "flow-xray graph" + (" (backward)" if args.backward else " (forward)")
        write_standalone_viewer_html(args.html, dot, title=title)
        print(f"Wrote {args.html} — open in browser.", file=sys.stderr)
        return 0
    out_path = args.output
    if out_path:
        write_dot(out_path, dot)
        print(out_path, file=sys.stderr)
    else:
        sys.stdout.write(dot)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="flow-xray", description="flow-xray — execution graph debugger")
    sub = p.add_subparsers(dest="command", required=True)

    # -- flow-xray run ---------------------------------------------------
    r = sub.add_parser("run", help="run a script with @trace, export HTML execution graph")
    r.add_argument("script", help="path to Python file using @trace")
    r.add_argument("--html", metavar="FILE.html", help="output path (default: <script>_trace.html)")
    r.add_argument("--title", metavar="TEXT", help="title shown in the viewer")
    r.set_defaults(func=cmd_run)

    # -- flow-xray dot demo ----------------------------------------------
    d = sub.add_parser("dot", help="scalar-Value DOT subcommands")
    dot_sub = d.add_subparsers(dest="dot_cmd", required=True)
    dd = dot_sub.add_parser("demo", help="built-in (a*b+c).relu().tanh() graph")
    dd.add_argument("which", nargs="?", default="forward", choices=("forward", "backward"))
    dd.add_argument("--output-dir", metavar="DIR")
    dd.add_argument("--html", metavar="FILE.html")
    dd.set_defaults(func=cmd_demo)

    de = dot_sub.add_parser("export", help="run .py that defines `root` (Value)")
    de.add_argument("script")
    de.add_argument("-o", "--output", metavar="FILE.dot")
    de.add_argument("--backward", action="store_true")
    de.add_argument("--html", metavar="FILE.html")
    de.set_defaults(func=cmd_export)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
