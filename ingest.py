from __future__ import annotations
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Sequence
import pandas as pd
__all__ = [
    "DatasetSchema",
    "ValidationReport",
    "load_dataset",
    "normalise_columns",
    "clean_values",
    "detect_entity_column",
    "detect_period_column",
    "detect_indicators",
    "add_time_axis",
    "build_schema",
    "validate",
    "describe",
]
@dataclass(frozen=True)
class DatasetSchema:
    entity_column: str
    period_column: str
    indicators: tuple[str, ...]
    rows: int
    periods: tuple[str, ...]
    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_column": self.entity_column,
            "period_column": self.period_column,
            "indicators": list(self.indicators),
            "rows": self.rows,
            "periods": list(self.periods),
        }
@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    row_count: int
    column_count: int
    entity_count: int
    period_count: int
    months_per_entity: dict[str, int]
    missing_by_column: dict[str, int]
    duplicate_keys: int
    dropped_rows: int
    unparsed_periods: tuple[str, ...]
    warnings: tuple[str, ...] = field(default=())
    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "entity_count": self.entity_count,
            "period_count": self.period_count,
            "months_per_entity": dict(self.months_per_entity),
            "missing_by_column": dict(self.missing_by_column),
            "duplicate_keys": self.duplicate_keys,
            "dropped_rows": self.dropped_rows,
            "unparsed_periods": list(self.unparsed_periods),
            "warnings": list(self.warnings),
        }
def load_dataset(source: str | Path | Any) -> pd.DataFrame:
    frame = pd.read_csv(source)
    return normalise_columns(frame)
def normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed: list[str] = []
    seen: dict[str, int] = {}
    for position, raw in enumerate(frame.columns):
        candidate = str(raw).strip()
        if not candidate:
            candidate = f"unnamed_{position}"
        if candidate in seen:
            seen[candidate] += 1
            candidate = f"{candidate}_{seen[candidate]}"
        else:
            seen[candidate] = 0
        renamed.append(candidate)
    out = frame.copy()
    out.columns = renamed
    return out
def clean_values(
    frame: pd.DataFrame,
    entity_column: str,
    period_column: str,
) -> tuple[pd.DataFrame, int]:
    out = frame.copy()
    for column in out.columns:
        if column in (entity_column, period_column):
            out[column] = out[column].astype("string").str.strip()
    for column in out.columns:
        if column in (entity_column, period_column):
            continue
        if out[column].dtype == object or str(out[column].dtype).startswith("str"):
            coerced = pd.to_numeric(out[column].astype("string").str.strip(), errors="coerce")
            if coerced.notna().any() or out[column].isna().all():
                out[column] = coerced
    empty = [column for column in out.columns if out[column].isna().all() and column not in (entity_column, period_column)]
    if empty:
        out = out.drop(columns=empty)
    before = len(out)
    out = out.loc[out[entity_column].notna() & (out[entity_column] != "")]
    out = out.loc[out[period_column].notna() & (out[period_column] != "")]
    return out.reset_index(drop=True), before - len(out)
