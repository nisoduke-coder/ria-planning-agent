"""Meeting prep: Claude turns the same numbers into a pre-meeting cheat-sheet.

This is a different *job* from plan drafting, but it reuses the whole engine.
The plan draft is a full document for the client; the meeting brief is a short,
scannable prep sheet the advisor reads in the five minutes before the meeting —
talking points, decisions to tee up, and questions to ask.
"""

import os

import anthropic

from .agent import MODEL, _build_brief
from .engine import MonteCarloResults, PlanResults
from .models import ClientProfile, MeetingContext

MEETING_SYSTEM_PROMPT = """\
You are a financial planning assistant preparing a Registered Investment \
Advisor (RIA) for a client meeting. Produce a SHORT, scannable pre-meeting \
briefing the advisor can read in five minutes before walking in. This is an \
internal cheat-sheet for the advisor, not a document for the client.

Use these sections and keep them tight — bullets, not paragraphs:

1. SNAPSHOT — two lines: who they are and the retirement timeline, plus the \
headline status (accumulation surplus/gap AND the lifecycle probability the \
money lasts).
2. SINCE LAST REVIEW — what to revisit given the meeting purpose and any open \
items. If the last review date is unknown, note what to confirm.
3. TOP TALKING POINTS — the three most important things to raise, each tied to \
a specific number.
4. DECISIONS TO TEE UP — concrete choices to put in front of the client, each \
with its quantified tradeoff from the scenarios / strategy / Social Security \
tables (e.g. "delay Social Security to 70 -> X% success").
5. QUESTIONS FOR THE CLIENT — the key assumptions to validate, phrased as \
questions to ask in the room.
6. OPEN ITEMS / FOLLOW-UPS — action items to track.

Ground every point in the figures provided; never invent or recompute numbers. \
Be direct and practical. End with a one-line note that the figures are a \
draft/illustrative for advisor use, not final advice."""


def prep_meeting(
    profile: ClientProfile,
    results: PlanResults,
    mc: MonteCarloResults,
    scenario_list: list,
    strategy_list: list,
    claiming_list: list,
    context: MeetingContext,
) -> str:
    """Call Claude to write the pre-meeting brief. Requires ANTHROPIC_API_KEY."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Open .env and paste your key, "
            "or run: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic()
    data = _build_brief(
        profile, results, mc, scenario_list, strategy_list, claiming_list
    )
    context_block = (
        "MEETING CONTEXT\n"
        f"  Purpose of meeting: {context.purpose}\n"
        f"  Last review: {context.last_review or 'unknown — confirm with client'}\n"
        f"  Open action items: {context.open_items or 'none on file'}\n"
        f"  Advisor notes for this meeting: {context.notes or 'none'}\n"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=MEETING_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Prepare a pre-meeting briefing.\n\n"
                    + context_block
                    + "\n"
                    + data
                ),
            }
        ],
    )
    return "".join(
        block.text for block in response.content if block.type == "text"
    )
