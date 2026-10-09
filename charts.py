from __future__ import annotations
from typing import Sequence
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
__all__ = ["severity_bar", "trend_line", "correlation_heatmap"]
_SEVERITY_COLOURS = {"High": "#c0392b", "Medium": "#e08e0b", "Low": "#2e7d32"}
_DEFAULT_SERIES = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#17becf"]
def severity_bar(counts: pd.DataFrame) -> Figure:
    figure, axes = plt.subplots(figsize=(6, 3.6))
    levels = list(counts["severity"])
    values = list(counts["count"])
    colours = [_SEVERITY_COLOURS.get(level, "#555555") for level in levels]
    bars = axes.bar(levels, values, color=colours, width=0.6)
    axes.bar_label(bars, padding=3, fontsize=10)
    axes.set_title("Insights by severity")
    axes.set_ylabel("insight count")
    axes.set_ylim(0, max(values + [0]) * 1.18 + 1)
    axes.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return figure
def trend_line(
    frame: pd.DataFrame,
    entity_column: str,
    indicator: str,
    entities: Sequence[str] | None = None,
) -> Figure:
    figure, axes = plt.subplots(figsize=(9, 4.2))
    if indicator not in frame.columns:
        axes.text(
            0.5, 0.5,
            f"No data for {indicator!r} in the current selection",
            ha="center", va="center", transform=axes.transAxes, fontsize=11,
        )
        axes.set_xticks([])
        axes.set_yticks([])
        axes.set_title(f"{indicator} by {entity_column}, over time")
        figure.tight_layout()
        return figure
    wanted = list(dict.fromkeys(entities)) if entities else sorted(frame[entity_column].unique())
    plotted = 0
    for position, entity in enumerate(wanted):
        block = frame.loc[frame[entity_column] == entity, ["_month", indicator]].dropna()
        if block.empty:
            continue
        block = block.sort_values("_month")
        axes.plot(
            block["_month"].dt.to_timestamp(),
            block[indicator].to_numpy(),
            marker="o",
            linewidth=2,
            markersize=4,
            label=str(entity),
            color=_DEFAULT_SERIES[position % len(_DEFAULT_SERIES)],
        )
        plotted += 1
    if plotted == 0:
        axes.text(
            0.5, 0.5,
            f"No data for {indicator!r} in the current selection",
            ha="center", va="center", transform=axes.transAxes, fontsize=11,
        )
        axes.set_xticks([])
    axes.set_title(f"{indicator} by {entity_column}, over time")
    axes.set_xlabel("month")
    axes.set_ylabel(indicator)
    axes.grid(True, alpha=0.25, linestyle=":")
    axes.spines[["top", "right"]].set_visible(False)
    axes.legend(title=entity_column, loc="best", fontsize=8, title_fontsize=9)
    figure.autofmt_xdate()
    figure.tight_layout()
    return figure
def correlation_heatmap(
    matrix: pd.DataFrame,
    flagged: Sequence[tuple[str, str, float]] = (),
    threshold: float = 0.70,
) -> Figure:
    if matrix.empty or not len(matrix.columns):
        figure, axes = plt.subplots(figsize=(4, 2.6))
        axes.text(
            0.5, 0.5, "Not enough numeric indicators to correlate",
            ha="center", va="center", transform=axes.transAxes, fontsize=11,
        )
        axes.set_xticks([])
        axes.set_yticks([])
        figure.tight_layout()
        return figure
    figure, axes = plt.subplots(figsize=(1.05 * len(matrix.columns) + 2.4, 1.0 * len(matrix) + 2.2))
    values = matrix.to_numpy(dtype=float)
    axes.imshow(values, cmap="RdBu_r", vmin=-1, vmax=1)
    axes.set_xticks(range(len(matrix.columns)), labels=matrix.columns, rotation=45, ha="right")
    axes.set_yticks(range(len(matrix.index)), labels=matrix.index)
    flagged_cells: set[tuple[str, str]] = set()
    for a, b, _ in flagged:
        flagged_cells.add((a, b))
        flagged_cells.add((b, a))
    for row in range(len(matrix.index)):
        for column in range(len(matrix.columns)):
            value = values[row, column]
            if np.isnan(value):
                continue
            shade = "white" if abs(value) > 0.55 else "black"
            label = f"{value:.2f}"
            axes.text(column, row, label, ha="center", va="center", color=shade, fontsize=9)
            if (matrix.index[row], matrix.columns[column]) in flagged_cells:
                axes.add_patch(
                    plt.Rectangle(
                        (column - 0.5, row - 0.5), 1, 1,
                        fill=False, edgecolor="#111111", linewidth=2.2,
                    )
                )
    axes.set_title(f"Pearson correlation (boxed: |r| >= {threshold:g})")
    figure.colorbar(
        matplotlib.cm.ScalarMappable(cmap="RdBu_r", norm=matplotlib.colors.Normalize(-1, 1)),
        ax=axes, fraction=0.046, pad=0.04,
    )
    axes.set_aspect("auto")
    figure.tight_layout()
    return figure
