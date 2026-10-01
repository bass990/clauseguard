"""LLM-as-judge on resolution language.

The agent proposes compromise language for every conflict. That text is
the most dangerous output in the product: it reads as authoritative and a
non-lawyer may paste it into a redline. The judge is a second, cheaper
model that scores each resolution on soundness, one-sidedness and
ambiguity, checks that the cited playbook entry exists and matches the
conflict topic, and returns a verdict:

    pass  -> shown as is
    flag  -> shown with a warning and the judge's reason
    hide  -> replaced by "resolution withheld pending counsel review"

The judge is itself calibrated against a small hand-labelled set
(eval/judge_calibration.json, `make judge-calibrate`), so its agreement
with a human is a number, not an assumption.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional

from backend.playbook import resolve_ref

JUDGE_SYSTEM = """You review suggested contract-resolution language written by an AI assistant for a company negotiating with a vendor.
Score the resolution, not the conflict. Answer with JSON only:
{
  "sound": true|false,            // false ONLY if legally incoherent, self-contradictory, invents facts, or would leave the company worse off than the vendor's clause; a vague or incomplete resolution is still sound
  "one_sided": true|false,        // demands everything for one party with no compromise or fallback
  "ambiguous": true|false,        // vague ("a reasonable time"), could be read two ways, or leaves the key term undefined
  "cites_playbook_correctly": true|false|null,  // null when no playbook entry was provided; false if the cited entry is for a different topic or the resolution contradicts it
  "verdict": "pass"|"flag"|"hide",
  "reason": "<one sentence>"
}
Verdict rules: hide only if not sound; flag if one_sided or ambiguous or the playbook citation is wrong; otherwise pass.
Hiding removes the text from the reviewer, so reserve it for resolutions that would mislead counsel."""

WITHHELD = "Resolution withheld pending counsel review (automated check found the suggested language unsound)."


def _fmt_entry(entry: Optional[dict]) -> str:
    if not entry:
        return "none"
    return json.dumps(
        {"id": entry["id"], "topic": entry["topic"], "standard_position": entry["standard_position"], "fallbacks": entry["fallbacks"]}
    )


def render_judge_input(conflict: dict) -> str:
    entry = resolve_ref(conflict.get("playbook_ref"))
    return json.dumps(
        {
            "topic": conflict.get("topic"),
            "risk": conflict.get("risk"),
            "company_text": conflict.get("company_text", "")[:1200],
            "vendor_text": conflict.get("vendor_text", "")[:1200],
            "conflict_explanation": conflict.get("conflict_explanation", "")[:1200],
            "favor": conflict.get("favor"),
            "resolution": conflict.get("resolution", "")[:2000],
            "playbook_ref": conflict.get("playbook_ref"),
            "playbook_entry": _fmt_entry(entry),
        }
    )


def parse_verdict(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    sound = bool(d.get("sound", True))
    one_sided = bool(d.get("one_sided", False))
    ambiguous = bool(d.get("ambiguous", False))
    cites = d.get("cites_playbook_correctly")
    model_verdict = str(d.get("verdict", "")).lower()
    # The verdict is derived from the flags, not read from the model, so
    # the rule stated in JUDGE_SYSTEM is applied the same way every time.
    # Hiding is the destructive outcome, so it needs two signals to agree:
    # the sound flag AND the model's explicit verdict. Disagreement flags.
    if not sound and model_verdict == "hide":
        verdict = "hide"
    elif not sound:
        verdict = "flag"
    elif one_sided or ambiguous or cites is False:
        verdict = "flag"
    else:
        verdict = "pass"
    return {
        "sound": sound,
        "one_sided": one_sided,
        "ambiguous": ambiguous,
        "cites_playbook_correctly": cites,
        "verdict": verdict,
        "model_verdict": model_verdict or None,
        "reason": str(d.get("reason", ""))[:400],
    }


def citation_check(conflict: dict) -> Optional[bool]:
    """Deterministic part of the judge: does playbook_ref exist and match the topic?"""
    ref = conflict.get("playbook_ref")
    if not ref:
        return None
    entry = resolve_ref(ref)
    if entry is None:
        return False
    from backend.router import clause_topics  # local import to avoid cycles

    topics = clause_topics([{"section": conflict.get("topic", ""), "text": conflict.get("conflict_explanation", "")}])
    return entry["topic"] in topics if topics else True


def judge_conflict(conflict: dict, client, model: str, trace=None) -> dict:
    """Return the review dict for one conflict. Never raises."""
    review: dict
    try:
        t0 = time.time()
        resp = client.messages.create(
            model=model,
            max_tokens=300,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": render_judge_input(conflict)}],
        )
        if trace is not None:
            trace.record_call("judge", model, resp, time.time() - t0)
        text = "".join(getattr(b, "text", "") for b in resp.content)
        review = parse_verdict(text) or {"verdict": "flag", "reason": "judge output unparseable", "sound": True, "one_sided": False, "ambiguous": False, "cites_playbook_correctly": None}
    except Exception as exc:
        review = {"verdict": "flag", "reason": f"judge unavailable ({type(exc).__name__}); treat resolution as unreviewed", "sound": True, "one_sided": False, "ambiguous": False, "cites_playbook_correctly": None}
    cite = citation_check(conflict)
    review["citation_valid"] = cite
    if cite is False and review["verdict"] == "pass":
        review["verdict"] = "flag"
        review["reason"] = (review["reason"] + " " if review["reason"] else "") + "Cited playbook entry does not match the conflict topic."
    return review


def apply_review(conflict: dict, review: dict) -> dict:
    out = dict(conflict)
    out["resolution_review"] = review
    if review.get("verdict") == "hide":
        out["resolution_original"] = out.get("resolution")
        out["resolution"] = WITHHELD
    return out
