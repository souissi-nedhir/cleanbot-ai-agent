# Definition of Done

Given a messy CSV, the agent:

- Profiles the dataset and detects a defined set of common data quality issues:
  missing values, duplicate rows, invalid or inconsistent data types, inconsistent formatting, invalid values, and referential inconsistencies.
- Flags potential anomalies for human review rather than treating them as confirmed errors.
- Offers 2–3 cleaning options for each detected issue, with trade-offs explained in plain English.
- Waits for approval of each individual cleaning operation before executing it.
- Preserves the original dataset.
- Returns a cleaned CSV and a complete change log after approved operations are executed.
- Explains every executed change in plain English and provides a before/after comparison.
- Validates the cleaning results and detects and reports unexpected row or column changes.
- Performs any intentional row or column removal only when it is included in the approved cleaning plan.
- Targets completion within 10 minutes for representative small-to-medium CSV files; this is a performance goal, not a universal guarantee.
