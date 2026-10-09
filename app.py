from __future__ import annotations
import json
from io import StringIO
from pathlib import Path
import pandas as pd
import streamlit as st
import charts
import correlations
import ingest
import insights
import outliers
import trends
DEFAULT_DATASET = Path(__file__).with_name("data.csv")
@st.cache_data(show_spinner="Reading dataset")
def load_frame(upload_bytes: bytes | None, source_label: str) -> tuple:
    if upload_bytes is not None:
        raw = pd.read_csv(StringIO(upload_bytes.decode("utf-8", errors="replace")))
        source = f"upload: {source_label}"
    else:
        raw = pd.read_csv(DEFAULT_DATASET)
        source = f"bundled: {DEFAULT_DATASET.name}"
    frame = ingest.normalise_columns(raw)
    cleaned, schema, dropped = ingest.build_schema(frame)
    cleaned, schema, unparsed = ingest.add_time_axis(cleaned, schema)
    report = ingest.validate(cleaned, schema)
    from dataclasses import replace as _replace
    report = _replace(report, dropped_rows=dropped + len(unparsed), unparsed_periods=unparsed)
    return cleaned, schema, report, source
def main() -> None:
    st.set_page_config(page_title="Automated Insight Generation", layout="wide")
    st.title("Automated Insight Generation")
    st.caption(
        "Trends compare a district to its own past. Outliers compare districts "
        "within one month. Every threshold below is configurable, and every "
        "sentence is generated from the data."
    )
    st.header("1. Data")
    uploaded = st.file_uploader("Upload a CSV (same shape as the sample)", type=["csv"])
    upload_bytes: bytes | None = None
    if uploaded is not None:
        upload_bytes = uploaded.getvalue()
    try:
        frame, schema, report, source = load_frame(upload_bytes, uploaded.name if uploaded else "")
    except Exception as error:
        st.error(f"Could not read this file: {error}")
        st.stop()
    st.success(f"Loaded {report.row_count} rows from {source}")
    columns = st.columns([2, 1])
    with columns[0]:
        st.dataframe(frame.head(10), width="stretch", height=460)
        with st.expander("Load report: head, dtypes, missing values"):
            st.code(ingest.describe(frame, schema, report))
    with columns[1]:
        st.markdown(f"**Entity column:** `{schema.entity_column}`")
        st.markdown(f"**Period column:** `{schema.period_column}`")
        st.markdown(f"**Periods:** {', '.join(schema.periods)}")
        st.markdown(f"**Indicators ({len(schema.indicators)}):**")
        st.code("\n".join(schema.indicators))
        if report.dropped_rows:
            st.warning(f"{report.dropped_rows} row(s) dropped during cleaning.")
        for warning in report.warnings:
            st.warning(warning, icon="⚠️")
    st.header("2. Parameters")
    st.caption("All four parameters from the brief, plus the severity band multipliers.")
    first, second, third, fourth = st.columns(4)
    with first:
        trend_threshold = st.slider(
            "Trend threshold (%)", 1.0, 50.0, 10.0, 0.5,
            help="Month-over-month change, within a district, needed to flag a trend.",
        )
    with second:
        outlier_threshold = st.slider(
            "Outlier threshold", 1.0, 6.0, 3.0, 0.25,
            help="IQR multiplier or |z|, depending on the method below.",
        )
    with third:
        outlier_method = st.selectbox(
            "Outlier method", [outliers.IQR, outliers.ZSCORE],
            help="IQR is more robust with few peers; Z-score needs roughly 10+ districts.",
        )
    with fourth:
        corr_threshold = st.slider(
            "Correlation threshold", 0.0, 1.0, 0.70, 0.05,
            help="Absolute Pearson r at which a pair is flagged.",
        )
    band_first, band_second = st.columns(2)
    with band_first:
        medium_at = st.slider(
            "Medium severity at", 0.1, 3.0, 1.0, 0.1,
            help="Deviation multiple of the active threshold at or above which severity is Medium.",
        )
    with band_second:
        high_at = st.slider(
            "High severity at", 0.1, 5.0, 1.5, 0.1,
            help="Deviation multiple of the active threshold at or above which severity is High.",
        )
    if high_at < medium_at:
        st.info("High cut-off is below Medium; showing everything as Low or Medium.")
    bands = insights.SeverityBands(medium_at=medium_at, high_at=max(high_at, medium_at))
    entity_filter = st.multiselect(
        "Districts", sorted(frame[schema.entity_column].unique()),
        default=sorted(frame[schema.entity_column].unique()),
    )
    period_filter = st.multiselect(
        "Months", list(schema.periods), default=list(schema.periods),
    )
    indicator_filter = st.multiselect(
        "Indicators", list(schema.indicators), default=list(schema.indicators),
    )
    entities = schema.entity_column
    periods = set(period_filter) or set(schema.periods)
    districts = entity_filter or sorted(frame[entities].unique())
    indicators = indicator_filter or list(schema.indicators)
    visible = frame.loc[
        frame[entities].isin(districts) & frame["period"].isin(periods)
    ]
    if indicators:
        visible = visible[[entities, "period", "_month", *indicators]]
    st.caption(
        f"Analysing {len(visible)} of {report.row_count} rows, "
        f"{len(districts)} districts, {len(periods)} months, {len(indicators)} indicators."
    )
    if visible.empty:
        st.warning("Nothing selected. Widen the filters above.")
        st.stop()
    selected_months = set(
        frame.loc[frame["period"].isin(periods), "_month"].tolist()
    )
    trend_source = frame.loc[
        frame[entities].isin(districts) & frame["_month"].isin(selected_months)
    ]
    if len(periods) < 2:
        trend_source = frame.loc[frame[entities].isin(districts)]
        st.caption(
            "Trends below use every month for the selected districts, since "
            "fewer than two selected months leaves no period to compare against."
        )
    found_trends = trends.find_trends(
        trend_source, entities, indicators, trend_threshold
    )
    found_outliers = outliers.detect_outliers(
        visible, entities, indicators, outlier_threshold, outlier_method
    )
    matrix, flagged_pairs = correlations.analyse(
        visible, entities, indicators, corr_threshold
    )
    built = insights.build_insights(found_trends, found_outliers, flagged_pairs, bands)
    st.header("3. Insights")
    if not built:
        st.info(
            f"No insights at the current settings ({trend_threshold:g}% trend, "
            f"{outlier_threshold:g} {outlier_method}, r >= {corr_threshold:g}). "
            "Lower a threshold or widen the filters."
        )
    else:
        table = insights.insights_frame(built)
        total, _high, _medium, _low = st.columns([1, 1, 1, 1])
        with total:
            st.metric("Insights", len(built))
        severity_table, type_table = st.columns(2)
        with severity_table:
            st.dataframe(
                insights.severity_counts(built),
                width="stretch",
                hide_index=True,
            height=38 * (max(len(insights.severity_counts(built)), len(insights.counts_by_type(built))) + 2),
            )
        with type_table:
            st.dataframe(
                insights.counts_by_type(built),
                width="stretch",
                hide_index=True,
                height=38 * (max(len(insights.severity_counts(built)), len(insights.counts_by_type(built))) + 2),
            )
        st.caption(
            "types: trend, outlier, correlation, threshold_breach"
        )
        st.dataframe(
            table[insights.INSIGHT_COLUMNS],
            width="stretch",
            hide_index=True,
            height=460,
            column_config={
                "insight_id": st.column_config.TextColumn(width="small", help="Auto-numbered"),
                "type": st.column_config.TextColumn(width="small"),
                "indicator": st.column_config.TextColumn(width="medium"),
                "entity": st.column_config.TextColumn(width="small"),
                "period": st.column_config.TextColumn(width="small"),
                "value": st.column_config.NumberColumn(format="%.1f"),
                "prev_value": st.column_config.NumberColumn(format="%.1f"),
                "change_pct": st.column_config.NumberColumn(format="%.1f"),
                "severity": st.column_config.TextColumn(width="small"),
                "explanation": st.column_config.TextColumn(width="large", help="Generated from the data"),
            },
        )
        type_choice = st.multiselect(
            "Insight types shown", table["type"].unique().tolist(),
            default=table["type"].unique().tolist(),
        )
        filtered = table.loc[table["type"].isin(type_choice or table["type"].unique())]
        st.download_button(
            "Download insights CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="insights.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download insights JSON",
            json.dumps([insight.as_dict() for insight in built], indent=2, default=str),
            file_name="insights.json",
            mime="application/json",
        )
        st.download_button(
            "Download correlation matrix CSV",
            matrix.round(4).to_csv().encode("utf-8"),
            file_name="correlation_matrix.csv",
            mime="text/csv",
        )
    st.header("4. Visualisation")
    tab_bar, tab_line, tab_heat = st.tabs(
        ["Severity counts", "Trend by district", "Correlation heatmap"]
    )
    with tab_bar:
        st.pyplot(charts.severity_bar(insights.severity_counts(built)))
    with tab_line:
        line_indicator = st.selectbox("Indicator", indicators)
        st.pyplot(charts.trend_line(visible, entities, line_indicator, entities=districts))
        st.caption("One line per district, compared with itself month to month.")
    with tab_heat:
        st.pyplot(charts.correlation_heatmap(matrix, correlations.flag_pairs(matrix, corr_threshold), corr_threshold))
        st.caption(
            "Pooled across all selected districts and months, so each cell rests on "
            f"{len(visible)} observations."
        )
        st.warning(
            "With this few districts and months, these correlations are unstable and "
            "should be read as descriptive only. Both measures may also share reporting "
            "bias, which inflates r without any real relationship."
        )
    st.header("5. Caveats")
    st.markdown(
        f"- **{report.entity_count} districts x {report.period_count} months.** "
        "The assignment recommends at least 3 months per district for trend work and "
        "10 districts for a stable correlation matrix. Below that, treat correlations "
        "as illustrative.\n"
        "- **Correlation is not causation.** Two indicators measured by the same "
        "reporting process can correlate for that reason alone.\n"
        "- **The sample's `institutional_delivery` / `immunization` pair at r=+0.98 is "
        "almost certainly an artefact** of having only two months of data, not a real "
        "dependency between the two services.\n"
        "- **Outliers are judged within a month, never across the whole dataset**, so a "
        "district that is consistently low is not flagged while one unusual month is.\n"
        "- **A trend and an outlier on the same cell are two separate insights** and are "
        "reported as such."
    )
if __name__ == "__main__":
    main()
