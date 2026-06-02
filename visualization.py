from typing import Dict, List, Optional

import plotly.graph_objects as go


def build_zone_grid(
    rows: List[Dict[str, object]],
    metric: str = "shots",
    x_bins: int = 12,
    y_bins: int = 8,
) -> Dict[str, object]:
    grid = [[0.0 for _ in range(x_bins)] for _ in range(y_bins)]
    hover_text = [["" for _ in range(x_bins)] for _ in range(y_bins)]

    for row in rows:
        if "zone_x" not in row or "zone_y" not in row:
            continue
        x = int(row["zone_x"])
        y = int(row["zone_y"])
        if 0 <= x < x_bins and 0 <= y < y_bins:
            grid[y][x] = float(row.get(metric, 0.0) or 0.0)
            hover_text[y][x] = (
                f"zone=({x},{y})<br>"
                f"shots={row.get('shots', 0)}<br>"
                f"goals={row.get('goals', 0)}<br>"
                f"xG={row.get('xg_sum', 0.0):.3f}<br>"
                f"goal_rate={row.get('goal_rate', 0.0):.3f}<br>"
                f"avg_xg={row.get('avg_xg', 0.0):.3f}"
            )

    return {
        "z": grid,
        "text": hover_text,
        "x": list(range(x_bins)),
        "y": list(range(y_bins)),
    }


def zone_heatmap(
    rows: List[Dict[str, object]],
    metric: str = "shots",
    title: Optional[str] = None,
    x_bins: int = 12,
    y_bins: int = 8,
) -> go.Figure:
    data = build_zone_grid(rows, metric, x_bins, y_bins)

    fig = go.Figure(
        data=
        go.Heatmap(
            z=data["z"],
            x=data["x"],
            y=data["y"],
            text=data["text"],
            hoverinfo="text",
            colorscale="YlOrRd",
            colorbar=dict(title=metric),
        )
    )

    fig.update_layout(
        title=title or f"Hotzone: {metric}",
        xaxis=dict(title="zone_x", dtick=1),
        yaxis=dict(title="zone_y", autorange="reversed", dtick=1),
        template="plotly_white",
        width=900,
        height=700,
    )
    fig.update_xaxes(side="top")
    return fig


def save_hotzone_html(
    rows: List[Dict[str, object]],
    output_path: str,
    metric: str = "shots",
    title: Optional[str] = None,
    x_bins: int = 12,
    y_bins: int = 8,
) -> None:
    fig = zone_heatmap(rows, metric, title, x_bins, y_bins)
    fig.write_html(output_path, include_plotlyjs="cdn")
