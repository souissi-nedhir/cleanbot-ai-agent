"""Detect data quality issues from a profiler result using Groq."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_CONTEXT_FILES = ("SOUL.md", "IDENTITY.md", "USER.md", "DoD.md")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL_NAME = "openai/gpt-oss-20b"
REQUIRED_ISSUE_KEYS = (
    "id",
    "issue_type",
    "column",
    "severity",
    "description",
    "potential_impact",
    "evidence",
)
SLIM_PROFILE_KEYS = (
    "shape",
    "columns",
    "dtypes",
    "missing",
    "duplicates",
    "unique_counts",
    "outliers",
    "constant_columns",
    "high_missing_columns",
    "mixed_type_columns",
)
DEBUG_RESPONSE_PATH = PROJECT_ROOT / "sample_data" / "debug_raw_response.txt"


def _load_agent_context() -> str:
    """Load the four project identity files into one system prompt."""
    context_sections = []
    for filename in REQUIRED_CONTEXT_FILES:
        file_path = PROJECT_ROOT / filename
        if not file_path.is_file():
            raise FileNotFoundError(
                f"Required agent context file was not found: {file_path}"
            )
        context_sections.append(
            f"--- {filename} ---\n{file_path.read_text(encoding='utf-8')}"
        )
    return "\n\n".join(context_sections)


def _build_system_prompt() -> str:
    """Build the system prompt from project context and detector rules."""
    context = _load_agent_context()
    instructions = (
        "You are CleanBot, the Data Cleaning Agent. Your job is to analyze "
        "the data profile and produce a JSON list of data quality issues. "
        "Follow the SOUL, IDENTITY, USER, and DoD files exactly. Only use "
        "the numbers and columns present in the profile. Do not invent "
        "issues. For each issue, assign severity: High if it will break "
        "analysis or mislead, Medium if it needs attention, Low if it is "
        "minor. Return ONLY valid JSON, no markdown, no explanations "
        "outside the JSON.\n\n"
        "Return ONLY a valid JSON object with a single key called 'issues' "
        "whose value is a list of issue objects. Example: "
        "{\"issues\": [{\"id\": 1, ...}]}. Do not wrap in markdown. Do not "
        "add any text outside the JSON.\n\n"
        "Each issue object must have EXACTLY these keys:\n"
        "{\n"
        '  "id": 1,\n'
        '  "issue_type": "missing_values",\n'
        '  "column": "region",\n'
        '  "severity": "Medium",\n'
        '  "description": "10% of region values are missing.",\n'
        '  "potential_impact": "Grouping sales by region will misclassify or drop rows.",\n'
        '  "evidence": "missing: {count: 2, percent: 10.0}"\n'
        "}\n"
        "Do not use the key 'issue'. Do not omit any keys. Return ONLY valid JSON."
        "\nBe concise. Keep each description, potential_impact, and evidence "
        "to one short sentence. Do not repeat the issue type in the description."
    )
    return f"{context}\n\n--- Detector instructions ---\n{instructions}"


def slim_profile(profile: dict) -> dict:
    """Return only the profile fields needed for issue detection."""
    return {key: profile.get(key) for key in SLIM_PROFILE_KEYS}


def extract_json(text: str) -> dict:
    """Extract and parse a JSON object from a model response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _has_complete_issue_fields(issues: list[dict]) -> bool:
    """Check that every parsed issue has all required fields and complete text."""
    for issue in issues:
        if any(key not in issue for key in REQUIRED_ISSUE_KEYS):
            return False
        for value in issue.values():
            if not isinstance(value, str):
                continue
            if value.count("{") != value.count("}"):
                return False
    return True


def normalize_issues(raw_issues: list[dict]) -> list[dict]:
    """Normalize model output to the required issue schema."""
    normalized = []
    default_impacts = {
        "missing_values": "Analysis may be incomplete or misleading.",
        "duplicates": "Repeated records may inflate totals and counts.",
        "duplicate_rows": "Repeated records may inflate totals and counts.",
        "outliers": "Extreme values may distort summaries and analysis.",
        "outlier": "Extreme values may distort summaries and analysis.",
        "mixed_types": "Inconsistent values may cause parsing or analysis errors.",
        "mixed_type": "Inconsistent values may cause parsing or analysis errors.",
        "constant_column": "The column may add little information to analysis.",
        "high_missing": "Many missing values may make the column unreliable.",
    }

    for index, raw_issue in enumerate(raw_issues, start=1):
        issue = dict(raw_issue)
        issue_type = issue.get("issue_type", issue.get("issue", "unknown"))
        issue["id"] = issue.get("id", index)
        issue["issue_type"] = issue_type
        issue["potential_impact"] = issue.get(
            "potential_impact",
            default_impacts.get(
                issue_type, "This issue may affect the reliability of analysis."
            ),
        )
        issue["evidence"] = issue.get(
            "evidence", "No specific evidence was provided by the model."
        )
        normalized.append(
            {key: issue.get(key, "") for key in REQUIRED_ISSUE_KEYS}
        )
    return normalized


def detect_issues(profile: dict) -> list[dict]:
    """Return data quality issues identified from a profiler output."""
    # Load the local placeholder or user-provided Groq API key.
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Copy a real key into .env "
            "before running issue detection."
        )

    # Build the OpenAI-compatible client pointed at Groq.
    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    # Try the request twice when the model returns empty or invalid JSON.
    last_error = "unknown response error"
    last_content = ""
    reduced_profile = slim_profile(profile)
    for attempt in range(2):
        # Send the profile as JSON without changing its contents.
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": json.dumps(reduced_profile)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=4096,
        )

        content = response.choices[0].message.content
        last_content = content or ""
        print(f"RAW RESPONSE LENGTH: {len(last_content)}")

        if not content:
            last_error = "the model returned an empty response"
        else:
            parsed = extract_json(content)
            issues = parsed.get("issues") if parsed else None
            if isinstance(issues, list) and all(
                isinstance(issue, dict) for issue in issues
            ):
                print(f"ISSUES PARSED: {len(issues)}")
                if _has_complete_issue_fields(issues):
                    return normalize_issues(issues)
                last_error = "the parsed issue data was incomplete or truncated"
            else:
                print("ISSUES PARSED: 0")
                last_error = (
                    "the model returned invalid JSON or no valid 'issues' list"
                )

        DEBUG_RESPONSE_PATH.write_text(last_content, encoding="utf-8")

        if attempt == 0:
            continue

    raise ValueError(
        "Issue detection failed after 2 attempts: "
        f"{last_error}. See the raw response at {DEBUG_RESPONSE_PATH}."
    )
