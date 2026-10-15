"""Single source of truth for supported cleaning operations."""

VALID_OPERATIONS = {
    "missing_values": [
        "Keep as is (Do nothing)",
        "Drop rows with missing values",
        "Impute with median",
        "Impute with mean",
        "Impute with mode",
    ],
    "duplicates": [
        "Keep as is (Do nothing)",
        "Drop duplicates",
    ],
    "outlier": [
        "Keep as is (Do nothing)",
        "Remove outliers (IQR)",
        "Cap outliers (IQR)",
    ],
    "mixed_type": [
        "Keep as is (Do nothing)",
        "Standardize to ISO 8601",
        "Drop rows with unparseable dates",
    ],
    "constant_column": [
        "Keep as is (Do nothing)",
        "Drop column",
    ],
    "high_missing": [
        "Keep as is (Do nothing)",
        "Drop column",
        "Impute with median",
    ],
    "low_uniqueness": [
        "Keep as is (Do nothing)",
        "Drop column",
    ],
}

ISSUE_TYPE_ALIASES = {
    "missing": "missing_values",
    "missing_value": "missing_values",
    "duplicate_rows": "duplicates",
    "duplicate_values": "duplicates",
    "outliers": "outlier",
    "outlier_values": "outlier",
    "mixed_types": "mixed_type",
    "mixed_type_column": "mixed_type",
    "mixed_type_columns": "mixed_type",
    "inconsistent_format": "mixed_type",
    "constant_columns": "constant_column",
}
