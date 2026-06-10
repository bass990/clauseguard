const PptxGenJS = require("pptxgenjs");

const pres = new PptxGenJS();
pres.layout = "LAYOUT_16x9";
pres.title = "ClauseGuard — The Agentic Loop";
pres.author = "Agentic AI Class — Project 1/3";

// ── PALETTE ──────────────────────────────────────────────────────────────────
const NAVY    = "1E3A5F";
const NAVY_LT = "2D5282";
const NAVY_XL = "EBF2FB";
const PURPLE  = "7C3AED";
const PURP_LT = "F5F0FF";
const INK     = "0F172A";
const MUTED   = "64748B";
const BORDER  = "E2E8F0";
const WHITE   = "FFFFFF";
const SURFACE = "F8FAFC";
const GREEN   = "16A34A";
const GREEN_BG = "F0FDF4";

// ── HELPERS ───────────────────────────────────────────────────────────────────
const makeShadow = () => ({ type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.08 });

function slideBase(slide, dark = false) {
  slide.background = { color: dark ? NAVY : WHITE };
}

function navyHeader(s, title, sub = "") {
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText(title, {
    x: 0.5, y: 0, w: sub ? 6.5 : 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });
  if (sub) {
    s.addText(sub, {
      x: 0.5, y: 0, w: 9, h: 0.85,
      fontSize: 10, fontFace: "Calibri", color: "CADCFC",
      align: "right", valign: "middle", margin: 0
    });
  }
}

function codeBlock(s, text, x, y, w, h, fontSize = 9) {
  s.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: "0F172A" }, line: { color: "1E293B" }
  });
  s.addText(text, {
    x: x + 0.12, y, w: w - 0.15, h,
    fontSize, fontFace: "Courier New", color: "7DD3FC",
    valign: "middle", margin: 0
  });
}

