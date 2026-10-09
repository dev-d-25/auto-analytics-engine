from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np
import pandas as pd
__all__ = [
    "OutlierFinding",
    "detect_iqr_outliers",
    "detect_zscore_outliers",
    "detect_outliers",
    "IQR",
    "ZSCORE",
]
IQR = "IQR"
ZSCORE = "Z-score"
@dataclass(frozen=True)
class OutlierFinding:
    entity: str
    indicator: str
    period: str
    value: float
    peer_mean: float
    peer_std: float
    score: float
    method: str
    lower_fence: float
    upper_fence: float
    threshold: float
    deviation_ratio: float
    peers: int
    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "outlier",
            "entity": self.entity,
            "indicator": self.indicator,
            "period": self.period,
            "value": self.value,
            "peer_mean": self.peer_mean,
            "peer_std": self.peer_std,
            "score": self.score,
            "method": self.method,
            "lower_fence": self.lower_fence,
            "upper_fence": self.upper_fence,
            "threshold": self.threshold,
            "deviation_ratio": self.deviation_ratio,
            "peers": self.peers,
        }
def detect_iqr_outliers(
    frame: pd.DataFrame,
    entity_column: str,
    indicators: Sequence[str],
    method: str = IQR,
) -> list[OutlierFinding]:
    if method not in {"linear", "tukey"}:
        raise ValueError(f"Unknown IQR method: {method!r}. Use 'linear' or 'tukey'.")
    findings: list[OutlierFinding] = []
    for indicator in indicators:
        for period, block in frame.groupby("period", sort=True):
            values = block[indicator].dropna()
            if len(values) < 3:
                continue
            if method == "linear":
                q1, q3 = values.quantile(0.25), values.quantile(0.75)
            else:
                q1, q3 = _tukey_hinges(sorted(values.tolist()))
            spread = q3 - q1
            lower = q1 - 1.5 * spread
            upper = q3 + 1.5 * spread
            if spread <= 0:
                continue
            for row in block.loc[values.index].itertuples(index=False):
                value = getattr(row, indicator)
                if pd.isna(value):
                    continue
                if not (value < lower or value > upper):
                    continue
                distance = (lower - value) if value < lower else (value - upper)
                findings.append(
                    OutlierFinding(
                        entity=str(getattr(row, entity_column)),
                        indicator=indicator,
                        period=str(period),
                        value=float(value),
                        peer_mean=float(values.mean()),
                        peer_std=float(values.std(ddof=1)),
                        score=float(distance / spread * (-1.0 if value < lower else 1.0)),
                        method=f"IQR ({method})",
                        lower_fence=float(lower),
                        upper_fence=float(upper),
                        threshold=1.5,
                        deviation_ratio=float(distance / spread) / 1.5,
                        peers=len(values),
                    )
                )
    return sorted(findings, key=lambda f: -abs(f.deviation_ratio))
def _tukey_hinges(ordered: list[float]) -> tuple[float, float]:
    count = len(ordered)
    middle = count // 2
    lower_half = ordered[:middle]
    upper_half = ordered[-middle:] if count % 2 == 0 else ordered[middle + 1:]
    if not lower_half or not upper_half:
        return float(ordered[0]), float(ordered[-1])
    q1 = float(np.median(lower_half))
    q3 = float(np.median(upper_half))
    return q1, q3
def detect_zscore_outliers(
    frame: pd.DataFrame,
    entity_column: str,
    indicators: Sequence[str],
    z_threshold: float = 3.0,
) -> list[OutlierFinding]:
    if z_threshold <= 0:
        raise ValueError("z_threshold must be greater than zero.")
    findings: list[OutlierFinding] = []
    for indicator in indicators:
        for period, block in frame.groupby("period", sort=True):
            values = block[indicator].dropna()
            if len(values) < 3:
                continue
            std = values.std(ddof=1)
            if not std or np.isnan(std) or std == 0:
                continue
            mean = values.mean()
            for row in block.loc[values.index].itertuples(index=False):
                value = getattr(row, indicator)
                if pd.isna(value):
                    continue
                score = float((value - mean) / std)
                if abs(score) < z_threshold:
                    continue
                findings.append(
                    OutlierFinding(
                        entity=str(getattr(row, entity_column)),
                        indicator=indicator,
                        period=str(period),
                        value=float(value),
                        peer_mean=float(mean),
                        peer_std=float(std),
                        score=score,
                        method="Z-score",
                        lower_fence=float(mean - z_threshold * std),
                        upper_fence=float(mean + z_threshold * std),
                        threshold=float(z_threshold),
                        deviation_ratio=abs(score) / float(z_threshold),
                        peers=len(values),
                    )
                )
    return sorted(findings, key=lambda f: -abs(f.deviation_ratio))
def detect_outliers(
    frame: pd.DataFrame,
    entity_column: str,
    indicators: Sequence[str],
    outlier_threshold: float = 3.0,
    method: str = IQR,
) -> list[OutlierFinding]:
    if method == ZSCORE:
        return detect_iqr_outliers(frame, entity_column, indicators, method="linear")
    return detect_zscore_outliers(frame, entity_column, indicators, outlier_threshold)
    raise ValueError(f"Unknown outlier method: {method!r}. Use {IQR!r} or {ZSCORE!r}.")
if __name__ == "__main__":
    import sys
    from pathlib import Path
    import ingest
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data.csv")
    choice = sys.argv[2] if len(sys.argv) > 2 else IQR
    frame, schema, _ = ingest.build_schema(ingest.load_dataset(target))
    frame, schema, _ = ingest.add_time_axis(frame, schema)
    hits = detect_outliers(frame, schema.entity_column, schema.indicators, 3.0, choice)
    print(f"Method: {choice}   Threshold: 3.0")
    print(f"Flagged outliers: {len(hits)}\n")
    if hits:
        print(pd.DataFrame([h.as_dict() for h in hits]).to_string(index=False))
