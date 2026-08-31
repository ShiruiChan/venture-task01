from __future__ import annotations

from typing import Any, Optional


def line_chart(
    rows: list[dict[str, Any]],
    series: list[tuple[str, str, str]],
    width: int = 960,
    height: int = 260,
    pad_left: int = 48,
    pad_bottom: int = 28,
    pad_top: int = 12,
    pad_right: int = 12,
) -> dict[str, Any]:
    labels = [row.get("day", "") for row in rows]
    values = [row[key] for key, _, _ in series for row in rows if row.get(key) is not None]
    top = max(values) if values else 0
    top = _nice_ceiling(top)
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n = len(rows)

    def x_of(index: int) -> float:
        if n <= 1:
            return pad_left + plot_w / 2
        return pad_left + plot_w * index / (n - 1)

    def y_of(value: float) -> float:
        return pad_top + plot_h * (1 - (value / top if top else 0))

    out_series = []
    for key, title, css in series:
        segments: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        points: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            value = row.get(key)
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            point = (round(x_of(index), 2), round(y_of(value), 2))
            current.append(point)
            points.append({"x": point[0], "y": point[1], "value": value, "label": labels[index]})
        if current:
            segments.append(current)
        out_series.append(
            {
                "key": key,
                "title": title,
                "css": css,
                "paths": [" ".join(f"{x},{y}" for x, y in seg) for seg in segments if len(seg) > 1],
                "dots": points,
            }
        )

    ticks = [
        {"value": int(top * frac), "y": round(y_of(top * frac), 2)}
        for frac in (0, 0.25, 0.5, 0.75, 1.0)
    ] if top else [{"value": 0, "y": round(y_of(0), 2)}]

    step = max(1, n // 8)
    x_labels = [
        {"x": round(x_of(i), 2), "text": _short_day(labels[i])}
        for i in range(n)
        if i % step == 0 or i == n - 1
    ]

    return {
        "width": width,
        "height": height,
        "series": out_series,
        "ticks": ticks,
        "x_labels": x_labels,
        "baseline_y": round(y_of(0), 2),
        "pad_left": pad_left,
        "plot_right": width - pad_right,
        "empty": not values,
    }


def bar_chart(rows: list[dict[str, Any]], key: str, label_key: str, width: int = 960, height: int = 220) -> dict[str, Any]:
    """Горизонтальные доли для рейтинга подразделений."""
    top = max((abs(row.get(key) or 0) for row in rows), default=0) or 1
    return {
        "width": width,
        "height": height,
        "items": [
            {
                "label": row.get(label_key, ""),
                "value": row.get(key),
                "pct": round(abs(row.get(key) or 0) / top * 100, 1),
                "negative": (row.get(key) or 0) < 0,
            }
            for row in rows
        ],
    }


def _nice_ceiling(value: float) -> float:
    if value <= 0:
        return 0
    magnitude = 10 ** (len(str(int(value))) - 1)
    for factor in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        candidate = magnitude * factor
        if candidate >= value:
            return candidate
    return value


def _short_day(iso: str) -> str:
    parts = str(iso).split("-")
    return f"{parts[2]}.{parts[1]}" if len(parts) == 3 else str(iso)
