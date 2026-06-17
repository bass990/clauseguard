# ClauseGuard Eval Rubric

**Status:** Committed Day 1, BEFORE any scenarios are labeled.
**Authority:** Quotes `clauseguard/config.py` SYSTEM_PROMPT verbatim where applicable, then encodes the rubric into deterministic rules in `eval/rubric_audit.py`.
**Discipline:** If a scenario's gold answer conflicts with this rubric, the rubric wins. Edit the rubric explicitly, with a justification in the commit message, then re-verify all scenarios against the new rules.

This rubric exists to answer the M9 zinger *"you wrote the scenarios AND the rubric — aren't you scoring against your own preferences?"* by making the rules public before the scoring artifacts are.

---

## §1 What counts as a "conflict"

Quoting the production system prompt (`config.py` SYSTEM_PROMPT, rules section):

> *"Only flag genuine conflicts — direct contradictions or materially different terms. Do NOT fabricate conflicts. If clauses cover different topics, they are not conflicts. If a clause is ambiguous rather than conflicting, flag it as LOW risk with explanation."*

This produces three eval rules:

**Rule 1 (conflict required).** A conflict EXISTS between a company clause C and a vendor clause V if and only if:
- C and V cover the same legal topic (same canonical-topic bucket — see §3), AND
- C and V impose different obligations, rights, or consequences on the parties, AND
- The difference is material (not stylistic rewording of the same substance).

**Rule 2 (no fabrication).** If C and V cover the same topic and impose the same substantive obligations in different wording, NO conflict exists. The agent should NOT flag.

**Rule 3 (topic mismatch).** If C and V cover different legal topics, NO conflict exists by definition. (Two unrelated clauses cannot conflict.)

**Rule 4 (ambiguity carve-out).** If C is genuinely ambiguous (multiple reasonable interpretations) AND vendor V exists on the same topic, the agent MAY flag the conflict as LOW risk — but flagging is not required. This makes ambiguity a gray zone; the `ambiguous` tier of scenarios tests where the gray zone lives.

---

## §2 4-tier risk taxonomy

Quoting the production system prompt risk guidance verbatim:

> *Risk level guidance:*
> *- CRITICAL: liability caps, indemnification, IP ownership, termination rights, governing law, arbitration*
> *- HIGH: payment terms, penalties, breach consequences, confidentiality, exclusivity, auto-renewal*
> *- MEDIUM: notice periods, amendments, assignment, subcontracting, insurance, force majeure*
> *- LOW: ambiguous clauses, minor inconsistencies*

This becomes the canonical-risk lookup. The deterministic encoding in `rubric_audit.py`:

```
TOPIC_TO_CANONICAL_RISK = {
    "liability_cap":         "CRITICAL",
    "indemnification":       "CRITICAL",
    "ip_ownership":          "CRITICAL",
    "termination_rights":    "CRITICAL",
    "governing_law":         "CRITICAL",
    "arbitration":           "CRITICAL",
    "payment_terms":         "HIGH",
    "penalties":             "HIGH",
    "breach_consequences":   "HIGH",
    "confidentiality":       "HIGH",
    "exclusivity":           "HIGH",
    "auto_renewal":          "HIGH",
    "notice_periods":        "MEDIUM",
    "amendments":            "MEDIUM",
    "assignment":            "MEDIUM",
    "subcontracting":        "MEDIUM",
    "insurance":             "MEDIUM",
    "force_majeure":         "MEDIUM",
    "ambiguous_clause":      "LOW",
    "minor_inconsistency":   "LOW",
}
```

**Adjacent-tier tolerance.** Some topics are genuine borderlines. The `acceptable_risks` set per scenario lets a scenario admit (for example) both CRITICAL and HIGH as defensible for a payment-terms-with-penalty-clause hybrid. The rubric is strict where strictness is defensible and lenient where it's not.

