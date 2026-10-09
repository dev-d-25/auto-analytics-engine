# Automated Insight Generation

**DEV VAGHELA (IT)**

An auto-analytics engine for district-level healthcare performance data. It loads a
CSV, finds trends, outliers and correlations, and writes plain-English explanations
for each one. Every threshold is adjustable in the UI, and the same code runs on a
different CSV without edits.

Built for Assignment 4: Automated Insight Generation.

---

## What it does

Three comparisons, kept strictly separate:

| Comparison | Question | Module |
|---|---|---|
| Same district, across months | Did this district change? | `trends.py` |
| Different districts, same month | Is this district unusual among its peers? | `outliers.py` |
| All districts and months pooled | Do two indicators move together? | `correlations.py` |

The separation matters. A district that is always low is *not* an outlier, and a
district that fell sharply *is* a trend even if it lands near its peers. Mixing the
two comparisons produces findings that mean nothing.

## Design rules

**No hardcoded narratives.** No district name, indicator name or figure appears in
the source. `grep -i "mehsana\|anc_coverage" *.py` returns nothing. Every sentence is
an f-string template with numbers substituted from the data.

**Indicators are discovered, not declared.** The engine finds the entity column and
the period column by inspecting the frame, then treats every remaining numeric column
as an indicator. A CSV with different districts or extra measures is analysed without
touching the code.

**Severity is relative, never absolute.** No magic numbers like `if change > 50`.
Each finding carries a ratio of how many multiples of *your* active threshold it
represents, and that ratio is banded. Move the trend slider from 10% to 20% and
everything re-bands without a code change.

**No LLM anywhere.** Templated sentences only, as the brief allows.

## Project layout

```
ingest.py         CSV loading, cleaning, schema discovery, validation report
trends.py         Month-over-month change per district
outliers.py       Within-month outlier detection (IQR and Z-score)
correlations.py   Pearson matrix, flagged pairs, per-district attribution
insights.py       Sentence templates, severity banding, output assembly
charts.py         matplotlib figures (bar, line, heatmap)
app.py            Streamlit UI — the only module that does IO
verify.py         93 assertions against the reference figures and the sample CSVs
```

Each analysis module is plain functions taking a DataFrame plus thresholds and
returning findings. No globals, no file reads inside functions. `load_dataset()` in
`ingest.py` is the single exception and is the only side effect in the codebase.

## Setup

Requires Python 3.12.

### With uv (recommended)

```bash
uv venv --python 3.12
uv sync
uv run streamlit run app.py
```

### Without uv, using requirements.txt

```bash
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Both paths install identical versions: pandas 3.0.6, numpy 2.5.3,
streamlit 1.65.0, matplotlib 3.11.2.

## Running it

Start the UI:

```bash
uv run streamlit run app.py
```

Then open the printed URL. Upload a CSV with the widget, or leave it empty to use the
bundled `data.csv`.

Each module also runs standalone from the terminal, which is the fastest way to check
a change:

```bash
uv run python ingest.py       data.csv              # load report and detected schema
uv run python trends.py       data.csv 10           # trends at a 10% threshold
uv run python outliers.py     data.csv IQR          # outliers, method IQR or Z-score
uv run python correlations.py data.csv 0.70         # matrix and flagged pairs
uv run python insights.py     data.csv              # full insight table with severities

# Any bundled CSV works, including the malformed one:
uv run python insights.py sample_lab_data.csv
uv run python ingest.py    messy_sample_data.csv
```

Run the checks:

```bash
uv run python verify.py
```

## Using your own data

One row per entity per month, plus at least one numeric measure:

```csv
month,district,anc_coverage,institutional_delivery,immunization,high_risk_cases
2026-07,Ahmedabad,85,91,93,10
2026-08,Ahmedabad,69,90,92,13
```

The engine tolerates more than the brief requires. It strips whitespace from headers
and values, parses `2026-07`, `2026-07-01`, `2026/07` and full timestamps through
`pd.to_datetime(format="mixed")`, drops rows with unparseable dates and reports them,
and infers the entity and period columns from name hints with a structural fallback.

### Bundled datasets

Four CSVs ship with the repo. All are committed, and the UI can load any of them
through the upload widget.

| File | Purpose | What it proves |
|---|---|---|
| `data.csv` | The assignment's sample: 6 districts × 2 months, 4 indicators | Baseline, and every reference figure in `verify.py` |
| `sample_lab_data.csv` | Different entity column (`facility`), 3 renamed indicators, ISO dates | Generality. 16 insights, zero code changes |
| `messy_sample_data.csv` | Spaces in headers and values, blank cells, an unparseable date, a trailing comma | Cleaning: 10 raw rows become 9, with every defect reported |
| `outputs/correlation_matrix.csv` | Pearson matrix from the sample | The section 4.2 correlation deliverable |

`sample_lab_data.csv` is the generality proof: a different entity column, different
indicator names, and full ISO dates instead of `YYYY-MM`, analysed by the same source
with no edits.

## The four parameters

All on sliders, all live:

| Parameter | Default | Meaning |
|---|---|---|
| Trend threshold | 10% | Month-over-month change needed to flag a trend |
| Outlier threshold | 3.0 | IQR multiplier, or \|z\| when the method is Z-score |
| Outlier method | IQR | `IQR` or `Z-score` |
| Correlation threshold | 0.70 | Absolute Pearson r at which a pair is flagged |

Plus two severity band multipliers, also sliders. Severity is `deviation ÷ threshold`,
banded at Low below 1.0x, Medium 1.0–1.5x, High at or above 1.5x. Both multipliers are
user-configurable, so the whole ladder moves with the sliders.

## Sample output

```
INS-0001  trend        high_risk_cases  Mehsana     2026-08  28.0  prev 11.0  +154.5  High
INS-0002  trend        anc_coverage     Mehsana     2026-08  42.0  prev 84.0  -50.0   High
INS-0004  outlier      high_risk_cases  Mehsana     2026-08  28.0  prev 14.7  +90.9    High
INS-0008  correlation  anc_coverage:high_risk_cases  Mehsana  -0.933         Medium

