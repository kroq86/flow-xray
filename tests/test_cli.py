import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}


def test_cli_dot_demo_forward_runs() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "demo", "forward"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
        env=ENV,
    )
    assert "digraph G" in r.stdout
    assert "v0" in r.stdout


def test_cli_dot_demo_html(tmp_path: Path) -> None:
    out = tmp_path / "x.html"
    subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "demo", "forward", "--html", str(out)],
        cwd=str(ROOT),
        check=True,
        env=ENV,
    )
    t = out.read_text(encoding="utf-8")
    assert "digraph G" in t and "fetch(" not in t


def test_cli_dot_export_example(tmp_path: Path) -> None:
    script = tmp_path / "g.py"
    script.write_text(
        "from flow_xray import Value\n"
        "a = Value(1.0)\n"
        "root = a * a\n",
        encoding="utf-8",
    )
    out = tmp_path / "o.dot"
    subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "export", str(script), "-o", str(out)],
        cwd=str(ROOT),
        check=True,
        env=ENV,
    )
    t = out.read_text(encoding="utf-8")
    assert "digraph G" in t


def test_cli_run_trace(tmp_path: Path) -> None:
    script = tmp_path / "s.py"
    script.write_text(
        "from flow_xray import trace\n"
        "@trace\n"
        "def step():\n"
        "    return 1\n"
        "step()\n",
        encoding="utf-8",
    )
    out = tmp_path / "t.html"
    subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "run", str(script), "--html", str(out)],
        cwd=str(ROOT),
        check=True,
        env=ENV,
    )
    t = out.read_text(encoding="utf-8")
    assert "flow-xray trace" in t or "step" in t


def test_cli_run_warns_when_no_traced_calls_execute(tmp_path: Path) -> None:
    script = tmp_path / "s.py"
    script.write_text(
        "from flow_xray import trace\n"
        "@trace\n"
        "def step():\n"
        "    return 1\n"
        "if __name__ == '__main__':\n"
        "    step()\n",
        encoding="utf-8",
    )
    out = tmp_path / "t.html"
    r = subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "run", str(script), "--html", str(out)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
        env=ENV,
    )
    assert "0 nodes" in r.stderr
    assert "__main__" in r.stderr
    assert out.exists()


def test_cli_dot_export_requires_existing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    r = subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "export", str(missing)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=ENV,
    )
    assert r.returncode == 2
    assert "error: not a file" in r.stderr


def test_cli_dot_export_requires_root_variable(tmp_path: Path) -> None:
    script = tmp_path / "g.py"
    script.write_text("x = 1\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "export", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=ENV,
    )
    assert r.returncode == 2
    assert "must define variable `root`" in r.stderr


def test_cli_dot_export_rejects_invalid_root_type(tmp_path: Path) -> None:
    script = tmp_path / "g.py"
    script.write_text("root = 123\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "export", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=ENV,
    )
    assert r.returncode == 2
    assert "must be a flow_xray.Value" in r.stderr


def test_cli_dot_export_reports_script_failure(tmp_path: Path) -> None:
    script = tmp_path / "g.py"
    script.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "flow_xray.cli", "dot", "export", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=ENV,
    )
    assert r.returncode == 2
    assert "script execution failed: RuntimeError: boom" in r.stderr
