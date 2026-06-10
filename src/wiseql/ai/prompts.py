"""Prompt builders for the AI add-on (provider-agnostic).

Kept separate from any backend so both the non-streaming provider methods and
the streaming TUI path build identical prompts. Each is deliberately small and
asks for concise output — these run on a local Gemma, not a frontier model.
"""

from __future__ import annotations


def build_validate_prompt(recipe_text: str, context: str) -> str:
    return (
        "You are reviewing a WiseQL SQL recipe for *semantic* problems a "
        "structural validator cannot catch — e.g. a step referencing a column an "
        "upstream step does not output, or a join key that does not exist.\n"
        "Report concrete issues as a short bullet list. If you find no problems, "
        "reply with exactly: No semantic issues found.\n"
        "Do not restate the recipe.\n\n"
        f"--- schema/context ---\n{context or '(none provided)'}\n\n"
        f"--- recipe ---\n{recipe_text}\n"
    )


def build_explain_prompt(report_json: str, recipe_text: str, context: str) -> str:
    return (
        "A WiseQL run failed. Using the run report, the recipe, and the schema "
        "context, explain in 2-4 sentences the most likely cause and name the step "
        "to inspect first. Be concrete; do not dump the inputs back.\n\n"
        f"--- schema/context ---\n{context or '(none provided)'}\n\n"
        f"--- recipe ---\n{recipe_text}\n\n"
        f"--- run report (JSON) ---\n{report_json}\n"
    )


def build_narrative_prompt(report_json: str, context: str) -> str:
    return (
        "Summarise this WiseQL run for a teammate who did not see it run: what each "
        "step did, row counts, and any assertion that failed and why it matters. "
        "A few short paragraphs, plain language.\n\n"
        f"--- schema/context ---\n{context or '(none provided)'}\n\n"
        f"--- run report (JSON) ---\n{report_json}\n"
    )
