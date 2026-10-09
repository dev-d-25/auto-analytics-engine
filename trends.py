from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np
import pandas as pd
__all__ = ["TrendFinding", "compute_changes", "find_trends", "summarise_trends"]
@dataclass(frozen=True)
class TrendFinding:
    entity: str
    indicator: str
    period: str
    value: float
    prev_value: float
    prev_period: str
    pct_change: float
    threshold: float
    deviation_ratio: float
    periods_observed: int
    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "trend",
            "entity": self.entity,
            "indicator": self.indicator,
            "period": self.period,
            "value": self.value,
            "prev_value": self.prev_value,
            "prev_period": self.prev_period,
            "change_pct": self.pct_change,
            "deviation_ratio": self.deviation_ratio,
            "threshold": self.threshold,
            "periods_observed": self.periods_observed,
        }
def compute_changes(
    frame: pd.DataFrame,
    entity_column: str,
    indicators: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ordered = frame.sort_values(
        [entity_column, "_month"], kind="mergesort"
    ).reset_index(drop=True)
    names = list(indicators)
    grouped = ordered.groupby(entity_column, sort=False)
    previous = grouped[names].shift(1)
    safe_previous = previous.where(previous == 0)
    pct_change = ordered[names].sub(safe_previous).div(safe_previous).mul(100.0)
    valid = previous.notna() & ordered[names].notna() & safe_previous.notna()
    pct_change = pct_change.where(valid).replace([np.inf, -np.inf], np.nan)
    return ordered, previous, pct_change
def find_trends(
    frame: pd.DataFrame,
    entity_column: str,
    indicators: Sequence[str],
    trend_threshold: float,
) -> list[TrendFinding]:
    if trend_threshold <= 0:
        raise ValueError("trend_threshold must be greater than zero.")
    ordered, previous, pct_change = compute_changes(frame, entity_column, indicators)
    periods_seen = ordered.groupby(entity_column)["_month"].transform("nunique")
    findings: list[TrendFinding] = []
    for indicator in indicators:
        moved = pct_change[indicator].dropna()
        if moved.empty:
            continue
        flagged = moved[moved.abs() >= trend_threshold]
        for index, change in flagged.items():
            row = ordered.loc[index]
            findings.append(
                TrendFinding(
                    entity=str(row[entity_column]),
                    indicator=indicator,
                    period=str(row["period"]),
                    value=float(row[indicator]),
                    prev_value=float(previous.loc[index, indicator]),
                    prev_period=(
                        str(row["_month"] - 1) if pd.notna(row["_month"]) else ""
                    ),
                    pct_change=float(change),
                    threshold=float(trend_threshold),
                    deviation_ratio=float(change) / float(trend_threshold),
                    periods_observed=int(periods_seen.loc[index]),
                )
            )
    return sorted(findings, key=lambda f: -abs(f.deviation_ratio))
def summarise_trends(findings: Sequence[TrendFinding]) -> pd.DataFrame:
    columns = [
        "entity", "indicator", "period", "prev_period",
        "prev_value", "value", "change_pct", "threshold", "deviation_ratio",
    ]
    if not findings:
        return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})
    return pd.DataFrame([f.as_dict() for f in findings])[columns]
if __name__ == "__main__":
    import sys
    from pathlib import Path
    import ingest
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data.csv")
    cutoff = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    frame, schema, dropped = ingest.build_schema(ingest.load_dataset(target))
    frame, schema, unparsed = ingest.add_time_axis(frame, schema)
    hits = find_trends(frame, schema.entity_column, schema.indicators, cutoff)
    print(f"Threshold: +/-{cutoff}%")
    print(f"Flagged trends: {len(hits)}\n")
    print(summarise_trends(hits).to_string(index=False))