**The "LOW for ambiguous" rule.** Per the production system prompt's last bullet, ambiguous-but-not-clearly-conflicting clauses get LOW. This is what makes the `ambiguous` tier of scenarios accept variable conflict counts: a scenario can have 2 clearly-CRITICAL conflicts and 3 maybe-clauses, with acceptable_total_conflicts of `{2, 5}` depending on how generous the agent's interpretation of "material" is.

---

## §3 Canonical-topic lookup (for matching predicted ↔ gold conflicts)

The agent emits a `topic` field per conflict (free-text short string, e.g., "Liability cap" or "Indemnification scope"). The eval matches predicted topics to gold topics via:

1. Lowercase + strip + normalize whitespace.
2. Look up in `TOPIC_SYNONYMS` (deterministic mapping in `rubric_audit.py`):

```
TOPIC_SYNONYMS = {
    "liability_cap": [
        "liability cap", "limitation of liability", "liability limit",
        "cap on liability", "liability ceiling", "damages cap"
    ],
    "indemnification": [
        "indemnification", "indemnity", "hold harmless",
        "indemnification scope", "indemnification clause"
    ],
    "ip_ownership": [
        "ip ownership", "intellectual property", "work product",
        "ownership of work", "ip assignment", "ip rights"
    ],
    "termination_rights": [
        "termination", "termination rights", "right to terminate",
        "termination for convenience", "termination for cause"
    ],
    "governing_law": [
        "governing law", "choice of law", "applicable law",
        "jurisdiction", "venue"
    ],
    "arbitration": [
        "arbitration", "dispute resolution", "mediation",
        "binding arbitration", "arbitration clause"
    ],
    "payment_terms": [
        "payment terms", "payment", "invoice", "net 30", "net 60",
        "net 90", "payment schedule", "due date"
    ],
    "penalties": [
        "penalties", "late fee", "late payment", "default penalty"
    ],
    "confidentiality": [
        "confidentiality", "non-disclosure", "nda", "trade secrets"
    ],
    "exclusivity": [
        "exclusivity", "exclusive", "non-compete", "exclusive dealing"
    ],
    "auto_renewal": [
        "auto-renewal", "automatic renewal", "renewal", "evergreen clause"
    ],
    "notice_periods": [
        "notice", "notice period", "notice requirement", "advance notice"
    ],
    "amendments": [
        "amendments", "amendment", "modification", "changes to agreement"
    ],
    "assignment": [
        "assignment", "assignability", "transfer of agreement"
    ],
    "subcontracting": [
        "subcontracting", "subcontractors", "delegation"
    ],
    "insurance": [
        "insurance", "insurance requirements", "coverage"
    ],
    "force_majeure": [
        "force majeure", "act of god", "uncontrollable circumstances"
    ],
    "warranty": [
        "warranty", "warranties", "representations and warranties"
    ],
    "breach_consequences": [
        "breach", "material breach", "cure period", "remedies for breach"
    ],
}
```

A predicted topic matches a gold topic if BOTH normalize to the same canonical bucket key. The agent does NOT need to use the exact wording in the lookup — substring match against synonym values suffices.

**Unknown topic handling.** If the agent's predicted topic doesn't map to any canonical bucket via synonyms, the conflict is recorded as `unmatched_predicted` and counts as a false positive unless the scenario's gold conflicts also have an unmatched topic the predicted one could be assigned to.

---

## §4 The `favor` field decision rule

Quoting the production system prompt verbatim:

> *"favor: 'Company' or 'Vendor' — from the company's perspective, which party's language gives the company the stronger position: 'Company' if the company's standard terms are more protective of the company's interests and should be retained; 'Vendor' only if the vendor's proposed terms are genuinely more favorable or balanced from the company's standpoint"*

**Rule (favor):** For each gold conflict, the rubric specifies a `canonical_favor` of `Company` or `Vendor`:
- `canonical_favor = Company` if the company's clause is more protective of the company's interests.
- `canonical_favor = Vendor` if the vendor's clause is genuinely more favorable to the company (rare but defensible).

