"""Utilities for profiling tabular data."""

import numpy as np
import pandas as pd


def profile_dataframe(df: pd.DataFrame) -> dict:
    """Profile a pandas DataFrame without modifying the input."""
    # Copy the input so every operation in this function is non-destructive.
    working = df.copy(deep=True)

    # Record the basic shape and column names.
    shape = (int(working.shape[0]), int(working.shape[1]))
    columns = working.columns.tolist()

    # Convert pandas dtypes to strings so the result is JSON serializable.
    dtypes = {column: str(working[column].dtype) for column in columns}

    # Count missing values and calculate each column's missing percentage.
    missing = {
        column: {
            "count": int(working[column].isna().sum()),
            "percent": float(working[column].isna().mean() * 100)
            if len(working) else 0.0,
        }
        for column in columns
    }

    # Count rows that are exact duplicates of an earlier row.
    duplicates = int(working.duplicated().sum())

    # Count distinct non-missing values in every column.
    unique_counts = {
        column: int(working[column].nunique(dropna=True)) for column in columns
    }

    # Prepare numeric summaries, including quartiles used by the IQR rule.
    numeric_stats = {}
    outliers = {}
    numeric_columns = working.select_dtypes(include=[np.number]).columns
    for column in numeric_columns:
        # Remove missing values before calculating numeric statistics.
        values = working[column].dropna()
        if values.empty:
            numeric_stats[column] = {
                "mean": None,
                "median": None,
                "std": None,
                "min": None,
                "max": None,
                "q1": None,
                "q3": None,
            }
            outliers[column] = 0
            continue

        # Calculate the requested descriptive statistics.
        q1 = float(values.quantile(0.25))
        q3 = float(values.quantile(0.75))
        numeric_stats[column] = {
            "mean": float(values.mean()),
            "median": float(values.median()),
            "std": float(values.std()) if len(values) > 1 else 0.0,
            "min": float(values.min()),
            "max": float(values.max()),
            "q1": q1,
            "q3": q3,
        }

        # Count values outside the inclusive IQR bounds.
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outliers[column] = int(
            ((values < lower_bound) | (values > upper_bound)).sum()
        )

    # Identify columns with one or fewer observed distinct values.
    constant_columns = [
        column for column in columns if unique_counts[column] <= 1
    ]

    # Flag columns whose missing percentage is strictly greater than 40%.
    high_missing_columns = [
        column for column in columns if missing[column]["percent"] > 40
    ]

    # Identify object columns containing both numeric-like and non-numeric values.
    mixed_type_columns = []
    for column in columns:
        if not (
            pd.api.types.is_object_dtype(working[column])
            or pd.api.types.is_string_dtype(working[column])
        ):
            continue
        values = working[column].dropna().astype(str).str.strip()
        if values.empty:
            continue
        numeric_like = pd.to_numeric(values, errors="coerce").notna()
        # Detect columns mixing numeric-looking and non-numeric-looking values.
        has_mixed_numeric_types = numeric_like.any() and (~numeric_like).any()

        # Detect date-like values written with more than one separator/order.
        date_patterns = values.str.extract(
            r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})$",
            expand=False,
        ).dropna()
        date_formats = {
            "year-first"
            if value[:4].isdigit() and value[4] in "-/"
            else "day-first"
            for value in date_patterns
        }
        has_mixed_date_formats = len(date_formats) > 1

        if has_mixed_numeric_types or has_mixed_date_formats:
            mixed_type_columns.append(column)

    # Convert the first five rows to plain dictionaries for easy display.
    sample_rows = working.head(5).replace({np.nan: None}).to_dict(
        orient="records"
    )

    # Return all profiling results in the requested structured form.
    return {
        "shape": shape,
        "columns": columns,
        "dtypes": dtypes,
        "missing": missing,
        "duplicates": duplicates,
        "unique_counts": unique_counts,
        "numeric_stats": numeric_stats,
        "outliers": outliers,
        "constant_columns": constant_columns,
        "high_missing_columns": high_missing_columns,
        "mixed_type_columns": mixed_type_columns,
        "sample_rows": sample_rows,
    }
