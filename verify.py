from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import correlations
import ingest
import insights
import outliers
import trends
HERE = Path(__file__).parent
PASSED = 0
FAILED: list[str] = []
def check(label: str, actual, expected) -> None:
    global PASSED
    if actual == expected:
        PASSED += 1
    else:
        FAILED.append(f"{label}: expected {expected!r}, got {actual!r}")
def close(label: str, actual: float, expected: float, tolerance: float = 0.05) -> None:
    global PASSED
    if actual is not None and abs(float(actual) - expected) <= tolerance:
        PASSED += 1
    else:
        FAILED.append(f"{label}: expected {expected}, got {actual}")
def load(name: str):
    frame, schema, _ = ingest.build_schema(ingest.load_dataset(HERE / name))
    frame, schema, _ = ingest.add_time_axis(frame, schema)
    return frame, schema
def section(title: str) -> None:
    print(f"\n{title}")
section("Ingest: sample data")
frame, schema = load("data.csv")
check("entity column", schema.entity_column, "district")
check("period column", schema.period_column, "month")
check("indicator count", len(schema.indicators), 4)
check("indicator names", set(schema.indicators),
      {"anc_coverage", "institutional_delivery", "immunization", "high_risk_cases"})
check("rows retained", len(frame), 12)
check("periods", list(schema.periods), ["2026-07", "2026-08"])
check("whitespace stripped from values", bool((frame["district"] == "Surat").any()), True)
check("missing values after cleaning", int(frame[list(schema.indicators)].isna().sum().sum()), 0)
report = ingest.validate(frame, schema)
check("duplicate keys", report.duplicate_keys, 0)
section("Trends: all 24 pct changes vs the assignment's reference table")
ordered, previous, change = trends.compute_changes(frame, schema.entity_column, schema.indicators)
change = change.assign(district=ordered["district"].to_numpy())
reference = {
    "Ahmedabad": (-18.8, -1.1, -1.1, 30.0),
    "Surat": (2.5, 2.3, 1.1, -7.7),
    "Vadodara": (1.1, 1.1, 1.0, -14.3),
    "Rajkot": (1.3, 1.2, 1.1, -6.7),
    "Mehsana": (-50.0, -1.1, -1.1, 154.5),
    "Bhavnagar": (2.6, 2.4, 2.3, -11.8),
}
short = ["anc_coverage", "institutional_delivery", "immunization", "high_risk_cases"]
for district, expected_row in reference.items():
    block = change.loc[change["district"] == district].dropna(subset=["anc_coverage"])
    for name, expected in zip(short, expected_row):
        close(f"{district}/{name}", float(block.iloc[0][name]), expected)
check("first month NaN count (6 districts x 4 indicators)",
      int(change[short].isna().sum().sum()), 24)