function labelBox(s, label, x, y, color = NAVY) {
  const w = label.length * 0.082 + 0.22;
  s.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h: 0.24,
    fill: { color }, line: { color }
  });
  s.addText(label, {
    x, y, w, h: 0.24,
    fontSize: 8, fontFace: "Calibri", bold: true,
    color: WHITE, align: "center", valign: "middle", margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 1 — TITLE
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s, true);

  // Left navy block
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 6.2, h: 5.625,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: PURPLE }, line: { color: PURPLE }
  });

  s.addText("The Agentic Loop", {
    x: 0.4, y: 1.1, w: 5.5, h: 1.1,
    fontSize: 42, fontFace: "Georgia", bold: true,
    color: WHITE, align: "left", margin: 0
  });
  s.addText("How ClauseGuard talks to Claude", {
    x: 0.4, y: 2.25, w: 5.5, h: 0.45,
    fontSize: 16, fontFace: "Calibri Light", italic: true,
    color: "CADCFC", align: "left", margin: 0
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 2.85, w: 4.5, h: 0.025,
    fill: { color: PURPLE, transparency: 40 }, line: { color: PURPLE, transparency: 40 }
  });
  s.addText("A step-by-step walkthrough of the agentic loop —\nfrom file upload to final report.", {
    x: 0.4, y: 3.05, w: 5.5, h: 0.7,
    fontSize: 12, fontFace: "Calibri", color: "94B8D4",
    align: "left", margin: 0
  });
  s.addText([
    { text: "Project 1/3  ·  Agentic AI & Process Automation", options: { breakLine: true } },
    { text: "BUAN 6v99.s01  ·  UT Dallas  ·  April 2026" }
  ], {
    x: 0.4, y: 4.5, w: 5.5, h: 0.7,
    fontSize: 10, fontFace: "Calibri", color: "7A9BBF",
    align: "left", margin: 0
  });

  // Right panel — turn counter
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.4, y: 1.2, w: 3.2, h: 3.1,
    fill: { color: WHITE }, line: { color: WHITE }, shadow: makeShadow()
  });
  s.addText("4", {
    x: 6.4, y: 1.3, w: 3.2, h: 1.4,
    fontSize: 88, fontFace: "Georgia", bold: true,
    color: NAVY, align: "center", valign: "middle", margin: 0
  });
  s.addText("turns with Claude", {
    x: 6.4, y: 2.75, w: 3.2, h: 0.38,
    fontSize: 13, fontFace: "Calibri", color: MUTED,
    align: "center", margin: 0
  });
  s.addText("2 tools dispatched · 1 report produced", {
    x: 6.4, y: 3.18, w: 3.2, h: 0.35,
    fontSize: 10, fontFace: "Calibri", color: PURPLE,
    align: "center", bold: true, margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 2 — THE MESSAGES ARRAY
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);
  navyHeader(s, "The Messages Array", "The loop's memory — grows with every exchange");

  s.addText("Before the loop starts, the server creates a messages array — the running transcript of the entire conversation between the server and Claude. Every message ever sent or received gets appended here. This is how Claude knows where it is in the workflow.", {
    x: 0.5, y: 1.0, w: 9, h: 0.65,
    fontSize: 11, fontFace: "Calibri", color: INK,
    align: "left", margin: 0
  });

  // Initial state
  s.addText("INITIAL STATE  —  1 message", {
    x: 0.5, y: 1.75, w: 9, h: 0.28,
    fontSize: 9, fontFace: "Calibri", bold: true, color: MUTED, margin: 0
  });
  codeBlock(s,
    `messages = [\n  { role: "user", content: "Analyze contract_a.pdf and contract_b.pdf. Follow your workflow." }\n]`,
    0.5, 2.05, 9, 0.72, 9.5
  );

  // After full run
  s.addText("AFTER FULL RUN  —  7 messages", {
    x: 0.5, y: 2.9, w: 9, h: 0.28,
    fontSize: 9, fontFace: "Calibri", bold: true, color: MUTED, margin: 0
  });

  const msgs = [
    { role: "user",      content: '"Analyze contract_a.pdf and contract_b.pdf..."',            color: NAVY_LT },
    { role: "assistant", content: '[tool_use]  extract_clauses(contract_a.pdf, "company")',    color: PURPLE },
    { role: "user",      content: '[tool_result]  { clauses: [...80 clauses from Contract A] }', color: NAVY_LT },
    { role: "assistant", content: '[tool_use]  extract_clauses(contract_b.pdf, "vendor")',     color: PURPLE },
    { role: "user",      content: '[tool_result]  { clauses: [...95 clauses from Contract B] }', color: NAVY_LT },
    { role: "assistant", content: '[tool_use]  generate_redline_brief([...10 conflicts...])',  color: PURPLE },
    { role: "user",      content: '[tool_result]  { success: true, report: {...} }',           color: NAVY_LT },
  ];

  msgs.forEach((m, i) => {
    const x = 0.5;
    const y = 3.2 + i * 0.3;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 9, h: 0.26,
      fill: { color: m.role === "assistant" ? PURP_LT : NAVY_XL },
      line: { color: m.role === "assistant" ? "DDD6FE" : BORDER }
    });
    s.addText(m.role === "assistant" ? "CLAUDE" : "SERVER", {
      x: x + 0.08, y, w: 0.85, h: 0.26,
      fontSize: 7.5, fontFace: "Calibri", bold: true,
      color: m.role === "assistant" ? PURPLE : NAVY,
      valign: "middle", margin: 0
    });
    s.addText(m.content, {
      x: x + 1.0, y, w: 7.9, h: 0.26,
      fontSize: 8.5, fontFace: "Courier New",
      color: INK, valign: "middle", margin: 0
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 3 — TURN 1: Claude reads transcript, requests extract_clauses(A)
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);
  navyHeader(s, "Turn 1 — Claude Decides What To Do First", "stop_reason: tool_use");

  // Left — what the server sends
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 1.0, w: 4.2, h: 4.3,
    fill: { color: NAVY_XL }, line: { color: BORDER }, shadow: makeShadow()
  });
  s.addText("What the server sends", {
    x: 0.55, y: 1.1, w: 3.9, h: 0.3,
    fontSize: 10, fontFace: "Calibri", bold: true, color: NAVY, margin: 0
  });
  codeBlock(s,
    `client.messages.stream(\n  model: "claude-sonnet-4-6",\n  system: SYSTEM_PROMPT,\n  tools: [extract_clauses, generate_redline_brief],\n  messages: [ {role:"user", content:"Analyze..."} ]\n)`,
    0.55, 1.5, 3.9, 1.5, 8.5
  );
  s.addText("Claude receives:\n\n• Its role and instructions (system prompt)\n• The list of tools it's allowed to use\n• The messages array (currently just the user's request)", {
    x: 0.55, y: 3.1, w: 3.9, h: 1.95,
    fontSize: 10, fontFace: "Calibri", color: INK, margin: 0
  });

  // Right — what Claude responds with
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 1.0, w: 4.6, h: 4.3,
    fill: { color: PURP_LT }, line: { color: "DDD6FE" }, shadow: makeShadow()
  });
  s.addText("What Claude responds with", {
    x: 5.15, y: 1.1, w: 4.3, h: 0.3,
    fontSize: 10, fontFace: "Calibri", bold: true, color: PURPLE, margin: 0
  });
  codeBlock(s,
    `stop_reason: "tool_use"\n\ncontent: [\n  {\n    type: "tool_use",\n    name: "extract_clauses",\n    input: {\n      pdf_path: "uploads/.../contract_a.pdf",\n      party_label: "company"\n    }\n  }\n]`,
    5.15, 1.5, 4.3, 2.5, 8.5
  );
  s.addText('stop_reason: "tool_use" means:\n"I\'m not done — run this function for me and report back."', {
    x: 5.15, y: 4.1, w: 4.3, h: 0.9,
    fontSize: 10, fontFace: "Calibri", color: INK,
    italic: true, margin: 0
  });

  labelBox(s, "API CALL #1", 0.55, 0.95, NAVY);
  labelBox(s, "CLAUDE'S DECISION", 5.15, 0.95, PURPLE);
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 4 — TOOL DISPATCH: extract_clauses(A)
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);
  navyHeader(s, "Tool Dispatch — Server Runs extract_clauses( )", "Claude can't open files — the server does it on its behalf");

  // Step flow
  const steps = [
    { n: "1", title: "Look up the function", body: 'Server reads block.name ("extract_clauses") and finds the matching Python function in TOOL_MAP.', color: NAVY },
    { n: "2", title: "Call it with Claude's inputs", body: 'extract_clauses(pdf_path="contract_a.pdf", party_label="company") is called directly in Python.', color: NAVY_LT },
    { n: "3", title: "PyMuPDF opens the PDF", body: "fitz.open() reads the file, extracts all text page by page, checks it isn't a scanned image.", color: PURPLE },
    { n: "4", title: "Split into clauses", body: 'Regex finds section headings ("3.1 Liability", "Article IV"). Each heading + its text = one clause object.', color: "065A82" },
    { n: "5", title: "Return result to loop", body: "{ success: true, party: 'company', clause_count: 80, clauses: [...] } is wrapped in a tool_result message and appended to messages[].", color: GREEN },
  ];

  steps.forEach((st, i) => {
    const x = 0.4;
    const y = 1.05 + i * 0.84;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 9.2, h: 0.72,
      fill: { color: SURFACE }, line: { color: BORDER }
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.45, h: 0.72,
      fill: { color: st.color }, line: { color: st.color }
    });
    s.addText(st.n, {
      x, y, w: 0.45, h: 0.72,
      fontSize: 14, fontFace: "Georgia", bold: true,
      color: WHITE, align: "center", valign: "middle", margin: 0
    });
    s.addText(st.title, {
      x: 0.6, y: y + 0.06, w: 3.5, h: 0.26,
      fontSize: 10.5, fontFace: "Calibri", bold: true, color: INK, margin: 0
    });
    s.addText(st.body, {
      x: 0.6, y: y + 0.34, w: 8.9, h: 0.3,
      fontSize: 9.5, fontFace: "Calibri", color: MUTED, margin: 0
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 5 — TURN 2 & 3: Contract B + Legal Reasoning
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);
  navyHeader(s, "Turns 2 & 3 — Read Contract B, Then Think", "The same pattern repeats, then Claude reasons on its own");

  // Turn 2 card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 1.05, w: 4.2, h: 3.9,
    fill: { color: NAVY_XL }, line: { color: BORDER }, shadow: makeShadow()
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 1.05, w: 4.2, h: 0.42,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Turn 2 — Extract Contract B", {
    x: 0.5, y: 1.05, w: 4.0, h: 0.42,
    fontSize: 11, fontFace: "Calibri", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });
  s.addText('The server sends the updated messages array — now including Contract A\'s 80 clauses — back to Claude.\n\nClaude sees it already has Contract A. It issues the same tool call again, this time for Contract B with party_label: "vendor".\n\nTool dispatch runs again. Contract B\'s 95 clauses are extracted and appended to messages[].', {
    x: 0.55, y: 1.6, w: 3.9, h: 2.3,
    fontSize: 10.5, fontFace: "Calibri", color: INK, margin: 0
  });
  codeBlock(s, 'extract_clauses(\n  pdf_path: "contract_b.pdf",\n  party_label: "vendor"\n)', 0.55, 3.95, 3.9, 0.72, 9);

  // Turn 3 card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 1.05, w: 4.6, h: 3.9,
    fill: { color: PURP_LT }, line: { color: "DDD6FE" }, shadow: makeShadow()
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 1.05, w: 4.6, h: 0.42,
    fill: { color: PURPLE }, line: { color: PURPLE }
  });
  s.addText("Turn 3 — The Legal Reasoning Happens", {
    x: 5.1, y: 1.05, w: 4.4, h: 0.42,
    fontSize: 11, fontFace: "Calibri", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });
  s.addText("Claude now has both clause lists sitting in its context window simultaneously.\n\nThis is the most important step — and there is no Python code doing the work here. Claude reads every clause from both contracts side by side and reasons through them semantically, the way a lawyer would.\n\nIt identifies direct contradictions, mismatched obligations, and incompatible rights. Then it calls generate_redline_brief() with the full structured conflict array.", {
    x: 5.15, y: 1.6, w: 4.3, h: 3.2,
    fontSize: 10.5, fontFace: "Calibri", color: INK, margin: 0
  });

  // Key callout
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.15, y: 4.1, w: 4.3, h: 0.55,
    fill: { color: PURPLE }, line: { color: PURPLE }
  });
  s.addText("No Python algorithm — Claude's legal reasoning IS the conflict detection.", {
    x: 5.25, y: 4.1, w: 4.1, h: 0.55,
    fontSize: 10, fontFace: "Calibri", bold: true, italic: true,
    color: WHITE, valign: "middle", margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 6 — TURN 4: end_turn + cleanup
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);
  navyHeader(s, "Turn 4 — Claude Signals It's Done", 'stop_reason: "end_turn"');

  s.addText("After generate_redline_brief() returns successfully, the server sends the transcript one final time. Claude sees the report was generated. It responds with a short plain-text message and a stop_reason of \"end_turn\" — its signal that the task is complete.", {
    x: 0.5, y: 1.0, w: 9, h: 0.7,
    fontSize: 11, fontFace: "Calibri", color: INK, margin: 0
  });

  // Three final action cards
  const cards = [
    {
      title: "Loop exits",
      body: 'The while loop checks stop_reason == "end_turn" and breaks. The 20-turn safety limit is never reached in a healthy run.',
      color: NAVY, bg: NAVY_XL
    },
    {
      title: "SSE fires to browser",
      body: 'The server emits a "complete" Server-Sent Event carrying the full redline_report as JSON. The browser receives it and renders the results.',
      color: PURPLE, bg: PURP_LT
    },
    {
      title: "Files deleted",
      body: "The finally block runs shutil.rmtree() on the session folder. Uploaded PDFs are gone — whether the run succeeded, hit an error, or the tab closed.",
      color: GREEN, bg: GREEN_BG
    },
  ];

  cards.forEach((c, i) => {
    const x = 0.4 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 2.95, h: 2.85,
      fill: { color: c.bg }, line: { color: c.color, width: 0.75 }, shadow: makeShadow()
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.9, w: 2.95, h: 0.44,
      fill: { color: c.color }, line: { color: c.color }
    });
    s.addText(c.title, {
      x: x + 0.12, y: 1.9, w: 2.7, h: 0.44,
      fontSize: 12, fontFace: "Calibri", bold: true,
      color: WHITE, valign: "middle", margin: 0
    });
    s.addText(c.body, {
      x: x + 0.12, y: 2.44, w: 2.7, h: 2.2,
      fontSize: 10.5, fontFace: "Calibri", color: INK, margin: 0
    });
  });

  // Code snippet
  codeBlock(s,
    `if response.stop_reason == "end_turn":\n    yield sse("complete", redline_report)\n    return\n\n# finally block always runs:\nfinally:\n    shutil.rmtree(session_dir, ignore_errors=True)`,
    0.4, 4.9, 9.2, 0.58, 9
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 7 — THE FULL PICTURE
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s, true);
  navyHeader(s, "The Full Loop — End to End", "4 turns · 3 tool dispatches · 1 report");

  const steps = [
    { actor: "SERVER",  msg: 'messages[ ] → Claude: "Analyze contract_a.pdf and contract_b.pdf"',               color: NAVY_LT,  bg: "162D4A" },
    { actor: "CLAUDE",  msg: 'stop_reason: tool_use  →  extract_clauses(contract_a.pdf, "company")',            color: PURPLE,   bg: "1E1040" },
    { actor: "SERVER",  msg: "tool_result → { success: true, clause_count: 80, clauses: [...] }",               color: NAVY_LT,  bg: "162D4A" },
    { actor: "CLAUDE",  msg: 'stop_reason: tool_use  →  extract_clauses(contract_b.pdf, "vendor")',             color: PURPLE,   bg: "1E1040" },
    { actor: "SERVER",  msg: "tool_result → { success: true, clause_count: 95, clauses: [...] }",               color: NAVY_LT,  bg: "162D4A" },
    { actor: "CLAUDE",  msg: "[reasons over 175 clauses] → generate_redline_brief([10 conflicts])",             color: PURPLE,   bg: "1E1040" },
    { actor: "SERVER",  msg: "tool_result → { success: true, report: { CRITICAL: 2, HIGH: 3, ... } }",         color: NAVY_LT,  bg: "162D4A" },
    { actor: "CLAUDE",  msg: 'stop_reason: end_turn  →  "Analysis complete. Redline brief generated."',        color: GREEN,    bg: "062010" },
    { actor: "BROWSER", msg: 'SSE "complete" event received → results render on screen',                       color: "F59E0B", bg: "1C1408" },
  ];

  steps.forEach((st, i) => {
    const y = 1.05 + i * 0.5;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.4, y, w: 9.2, h: 0.42,
      fill: { color: st.bg }, line: { color: "243F60" }
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.4, y, w: 1.05, h: 0.42,
      fill: { color: st.color + "33" }, line: { color: st.color + "33" }
    });
    s.addText(st.actor, {
      x: 0.4, y, w: 1.05, h: 0.42,
      fontSize: 7.5, fontFace: "Calibri", bold: true,
      color: st.color, align: "center", valign: "middle", margin: 0
    });
    s.addText(st.msg, {
      x: 1.55, y, w: 7.9, h: 0.42,
      fontSize: 9.5, fontFace: "Courier New",
      color: "CBD5E1", valign: "middle", margin: 0
    });
  });

  s.addText("Claude drives the workflow. The server executes. The messages array is the shared memory.", {
    x: 0.4, y: 5.65, w: 9.2, h: 0.24,
    fontSize: 9.5, fontFace: "Calibri", italic: true,
    color: "7A9BBF", align: "center", margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 8 — KEY INSIGHT
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s, true);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: 5.625,
    fill: { color: PURPLE }, line: { color: PURPLE }
  });

  s.addText("The key insight", {
    x: 0.5, y: 0.8, w: 9, h: 0.6,
    fontSize: 16, fontFace: "Calibri", color: "7A9BBF",
    align: "center", margin: 0
  });
  s.addText("Claude decides.\nThe server executes.", {
    x: 0.5, y: 1.45, w: 9, h: 1.6,
    fontSize: 44, fontFace: "Georgia", bold: true,
    color: WHITE, align: "center", margin: 0
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 2.5, y: 3.2, w: 5, h: 0.05,
    fill: { color: PURPLE, transparency: 40 }, line: { color: PURPLE, transparency: 40 }
  });

  const points = [
    { label: "Messages array", desc: "is the shared memory — both sides read and write to it" },
    { label: "tool_use",       desc: "means Claude is mid-task and needs the server to act" },
    { label: "end_turn",       desc: "means Claude is satisfied — loop exits, report delivered" },
    { label: "finally block",  desc: "guarantees cleanup regardless of what went wrong" },
  ];

  points.forEach((p, i) => {
    const x = i < 2 ? 0.6 : 5.2;
    const y = 3.45 + (i % 2) * 0.88;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 4.2, h: 0.72,
      fill: { color: "162D4A" }, line: { color: "243F60" }
    });
    s.addText(p.label, {
      x: x + 0.12, y: y + 0.06, w: 3.9, h: 0.26,
      fontSize: 11, fontFace: "Courier New", bold: true,
      color: "7DD3FC", margin: 0
    });
    s.addText(p.desc, {
      x: x + 0.12, y: y + 0.35, w: 3.9, h: 0.28,
      fontSize: 9.5, fontFace: "Calibri", color: "94A3B8", margin: 0
    });
  });

  s.addText("Project 1/3  ·  BUAN 6v99.s01  ·  UT Dallas  ·  April 2026", {
    x: 0.5, y: 5.25, w: 9, h: 0.25,
    fontSize: 9, fontFace: "Calibri", color: "4A6A8A",
    align: "center", margin: 0
  });
}

// ── WRITE FILE ────────────────────────────────────────────────────────────────
pres.writeFile({ fileName: "ClauseGuard_Loop_Presentation.pptx" })
  .then(() => console.log("Done: ClauseGuard_Loop_Presentation.pptx"))
  .catch(err => { console.error(err); process.exit(1); });
