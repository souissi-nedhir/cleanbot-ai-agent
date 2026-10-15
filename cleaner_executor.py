"""Execute explicitly approved cleaning operations and validate their results."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _total_missing(df: pd.DataFrame) -> int:
    """Return the total number of missing cells in a DataFrame."""
    return int(df.isna().sum().sum())


def _operation_name(plan: dict[str, Any]) -> str:
    """Return the user's chosen option, falling back to the recommendation."""
    chosen_option = plan.get("chosen_option")
    if not chosen_option:
        chosen_option = plan.get("recommended_option")
    if not chosen_option:
        raise ValueError("Approved plan has no chosen or recommended option.")
    return str(chosen_option)


def _iqr_bounds(series: pd.Series) -> tuple[float, float]:
    """Calculate inclusive IQR bounds for a numeric series."""
    values = pd.to_numeric(series, errors="raise").dropna()
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def _apply_operation(
    df: pd.DataFrame, plan: dict[str, Any], option: str
) -> tuple[pd.DataFrame, str]:
    """Apply one approved operation and return its result and notes."""
    issue_type = plan.get("issue_type")
    column = plan.get("column")

    if issue_type == "missing_values":
        if not column or column not in df.columns:
            raise KeyError(f"Missing-value column not found: {column!r}")
        if option == "Drop rows":
            return df.dropna(subset=[column]), f"Dropped rows missing {column}."
        if option == "Impute with median":
            df[column] = df[column].fillna(df[column].median())
            return df, f"Filled missing {column} values with the median."
        if option == "Impute with mean":
            df[column] = df[column].fillna(df[column].mean())
            return df, f"Filled missing {column} values with the mean."
        if option == "Impute with mode":
            modes = df[column].mode(dropna=True)
            if modes.empty:
                raise ValueError(f"Cannot find a mode for column {column!r}.")
            df[column] = df[column].fillna(modes.iloc[0])
            return df, f"Filled missing {column} values with the mode."
        if option == "Impute with constant":
            if "value" not in plan:
                raise ValueError(
                    "Impute with constant requires a 'value' in the approved plan."
                )
            df[column] = df[column].fillna(plan["value"])
            return df, f"Filled missing {column} values with an approved constant."

    elif issue_type in {"duplicates", "duplicate_rows"}:
        if (
            option == "Drop duplicates"
            or option.startswith("Drop duplicates")
            or option == "Drop duplicate rows"
        ):
            return df.drop_duplicates(), "Dropped duplicate rows."

    elif issue_type in {"outliers", "outlier"}:
        if not column or column not in df.columns:
            raise KeyError(f"Outlier column not found: {column!r}")
        numeric_values = pd.to_numeric(df[column], errors="raise")
        median = numeric_values.median()
        if pd.isna(median):
            raise ValueError(f"Cannot detect outliers in empty column {column!r}.")
        outlier_mask = numeric_values.notna() & (
            numeric_values.abs() > abs(median) * 5
        )
        if option == "Remove outliers (IQR)":
            keep = ~outlier_mask
            return df.loc[keep], (
                f"Removed values more than 5 times the median ({median})."
            )
        if option == "Cap outliers (IQR)":
            non_outliers = numeric_values.loc[~outlier_mask].dropna()
            if non_outliers.empty:
                raise ValueError(f"Cannot calculate a cap for {column!r}.")
            percentile_cap = float(numeric_values.dropna().quantile(0.99))
            maximum_non_outlier = float(non_outliers.max())
            cap = min(percentile_cap, maximum_non_outlier)
            df[column] = numeric_values.mask(outlier_mask, cap)
            return df, (
                f"Capped values more than 5 times the median ({median}) "
                f"at {cap}."
            )
        if option == "Cap at 95th percentile":
            non_outliers = numeric_values.loc[~outlier_mask].dropna()
            if non_outliers.empty:
                raise ValueError(f"Cannot calculate a cap for {column!r}.")
            percentile_cap = float(numeric_values.dropna().quantile(0.99))
            cap = min(percentile_cap, float(non_outliers.max()))
            df[column] = numeric_values.mask(outlier_mask, cap)
            return df, f"Capped outliers at the 99th percentile/non-outlier maximum ({cap})."
        if option == "Keep outliers":
            return df, "No action taken; outliers were kept."

    elif issue_type in {
        "mixed_type",
        "mixed_types",
        "mixed_type_column",
        "mixed_type_columns",
        "inconsistent_format",
    }:
        if not column or column not in df.columns:
            raise KeyError(f"Date column not found: {column!r}")
        parsed = pd.to_datetime(
            df[column], dayfirst=True, errors="coerce", format="mixed"
        )
        year_first_mask = df[column].astype("string").str.match(
            r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", na=False
        )
        if year_first_mask.any():
            parsed.loc[year_first_mask] = pd.to_datetime(
                df.loc[year_first_mask, column],
                dayfirst=False,
                errors="coerce",
                format="mixed",
            )
        unparseable_count = int(parsed.isna().sum())
        warning = (
            f" WARNING: dropped {unparseable_count} unparseable date rows."
            if unparseable_count
            else ""
        )
        if option in {
            "Standardize to ISO 8601",
            "Parse with pandas to_datetime (infer)",
            "Parse with pandas to datetime",
            "Parse with errors='coerce'",
            "Parse and standardize",
            "Parse to datetime",
            "Standardize to ISO format",
        }:
            if unparseable_count:
                df = df.loc[parsed.notna()].copy()
                parsed = parsed.loc[parsed.notna()]
            df[column] = parsed.dt.strftime("%Y-%m-%d")
            return df, f"Standardized dates to ISO 8601.{warning}"
        if option == "Drop rows with unparseable dates":
            return df.loc[parsed.notna()].assign(
                **{column: parsed.loc[parsed.notna()].dt.strftime("%Y-%m-%d")}
            ), f"Dropped rows with unparseable dates and standardized the rest.{warning}"

    elif issue_type in {"constant_column", "constant_columns"}:
        if not column or column not in df.columns:
            raise KeyError(f"Constant column not found: {column!r}")
        if option == "Drop column":
            return df.drop(columns=[column]), f"Dropped constant column {column}."
        if option == "Keep column":
            return df, "No action taken; the constant column was kept."

    raise ValueError(
        f"Unsupported approved operation {option!r} for issue type {issue_type!r}."
    )


