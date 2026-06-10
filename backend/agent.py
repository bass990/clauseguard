import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from config import MODEL, MAX_TOKENS, ANTHROPIC_API_KEY, SYSTEM_PROMPT
from backend.tools import TOOLS, TOOL_MAP

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def run_agent(contract_a_path: str, contract_b_path: str, on_progress=None) -> dict:
    """
    Run the ClauseGuard agent on two contract PDFs.

    Args:
        contract_a_path: Path to company standard contract (PDF)
        contract_b_path: Path to vendor contract (PDF)
        on_progress: Optional callback(message: str) for streaming progress updates

    Returns:
        dict with keys: success, report, error (if failed)
    """
    def log(msg):
        if on_progress:
            on_progress(msg)
        else:
            print(f"[Agent] {msg}")

    messages = [
        {
            "role": "user",
            "content": (
                f"Analyze these two contracts for conflicts and generate a complete redline brief.\n\n"
                f"Contract A (our company standard terms): {contract_a_path}\n"
                f"Contract B (vendor/supplier terms): {contract_b_path}\n\n"
                f"Follow your workflow: extract clauses from both, find conflicts, "
                f"then generate the final redline brief."
            )
        }
    ]

    turn = 0
    max_turns = 20  # safety limit
    redline_report = None

    while turn < max_turns:
        turn += 1
        log(f"Thinking... (turn {turn})")

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text
            log("Analysis complete.")
            return {
                "success": True,
                "final_message": final_text,
                "report": redline_report.get("report") if redline_report else None
            }

        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                log(f"Calling tool: {tool_name}()")

                if tool_name not in TOOL_MAP:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = TOOL_MAP[tool_name](**tool_input)
                        if tool_name == "generate_redline_brief" and result.get("success"):
                            redline_report = result
                            log("Redline brief generated.")
                        if tool_name == "extract_clauses" and result.get("truncated"):
                            log(result["truncation_warning"])
                    except Exception as e:
                        result = {"error": str(e)}
                        log(f"Tool error: {e}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result)
                })

            messages.append({"role": "user", "content": tool_results})

    return {"success": False, "error": "Max turns reached without completion.", "report": None}


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python agent.py <contract_a.pdf> <contract_b.pdf>")
        sys.exit(1)

    result = run_agent(sys.argv[1], sys.argv[2])
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))
