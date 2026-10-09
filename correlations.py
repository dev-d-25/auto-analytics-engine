from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Sequence
import pandas as pd
__all__ = [
    "CorrelationPair",
    "compute_matrix",
    "flag_pairs",
    "attribute_to_entities",
    "CAVEAT",
]
CAVEAT = (
    "Pearson r on this dataset is descriptive, not causal. Both measures are "
    "computed from the same underlying reporting process, so a strong r may "
    "reflect shared data-collection bias rather than a real relationship."
)
@dataclass(frozen=True)
class CorrelationPair:
    indicator_a: str
    indicator_b: str
    r: float
    threshold: float
    deviation_ratio: float
    n_obs: int
    entities: tuple[tuple[str, float], ...]
    @property
    def label(self) -> str:
        return f"{self.indicator_a}:{self.indicator_b}"
    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "correlation",
            "indicator": self.label,
            "entity": self.entities[0][0] if self.entities else "all entities",
            "period": f"{self.n_obs} observations",
            "value": self.r,
            "r": self.r,
            "prev_value": "n/a",
            "change_pct": "n/a",
            "threshold": self.threshold,
            "deviation_ratio": self.deviation_ratio,
            "n_obs": self.n_obs,
            "drivers": dict(self.entities),
            "caveat": CAVEAT,
        }
def compute_matrix(
    frame: pd.DataFrame,
    indicators: Sequence[str],
) -> pd.DataFrame:
    names = list(indicators)
    usable = [name for name in names if frame[name].notna().any()]
    if len(usable) < 2:
        return pd.DataFrame(index=usable, columns=usable, dtype=float)
    return frame[usable].corr(method="pearson")
def flag_pairs(
    matrix: pd.DataFrame,
    corr_threshold: float = 0.70,
) -> list[tuple[str, str, float]]:
    if not 0 <= corr_threshold <= 1:
        raise ValueError("corr_threshold must be between 0 and 1.")
    pairs: list[tuple[str, str, float]] = []
    for a, b in combinations(matrix.columns, 2):
        r = matrix.loc[a, b]
        if pd.isna(r):
            continue
        if abs(float(r)) >= corr_threshold:
            pairs.append((a, b, float(r)))
    return sorted(pairs, key=lambda item: -abs(item[2]))
def attribute_to_entities(
    frame: pd.DataFrame,
    entity_column: str,
    indicator_a: str,
    indicator_b: str,
    r: float,
    top_n: int = 3,
) -> tuple[tuple[str, float], ...]:
    if len(frame) == 0:
        return ()
    paired = frame[[entity_column, indicator_a, indicator_b]].dropna()
    if paired.empty:
        return ()
    raw: list[tuple[str, float, float]] = []
    for entity, block in paired.groupby(entity_column, sort=True):
        a = block[indicator_a].astype(float)
        b = block[indicator_b].astype(float)
        if len(block) >= 3 and a.std(ddof=1) and b.std(ddof=1):
            co_movement = float(a.corr(b))
        elif len(block) >= 2:
            spread_a, spread_b = a.std(ddof=0), b.std(ddof=0)
            za = (a - a.mean()) / spread_a if spread_a else a * 0.0
            zb = (b - b.mean()) / spread_b if spread_b else b * 0.0
            co_movement = float((za * zb).mean())
        else:
            continue
        if pd.isna(co_movement):
            continue
        moves = [float(a.diff().abs().mean()), float(b.diff().abs().mean())]
        magnitude = sum(moves) / len(moves)
        raw.append((str(entity), co_movement, magnitude))
    if not raw:
        return ()
    largest = max(magnitude for _, _, magnitude in raw)
    if not largest:
        return ()
    scores: list[tuple[str, float]] = []
    for entity, co_movement, magnitude in raw:
        weight = magnitude / largest
        aligned = abs(co_movement) * weight
        if (co_movement >= 0) != (r >= 0):
            aligned = -aligned
        scores.append((entity, aligned))
    if not scores or all(value == 0.0 for _, value in scores):
        return ()
    return tuple(sorted(scores, key=lambda item: -item[1])[:top_n])
def analyse(
    frame: pd.DataFrame,
    entity_column: str,
    indicators: Sequence[str],
    corr_threshold: float = 0.70,
) -> tuple[pd.DataFrame, list[CorrelationPair]]:
    matrix = compute_matrix(frame, indicators)
    pairs: list[CorrelationPair] = []
    for a, b, r in flag_pairs(matrix, corr_threshold):
        drivers = attribute_to_entities(frame, entity_column, a, b, r)
        pairs.append(
            CorrelationPair(
                indicator_a=a,
                indicator_b=b,
                r=r,
                threshold=corr_threshold,
                deviation_ratio=abs(r) / corr_threshold,
                n_obs=int(frame[[a, b]].dropna().shape[0]),
                entities=drivers,
            )
        )
    return matrix, pairs
if __name__ == "__main__":
    import sys
    from pathlib import Path
    import ingest
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data.csv")
    cutoff = float(sys.argv[2]) if len(sys.argv) > 2 else 0.70
    frame, schema, _ = ingest.build_schema(ingest.load_dataset(target))
    frame, schema, _ = ingest.add_time_axis(frame, schema)
    matrix, pairs = analyse(frame, schema.entity_column, schema.indicators, cutoff)
    print("Pearson correlation matrix:")
    print(matrix.round(2).to_string())
    print(f"\nFlagged pairs at |r| >= {cutoff}: {len(pairs)}\n")
    for pair in pairs:
        drivers = ", ".join(f"{name} ({value:+.2f})" for name, value in pair.entities)
        print(f"  {pair.label:45} r={pair.r:+.3f}  drivers: {drivers or 'none (single period per entity)'}")
    print(f"\n{CAVEAT}")
