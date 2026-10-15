"""Test approved cleaning execution and validation on the sample CSV."""

import json
from pathlib import Path

import pandas as pd

from cleaner_executor import apply_approved_plan, validate_cleaning
from cleaner_planner import suggest_cleaning_options
from issue_detector import detect_issues
from profiler import profile_dataframe


# Locate the sample CSV relative to this test file.
project_root = Path(__file__).parent
sample_path = project_root / "sample_data" / "messy_sales.csv"

# Load and profile the original data.
original_df = pd.read_csv(sample_path)
profile = profile_dataframe(original_df)
issues = detect_issues(profile)
plans = suggest_cleaning_options(issues, profile)

# Simulate explicit approval by selecting each recommended option.
approved_plan = [
    {
        "issue_id": plan["issue_id"],
        "issue_type": plan["issue_type"],
        "column": plan["column"],
        "recommended_option": plan["recommended_option"],
        "chosen_option": plan["recommended_option"],
    }
    for plan in plans
]

# Execute only the simulated approvals and validate the result.
cleaned_df, change_log = apply_approved_plan(original_df, approved_plan)
validation = validate_cleaning(original_df, cleaned_df, change_log)

# Save only the explicitly requested test artifacts.
cleaned_df.to_csv(project_root / "sample_data" / "messy_sales_cleaned.csv", index=False)
(project_root / "sample_data" / "change_log.json").write_text(
    json.dumps(change_log, indent=2), encoding="utf-8"
)

# Print the requested results.
print(json.dumps({"change_log": change_log, "validation": validation}, indent=2))
