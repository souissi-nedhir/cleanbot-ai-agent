"""Streamlit UI for the CleanBot data cleaning workflow."""

import json
import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure model responses containing Unicode are safe on Windows terminals.
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )

from cleaner_executor import apply_approved_plan, validate_cleaning
from cleaner_planner import suggest_cleaning_options
from issue_detector import detect_issues
from profiler import profile_dataframe


st.set_page_config(page_title="CleanBot", page_icon="🧹", layout="wide")

st.title("CleanBot - Data Cleaning Agent")
st.subheader("Upload a messy CSV. Get a clean file and a full audit log.")


def reset_workflow() -> None:
    """Clear all cached workflow data when a different file is uploaded."""
    for key in (
        "df",
        "profile",
        "issues",
        "cleaning_plans",
        "approved_plan",
        "cleaned_df",
        "change_log",
        "validation_result",
        "choice_values",
    ):
        st.session_state.pop(key, None)


uploaded_file = st.file_uploader(
    "Upload your dataset",
    type=["csv", "xlsx"],
    help="Supported formats: CSV and Excel (.xlsx).",
)

if uploaded_file is None:
    st.info(
        "Welcome to CleanBot. Upload a CSV or Excel file to profile it, "
        "review detected issues, and approve cleaning operations."
    )
    st.stop()

if st.session_state.get("uploaded_file_name") != uploaded_file.name:
    reset_workflow()
    st.session_state["uploaded_file_name"] = uploaded_file.name

try:
    if "df" not in st.session_state:
        if uploaded_file.name.lower().endswith(".xlsx"):
            dataframe = pd.read_excel(uploaded_file)
        else:
            dataframe = pd.read_csv(uploaded_file)
        st.session_state["df"] = dataframe
except Exception as exc:
    st.error(f"Could not load the uploaded file: {exc}")
    st.stop()

original_df = st.session_state["df"]

st.header("Step 2 - Profile")
if "profile" not in st.session_state:
    try:
        st.session_state["profile"] = profile_dataframe(original_df)
    except Exception as exc:
        st.error(f"Profiling failed: {exc}")
        st.stop()
profile = st.session_state["profile"]

with st.expander("View dataset profile", expanded=True):
    st.write("**Shape:**", profile["shape"])
    st.write("**Columns:**", profile["columns"])
    st.write("**Duplicates:**", profile["duplicates"])
    st.write("**Constant columns:**", profile["constant_columns"])
    st.write("**High-missing columns:**", profile["high_missing_columns"])
    st.write("**Mixed-type columns:**", profile["mixed_type_columns"])

    st.write("**Data types**")
    st.dataframe(
        pd.DataFrame(
            list(profile["dtypes"].items()), columns=["Column", "Data type"]
        ),
        width="stretch",
        hide_index=True,
    )

    st.write("**Missing values**")
    missing_table = pd.DataFrame(profile["missing"]).T.reset_index()
    missing_table.columns = ["Column", "Count", "Percent"]
    st.dataframe(missing_table, width="stretch", hide_index=True)

    if profile["numeric_stats"]:
        st.write("**Numeric statistics**")
        numeric_table = pd.DataFrame(profile["numeric_stats"]).T.reset_index()
        numeric_table = numeric_table.rename(columns={"index": "Column"})
        st.dataframe(numeric_table, width="stretch", hide_index=True)

    if profile["outliers"]:
        st.write("**Outliers**")
        outlier_table = pd.DataFrame(
            list(profile["outliers"].items()), columns=["Column", "Count"]
        )
        st.dataframe(outlier_table, width="stretch", hide_index=True)

st.header("Step 3 - Detect Issues")
if "issues" not in st.session_state:
    try:
        with st.spinner("Analyzing the profile for data quality issues..."):
            st.session_state["issues"] = detect_issues(profile)
    except Exception as exc:
        if "429" in str(exc) or "rate limit" in str(exc).lower():
            st.warning(
                "CleanBot is currently resting. The AI API limit has been "
                "reached. Please try again in a few minutes or switch to a "
                "different model."
            )
        else:
            st.error(f"Issue detection failed: {exc}")
        st.stop()
issues = st.session_state["issues"]

if issues:
    issue_table = pd.DataFrame(
        [
            {
                "id": issue.get("id"),
                "issue_type": issue.get("issue_type"),
                "column": issue.get("column"),
                "severity": issue.get("severity"),
                "description": issue.get("description"),
            }
            for issue in issues
        ]
    )

    def severity_style(value: object) -> str:
        colors = {"High": "#ffcccc", "Medium": "#ffe0b2", "Low": "#fff3b0"}
        return f"background-color: {colors.get(value, '')}"

    st.dataframe(
        issue_table.style.map(severity_style, subset=["severity"]),
        width="stretch",
        hide_index=True,
    )
