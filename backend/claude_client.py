import anthropic
import json
import os
from typing import List, Dict, Any

_SYSTEM_PROMPT = """\
You are an expert AWS cost analyst. You have been given an AWS Cost and Usage Report (CUR) \
data summary and must answer the user's question about their cloud spend.

ALWAYS respond with a single valid JSON object — no markdown fences, no extra text — in exactly this schema:

{
  "type": "text" | "table" | "chart",
  "content": <see below>,
  "insight": "<1-2 sentence key takeaway>"
}

Content rules by type:
- "text"  → content is a plain string
- "table" → content is {"headers": ["Col1", ...], "rows": [["v1", ...], ...]}
- "chart" → content is {
                "chart_type": "bar" | "line" | "pie",
                "title": "...",
                "labels": ["label1", ...],
                "datasets": [{"label": "...", "data": [1.0, ...]}]
            }

Guidance:
- Use "table" for comparisons, rankings, or lists of data across multiple services/months.
- Use "chart" when the user asks for trends, breakdowns, or visualisations.
- Use "text" for simple factual questions or explanations.
- Format all dollar amounts as numbers (not strings), 2 decimal places.
- If the data is insufficient to answer, say so clearly in the insight field.
"""


class ClaudeClient:
    def __init__(self):
        self._client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.model = "claude-sonnet-4-6"

    def analyze_costs(
        self,
        question: str,
        cur_data: Dict[str, Any],
        history: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        if history is None:
            history = []

        cur_context = (
            "CUR Data Context (monthly cost by service, USD):\n"
            + json.dumps(cur_data, indent=2)
        )

        messages: List[Dict] = []

        # Replay the last 10 turns of conversation history (without repeating context)
        for msg in history[-10:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Attach CUR context to the current question; cache the context block
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": cur_context,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": f"Question: {question}",
                },
            ],
        })

        response = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
        )

        raw = response.content[0].text.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "type": "text",
                "content": raw,
                "insight": "Response could not be parsed as structured JSON.",
            }
