"""Execute approved cleaning operations through a validated dispatch table."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from operations import ISSUE_TYPE_ALIASES, VALID_OPERATIONS


def _total_missing(df: pd.DataFrame) -> int:
    return int(df.isna().sum().sum())


def _canonical_issue_type(issue_type: Any) -> str:
    value = str(issue_type or "").strip().lower()
    return ISSUE_TYPE_ALIASES.get(value, value)


def _canonical_option_name(option: Any, issue_type: str) -> str:
    value = " ".join(str(option or "").strip().split())
    normalized = value.lower()
    aliases = {
        "drop rows": "Drop rows with missing values",
        "drop rows with missing values": "Drop rows with missing values",
        "drop missing": "Drop rows with missing values",
        "remove rows": "Drop rows with missing values",
        "remove missing": "Drop rows with missing values",
        "remove rows with missing values": "Drop rows with missing values",
        "drop duplicate rows": "Drop duplicates",
        "drop duplicates keeping first": "Drop duplicates",
        "keep as is": "Keep as is (Do nothing)",
        "keep column": "Keep as is (Do nothing)",
        "keep outliers": "Keep as is (Do nothing)",
        "standardize to iso format": "Standardize to ISO 8601",
        "parse dates": "Standardize to ISO 8601",
        "parse to datetime": "Standardize to ISO 8601",
        "parse and standardize": "Standardize to ISO 8601",
        "parse with errors='coerce'": "Standardize to ISO 8601",
    }
    canonical = aliases.get(normalized, value)
    if canonical in VALID_OPERATIONS.get(issue_type, []):
        return canonical
    return value


def _require_column(df: pd.DataFrame, plan: dict[str, Any]) -> str:
    column = plan.get("column")
    if not column or column not in df.columns:
        raise KeyError(f"Column not found: {column!r}")
    return str(column)


def _keep(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    return df, "No action taken; the issue was kept as is."


def _drop_missing(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column = _require_column(df, plan)
    return df.dropna(subset=[column]), f"Dropped rows missing {column}."


def _impute_median(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column = _require_column(df, plan)
    numeric = pd.to_numeric(df[column], errors="raise")
    df[column] = numeric.fillna(numeric.median())
    return df, f"Filled missing {column} values with the median."


def _impute_mean(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column = _require_column(df, plan)
    numeric = pd.to_numeric(df[column], errors="raise")
    df[column] = numeric.fillna(numeric.mean())
    return df, f"Filled missing {column} values with the mean."


def _impute_mode(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column = _require_column(df, plan)
    modes = df[column].mode(dropna=True)
    if modes.empty:
        raise ValueError(f"Cannot find a mode for column {column!r}.")
    df[column] = df[column].fillna(modes.iloc[0])
    return df, f"Filled missing {column} values with the mode."


def _drop_duplicates(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    return df.drop_duplicates(), "Dropped duplicate rows."


def _outlier_mask(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[str, pd.Series, pd.Series]:
    column = _require_column(df, plan)
    values = pd.to_numeric(df[column], errors="raise")
    median = values.median()
    if pd.isna(median):
        raise ValueError(f"Cannot detect outliers in empty column {column!r}.")
    return column, values, values.notna() & (values.abs() > abs(median) * 5)


def _remove_outliers(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column, values, mask = _outlier_mask(df, plan)
    return df.loc[~mask], f"Removed outliers from {column} using the median rule."


def _cap_outliers(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column, values, mask = _outlier_mask(df, plan)
    non_outliers = values.loc[~mask].dropna()
    if non_outliers.empty:
        raise ValueError(f"Cannot calculate a cap for {column!r}.")
    cap = min(float(values.dropna().quantile(0.99)), float(non_outliers.max()))
    df[column] = values.mask(mask, cap)
    return df, f"Capped outliers in {column} at {cap}."


def _parse_dates(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, pd.Series, int]:
    column = _require_column(df, plan)
    parsed = pd.to_datetime(
        df[column], dayfirst=True, errors="coerce", format="mixed"
    )
    year_first = df[column].astype("string").str.match(
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", na=False
    )
    if year_first.any():
        parsed.loc[year_first] = pd.to_datetime(
            df.loc[year_first, column],
            dayfirst=False,
            errors="coerce",
            format="mixed",
        )
    return column, parsed, int(parsed.isna().sum())


def _standardize_dates(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column, parsed, invalid = _parse_dates(df, plan)
    df = df.loc[parsed.notna()].copy()
    df[column] = parsed.loc[parsed.notna()].dt.strftime("%Y-%m-%d")
    note = f"Standardized dates in {column} to ISO 8601."
    if invalid:
        note += f" Dropped {invalid} unparseable date rows."
    return df, note


def _drop_unparseable_dates(
    df: pd.DataFrame, plan: dict[str, Any]
) -> tuple[pd.DataFrame, str]:
    column, parsed, _ = _parse_dates(df, plan)
    return df.loc[parsed.notna()].copy(), "Dropped rows with unparseable dates."


def _drop_column(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    column = _require_column(df, plan)
    return df.drop(columns=[column]), f"Dropped column {column}."


def _build_dispatch_table() -> dict[tuple[str, str], Callable[..., tuple[pd.DataFrame, str]]]:
    dispatch: dict[tuple[str, str], Callable[..., tuple[pd.DataFrame, str]]] = {}
    for issue_type in VALID_OPERATIONS:
        dispatch[(issue_type, "Keep as is (Do nothing)")] = _keep
    for issue_type in ("missing_values", "high_missing"):
        dispatch[(issue_type, "Impute with median")] = _impute_median
    dispatch[("missing_values", "Drop rows with missing values")] = _drop_missing
    dispatch[("missing_values", "Impute with mean")] = _impute_mean
    dispatch[("missing_values", "Impute with mode")] = _impute_mode
    dispatch[("duplicates", "Drop duplicates")] = _drop_duplicates
    dispatch[("outlier", "Remove outliers (IQR)")] = _remove_outliers
    dispatch[("outlier", "Cap outliers (IQR)")] = _cap_outliers
    dispatch[("mixed_type", "Standardize to ISO 8601")] = _standardize_dates
    dispatch[("mixed_type", "Drop rows with unparseable dates")] = _drop_unparseable_dates
    for issue_type in ("constant_column", "high_missing", "low_uniqueness"):
        dispatch[(issue_type, "Drop column")] = _drop_column
    return dispatch


DISPATCH_TABLE = _build_dispatch_table()


def apply_approved_plan(
    df: pd.DataFrame, approved_plan: list[dict]
) -> tuple[pd.DataFrame, list[dict]]:
    """Apply approved operations and log every attempted operation."""
    cleaned_df = df.copy(deep=True)
    change_log = []
    for plan in approved_plan:
        rows_before = len(cleaned_df)
        columns_before = len(cleaned_df.columns)
        missing_before = _total_missing(cleaned_df)
        issue_type = _canonical_issue_type(plan.get("issue_type"))
        option = _canonical_option_name(
            plan.get("chosen_option") or plan.get("recommended_option"),
            issue_type,
        )
        handler = DISPATCH_TABLE.get((issue_type, option))
        notes = ""
        if handler is None:
            notes = "Skipped: no matching handler."
        else:
            try:
                cleaned_df, notes = handler(cleaned_df, plan)
                rows_removed = rows_before - len(cleaned_df)
                if rows_removed > rows_before * 0.20:
                    notes += (
                        f" WARNING: operation removed {rows_removed} of "
                        f"{rows_before} rows ({rows_removed / rows_before:.1%})."
                    )
            except Exception as exc:
                notes = f"Skipped: operation error: {exc}"
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
    warnings = []
    if rows_added:
        warnings.append(f"Unexpected rows added: {rows_added}.")
    if cleaned_columns - original_columns:
        warnings.append(
            f"Unexpected columns added: {sorted(cleaned_columns - original_columns)}."
        )
    if any(entry.get("notes", "").startswith("Skipped:") for entry in change_log):
        warnings.append("One or more approved operations were skipped.")
    return {
        "rows_removed": rows_removed,
        "rows_added": rows_added,
        "columns_removed": len(original_columns - cleaned_columns),
        "columns_added": len(cleaned_columns - original_columns),
        "expected_changes_only": not warnings,
        "warnings": warnings,
    }
