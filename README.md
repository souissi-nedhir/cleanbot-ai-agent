# CleanBot: AI Data Cleaning Agent

An AI-powered data cleaning agent that profiles messy CSVs, detects data quality issues, suggests cleaning options, and produces a cleaned file with a full audit log.

## Features

- Profiles messy CSV and Excel data.
- Detects common data quality issues.
- Suggests explainable cleaning options and trade-offs.
- Executes only cleaning operations approved by the user.
- Produces a complete change log and validation result.
- Provides an interactive Streamlit UI.

## Tech Stack

- Python
- pandas
- Streamlit
- Groq API
- OpenAI library

## Project Structure

- `app.py` - Streamlit user interface
- `profiler.py` - Data profiling
- `issue_detector.py` - AI-powered issue detection
- `cleaner_planner.py` - Cleaning option suggestions
- `cleaner_executor.py` - Approved cleaning execution and validation
- `SOUL.md` - Agent principles
- `IDENTITY.md` - Agent identity and constraints
- `USER.md` - User context and preferences
- `DoD.md` - Definition of Done

## How to Run

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd first_ai_agent
   ```
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - Windows PowerShell:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```
4. Install the requirements:
   ```bash
   pip install -r requirements.txt
   ```
5. Create a `.env` file in the project root:
   ```text
   GROQ_API_KEY=your_groq_api_key_here
   ```
6. Start the Streamlit app:
   ```bash
   streamlit run app.py
   ```

## The Agent Architecture

CleanBot follows a controlled, approval-based flow:

**Profile -> Detect -> Suggest -> Approve -> Execute -> Audit**

1. **Profile**: Inspect the uploaded dataset and calculate data quality measures.
2. **Detect**: Identify common quality issues and potential anomalies.
3. **Suggest**: Present two or three explainable cleaning options per issue.
4. **Approve**: Let the human choose and approve each operation.
5. **Execute**: Apply only the approved operations to a copy of the original data.
6. **Audit**: Validate the result and produce a detailed change log.

## Definition of Done

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

## What I Learned

_Add lessons learned, design decisions, and project reflections here._