def apply_approved_plan(
    df: pd.DataFrame, approved_plan: list[dict]
) -> tuple[pd.DataFrame, list[dict]]:
    """Apply only the operations explicitly included in approved_plan."""
    cleaned_df = df.copy(deep=True)
    change_log = []

    for plan in approved_plan:
        rows_before = len(cleaned_df)
        columns_before = len(cleaned_df.columns)
        missing_before = _total_missing(cleaned_df)
        option = _operation_name(plan)
        notes = ""
        try:
            cleaned_df, notes = _apply_operation(cleaned_df, plan, option)
            rows_removed = rows_before - len(cleaned_df)
            if rows_removed > rows_before * 0.20:
                notes += (
                    f" WARNING: operation removed {rows_removed} of "
                    f"{rows_before} rows ({rows_removed / rows_before:.1%})."
                )
        except Exception as exc:
            notes = f"Operation failed and was skipped: {exc}"

        change_log.append(
            {
                "issue_id": plan.get("issue_id"),
                "issue_type": plan.get("issue_type"),
                "column": plan.get("column"),
                "option_applied": option,
                "rows_before": rows_before,
                "rows_after": len(cleaned_df),
                "columns_before": columns_before,
                "columns_after": len(cleaned_df.columns),
                "missing_before": missing_before,
                "missing_after": _total_missing(cleaned_df),
                "notes": notes,
            }
        )

    return cleaned_df, change_log


def validate_cleaning(
    original_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    change_log: list[dict],
) -> dict:
    """Validate row/column structure and report unexpected changes."""
    rows_removed = len(original_df) - len(cleaned_df)
    rows_added = max(0, len(cleaned_df) - len(original_df))
    original_columns = set(original_df.columns)
    cleaned_columns = set(cleaned_df.columns)
    columns_removed = len(original_columns - cleaned_columns)
    columns_added = len(cleaned_columns - original_columns)
    warnings = []

    if rows_added:
        warnings.append(f"Unexpected rows added: {rows_added}.")
    if columns_added:
        warnings.append(
            f"Unexpected columns added: {sorted(cleaned_columns - original_columns)}."
        )
    if any("Operation failed" in entry.get("notes", "") for entry in change_log):
        warnings.append("One or more approved operations failed and were skipped.")
    if any(
        entry.get("rows_after", 0) > entry.get("rows_before", 0)
        or entry.get("columns_after", 0) > entry.get("columns_before", 0)
        for entry in change_log
    ):
        warnings.append("An operation reported an unexpected row or column increase.")

    return {
        "rows_removed": rows_removed,
        "rows_added": rows_added,
        "columns_removed": columns_removed,
        "columns_added": columns_added,
        "expected_changes_only": not warnings,
        "warnings": warnings,
    }