**Acceptable_favors set.** Some clauses are genuinely balanced — neither party's wording is clearly better for the company. These scenarios set `acceptable_favors = {Company, Vendor}` (both defensible). The strict-favor metric counts only the canonical answer; the lenient-favor metric accepts any answer in the set.

**Common trap encoded explicitly.** Payment terms — longer payment windows (net 90 vs net 30) favor the *payer*, not the *payee*. If the company is the payer (most B2B agreements), the company's net-90 clause favors the *company*. The agent must reason about who pays whom, not just which number is bigger. The `severity_tiering` and `ambiguous` tiers include at least one payment-terms scenario specifically to catch this trap.

---

## §5 What this rubric does NOT cover (admitted edges)

This rubric is deliberately silent on:

1. **Resolution-language quality.** The agent emits a `resolution` field per conflict (suggested compromise wording). Whether the suggested wording is legally sound is out of scope for this eval — that would require an LLM-as-judge harness with attorney calibration. The `eval/RUBRIC.md` here scores conflict *detection*, not resolution *drafting*.
2. **Jurisdiction-specific reasoning.** "Governing law" conflicts are flagged as CRITICAL, but the rubric does not require the agent to reason about Delaware vs New York case law. Surfacing the conflict is enough; resolving it is the lawyer's job.
3. **Adversarial topic categories.** If the contract concerns something exotic (e.g., crypto-asset custody, AI model licensing) where the canonical-topic lookup has gaps, the agent's predicted topic might not match anything in `TOPIC_SYNONYMS`. This is treated as a rubric gap and the scenario is excluded from canonical-topic scoring — counted only under total-count calibration.
4. **Conflict-of-laws disputes.** If contract A says "governed by New York law" and contract B says "governed by California law", that's a conflict (canonical_topic=governing_law). The rubric does NOT require the agent to determine which jurisdiction wins under conflict-of-laws principles.
5. **Severity-tier borderlines.** The risk taxonomy has known edges (e.g., is a "subcontracting" clause that materially changes liability exposure CRITICAL or MEDIUM?). The `severity_tiering` tier explicitly tests these borderlines; scenarios in that tier accept multi-tier answers via `acceptable_risks`.

---

## §6 Programmatic encoding (`eval/rubric_audit.py`)

The deterministic subset of this rubric is encoded as a Python function:

```python
def rubric_canonical_conflicts(
    company_clauses: list[Clause],
    vendor_clauses: list[Clause],
) -> list[CanonicalConflict]:
    """Given two clause lists, emit the canonical conflict list."""
```

Where:
- `Clause` has `section`, `text`, `party`, and optionally `canonical_topic` (annotated by the scenario author).
- `CanonicalConflict` has `canonical_topic`, `canonical_risk` (from TOPIC_TO_CANONICAL_RISK), `canonical_favor`, gold section references.

The function applies Rules 1-4 in §1 plus the canonical-risk lookup in §2 plus the favor rule in §4. It deliberately does NOT cover ambiguity-tier carve-outs (Rule 4's "MAY flag") — those scenarios mark their conflicts manually with `is_optional=True` so the rubric audit accepts both inclusion and exclusion.

**Test discipline.** `tests/test_scenarios.py` calls `rubric_canonical_conflicts()` on every scenario's clause arrays and verifies that the gold answer is consistent with the rubric. If a scenario's gold says "no conflict" but the rubric says "conflict exists with topic=X, risk=Y", the test FAILS and forces me to either fix the scenario or update the rubric explicitly.

---

## §7 Rubric change log

| Date | Change | Justification |
|---|---|---|
| 2026-06-14 | Initial commit | Day 1 scaffold; mirrors production system prompt rules |

Any future change to this rubric must add a row here AND have a commit message referencing the row, AND must be followed by a rerun of `test_scenarios.py` to verify all scenarios still pass.

---

*This rubric is the contract between the scenarios and the scorers. The scenarios encode what conflicts exist; the scorers measure how well the agent finds them; the rubric is what both refer back to. If you disagree with the eval, this is the artifact to argue against — not the scenarios, not the scores.*
