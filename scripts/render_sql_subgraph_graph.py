#!/usr/bin/env python
"""Render the NexusOne SQL repair subgraph using LangGraph."""

from __future__ import annotations

import sys
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.sql_subgraph.langgraph_visualization import build_sql_repair_visualization_graph


OUTPUT_PATH = ROOT / "docs" / "graphs" / "sql_repair_subgraph.png"
MERMAID_PATH = ROOT / "docs" / "graphs" / "sql_repair_subgraph.mmd"


def _dot_id(value: str) -> str:
    return "n_" + "".join(char if char.isalnum() else "_" for char in value)


def _dot_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_with_graphviz(graph, output_path: Path) -> None:
    lines = [
        "digraph sql_repair_subgraph {",
        "  graph [rankdir=TB, bgcolor=\"white\", pad=\"0.35\", nodesep=\"0.42\", ranksep=\"0.55\"];",
        "  node [shape=box, style=\"rounded,filled\", fillcolor=\"#f8fafc\", color=\"#64748b\", fontname=\"DejaVu Sans\", fontsize=11];",
        "  edge [color=\"#475569\", fontname=\"DejaVu Sans\", fontsize=9];",
    ]
    for node_id, node in graph.nodes.items():
        label = "__start__" if node_id == "__start__" else "__end__" if node_id == "__end__" else node.name
        shape = "oval" if node_id in {"__start__", "__end__"} else "box"
        fill = "#e0f2fe" if node_id == "__start__" else "#dcfce7" if node_id == "__end__" else "#f8fafc"
        lines.append(f'  {_dot_id(node_id)} [label="{_dot_label(label)}", shape={shape}, fillcolor="{fill}"];')
    for edge in graph.edges:
        attrs: list[str] = []
        if edge.conditional:
            attrs.append('style="dashed"')
        if edge.data:
            attrs.append(f'label="{_dot_label(str(edge.data))}"')
        attr_text = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f"  {_dot_id(edge.source)} -> {_dot_id(edge.target)}{attr_text};")
    lines.append("}")

    dot_path = output_path.with_suffix(".dot")
    dot_path.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["dot", "-Tpng", str(dot_path), "-o", str(output_path)], check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the SQL repair subgraph.")
    parser.add_argument(
        "--renderer",
        choices=("local-dot", "langgraph-mermaid-png"),
        default="local-dot",
        help="local-dot renders without network. langgraph-mermaid-png uses LangGraph's draw_mermaid_png renderer.",
    )
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="PNG output path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output).resolve()
    agent = build_sql_repair_visualization_graph()
    graph = agent.get_graph(xray=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    MERMAID_PATH.write_text(graph.draw_mermaid(), encoding="utf-8")

    if args.renderer == "langgraph-mermaid-png":
        png = graph.draw_mermaid_png()
        output_path.write_bytes(png)
        try:
            from IPython.display import Image, display

            display(Image(png))
        except ImportError:
            pass
    else:
        render_with_graphviz(graph, output_path)

    print(output_path)
    print(MERMAID_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
