"""Suggest data cleaning options without executing any cleaning."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from config import MODELS
from operations import ISSUE_TYPE_ALIASES, VALID_OPERATIONS


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_CONTEXT_FILES = ("SOUL.md", "IDENTITY.md", "USER.md", "DoD.md")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
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


def _build_system_prompt(issue_types: list[str] | None = None) -> str:
    """Build the system prompt from project context and planner rules."""
    instructions = (
        "You are CleanBot, the Data Cleaning Agent. For each data quality "
        "issue, suggest 2-3 cleaning options. Do not execute anything. For "
        "each option, explain the method and the trade-off (what is lost, "
        "what is gained). Recommend one option and explain why. Only use "
        "columns and values present in the profile. Return ONLY valid JSON, "
        "no markdown.\n\n"
        "For each issue, choose 2-3 options from this exact list based on "
        "its issue_type. Do not invent new option names.\n"
        "Valid options by issue type:\n"
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
    selected_types = issue_types or list(VALID_OPERATIONS)
    valid_lines = []
    for issue_type in selected_types:
        canonical = ISSUE_TYPE_ALIASES.get(issue_type, issue_type)
        valid_lines.append(
            f"- {canonical}: {VALID_OPERATIONS.get(canonical, ['Keep as is (Do nothing)'])}"
        )
    return (
        f"{_load_agent_context()}\n\n--- Planner instructions ---\n"
        f"{instructions}\n" + "\n".join(valid_lines)
    )


def normalize_cleaning_plans(raw_plans: list[dict]) -> list[dict]:
    """Normalize model output to the required cleaning-plan schema."""
    normalized_plans = []
    for raw_plan in raw_plans:
        plan = dict(raw_plan)
        issue_type = ISSUE_TYPE_ALIASES.get(
            str(plan.get("issue_type", "")).strip().lower(),
            str(plan.get("issue_type", "")).strip().lower(),
        )
        valid_options = VALID_OPERATIONS.get(
            issue_type, ["Keep as is (Do nothing)"]
        )
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
                option_name = str(option["option_name"]).strip()
                if option_name == "Keep as is":
                    option_name = "Keep as is (Do nothing)"
                option["option_name"] = option_name
                if option_name in valid_options:
                    options.append(option)

        if not options:
            options = [
                {
                    "option_name": "Keep as is (Do nothing)",
                    "method": "Make no change.",
                    "trade_off": "Preserves the current data and issue.",
                }
            ]
        recommended = str(plan.get("recommended_option", "")).strip()
        if recommended == "Keep as is":
            recommended = "Keep as is (Do nothing)"
        if recommended not in valid_options:
            recommended = options[0]["option_name"]

        normalized_plans.append(
            {
                "issue_id": plan.get("issue_id"),
                "issue_type": issue_type,
                "column": plan.get("column"),
                "options": options,
                "recommended_option": recommended,
                "reason_for_recommendation": plan.get(
                    "reason_for_recommendation", ""
                ),
            }
        )
    return normalized_plans


def _is_model_fallback_error(exc: Exception) -> bool:
    message = str(exc)
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "429",
            "rate limit",
            "400",
            "404",
            "notfounderror",
            "model_not_found",
            "model_decommissioned",
        )
    )


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
    last_error = "unknown planner response error"
    for model_index, model_name in enumerate(MODELS):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": _build_system_prompt(
                            [
                                str(issue.get("issue_type", "")).strip().lower()
                                for issue in issues
                            ]
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"issues": issues, "profile": profile}),
                    },
                ],
                temperature=0,
            )
        except Exception as exc:
            if _is_model_fallback_error(exc):
                next_model = (
                    MODELS[model_index + 1]
                    if model_index + 1 < len(MODELS)
                    else "no remaining model"
                )
                print(
                    f"Model {model_name} hit a limit or is unavailable, "
                    f"trying {next_model}..."
                )
                last_error = str(exc)
                continue
            raise

        content = response.choices[0].message.content
        if not content:
            last_error = "the cleaning planner returned an empty response"
            continue
        try:
            raw_plans = json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = "the cleaning planner returned invalid JSON"
            if model_index + 1 < len(MODELS):
                continue
            raise ValueError(last_error) from exc
        if not isinstance(raw_plans, list) or not all(
            isinstance(plan, dict) for plan in raw_plans
        ):
            last_error = "the cleaning planner response must be a JSON list"
            continue
        return normalize_cleaning_plans(raw_plans)

    raise RuntimeError(
        "Cleaning planner failed after trying all configured models: "
        f"{last_error}"
    )
