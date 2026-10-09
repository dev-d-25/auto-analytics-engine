# Assignment 4: Automated Insight Generation — working brief

Source PDF: `04-automated-insight-generation  - AI_ML.pdf` (5 pages, produced by jsPDF, no text
layer — pages were extracted as images and read visually).

## 1. Problem statement

Build an **auto-analytics engine** that ingests a small district-level healthcare performance CSV
and automatically identifies trends, outliers, and correlations, then produces human-readable
insights.

The engine has to be general-purpose. No hardcoded district-specific narratives.

Example of the output style:

> "ANC Coverage in Ahmedabad dropped by 19% compared to the previous month."

## 2. Dataset

### 2.1 Sample data (given inline)

```csv
month,district,anc_coverage,institutional_delivery,immunization,high_risk_cases
2026-07,Ahmedabad,85,91,93,10
2026-08,Ahmedabad,69,90,92,13
2026-07,Surat,81,87,91,13
2026-08,Surat,83,89,92,12
2026-07,Vadodara,90,93,96,7
2026-08,Vadodara,91,94,97,6
2026-07,Rajkot,79,85,89,15
2026-08,Rajkot,80,86,90,14
2026-07,Mehsana,84,89,92,11
2026-08,Mehsana,42,88,91,28
2026-07,Bhavnagar,77,82,87,17
2026-08,Bhavnagar,79,84,89,15
```

Patterns the engine is expected to discover:

- Ahmedabad ANC: 85 → 69 (−18.8%), a clear trend.
- Mehsana ANC: 42, an extreme outlier against a state mean near 76.
- Mehsana high_risk_cases: 11 → 28, a correlated anomaly (coverage collapse alongside a risk-case
  spike).

### 2.2 Schema

| Column | Example | Notes |
|---|---|---|
| `month` | `2026-07-01` | Monthly |
| `district` | `"Ahmedabad"` | string |
| `anc_coverage` | `85` | % |
| `institutional_delivery` | `91` | % |
| `immunization` | `93` | % |
| `high_risk_cases` | `10` | raw count |

Granularity is 1 row per `(district, month)`. Recommended minimums for meaningful results: 3 or more
months per district for trend detection, 10 or more districts for correlation stability. The
sample data is 2 months × 6 districts, which sits under both.

## 3. Tasks

### Part A — data loading and validation

- Load the CSV with pandas.
- Print `head()`, `info()`, and a missing-value count per column.
- Provide UI filters for `district`, `month`, and `indicator` using any lightweight Python UI
  framework.

### Part B — trend detection

- For each `(district, indicator)` pair compute
  `pct_change = (current - previous) / previous * 100`.
- Flag as `is_significant` when `abs(pct_change) >= threshold`. Default threshold 10%, configurable
  in the UI.
- Output the list of flagged trends.

### Part C — outlier detection

- For each indicator apply the IQR rule: outlier if `value > Q3 + 1.5 * IQR` or
  `value < Q1 - 1.5 * IQR`.
- Alternatively a Z-score with threshold 3, configurable.
- List every outlier with `district`, `indicator`, `month`, `value`.

### Part D — correlation detection

- Compute a Pearson correlation matrix across the numeric indicators.
- Flag pairs with `abs(r) >= 0.70` (configurable).
- The assignment explicitly asks you to state the fragility of correlation given only 2 months × 6
  districts.

### Part E — automated insight generation

- Generate insights dynamically. Templated sentences are acceptable; numeric values must come from
  the data.
- Every insight row needs: `insight_id` (auto-numbered), `type` in
  `{trend, outlier, correlation, threshold_breach}`, `indicator`, `entity` (district), `period`
  (month), `metric` and `change` (numeric), `severity` in `{Low, Medium, High}`, and an
  auto-generated `explanation` sentence.

### Part F — UI and visualization

- Any lightweight Python UI framework, no separate backend API.
- Show: insight list, severity counts (bar chart), correlation heatmap, per-district line chart.
- Filters must update live.

## 4. Output specification

### 4.1 Insights CSV

Header, from the PDF (some trailing explanation text is cut off in the source image):

```csv
insight_id,type,indicator,entity,period,value,prev_value,change_pct,severity,explanation
INS-0001,trend,anc_coverage,Ahmedabad,2026-08,69,85,-18.8,High,"Ahmedabad ANC coverage..."
INS-0002,outlier,anc_coverage,Mehsana,2026-08,42,76,-44.7,High,"Mehsana's ANC coverage..."
INS-0003,correlation,anc_coverage:high_risk_cases,Mehsana,2026-07..08,r=-0.98,n/a,...
```

Note the mismatch worth planning around: Part E describes fields as `metric` and `change`, while
the sample CSV header uses `value`, `prev_value`, `change_pct`. Emitting the wider sample header and
carrying both names is the safe move.

### 4.2 Correlation matrix

