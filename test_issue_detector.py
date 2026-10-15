"""Run issue detection against the included messy sales sample."""

import json
from pathlib import Path

import pandas as pd

from issue_detector import detect_issues
from profiler import profile_dataframe


# Locate the sample CSV relative to this test file.
sample_path = Path(__file__).parent / "sample_data" / "messy_sales.csv"

# Load and profile the sample data without modifying it.
dataframe = pd.read_csv(sample_path)
profile = profile_dataframe(dataframe)

# Detect issues and print the returned list in readable JSON.
issues = detect_issues(profile)
print(json.dumps(issues, indent=2))