_ENTITY_HINTS = frozenset(
    {"district", "entity", "unit", "region", "state", "block", "facility",
     "hospital", "centre", "center", "city", "zone", "area", "tehsil", "taluka"}
)
_PERIOD_HINTS = frozenset(
    {"month", "period", "date", "yearmonth", "year_month", "ym", "reportingmonth", "reporting_period"}
)
def _squash(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("_", "")
def detect_entity_column(frame: pd.DataFrame) -> str:
    text_columns = [
        column
        for column in frame.columns
        if str(frame[column].dtype) in {"object", "string"} or isinstance(frame[column].dtype, pd.StringDtype)
    ]
    if not text_columns:
        raise ValueError("No text column found to group by (need a district/entity column).")
    for column in text_columns:
        if frame[column].nunique(dropna=True) <= max(2, len(frame) // 2):
            return column
    return text_columns[0]
def detect_period_column(frame: pd.DataFrame, entity_column: str) -> str:
    candidates = [column for column in frame.columns if column != entity_column]
    if not candidates:
        raise ValueError("No column found to use as a time period.")
    for column in candidates:
        if _squash(column) in _PERIOD_HINTS:
            return column
    for column in candidates:
        if frame[column].nunique(dropna=True) <= max(2, len(frame) // 2):
            return column
    return candidates[0]
def detect_indicators(frame: pd.DataFrame, entity_column: str, period_column: str) -> tuple[str, ...]:
    indicators = [
        column
        for column in frame.columns
        if column not in (entity_column, period_column) and pd.api.types.is_numeric_dtype(frame[column])
    ]
    return tuple(indicators)
def add_time_axis(
    frame: pd.DataFrame,
    schema: DatasetSchema,
) -> tuple[pd.DataFrame, DatasetSchema, tuple[str, ...]]:
    out = frame.copy()
    raw = out[schema.period_column].astype("string").str.strip()
    parsed = pd.to_datetime(raw, format="mixed", errors="coerce")
    out["_month"] = parsed.dt.to_period("M")
    out["period"] = out["_month"].dt.strftime("%Y-%m")
    unparsed = parsed.isna() & raw.notna() & (raw != "")
    bad = tuple(sorted(set(raw.loc[unparsed].dropna())))
    out = out.loc[~unparsed].reset_index(drop=True)
    refreshed = replace(
        schema,
        rows=len(out),
        periods=tuple(
            sorted(str(p) for p in out["_month"].dropna().unique())
        ),
    )
    return out, refreshed, bad
def build_schema(frame: pd.DataFrame) -> tuple[pd.DataFrame, DatasetSchema, int]:
    clean, dropped = clean_values(
        frame,
        detect_entity_column(frame),
        detect_period_column(frame, detect_entity_column(frame)),
    )
    entity_column = detect_entity_column(clean)
    period_column = detect_period_column(clean, entity_column)
    indicators = detect_indicators(clean, entity_column, period_column)
    if not indicators:
        raise ValueError("No numeric indicator columns found to analyse.")
    periods = tuple(sorted(p for p in clean[period_column].astype("string").unique() if p))
    schema = DatasetSchema(
        entity_column=entity_column,
        period_column=period_column,
        indicators=indicators,
        rows=len(clean),
        periods=periods,
    )
    return clean, schema, dropped
def validate(frame: pd.DataFrame, schema: DatasetSchema) -> ValidationReport:
    missing_by_column = {column: int(frame[column].isna().sum()) for column in frame.columns}
    entity_values = frame[schema.entity_column]
    per_entity = (
        frame.loc[frame["period"].notna()]
        .groupby(schema.entity_column)["period"]
        .nunique()
        .sort_index()
    )
    duplicate_keys = int(
        frame.duplicated(subset=[schema.entity_column, "period"]).sum()
    )
    warnings: list[str] = []
    thin = per_entity[per_entity < 3]
    if not thin.empty:
        worst = ", ".join(f"{name} ({count})" for name, count in thin.items())
        warnings.append(
            f"{len(thin)} of {len(per_entity)} entities have fewer than 3 periods; "
            f"trend detection is thin for: {worst}."
        )
    if len(per_entity) < 10:
        warnings.append(
            f"Only {len(per_entity)} entities. Correlations on fewer than 10 are unstable "
            "and should be read as descriptive, not causal."
        )
    if len(schema.periods) < 2:
        warnings.append("Fewer than 2 distinct periods, so no month-over-month change can be computed.")
    if duplicate_keys:
        warnings.append(
            f"{duplicate_keys} duplicated (entity, period) row(s); each measurement should appear once."
        )
    gaps = {column: count for column, count in missing_by_column.items() if count}
    if gaps:
        detail = ", ".join(f"{column}={count}" for column, count in sorted(gaps.items()))
        warnings.append(f"Missing values present: {detail}. Rows with gaps are skipped, not imputed.")
    return ValidationReport(
        ok=not duplicate_keys and not gaps and len(per_entity) > 0,
        row_count=len(frame),
        column_count=len(frame.columns),
        entity_count=int(len(per_entity)),
        period_count=len(schema.periods),
        months_per_entity={str(name): int(count) for name, count in per_entity.items()},
        missing_by_column=missing_by_column,
        duplicate_keys=duplicate_keys,
        dropped_rows=0,
        unparsed_periods=(),
        warnings=tuple(warnings),
    )
def describe(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    report: ValidationReport,
    head_rows: int = 5,
    extra_periods: Sequence[str] = (),
) -> str:
    bad_periods = tuple(extra_periods)
    warnings = report.warnings
    if bad_periods:
        warnings = warnings + (
            f"Could not parse {len(bad_periods)} period value(s) as a date: "
            f"{', '.join(bad_periods[:5])}.",
        )
    lines: list[str] = []
    lines.append(f"Shape: {report.row_count} rows x {report.column_count} columns")
    lines.append(
        f"Detected entity column: {schema.entity_column} "
        f"({report.entity_count} distinct)"
    )
    lines.append(
        f"Detected period column: {schema.period_column} "
        f"({report.period_count} periods: {', '.join(schema.periods)})"
    )
    lines.append(f"Detected indicators ({len(schema.indicators)}): {', '.join(schema.indicators)}")
    lines.append("")
    lines.append(f"head({head_rows}):")
    lines.append(frame.head(head_rows).to_string())
    lines.append("")
    lines.append("info():")
    lines.append(_info_block(frame))
    lines.append("")
    lines.append("Missing values per column:")
    missing = report.missing_by_column
    if not missing:
        lines.append("  (none)")
    for column, count in missing.items():
        lines.append(f"  {column}: {count}")
    lines.append("")
    lines.append("Rows per entity:")
    for name, count in report.months_per_entity.items():
        lines.append(f"  {name}: {count}")
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"  - {warning}")
    else:
        lines.append("")
        lines.append("Warnings: none")
    return "\n".join(lines)
def _info_block(frame: pd.DataFrame) -> str:
    lines = [f"RangeIndex: {len(frame)} entries, 0 to {max(len(frame) - 1, 0)}"]
    lines.append(f"Data columns (total {len(frame.columns)} columns):")
    for position, column in enumerate(frame.columns):
        lines.append(f" {position:>2}  {column:<24} {frame[column].dtype}  non-null: {int(frame[column].notna().sum())}")
    return "\n".join(lines)
if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data.csv")
    raw = load_dataset(target)
    cleaned, schema, dropped = build_schema(raw)
    cleaned, schema, unparsed = add_time_axis(cleaned, schema)
    base = validate(cleaned, schema)
    final = replace(base, dropped_rows=dropped + len(unparsed), unparsed_periods=unparsed)
    print(describe(cleaned, schema, final, extra_periods=unparsed))