Standard `pandas.DataFrame.corr()` output, serialized as CSV.

## 5. Functional requirements

1. CSV loads; missing-value report printed.
2. Filters work in the UI for district, month, indicator.
3. Trend detection with configurable threshold (default ±10%).
4. Outlier detection via IQR or Z-score (configurable).
5. Pearson correlation matrix emitted; pairs with `abs(r) >= 0.70` flagged.
6. Insights emitted with all required fields.
7. Severity levels: Low / Medium / High.
8. UI displays insights, severity counts, and at least one visualization.

## 6. Technical constraints

- Backend: Python only.
- Frontend: any lightweight Python UI framework, no separate backend API.
- Libraries: Python data-science stack of your choice (pandas, numpy, scipy and similar).
- All thresholds configurable through UI sliders.

## 7. Deliverables

- Source code (`.py` and/or `.ipynb`)
- `requirements.txt`
- Dataset CSV
- `README.md` with run instructions
- Screenshots or a sample insights JSON

## 8. Example output

```
Ahmedabad — anc_coverage — 2026-08 — 69 (prev 85), Δ −18.8% — Severity: HIGH
"ANC Coverage in Ahmedabad dropped by 18.8% compared to the previous month,
exceeding the 10% significant-change threshold."

Mehsana — anc_coverage — 2026-08 — 42 — Severity: HIGH
"Mehsana's ANC coverage of 42% is 3.1σ below the state mean (76), flagging for review."
```

## 9. Evaluation rubric (10 marks)

| # | Criterion | Marks |
|---|---|---|
| 1 | Data loading + validation + filters in UI | 1.5 |
| 2 | Trend detection (configurable threshold) | 2.0 |
| 3 | Outlier detection (IQR or Z-score, configurable) | 2.0 |
| 4 | Correlation detection with threshold flagging | 1.5 |
| 5 | Insights: dynamic, structured fields, severity Low/Medium/High | 2.0 |
| 6 | UI + visualizations (line, bar, heatmap) | 1.0 |
| **Total** | | **10** |

### 9.1 Pass criteria

- 6/10 or higher overall, **and**
- At least 1 mark on Criterion 5, since insight generation is the core deliverable.

### 9.2 Scoring scale

0 = not done, 0.5 = started, 1.0 = partial, 1.5 = mostly done, 2.0 = complete.

## 10. Notes for candidates (the traps)

- **No hardcoded narratives.** Writing `"ANC coverage in Ahmedabad dropped"` with the numbers baked
  in is an automatic fail. Templates are fine; the numbers have to be data-driven.
- **The sample is thin.** 2 months × 6 districts = 12 rows. Most Pearson correlations will be
  unstable. Say so in the README and show the matrix as it actually is.
- **Trend and outlier are different insight types.** Mehsana's 42 can be both, but don't collapse
  them into one bucket.
- **Severity must come from data.** A magic number like `if change > 50: HIGH` is called out by name
  as unacceptable. The instruction closes with "Use the configurable threshold" — severity bands are
  relative to the user's own threshold setting, never absolute numbers baked into the code. See the
  severity design note below for how that resolves the three levels.

## Severity design note

Section 10's closing line is "Use the configurable threshold." Taken literally, severity bands are
relative to whatever the user set, never absolute numbers in the source.

Approach: express the deviation as a **multiple of the active threshold**, then band that ratio.
Band multipliers (defaults 1.0 / 1.5 / 2.0) are themselves sliders, so the whole ladder moves with
the user's setting and nothing is baked in.

| Insight type | Ratio | Input |
|---|---|---|
| trend | `abs(pct_change) / trend_threshold` | configured trend threshold |
| outlier | `abs(z) / z_threshold` | configured Z threshold |
| correlation | `abs(r) / corr_threshold` | configured correlation threshold |

Low below 1.0x, Medium 1.0 to 1.5x, High at or above 1.5x.

Checked against the two worked examples in section 8, with the trend threshold at its 10% default:

- Ahmedabad `anc_coverage`, −18.8% ÷ 10 = 1.88x → High. Section 8 says High.
- Mehsana `anc_coverage`, −50.0% ÷ 10 = 5.0x → High. Section 8 says High.

The 1.5x Medium/High boundary is a design choice that happens to reproduce both examples. It is not
uniquely determined by the statement, which is exactly why the multipliers stay on sliders.

## Automation target: zero code changes on a new CSV

Our standing requirement, above what the PDF strictly demands. The goal is that once built, dropping
in a different healthcare CSV with the same shape produces correct insights with no edits to the
source.

### What the statement does and does not say

It never uses the words "no code changes" or "any dataset." The closest mandate is section 1:
*"The engine must be general-purpose — no hardcoded district-specific narratives,"* reinforced in
section 10 by *"Templated copy is OK; numeric values must come from the data."*

