"""Test approved cleaning execution and validation on the sample CSV."""

import json
import sys
from pathlib import Path

import pandas as pd

from cleaner_executor import apply_approved_plan, validate_cleaning
from cleaner_planner import suggest_cleaning_options
from issue_detector import detect_issues
from profiler import profile_dataframe


project_root = Path(__file__).parent
sample_path = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else project_root / "sample_data" / "messy_sales.csv"
)

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
output_dir = sample_path.parent
cleaned_path = output_dir / f"{sample_path.stem}_cleaned.csv"
change_log_path = output_dir / f"{sample_path.stem}_change_log.json"
cleaned_df.to_csv(cleaned_path, index=False)
change_log_path.write_text(
    json.dumps(change_log, indent=2), encoding="utf-8"
)

# Print the requested results.
print(json.dumps({"change_log": change_log, "validation": validation}, indent=2))
