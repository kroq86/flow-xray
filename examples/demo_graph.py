"""Example graph for ``flow-xray dot export examples/demo_graph.py``."""

from flow_xray import Value

a = Value(2.0, label="a")
b = Value(-3.0, label="b")
c = Value(10.0, label="c")
root = ((a * b) + c).relu().tanh()
root.label = "L"