else:
    st.success("No data quality issues were detected.")

st.header("Step 4 - Review Cleaning Options")
if "cleaning_plans" not in st.session_state:
    try:
        with st.spinner("Preparing cleaning options for review..."):
            st.session_state["cleaning_plans"] = suggest_cleaning_options(
                issues, profile
            )
    except Exception as exc:
        if "429" in str(exc) or "rate limit" in str(exc).lower():
            st.warning(
                "CleanBot is currently resting. The AI API limit has been "
                "reached. Please try again in a few minutes or switch to a "
                "different model."
            )
        else:
            st.error(f"Could not prepare cleaning options: {exc}")
        st.stop()
plans = st.session_state["cleaning_plans"]

if not plans:
    st.info("There are no cleaning options to review.")

choice_values = st.session_state.setdefault("choice_values", {})
for plan in plans:
    issue_id = plan.get("issue_id")
    options = plan.get("options", [])
    option_names = [option.get("option_name", "") for option in options]
    manual_option = "Keep as is (Do nothing)"
    option_names = list(
        dict.fromkeys(
            [manual_option]
            + [option_name for option_name in option_names if option_name]
        )
    )

    issue = next((item for item in issues if item.get("id") == issue_id), {})
    with st.container(border=True):
        st.markdown(
            f"**Issue {issue_id}: {issue.get('description', plan.get('issue_type', ''))}**"
        )
        recommended = plan.get("recommended_option")
        default_index = (
            option_names.index(recommended) if recommended in option_names else 0
        )
        selected = st.radio(
            "Choose one operation",
            option_names,
            index=default_index,
            key=f"choice_{issue_id}",
        )
        choice_values[issue_id] = selected
        for option in options:
            st.caption(
                f"**{option.get('option_name', '')}:** "
                f"{option.get('trade_off', '')}"
            )
        st.caption(f"Recommendation: {recommended or 'None'}")
        st.caption(plan.get("reason_for_recommendation", ""))

st.header("Step 5 - Apply Cleaning")
if st.button("Apply Cleaning Plan", type="primary", disabled=not plans):
    approved_plan = []
    for plan in plans:
        issue_id = plan.get("issue_id")
        chosen_option = choice_values.get(
            issue_id, plan.get("recommended_option")
        )
        if chosen_option == "Keep as is (Do nothing)":
            continue
        approved_plan.append(
            {
                "issue_id": issue_id,
                "issue_type": plan.get("issue_type"),
                "column": plan.get("column"),
                "recommended_option": plan.get("recommended_option"),
                "chosen_option": chosen_option,
            }
        )

    try:
        with st.spinner("Applying approved cleaning operations..."):
            cleaned_df, change_log = apply_approved_plan(
                original_df, approved_plan
            )
            validation = validate_cleaning(
                original_df, cleaned_df, change_log
            )
        st.session_state["cleaned_df"] = cleaned_df
        st.session_state["change_log"] = change_log
        st.session_state["approved_plan"] = approved_plan
        st.session_state["validation_result"] = validation
        st.success("Approved cleaning operations completed.")
    except Exception as exc:
        st.error(f"Cleaning failed: {exc}")

if "validation_result" in st.session_state:
    st.header("Step 6 - Results")
    validation = st.session_state["validation_result"]
    if validation["expected_changes_only"]:
        st.success("Validation passed: no unexpected changes were detected.")
    else:
        st.warning("Validation completed with warnings.")
    st.json(validation)

    cleaned_df = st.session_state["cleaned_df"]
    comparison = pd.DataFrame(
        [
            {
                "Metric": "Rows",
                "Before": len(original_df),
                "After": len(cleaned_df),
            },
            {
                "Metric": "Columns",
                "Before": len(original_df.columns),
                "After": len(cleaned_df.columns),
            },
            {
                "Metric": "Missing values",
                "Before": int(original_df.isna().sum().sum()),
                "After": int(cleaned_df.isna().sum().sum()),
            },
        ]
    )
    st.write("**Before / after comparison**")
    st.dataframe(comparison, width="stretch", hide_index=True)

    st.write("**Change log**")
    st.dataframe(
        pd.DataFrame(st.session_state["change_log"]),
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        "Download cleaned CSV",
        data=cleaned_df.to_csv(index=False).encode("utf-8"),
        file_name=(
            f"{Path(st.session_state['uploaded_file_name']).stem}_cleaned.csv"
        ),
        mime="text/csv",
    )
    st.download_button(
        "Download change log (JSON)",
        data=json.dumps(
            st.session_state["change_log"], indent=2, default=str
        ).encode("utf-8"),
        file_name=(
            f"{Path(st.session_state['uploaded_file_name']).stem}"
            "_change_log.json"
        ),
        mime="application/json",
    )
