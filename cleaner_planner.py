"""Suggest data cleaning options without executing any cleaning."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_CONTEXT_FILES = ("SOUL.md", "IDENTITY.md", "USER.md", "DoD.md")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL_NAME = "openai/gpt-oss-20b"
REQUIRED_PLAN_KEYS = (
    "issue_id",
    "issue_type",
    "column",
    "options",
    "recommended_option",
    "reason_for_recommendation",
)
REQUIRED_OPTION_KEYS = ("option_name", "method", "trade_off")


def _load_agent_context() -> str:
    """Load the project identity files for the planning prompt."""
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
    """Build the system prompt from project context and planner rules."""
    instructions = (
        "You are CleanBot, the Data Cleaning Agent. For each data quality "
        "issue, suggest 2-3 cleaning options. Do not execute anything. For "
        "each option, explain the method and the trade-off (what is lost, "
        "what is gained). Recommend one option and explain why. Only use "
        "columns and values present in the profile. Return ONLY valid JSON, "
        "no markdown.\n\n"
        "Return a JSON list matching this schema:\n"
        "[\n"
        "  {\n"
        '    "issue_id": 1,\n'
        '    "issue_type": "missing_values",\n'
        '    "column": "region",\n'
        '    "options": [\n'
        '      {"option_name": "Drop rows", "method": "Remove rows where '
        'region is missing.", "trade_off": "Loses 2 rows (10%), but keeps '
        'data clean."},\n'
        '      {"option_name": "Impute with mode", "method": "Fill missing '
        'region with the most frequent region.", "trade_off": "Keeps all '
        'rows, but introduces artificial values."}\n'
        "    ],\n"
        '    "recommended_option": "Drop rows",\n'
        '    "reason_for_recommendation": "Dataset is small and region is '
        'important for grouping."\n'
        "  }\n"
        "]"
    )
    return f"{_load_agent_context()}\n\n--- Planner instructions ---\n{instructions}"


def normalize_cleaning_plans(raw_plans: list[dict]) -> list[dict]:
    """Normalize model output to the required cleaning-plan schema."""
    normalized_plans = []
    for raw_plan in raw_plans:
        plan = dict(raw_plan)
        raw_options = plan.get("options", [])
        options = []
        if isinstance(raw_options, list):
            for raw_option in raw_options:
                if not isinstance(raw_option, dict):
                    continue
                option = {
                    key: raw_option.get(key, "")
                    for key in REQUIRED_OPTION_KEYS
                }
                options.append(option)

        normalized_plans.append(
            {
                "issue_id": plan.get("issue_id"),
                "issue_type": plan.get("issue_type", ""),
                "column": plan.get("column"),
                "options": options,
                "recommended_option": plan.get("recommended_option", ""),
                "reason_for_recommendation": plan.get(
                    "reason_for_recommendation", ""
                ),
            }
        )
    return normalized_plans


def suggest_cleaning_options(
    issues: list[dict], profile: dict
) -> list[dict]:
    """Suggest cleaning plans without executing any cleaning operation."""
    # Load the local API key and reject the placeholder explicitly.
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Copy a real key into .env "
            "before running the cleaning planner."
        )

    # Build the OpenAI-compatible Groq client.
    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {
                "role": "user",
                "content": json.dumps({"issues": issues, "profile": profile}),
            },
        ],
        temperature=0,
    )

    # Require valid JSON and normalize it without executing any plan.
    content = response.choices[0].message.content
    if not content:
        raise ValueError("The cleaning planner returned an empty response.")
    try:
        raw_plans = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "The cleaning planner returned invalid JSON."
        ) from exc
    if not isinstance(raw_plans, list) or not all(
        isinstance(plan, dict) for plan in raw_plans
    ):
        raise ValueError("The cleaning planner response must be a JSON list.")
    return normalize_cleaning_plans(raw_plans)
