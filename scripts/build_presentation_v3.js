const PptxGenJS = require("pptxgenjs");

const pres = new PptxGenJS();
pres.layout = "LAYOUT_16x9";
pres.title = "ClauseGuard — Contract Conflict Detector";
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

const CRIT  = "DC2626"; const CRIT_BG  = "FEF2F2";
const HIGH  = "EA580C"; const HIGH_BG  = "FFF7ED";
const MED   = "D97706"; const MED_BG   = "FFFBEB";
const LOW   = "16A34A"; const LOW_BG   = "F0FDF4";

// ── HELPERS ───────────────────────────────────────────────────────────────────
const makeShadow = () => ({ type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.08 });

function slideBase(slide, dark = false) {
  slide.background = { color: dark ? NAVY : WHITE };
}

function addTag(slide, text, x, y, color, bgColor) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w: text.length * 0.085 + 0.25, h: 0.26,
    fill: { color: bgColor }, line: { color: bgColor }
  });
  slide.addText(text, {
    x, y, w: text.length * 0.085 + 0.25, h: 0.26,
    fontSize: 9, fontFace: "Calibri", bold: true,
    color, align: "center", valign: "middle", margin: 0
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

  // Accent purple bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: PURPLE }, line: { color: PURPLE }
  });

  // Title
  s.addText("ClauseGuard", {
    x: 0.4, y: 1.3, w: 5.5, h: 1.1,
    fontSize: 52, fontFace: "Georgia", bold: true,
    color: WHITE, align: "left", margin: 0
  });

  s.addText("Contract Conflict Detector", {
    x: 0.4, y: 2.45, w: 5.5, h: 0.45,
    fontSize: 18, fontFace: "Calibri Light", italic: true,
    color: "CADCFC", align: "left", margin: 0
  });

  // Divider
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 3.05, w: 4.5, h: 0.025,
    fill: { color: PURPLE, transparency: 40 }, line: { color: PURPLE, transparency: 40 }
  });

  s.addText("Find every conflict — before you sign.", {
    x: 0.4, y: 3.2, w: 5.5, h: 0.4,
    fontSize: 13, fontFace: "Calibri", color: "94B8D4",
    align: "left", margin: 0
  });

  // Meta
  s.addText([
    { text: "Project 1/3  ·  Week 1  ·  Agentic AI & Process Automation", options: { breakLine: true } },
    { text: "BUAN 6v99.s01  ·  UT Dallas  ·  April 2026" }
  ], {
    x: 0.4, y: 4.5, w: 5.5, h: 0.7,
    fontSize: 10, fontFace: "Calibri", color: "7A9BBF",
    align: "left", margin: 0
  });

  // Right panel white card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.3, y: 1.3, w: 3.4, h: 2.8,
    fill: { color: WHITE }, line: { color: WHITE }
  });
  s.addText("60s", {
    x: 6.3, y: 1.4, w: 3.4, h: 1.3,
    fontSize: 80, fontFace: "Georgia", bold: true,
    color: NAVY, align: "center", valign: "middle", margin: 0
  });
  s.addText("to a complete redline brief", {
    x: 6.3, y: 2.75, w: 3.4, h: 0.4,
    fontSize: 13, fontFace: "Calibri", color: MUTED,
    align: "center", margin: 0
  });
  s.addText("vs. 4 hours of lawyer time", {
    x: 6.3, y: 3.2, w: 3.4, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: PURPLE,
    align: "center", bold: true, margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 2 — THE PROBLEM
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("The Problem", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });

  // Big quote
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.05, w: 9, h: 1.5,
    fill: { color: NAVY_XL }, line: { color: NAVY_XL }
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.05, w: 0.07, h: 1.5,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText(
    "Every vendor contract contains clauses that silently conflict with your standard terms — and nobody catches them until it's too late.",
    {
      x: 0.75, y: 1.1, w: 8.6, h: 1.4,
      fontSize: 15, fontFace: "Georgia", italic: true,
      color: NAVY, valign: "middle", margin: 0
    }
  );

  // 3 pain cards
  const cards = [
    { icon: "$", title: "$400/hr", sub: "junior lawyer rate\nfor manual review", color: CRIT, bg: CRIT_BG },
    { icon: "⏱", title: "3–5 hrs", sub: "per contract\nmanual comparison", color: HIGH, bg: HIGH_BG },
    { icon: "✗", title: "Missed clauses", sub: "discovered only\nafter signing", color: MED, bg: MED_BG },
  ];
  cards.forEach((c, i) => {
    const x = 0.5 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.85, w: 2.9, h: 1.9,
      fill: { color: c.bg }, line: { color: c.color, width: 1 },
      shadow: makeShadow()
    });
    s.addText(c.title, {
      x: x + 0.15, y: 2.95, w: 2.6, h: 0.6,
      fontSize: 26, fontFace: "Georgia", bold: true,
      color: c.color, align: "center", margin: 0
    });
    s.addText(c.sub, {
      x: x + 0.15, y: 3.6, w: 2.6, h: 0.9,
      fontSize: 11, fontFace: "Calibri", color: INK,
      align: "center", margin: 0
    });
  });

  s.addText("Who feels this pain: Law firms · Procurement teams · Startups signing vendor deals", {
    x: 0.5, y: 4.95, w: 9, h: 0.35,
    fontSize: 10, fontFace: "Calibri", color: MUTED,
    align: "center", italic: true, margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 3 — THE SOLUTION
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("The Solution", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });

  s.addText("Upload two PDFs. ClauseGuard does the rest.", {
    x: 0.5, y: 1.05, w: 9, h: 0.5,
    fontSize: 16, fontFace: "Georgia", italic: true,
    color: NAVY, align: "center", margin: 0
  });

  // Flow steps
  const steps = [
    { n: "1", label: "Extract clauses\nfrom both PDFs", color: NAVY },
    { n: "2", label: "Semantic\nconflict analysis", color: NAVY_LT },
    { n: "3", label: "Risk\nassessment", color: PURPLE },
    { n: "4", label: "Redline brief\n+ PDF export", color: "065A82" },
  ];

  steps.forEach((st, i) => {
    const x = 0.7 + i * 2.2;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.75, w: 1.8, h: 1.8,
      fill: { color: st.color }, line: { color: st.color },
      shadow: makeShadow()
    });
    s.addText(st.n, {
      x, y: 1.85, w: 1.8, h: 0.6,
      fontSize: 28, fontFace: "Georgia", bold: true,
      color: WHITE, align: "center", margin: 0
    });
    s.addText(st.label, {
      x, y: 2.5, w: 1.8, h: 0.9,
      fontSize: 10.5, fontFace: "Calibri", color: "CADCFC",
      align: "center", margin: 0
    });
    // Arrow
    if (i < 3) {
      s.addShape(pres.shapes.LINE, {
        x: x + 1.82, y: 2.65, w: 0.36, h: 0,
        line: { color: BORDER, width: 1.5 }
      });
      s.addText("›", {
        x: x + 1.97, y: 2.5, w: 0.25, h: 0.35,
        fontSize: 14, fontFace: "Calibri", color: MUTED,
        align: "center", margin: 0
      });
    }
  });

  // Output preview
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.75, w: 9, h: 1.55,
    fill: { color: SURFACE }, line: { color: BORDER }, shadow: makeShadow()
  });
  s.addText("Sample output:", {
    x: 0.75, y: 3.85, w: 2, h: 0.3,
    fontSize: 9, fontFace: "Calibri", bold: true, color: MUTED, margin: 0
  });

  const conflicts = [
    { risk: "CRITICAL", topic: "Liability cap", detail: "3-month cap vs. 12-month + unlimited for IP claims", color: CRIT, bg: CRIT_BG },
    { risk: "HIGH",     topic: "Payment terms", detail: "Net 60 vs. Net 30 — 30-day gap in cash flow",         color: HIGH, bg: HIGH_BG },
    { risk: "HIGH",     topic: "IP ownership",  detail: "Company owns all work vs. Vendor retains all rights", color: HIGH, bg: HIGH_BG },
  ];
  conflicts.forEach((c, i) => {
    const x = 0.65 + i * 3.05;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.25, w: 2.85, h: 0.85,
      fill: { color: c.bg }, line: { color: c.color, width: 0.75 }
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 4.25, w: 0.06, h: 0.85,
      fill: { color: c.color }, line: { color: c.color }
    });
    s.addText(c.risk, {
      x: x + 0.12, y: 4.3, w: 1.2, h: 0.22,
      fontSize: 8, fontFace: "Calibri", bold: true, color: c.color, margin: 0
    });
    s.addText(c.topic, {
      x: x + 0.12, y: 4.52, w: 2.6, h: 0.22,
      fontSize: 10, fontFace: "Calibri", bold: true, color: INK, margin: 0
    });
    s.addText(c.detail, {
      x: x + 0.12, y: 4.74, w: 2.6, h: 0.3,
      fontSize: 8.5, fontFace: "Calibri", color: MUTED, margin: 0
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 4 — AGENT ARCHITECTURE
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Agent Architecture", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });
  s.addText("Built from scratch · Anthropic Claude SDK · No low-code platforms", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 10, fontFace: "Calibri", color: "CADCFC",
    align: "right", valign: "middle", margin: 0
  });

  // Left — tool list
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 1.0, w: 4.1, h: 4.3,
    fill: { color: SURFACE }, line: { color: BORDER }, shadow: makeShadow()
  });
  s.addText("The 2 Tools Claude Can Call", {
    x: 0.55, y: 1.1, w: 3.8, h: 0.35,
    fontSize: 11, fontFace: "Calibri", bold: true, color: NAVY, margin: 0
  });

  const tools = [
    { name: "extract_clauses()", desc: "Parses PDF → structured clause list per contract", color: NAVY },
    { name: "generate_redline_brief()", desc: "Compiles Claude's identified conflicts into a structured JSON report", color: PURPLE },
  ];
  tools.forEach((t, i) => {
    const y = 1.65 + i * 1.4;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.55, y, w: 3.8, h: 1.1,
      fill: { color: WHITE }, line: { color: BORDER }
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.55, y, w: 0.06, h: 1.1,
      fill: { color: t.color }, line: { color: t.color }
    });
    s.addText(t.name, {
      x: 0.72, y: y + 0.12, w: 3.5, h: 0.3,
      fontSize: 9.5, fontFace: "Courier New", bold: true, color: t.color, margin: 0
    });
    s.addText(t.desc, {
      x: 0.72, y: y + 0.5, w: 3.5, h: 0.45,
      fontSize: 9, fontFace: "Calibri", color: MUTED, margin: 0
    });
  });

  s.addText("Conflict detection and risk assignment happen inside Claude's reasoning — no Python heuristic needed.", {
    x: 0.55, y: 4.55, w: 3.8, h: 0.55,
    fontSize: 8.5, fontFace: "Calibri", italic: true, color: MUTED, margin: 0
  });

  // Right — loop diagram
  s.addShape(pres.shapes.RECTANGLE, {
    x: 4.9, y: 1.0, w: 4.7, h: 4.3,
    fill: { color: NAVY }, line: { color: NAVY }, shadow: makeShadow()
  });
  s.addText("Agentic Loop", {
    x: 5.1, y: 1.1, w: 4.3, h: 0.35,
    fontSize: 11, fontFace: "Calibri", bold: true, color: WHITE, margin: 0
  });

  const loopSteps = [
    "User uploads Contract A + Contract B",
    "Agent calls extract_clauses() × 2",
    "Claude reasons over both contracts — identifies conflicts, assigns risk levels",
    "Agent calls generate_redline_brief()",
    "Final report rendered in UI",
  ];
  loopSteps.forEach((step, i) => {
    const y = 1.6 + i * 0.67;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 5.1, y, w: 4.3, h: 0.55,
      fill: { color: i === 4 ? PURPLE : "1E3A5F" }, line: { color: i === 4 ? PURPLE : "2D5282" }
    });
    s.addText(`${i + 1}`, {
      x: 5.1, y, w: 0.35, h: 0.55,
      fontSize: 10, fontFace: "Calibri", bold: true,
      color: i === 4 ? WHITE : "CADCFC",
      align: "center", valign: "middle", margin: 0
    });
    s.addText(step, {
      x: 5.48, y, w: 3.8, h: 0.55,
      fontSize: 10, fontFace: "Calibri",
      color: WHITE, valign: "middle", margin: 0
    });
    if (i < 4) {
      s.addShape(pres.shapes.LINE, {
        x: 5.28, y: y + 0.55, w: 0, h: 0.12,
        line: { color: "2D5282", width: 1 }
      });
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 5 — BUILD vs BEND
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Why We BUILD — Not Bend", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });

  s.addText("Professor's 6-Dimension Framework Applied", {
    x: 0.5, y: 1.0, w: 9, h: 0.35,
    fontSize: 12, fontFace: "Calibri", italic: true, color: MUTED, align: "center", margin: 0
  });

  const dims = [
    { dim: "Control",         verdict: "BUILD", why: "Custom clause-matching logic — no platform handles domain-specific legal reasoning", score: 5 },
    { dim: "Cost",            verdict: "BUILD", why: "SDK ~$0.02/run vs. $500+/month for legal review platforms",                          score: 5 },
    { dim: "Time to Value",   verdict: "BUILD", why: "Demo-ready in one week. Single focused problem scope",                               score: 4 },
    { dim: "Integration",     verdict: "BUILD", why: "Proprietary PDF parsing + structured JSON output — non-standard data flow",          score: 5 },
    { dim: "Maintenance",     verdict: "HYBRID", why: "Team owns the reasoning logic; infra stays lean",                                   score: 3 },
    { dim: "Differentiation", verdict: "BUILD", why: "Core competitive moat — contract intelligence is the product",                      score: 5 },
  ];

  dims.forEach((d, i) => {
    const row = Math.floor(i / 2);
    const col = i % 2;
    const x = 0.4 + col * 4.85;
    const y = 1.5 + row * 1.1;

    const isB = d.verdict === "BUILD";
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 4.65, h: 0.95,
      fill: { color: isB ? NAVY_XL : PURP_LT },
      line: { color: isB ? NAVY : PURPLE, width: 0.75 },
      shadow: makeShadow()
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.06, h: 0.95,
      fill: { color: isB ? NAVY : PURPLE }, line: { color: isB ? NAVY : PURPLE }
    });
    s.addText(d.dim, {
      x: x + 0.12, y: y + 0.07, w: 1.5, h: 0.26,
      fontSize: 10, fontFace: "Calibri", bold: true, color: INK, margin: 0
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: x + 3.3, y: y + 0.09, w: 1.2, h: 0.24,
      fill: { color: isB ? NAVY : PURPLE }, line: { color: isB ? NAVY : PURPLE }
    });
    s.addText(d.verdict, {
      x: x + 3.3, y: y + 0.09, w: 1.2, h: 0.24,
      fontSize: 8, fontFace: "Calibri", bold: true, color: WHITE,
      align: "center", valign: "middle", margin: 0
    });
    s.addText(d.why, {
      x: x + 0.12, y: y + 0.38, w: 4.4, h: 0.48,
      fontSize: 9, fontFace: "Calibri", color: MUTED, margin: 0
    });
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 4.85, w: 9.2, h: 0.44,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Score: 5/6 BUILD → Full Claude SDK investment justified. Maximum control, maximum differentiation.", {
    x: 0.5, y: 4.85, w: 9, h: 0.44,
    fontSize: 10.5, fontFace: "Calibri", bold: true, color: WHITE,
    align: "center", valign: "middle", margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 6 — LIVE DEMO SLIDE
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s, true);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 5.625,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: "162D4A" }, line: { color: "162D4A" }
  });
  s.addText("Live Demo", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });

  // Central demo script
  const demoSteps = [
    { t: "0:00", action: "Open browser → localhost:3000" },
    { t: "1:00", action: "Upload company_standard_terms.pdf  +  vendor_proposed_terms.pdf" },
    { t: "2:00", action: "Click Analyze Contracts → show progress bar + tool calls firing in terminal" },
    { t: "4:30", action: "Walk through redline output — point to CRITICAL: Liability Cap conflict" },
    { t: "6:30", action: "Read the resolution language Claude generated for that conflict" },
    { t: "8:00", action: "Show the full conflict table — 10 conflicts, 2 CRITICAL, 3 HIGH" },
    { t: "9:00", action: "Click ↓ PDF — show the formatted redline brief downloading instantly" },
  ];

  demoSteps.forEach((d, i) => {
    const y = 1.05 + i * 0.57;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: 0.9, h: 0.44,
      fill: { color: PURPLE }, line: { color: PURPLE }
    });
    s.addText(d.t, {
      x: 0.5, y, w: 0.9, h: 0.44,
      fontSize: 10, fontFace: "Courier New", bold: true,
      color: WHITE, align: "center", valign: "middle", margin: 0
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 1.55, y, w: 8.1, h: 0.44,
      fill: { color: "162D4A" }, line: { color: "243F60" }
    });
    s.addText(d.action, {
      x: 1.7, y, w: 7.8, h: 0.44,
      fontSize: 11, fontFace: "Calibri", color: "CADCFC",
      valign: "middle", margin: 0
    });
  });

  s.addText("Key moment: Show the terminal with tool calls printing live as the agent works", {
    x: 0.5, y: 5.12, w: 9, h: 0.35,
    fontSize: 9.5, fontFace: "Calibri", italic: true, color: "7A9BBF",
    align: "center", margin: 0
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 7 — BUSINESS CASE
// ═══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  slideBase(s);

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Business Case", {
    x: 0.5, y: 0, w: 9, h: 0.85,
    fontSize: 22, fontFace: "Georgia", bold: true,
    color: WHITE, valign: "middle", margin: 0
  });

  // 3 buyer cards
  const buyers = [
    {
      type: "Law Firms",
      pain: "Associates bill $400/hr for contract comparison",
      value: "ClauseGuard does it in 60s — bill the client, save the associate",
      roi: "$50K+ saved per attorney per year",
      color: NAVY, bg: NAVY_XL
    },
    {
      type: "Procurement Teams",
      pain: "No legal review budget for standard vendor deals",
      value: "Instant conflict detection before any signature",
      roi: "Prevent one bad clause = $100K+ in penalties avoided",
      color: PURPLE, bg: PURP_LT
    },
    {
      type: "Startups",
      pain: "Sign vendor contracts without reading them",
      value: "Affordable legal intelligence on every agreement",
      roi: "First conflict caught pays for the tool 100x over",
      color: "065A82", bg: NAVY_XL
    },
  ];

  buyers.forEach((b, i) => {
    const x = 0.4 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.05, w: 2.9, h: 4.25,
      fill: { color: b.bg }, line: { color: b.color, width: 0.75 },
      shadow: makeShadow()
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.05, w: 2.9, h: 0.5,
      fill: { color: b.color }, line: { color: b.color }
    });
    s.addText(b.type, {
      x: x + 0.1, y: 1.05, w: 2.7, h: 0.5,
      fontSize: 12, fontFace: "Calibri", bold: true,
      color: WHITE, valign: "middle", margin: 0
    });

    const items = [
      { label: "Pain point", text: b.pain },
      { label: "Value", text: b.value },
      { label: "ROI", text: b.roi },
    ];
    items.forEach((item, j) => {
      const y = 1.75 + j * 1.15;
      s.addText(item.label.toUpperCase(), {
        x: x + 0.15, y, w: 2.6, h: 0.22,
        fontSize: 7.5, fontFace: "Calibri", bold: true, color: b.color, margin: 0
      });
      s.addText(item.text, {
        x: x + 0.15, y: y + 0.22, w: 2.6, h: 0.75,
        fontSize: 10, fontFace: "Calibri", color: INK, margin: 0
      });
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SLIDE 8 — CLOSING
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

  s.addText("ClauseGuard", {
    x: 0.5, y: 1.3, w: 9, h: 1.1,
    fontSize: 52, fontFace: "Georgia", bold: true,
    color: WHITE, align: "center", margin: 0
  });

  s.addText("A junior lawyer takes 4 hours.\nClauseGuard takes 60 seconds.", {
    x: 0.5, y: 2.5, w: 9, h: 0.9,
    fontSize: 16, fontFace: "Georgia", italic: true,
    color: "CADCFC", align: "center", margin: 0
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 3.2, y: 3.6, w: 3.6, h: 0.06,
    fill: { color: PURPLE, transparency: 50 }, line: { color: PURPLE, transparency: 50 }
  });

  // Stats row
  const stats = [
    { n: "1", label: "agent" },
    { n: "2", label: "tools" },
    { n: "<60s", label: "analysis time" },
    { n: "5/6", label: "BUILD score" },
  ];
  stats.forEach((st, i) => {
    const x = 0.8 + i * 2.2;
    s.addText(st.n, {
      x, y: 3.9, w: 2, h: 0.65,
      fontSize: 30, fontFace: "Georgia", bold: true,
      color: WHITE, align: "center", margin: 0
    });
    s.addText(st.label, {
      x, y: 4.55, w: 2, h: 0.3,
      fontSize: 10, fontFace: "Calibri", color: "7A9BBF",
      align: "center", margin: 0
    });
  });

  s.addText("Project 1/3  ·  BUAN 6v99.s01  ·  UT Dallas  ·  April 2026", {
    x: 0.5, y: 5.1, w: 9, h: 0.3,
    fontSize: 9, fontFace: "Calibri", color: "4A6A8A",
    align: "center", margin: 0
  });
}

// ── WRITE FILE ────────────────────────────────────────────────────────────────
pres.writeFile({ fileName: "/Users/nicholasthomas/Downloads/clauseguard/ClauseGuard_Presentation_v3.pptx" })
  .then(() => console.log("Presentation created: ClauseGuard_Presentation.pptx"))
  .catch(err => { console.error(err); process.exit(1); });