Read that scope carefully. It governs **narratives**, not schema, columns, or file paths. Meanwhile
section 2.2 is titled "**Required** schema" and pins five exact column names, which pulls the other
way. So full schema-independence is implied rather than required.

Treating it as optional is the riskier read. Section 10 is written from a grader's perspective as a
list of ways marks get withheld, and a grader swapping in a different CSV to see whether the code
survives is a natural test of "general-purpose."

### The five things that break generality

1. **Indicator names.** Never reference `anc_coverage` in code. Detect numeric columns from the
   frame, exclude `month` and `district` by name, treat the remainder as indicators, loop over them.
   Any measure the new CSV brings along gets analysed for free.
2. **District names.** Group by whatever the column holds. Never an allowlist or a `.str.contains()`
   on a known city.
3. **Correlation insights.** The sample's `INS-0003` pins the correlation to `Mehsana`, which is how
   the PDF telegraphs the Mehsana ANC / high-risk-cases coupling. On the sample data the global
   `anc_coverage` / `high_risk_cases` Pearson correlation is **r = −0.93**, so a plain global matrix
   does surface the pair. Deriving the *per-district attribution* generically is the
   hardest piece: compute the global matrix, flag pairs over threshold, then test which districts
   actually drive each flagged pair, so one global number becomes per-district insights without
   special-casing anyone.
4. **Severity.** Derived from configured thresholds and observed deviation, never a literal.
5. **Dates.** The sample uses `2026-07` while the schema table shows `2026-07-01`. Parse flexibly
   rather than assuming a day component.

Additionally, expose a file-upload widget in the UI. Part A only says "load the CSV with pandas,"
but an uploader covers both a grader editing a path constant and a grader dropping in a new file,
at no cost.

### Practical bar

A new CSV with the same schema, handed to the same running engine, must yield correct insights with
the source untouched. Build a second dataset during testing to prove it, ideally with different
districts and at least one differently named indicator.

## Open questions for the grader or for us

1. **The two worked examples in section 8 do not reconcile with the sample data.** Worth raising
   with the grader before submission, since both figures are cited as expected output.
   - Section 8 says Mehsana's 42 is "3.1σ below the state mean (76)". Recomputing the Z-score of 42
     against the other five districts' 2026-08 values gives **−1.86σ**, not 3.1σ. With only n = 6 the
     spread is wide enough that 3.1σ is unreachable for this value.
   - Section 4.1 gives Mehsana's outlier row `prev_value = 76` and `change_pct = −44.7`. The actual
     2026-08 mean of `anc_coverage` across all six districts is **74.0**, not 76. The value 76 does
     not correspond to the month mean, the all-rows mean (78.3), or the median of 2026-08 (80.5).
     Note also that Mehsana's own previous-month value was 84, which would give −50.0%.
   - Neither discrepancy affects implementation, since no code should be matching these figures.
     Raise them for the record.
2. Is `type = threshold_breach` used anywhere, or is it an unused enum member for students to define
   themselves?
3. Does the correlation insight row need a fixed `entity`/`period`, or should correlations be emitted
   once globally rather than per district?

## Verified figures from the sample data

Computed directly from the CSV, for checking implementation output against.

| District | anc Δ% | id Δ% | imm Δ% | hr Δ% |
|---|---|---|---|---|
| Ahmedabad | −18.8 | −1.1 | −1.1 | +30.0 |
| Surat | +2.5 | +2.3 | +1.1 | −7.7 |
| Vadodara | +1.1 | +1.1 | +1.0 | −14.3 |
| Rajkot | +1.3 | +1.2 | +1.1 | −6.7 |
| Mehsana | −50.0 | −1.1 | −1.1 | +154.5 |
| Bhavnagar | +2.6 | +2.4 | +2.3 | −11.8 |

At the default 10% trend threshold, five trends fire: Ahmedabad `anc_coverage`, Mehsana
`anc_coverage`, and `high_risk_cases` for Ahmedabad, Bhavnagar, and Mehsana.

Pearson matrix, all 12 rows:

| | anc | id | imm | hr |
|---|---|---|---|---|
| anc | 1.00 | 0.28 | 0.37 | **−0.93** |
| id | 0.28 | 1.00 | **0.98** | −0.56 |
| imm | 0.37 | **0.98** | 1.00 | −0.62 |
| hr | **−0.93** | −0.56 | −0.62 | 1.00 |

At the 0.70 threshold, three pairs flag: `anc`/`hr` (−0.93), `id`/`imm` (+0.98), and `imm`/`hr`
(−0.62 stays under). The `institutional_delivery`/`immunization` pair at 0.98 is also worth flagging
as a likely artefact of only two months of data rather than a real relationship, which is the honesty
caveat section 10 asks for.

Mehsana's August Z-scores against same-month peers: `anc_coverage` −1.86, `high_risk_cases` +1.84.
The two-point co-movement is what the correlation insight should surface.