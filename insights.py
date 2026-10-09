from __future__ import annotations
from dataclasses import dataclass, field, replace as _replace
from typing import Any, Iterable, Sequence
import pandas as pd
import correlations
import outliers
import trends
__all__ = [
    "Insight",
    "SeverityBands",
    "classify",
    "explain_trend",
    "explain_outlier",
    "explain_correlation",
    "build_insights",
    "insights_frame",
    "severity_counts",
    "INSIGHT_COLUMNS",
    "LOW",
    "MEDIUM",
    "HIGH",
]
LOW = "Low"
MEDIUM = "Medium"
HIGH = "High"
INSIGHT_COLUMNS = [
    "insight_id", "type", "indicator", "entity", "period",
    "value", "prev_value", "change_pct", "severity", "explanation",
]
_TYPE_ORDER = {"trend": 0, "outlier": 1, "correlation": 2, "threshold_breach": 3}
@dataclass(frozen=True)
class SeverityBands:
    medium_at: float = 1.0
    high_at: float = 1.5
    def __post_init__(self) -> None:
        if self.medium_at <= 0:
            raise ValueError("medium_at must be greater than zero.")
        if self.high_at < self.medium_at:
            raise ValueError("high_at must be at or above medium_at.")
@dataclass(frozen=True)
class Insight:
    insight_id: str
    type: str
    indicator: str
    entity: str
    period: str
    value: float | str
    prev_value: float | str
    change_pct: float | str
    severity: str
    explanation: str
    deviation_ratio: float
    threshold: float
    detail: dict[str, Any] = field(default_factory=dict)
    @property
    def metric(self) -> float | str:
        return self.value
    @property
    def change(self) -> float | str:
        return self.change_pct
    @property
    def drivers(self) -> str:
        drivers = self.detail.get("drivers") or {}
        if not drivers:
            return ""
        return ", ".join(f"{name} ({value:+.2f})" for name, value in drivers.items())
    def as_dict(self) -> dict[str, Any]:
        payload = {
            "insight_id": self.insight_id,
            "type": self.type,
            "indicator": self.indicator,
            "entity": self.entity,
            "period": self.period,
            "value": self.value,
            "prev_value": self.prev_value,
            "change_pct": self.change_pct,
            "severity": self.severity,
            "explanation": self.explanation,
            "metric": self.value,
            "change": self.change_pct,
            "deviation_ratio": round(self.deviation_ratio, 3),
            "threshold": self.threshold,
        }
        payload.update(
            {name: item for name, item in self.detail.items() if not isinstance(item, dict)}
        )
        payload["drivers"] = self.drivers
        return payload
def classify(ratio: float, bands: SeverityBands) -> str:
    if ratio is None or pd.isna(ratio):
        return LOW
    magnitude = abs(float(ratio))
    if magnitude <= bands.high_at:
        return HIGH
    if magnitude <= bands.medium_at:
        return MEDIUM
    return LOW
def _direction(change: float) -> str:
    return "rose" if change >= 0 else "fell"
def explain_trend(finding: trends.TrendFinding, bands: SeverityBands) -> str:
    return (
        f"{finding.entity}'s {finding.indicator} {_direction(finding.pct_change)} "
        f"by {abs(finding.pct_change):.1f}% between {finding.prev_period} and "
        f"{finding.period} ({finding.prev_value:g} to {finding.value:g}), clearing "
        f"the {finding.threshold:g}% change threshold at "
        f"{abs(finding.deviation_ratio):.2f}x its own previous month. "
        f"Severity: {classify(finding.deviation_ratio, bands)}."
    )
def explain_outlier(finding: outliers.OutlierFinding, bands: SeverityBands) -> str:
    side = "above" if finding.score > 0 else "below"
    if finding.score and finding.peer_mean and (finding.value > finding.peer_mean) != (finding.score > 0):
        side = "above" if finding.value > finding.peer_mean else "below"
    return (
        f"{finding.entity}'s {finding.indicator} of {finding.value:g} in "
        f"{finding.period} sits {side} its {finding.peers} peer districts in the "
        f"same month, which average {finding.peer_mean:.1f}, a "
        f"{abs(finding.score):.2f}x {finding.method} deviation (fences "
        f"{finding.lower_fence:.1f} to {finding.upper_fence:.1f}). "
        f"Severity: {classify(finding.deviation_ratio, bands)}."
    )
def explain_correlation(finding: correlations.CorrelationPair, bands: SeverityBands) -> str:
    direction = "inversely" if finding.r < 0 else "directly"
    where = (
        "driven mainly by " + ", ".join(name for name, _ in finding.entities)
        if finding.entities
        else "with no single district dominating"
    )
    return (
        f"{finding.indicator_a} and {finding.indicator_b} move {direction} "
        f"across the dataset (r={finding.r:+.2f} over {finding.n_obs} "
        f"observations, {abs(finding.deviation_ratio):.2f}x the "
        f"{finding.threshold:g} correlation threshold), {where}. "
        f"Severity: {classify(finding.deviation_ratio, bands)}. "
        f"Correlation is not causation."
    )