"Mehsana's anc_coverage fell by 50.0% between 2026-07 and 2026-08 (84 to 42),
clearing the 10% change threshold at 5.00x its own previous month. Severity: High."

"Mehsana's anc_coverage of 42 in 2026-08 sits below its 6 peer districts in the same
month, which average 74.0, a 1.24x IQR (linear) deviation (fences 55.4 to 98.3).
Severity: Low."
```

A full run is in [`outputs/`](outputs/): `insights.csv`, `insights.json` and
`correlation_matrix.csv`.

## Caveats, and why they matter

**The sample is too small for the statistics it asks for.** Two months across six
districts is 12 rows. The assignment itself recommends at least 3 months per district
for trend work and 10 districts for a stable correlation matrix. This dataset sits
under both, so:

- Trends are computed, but each rests on a single month-over-month pair. There is no
  way to distinguish a real trend from noise.
- **The `institutional_delivery` / `immunization` correlation at r=+0.98 is almost
  certainly an artefact of two months of data**, not a dependency between the two
  services. Two points per district that happen to move together will correlate near
  1.0 regardless of any real relationship.
- A Z-score threshold of 3.0 is **unreachable at this sample size**. With n=6 the
  largest possible |z| is (n−1)/√n = 2.04, so no amount of extremity can trip a 3.0
  threshold. IQR is the default for this reason, since its fences come from observed
  spread rather than a parametric standard deviation.

**Two figures in the assignment PDF do not match the data.** Both are recorded here
for the marker rather than coded around:

- The PDF states Mehsana's 42 is "3.1σ below the state mean (76)". The actual August
  mean is **74.0**, and the Z-score is **−1.86**, not −3.1.
- Section 4.1 gives that outlier `prev_value = 76` and `change_pct = −44.7`. The
  value 76 matches no summary of this dataset — not the August mean (74.0), the
  all-row mean (78.3), or the August median (80.5).

No code matches these numbers, so neither affects the output.

**Correlation is not causation.** Both measures come from the same reporting process,
so shared collection bias can produce a strong r with no underlying relationship.
Every correlation sentence says so.

**A cell can be both a trend and an outlier.** Mehsana's August coverage of 42 is two
separate findings and is reported as two rows, since "fell 50% from July" and "far
below its peers" are different claims.

## Deliverables checklist

| Requirement | Where |
|---|---|
| CSV loads, missing-value report printed | `ingest.py`, UI section 1 |
| Filters for district, month, indicator | `app.py`, all live |
| Trend detection, configurable threshold | `trends.py` |
| Outlier detection, IQR or Z-score | `outliers.py` |
| Pearson matrix, pairs flagged | `correlations.py` |
| Insights with all required fields | `insights.py` |
| Severity Low / Medium / High, data-derived | `insights.SeverityBands` |
| UI with bar, line and heatmap charts | `charts.py`, `app.py` |
| File upload, no path edit needed | `app.py` |
| Second dataset proving generality | `sample_lab_data.csv` |
| Malformed input handled and reported | `messy_sample_data.csv` |

`type` is one of `trend`, `outlier`, `correlation`, `threshold_breach`. The first
three are emitted; `threshold_breach` is defined in the enum as the brief lists it but
has no rule generating it, since the brief defines no threshold to breach.

The CSV header follows section 4.1 (`insight_id, type, indicator, entity, period,
value, prev_value, change_pct, severity, explanation`) and carries `metric` and
`change` as aliases, because Part E names those same two fields differently.