check("no inf anywhere", bool(change[short].isin([float("inf"), float("-inf")]).any().any()), False)
found = trends.find_trends(frame, schema.entity_column, schema.indicators, 10.0)
check("trends at 10%", len(found), 6)
check("trend types are all trends", {f.indicator for f in found} <= set(schema.indicators), True)
mehsana_hr = next(f for f in found if f.entity == "Mehsana" and f.indicator == "high_risk_cases")
close("Mehsana risk-case change", mehsana_hr.pct_change, 154.5, 0.1)
check("Mehsana prev_value", mehsana_hr.prev_value, 11.0)
section("Outliers: within-month, never pooled")
iqr = outliers.detect_outliers(frame, schema.entity_column, schema.indicators, 3.0, outliers.IQR)
keys = {(f.entity, f.indicator, f.period) for f in iqr}
check("Mehsana anc flagged by IQR", ("Mehsana", "anc_coverage", "2026-08") in keys, True)
check("Mehsana hr flagged by IQR", ("Mehsana", "high_risk_cases", "2026-08") in keys, True)
check("no July outliers from August data", any(f.period == "2026-07" for f in iqr), False)
august = frame.loc[frame["period"] == "2026-08", "anc_coverage"]
mehsana_outlier = next(f for f in iqr if f.entity == "Mehsana" and f.indicator == "anc_coverage")
close("linear lower fence", mehsana_outlier.lower_fence, 55.375, 0.01)
tukey = outliers.detect_iqr_outliers(frame, schema.entity_column, schema.indicators, method="tukey")
check("Tukey variant flags Mehsana coverage", any(
    f.entity == "Mehsana" and f.indicator == "anc_coverage" for f in tukey
), True)
check("Tukey variant flags the same cell as linear", len(
    [f for f in tukey if f.entity == "Mehsana" and f.indicator == "anc_coverage"]
), 1)
close("Tukey hinge Q1 on August coverage", outliers._tukey_hinges(sorted(august.tolist()))[0], 69.0, 0.01)
z3 = outliers.detect_outliers(frame, schema.entity_column, schema.indicators, 3.0, outliers.ZSCORE)
check("Z-score at 3.0 finds nothing (max |z| is 2.04 at n=6)", len(z3), 0)
z15 = outliers.detect_zscore_outliers(frame, schema.entity_column, schema.indicators, 1.5)
mehsana_z = next((f for f in z15 if f.entity == "Mehsana" and f.indicator == "anc_coverage"), None)
close("Mehsana August z-score", mehsana_z.score if mehsana_z else None, -1.86, 0.01)
section("Correlations: matrix and flagged pairs")
matrix, pairs = correlations.analyse(frame, schema.entity_column, schema.indicators, 0.70)
expected_matrix = {
    ("anc_coverage", "institutional_delivery"): 0.28,
    ("anc_coverage", "immunization"): 0.37,
    ("anc_coverage", "high_risk_cases"): -0.93,
    ("institutional_delivery", "immunization"): 0.98,
    ("institutional_delivery", "high_risk_cases"): -0.56,
    ("immunization", "high_risk_cases"): -0.62,
}
for (a, b), expected in expected_matrix.items():
    close(f"r({a},{b})", matrix.loc[a, b], expected, 0.005)
check("flagged pairs at 0.70", len(pairs), 2)
flagged = {(p.indicator_a, p.indicator_b) for p in pairs}
check("anc/hr flagged", ("anc_coverage", "high_risk_cases") in flagged, True)
check("id/imm flagged", ("institutional_delivery", "immunization") in flagged, True)
check("Mehsana drives anc/hr", pairs and any(
    p.indicator_a == "anc_coverage" and p.entities and p.entities[0][0] == "Mehsana" for p in pairs
), True)
section("Insights: fields, aliases, severity")
built = insights.build_insights(found, iqr, pairs, insights.SeverityBands(1.0, 1.5))
frame_out = insights.insights_frame(built)
check("all 10 CSV columns present", all(c in frame_out.columns for c in insights.INSIGHT_COLUMNS), True)
check("metric alias present", "metric" in frame_out.columns, True)
check("change alias present", "change" in frame_out.columns, True)
check("ids sequential", built[0].insight_id, "INS-0001")
check("last id", built[-1].insight_id, f"INS-{len(built):04d}")
check("severities valid", {i.severity for i in built} <= {"Low", "Medium", "High"}, True)
check("types valid", {i.type for i in built} <= {"trend", "outlier", "correlation", "threshold_breach"}, True)
check("every row has an explanation", all(len(i.explanation) > 40 for i in built), True)
same_cell = [
    i for i in built
    if i.entity == "Mehsana" and i.indicator == "anc_coverage" and i.period == "2026-08"
]
check("Mehsana coverage is both a trend and an outlier", len(same_cell), 2)
check("...one of each type", {i.type for i in same_cell}, {"trend", "outlier"})
close("Ahmedabad coverage ratio (-18.8 / 10)", next(
    i.deviation_ratio for i in built
    if i.entity == "Ahmedabad" and i.indicator == "anc_coverage" and i.type == "trend"
), -1.88, 0.01)
check("...banded High", next(
    i.severity for i in built
    if i.entity == "Ahmedabad" and i.indicator == "anc_coverage" and i.type == "trend"
), "High")
close("Mehsana coverage ratio (-50.0 / 10)", next(
    i.deviation_ratio for i in built
    if i.entity == "Mehsana" and i.indicator == "anc_coverage" and i.type == "trend"
), -5.0, 0.01)
check("...banded High", next(
    i.severity for i in built
    if i.entity == "Mehsana" and i.indicator == "anc_coverage" and i.type == "trend"
), "High")
wide = insights.build_insights(
    trends.find_trends(frame, schema.entity_column, schema.indicators, 30.0),
    iqr, pairs, insights.SeverityBands(1.0, 1.5),
)
check("30% threshold drops the 30% finding off the edge", len(wide) < len(built), True)
bands = insights.SeverityBands(medium_at=1.0, high_at=1.5)
check("ratio 0.9 is Low", insights.classify(0.9, bands), "Low")
check("ratio 1.0 is Medium", insights.classify(1.0, bands), "Medium")
check("ratio 1.5 is High", insights.classify(1.5, bands), "High")
check("ratio -1.88 bands on magnitude", insights.classify(-1.88, bands), "High")
try:
    insights.SeverityBands(medium_at=2.0, high_at=1.0)
    FAILED.append("SeverityBands: inverted bands should raise")