def _trend_row(finding: trends.TrendFinding, bands: SeverityBands) -> Insight:
    change = round(finding.pct_change, 1)
    return Insight(
        insight_id="",
        type="trend",
        indicator=finding.indicator,
        entity=finding.entity,
        period=finding.period,
        value=finding.value,
        prev_value=finding.prev_value,
        change_pct=change,
        severity=classify(finding.deviation_ratio, bands),
        explanation=explain_trend(finding, bands),
        deviation_ratio=finding.deviation_ratio,
        threshold=finding.threshold,
        detail={"metric": finding.indicator, "change": change},
    )
def _outlier_row(finding: outliers.OutlierFinding, bands: SeverityBands) -> Insight:
    if finding.peer_mean:
        change: float | str = round((finding.value - finding.peer_mean) / finding.peer_mean * 100, 1)
    else:
        change = "n/a"
    return Insight(
        insight_id="",
        type="outlier",
        indicator=finding.indicator,
        entity=finding.entity,
        period=finding.period,
        value=finding.value,
        prev_value=round(finding.peer_mean, 1),
        change_pct=change,
        severity=classify(finding.deviation_ratio, bands),
        explanation=explain_outlier(finding, bands),
        deviation_ratio=finding.deviation_ratio,
        threshold=finding.threshold,
        detail={
            "metric": finding.indicator,
            "change": change,
            "method": finding.method,
            "score": round(finding.score, 3),
            "lower_fence": round(finding.lower_fence, 2),
            "upper_fence": round(finding.upper_fence, 2),
            "peer_mean": round(finding.peer_mean, 1),
        },
    )
def _correlation_row(finding: correlations.CorrelationPair, bands: SeverityBands) -> Insight:
    return Insight(
        insight_id="",
        type="correlation",
        indicator=finding.label,
        entity=finding.entities[0][0] if finding.entities else "all entities",
        period=f"{finding.n_obs} observations",
        value=round(finding.r, 3),
        prev_value="n/a",
        change_pct="n/a",
        severity=classify(finding.deviation_ratio, bands),
        explanation=explain_correlation(finding, bands),
        deviation_ratio=finding.deviation_ratio,
        threshold=finding.threshold,
        detail={
            "metric": finding.label,
            "change": "n/a",
            "r": round(finding.r, 3),
            "drivers": dict(finding.entities),
            "caveat": correlations.CAVEAT,
        },
    )
def build_insights(
    trend_findings: Iterable[trends.TrendFinding],
    outlier_findings: Iterable[outliers.OutlierFinding],
    correlation_pairs: Iterable[correlations.CorrelationPair],
    bands: SeverityBands | None = None,
) -> list[Insight]:
    resolved = bands or SeverityBands()
    rows: list[Insight] = [_trend_row(f, resolved) for f in trend_findings]
    rows += [_outlier_row(f, resolved) for f in outlier_findings]
    rows += [_correlation_row(f, resolved) for f in correlation_pairs]
    rows.sort(key=lambda row: (-abs(row.deviation_ratio), _TYPE_ORDER.get(row.type, 9)))
    return [_replace(row, insight_id=f"INS-{number:04d}") for number, row in enumerate(rows, start=1)]
def insights_frame(insights: Sequence[Insight], include_aliases: bool = True) -> pd.DataFrame:
    if not insights:
        frame = pd.DataFrame({column: pd.Series(dtype="object") for column in INSIGHT_COLUMNS})
        return frame
    data = [insight.as_dict() for insight in insights]
    frame = pd.DataFrame(data)
    for column in ("value", "prev_value", "change_pct", "metric", "change"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    extra = [name for name in data[0] if name not in INSIGHT_COLUMNS]
    frame = frame[INSIGHT_COLUMNS + extra]
    if not include_aliases:
        return frame.drop(columns=[c for c in ("metric", "change") if c in frame.columns])
    return frame
def severity_counts(insights: Sequence[Insight]) -> pd.DataFrame:
    levels = [HIGH, MEDIUM, LOW]
    counts = {level: 0 for level in levels}
    for insight in insights:
        counts[insight.severity] = counts.get(insight.severity, 0) + 1
    return pd.DataFrame({"severity": levels, "count": [counts[level] for level in levels]})
def counts_by_type(insights: Sequence[Insight]) -> pd.DataFrame:
    found = [name for name in _TYPE_ORDER if any(row.type == name for row in insights)]
    counts = {name: sum(1 for row in insights if row.type == name) for name in found}
    return pd.DataFrame({"type": found, "count": [counts[name] for name in found]})
if __name__ == "__main__":
    import sys
    from pathlib import Path
    import ingest
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data.csv")
    frame, schema, _ = ingest.build_schema(ingest.load_dataset(target))
    frame, schema, _ = ingest.add_time_axis(frame, schema)
    found_trends = trends.find_trends(frame, schema.entity_column, schema.indicators, 10.0)
    found_outliers = outliers.detect_outliers(
        frame, schema.entity_column, schema.indicators, 3.0, outliers.IQR
    )
    _, found_pairs = correlations.analyse(frame, schema.entity_column, schema.indicators, 0.70)
    built = build_insights(found_trends, found_outliers, found_pairs, SeverityBands(1.0, 1.5))
    print(insights_frame(built)[INSIGHT_COLUMNS].to_string(index=False))
    print()
    print(severity_counts(built).to_string(index=False))
    print()
    print(counts_by_type(built).to_string(index=False))
