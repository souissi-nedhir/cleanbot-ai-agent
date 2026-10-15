"""Run the profiler against the included messy sales sample."""

import json
from pathlib import Path

import pandas as pd

from profiler import profile_dataframe


# Locate the sample CSV relative to this test file.
sample_path = Path(__file__).parent / "sample_data" / "messy_sales.csv"

# Load the sample data without applying cleaning operations.
dataframe = pd.read_csv(sample_path)

# Profile the DataFrame and print the structured result readably.
profile = profile_dataframe(dataframe)
print(json.dumps(profile, indent=2))