except ValueError:
    PASSED_LOCAL = True
    globals()["PASSED"] += 1
section("Generality: a different CSV, unchanged source")
other, other_schema = load("sample_lab_data.csv")
check("new entity column discovered", other_schema.entity_column, "facility")
check("new period column discovered", other_schema.period_column, "reporting_period")
check("new indicators discovered", len(other_schema.indicators), 3)
check("ISO dates parsed to months", list(other_schema.periods),
      ["2025-04", "2025-05", "2025-06"])
check("all 18 rows kept", len(other), 18)
other_trends = trends.find_trends(other, other_schema.entity_column, other_schema.indicators, 10.0)
check("trends found in new dataset", len(other_trends) > 0, True)
check("no sample indicator names leaked",
      bool({i.indicator for i in other_trends} & {"anc_coverage", "high_risk_cases"}), False)
other_outliers = outliers.detect_outliers(
    other, other_schema.entity_column, other_schema.indicators, 3.0, outliers.IQR
)
check("outliers found in new dataset", len(other_outliers) > 0, True)
other_insights = insights.build_insights(other_trends, other_outliers, [], insights.SeverityBands())
check("new dataset yields insights", len(other_insights) > 0, True)
check("explanations quote real entity names",
      all(any(e in i.explanation for e in other[other_schema.entity_column].unique())
          for i in other_insights), True)
section("Robustness: malformed input")
messy_path = Path("/tmp/opencode/messy.csv")
if messy_path.exists():
    messy, messy_schema = load(str(messy_path))
    check("messy: entity column", messy_schema.entity_column, "zone")
    check("messy: unparseable date dropped", len(messy), 7)
    check("messy: no unnamed column treated as indicator",
          any("unnamed" in i.lower() or i.startswith("Unnamed") for i in messy_schema.indicators),
          False)
zero_frame = pd.DataFrame({
    "district": ["A", "A", "B", "B"],
    "month": ["2026-07", "2026-08", "2026-07", "2026-08"],
    "measure": [0, 5, 0, 7],
})
zero_frame = ingest.normalise_columns(zero_frame)
clean_zero, zero_schema, _ = ingest.build_schema(zero_frame)
clean_zero, zero_schema, _ = ingest.add_time_axis(clean_zero, zero_schema)
zero_trends = trends.find_trends(clean_zero, "district", ["measure"], 10.0)
check("zero predecessor yields no insight rather than inf", len(zero_trends), 0)
single = pd.DataFrame({"district": ["A"], "month": ["2026-07"], "m": [1.0]})
single = ingest.normalise_columns(single)
c_single, s_single, _ = ingest.build_schema(single)
c_single, s_single, _ = ingest.add_time_axis(c_single, s_single)
check("single row yields no trend",
      len(trends.find_trends(c_single, "district", ["m"], 10.0)), 0)
print(f"\n{'=' * 66}")
if FAILED:
    print(f"FAILED: {len(FAILED)} of {PASSED + len(FAILED)} checks")
    for failure in FAILED:
        print(f"  x {failure}")
    sys.exit(1)
print(f"PASSED: all {PASSED} checks")
