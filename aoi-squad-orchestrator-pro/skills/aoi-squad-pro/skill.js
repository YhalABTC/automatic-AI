#!/usr/bin/env node
/**
 * 🌌 Aoineco-Verified | Multi-Agent Collective (PRO)
 * S-DNA: AOI-2026-0302-SDNA-ORCHPRO-01
 * Author: Aoineco (CHUNGHO)
 * License: Proprietary Beta (see LICENSE_PROPRIETARY_BETA.md)
 * Integrity: tracked via git history (private distribution)
 */
import fs from "fs";
import os from "os";
import path from "path";
import crypto from "crypto";

// Pro v0.1 M2: preset storage + stable pseudonym names + run skeleton (routing + fixed report schema)

const REPORT_SCHEMA_VERSION = "aoi.squad.report.v0.1";

// v0.1: approvals are single-file only
const V0_1_SINGLE_FILE_APPROVAL = true;

const DEFAULT_APPROVAL_CONSTRAINTS = {
  allowed_roots: ["./"],
  deny_globs: ["**/.env", "**/vault/**", "**/.git/**", "**/node_modules/**"],
  max_files: 1,
  max_total_bytes: 200000
};

const PRO_PRESETS = {
  "pro-a": {
    label: "Pro Preset A (Planner/Researcher/Builder/Reviewer/Operator)",
    roles: [
      { key: "planner", archetype: "Planner" },
      { key: "researcher", archetype: "Researcher" },
      { key: "builder", archetype: "Builder" },
      { key: "reviewer", archetype: "Reviewer" },
      { key: "operator", archetype: "Operator" }
    ]
  },
  "pro-b": {
    label: "Pro Preset B (Researcher/Writer/Builder/Security/Operator)",
    roles: [
      { key: "researcher", archetype: "Researcher" },
      { key: "writer", archetype: "Writer" },
      { key: "builder", archetype: "Builder" },
      { key: "security", archetype: "Sentinel" },
      { key: "operator", archetype: "Operator" }
    ]
  }
};

const CALLSIGNS = [
  "Vega","Kestrel","Orion","Lyra","Atlas","Nova","Rune","Cobalt","Sable","Juniper",
  "Nimbus","Ash","Mosaic","Pulse","Quill","Beacon","Astra","Zenith","Hawke","Tundra"
];

function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const [k, v] = a.includes("=") ? a.slice(2).split("=") : [a.slice(2), argv[i + 1]];
      if (!a.includes("=")) i++;
      out[k] = v;
    } else {
      out._.push(a);
    }
  }
  return out;
}

function jsonOut(obj, code = 0) {
  process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
  process.exit(code);
}

function fail(message, extra = {}) {
  jsonOut({ ok: false, error: message, ...extra }, 1);
}

function ensureDirForFile(fp) {
  fs.mkdirSync(path.dirname(fp), { recursive: true });
}

function namesFile() {
  return path.join(os.homedir(), ".openclaw", "aoi", "squad_names.json");
}

function presetsFile() {
  return path.join(os.homedir(), ".openclaw", "aoi", "presets.json");
}

function runsDir() {
  return path.join(os.homedir(), ".openclaw", "aoi", "runs");
}

function writeRun(runId, obj) {
  const dir = runsDir();
  fs.mkdirSync(dir, { recursive: true });
  const fp = path.join(dir, `${runId}.json`);
  fs.writeFileSync(fp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  return fp;
}

function readRun(runId) {
  const fp = path.join(runsDir(), `${runId}.json`);
  const obj = JSON.parse(fs.readFileSync(fp, "utf8"));
  return { fp, obj };
}

function loadJson(fp, fallback) {
  try {
    return JSON.parse(fs.readFileSync(fp, "utf8"));
  } catch {
    return fallback;
  }
}

function saveJson(fp, obj) {
  ensureDirForFile(fp);
  fs.writeFileSync(fp, JSON.stringify(obj, null, 2) + "\n", "utf8");
}

function pickCallsign(used) {
  const available = CALLSIGNS.filter(c => !used.has(c));
  const arr = available.length ? available : CALLSIGNS;
  return arr[Math.floor(Math.random() * arr.length)];
}

function defaultName(archetype, used) {
  const cs = pickCallsign(used);
  used.add(cs);
  return `${archetype} ${cs}`;
}

function getPresetDef(name) {
  const db = loadJson(presetsFile(), { schema: "aoi.squad.pro.presets.v0.1", presets: {} });
  if (db.presets?.[name]) return { source: "user", preset: db.presets[name], db };
  if (PRO_PRESETS[name]) return { source: "builtin", preset: PRO_PRESETS[name], db };
  return { source: null, preset: null, db };
}

function listPresets() {
  const db = loadJson(presetsFile(), { schema: "aoi.squad.pro.presets.v0.1", presets: {} });
  const builtins = Object.entries(PRO_PRESETS).map(([k, v]) => ({ name: k, label: v.label, builtin: true, roles: v.roles.map(r => r.key) }));
  const user = Object.entries(db.presets || {}).map(([k, v]) => ({ name: k, label: v.label || k, builtin: false, roles: (v.roles || []).map(r => r.key) }));
  jsonOut({ ok: true, file: presetsFile(), presets: [...builtins, ...user] });
}

function showPreset(args) {
  const name = args.name;
  if (!name) return fail("Missing --name");
  const got = getPresetDef(name);
  if (!got.preset) return fail(`Unknown preset: ${name}`);
  jsonOut({ ok: true, name, source: got.source, preset: got.preset });
}

function clonePreset(args) {
  const from = args.from;
  const to = args.to;
  if (!from) return fail("Missing --from");
  if (!to) return fail("Missing --to");
  const got = getPresetDef(from);
  if (!got.preset) return fail(`Unknown preset: ${from}`);

  const db = got.db;
  db.presets ||= {};
  if (db.presets[to]) return fail(`Preset already exists: ${to}`);

  // deep copy
  const copy = JSON.parse(JSON.stringify(got.preset));
  copy.label = copy.label || to;
  db.presets[to] = copy;
  saveJson(presetsFile(), db);
  jsonOut({ ok: true, from, to, file: presetsFile() });
}

function loadNamesDb() {
  return loadJson(namesFile(), { schema: "aoi.squad.names.v0.1", presets: {} });
}

function saveNamesDb(db) {
  saveJson(namesFile(), db);
}

function getOrInitTeam(presetName, presetDef) {
  const db = loadNamesDb();
  db.presets ||= {};
  db.presets[presetName] ||= { roles: {} };

  const used = new Set(
    Object.values(db.presets[presetName].roles || {})
      .map(x => x.split(" ").slice(1).join(" "))
      .filter(Boolean)
  );

  for (const r of presetDef.roles) {
    if (!db.presets[presetName].roles[r.key]) {
      db.presets[presetName].roles[r.key] = defaultName(r.archetype, used);
    }
  }

  saveNamesDb(db);
  return { team: db.presets[presetName].roles, file: namesFile() };
}

function teamShow(args) {
  const presetName = args.preset;
  if (!presetName) return fail("Missing --preset");
  const got = getPresetDef(presetName);
  if (!got.preset) return fail(`Unknown preset: ${presetName}`);
  const res = getOrInitTeam(presetName, got.preset);
  jsonOut({ ok: true, preset: presetName, team: res.team, file: res.file });
}

function validateName(name) {
  if (!name || typeof name !== "string") return "Name must be a string";
  if (name.length < 3 || name.length > 40) return "Name length must be 3..40";
  const bad = ["http://","https://","/","\\","://",".env","$", "~"];
  if (bad.some(b => name.includes(b))) return "Name contains disallowed characters";
  return null;
}

function isAbsoluteOrTraversal(p) {
  if (typeof p !== "string" || !p) return true;
  if (p.startsWith("/") || p.match(/^[A-Za-z]:\\/)) return true; // unix/windows
  if (p.includes("..")) return true;
  return false;
}

function matchGlob(pathStr, glob) {
  // v0.1 conservative glob matcher (supports ** and *)
  // Convert glob to regex safely.
  const token = "__GLOBSTAR__";
  let g = String(glob);
  g = g.replaceAll("**", token);
  // escape regex specials
  g = g.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  // restore glob tokens
  g = g.replaceAll(token, ".*");
  g = g.replaceAll("*", "[^/]*");
  const re = new RegExp(`^${g}$`);
  return re.test(String(pathStr));
}

function violatesConstraints(relPath, constraints) {
  if (isAbsoluteOrTraversal(relPath)) return "Path must be relative and must not contain '..'";
  // enforce allowed_roots (v0.1 only supports "./")
  if (!(constraints.allowed_roots || []).includes("./")) return "Invalid allowed_roots";
  // deny globs
  for (const g of (constraints.deny_globs || [])) {
    if (matchGlob(relPath, g)) return `Path denied by glob: ${g}`;
  }
  return null;
}

function sha256Hex(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function teamRename(args) {
  const { preset, role, name } = args;
  if (!preset) return fail("Missing --preset");
  if (!role) return fail("Missing --role");
  if (!name) return fail("Missing --name");

  const got = getPresetDef(preset);
  if (!got.preset) return fail(`Unknown preset: ${preset}`);
  const roleKeys = new Set((got.preset.roles || []).map(r => r.key));
  if (!roleKeys.has(role)) return fail(`Unknown role '${role}' for preset '${preset}'`);

  const err = validateName(name);
  if (err) return fail(err);

  const db = loadNamesDb();
  db.presets ||= {};
  db.presets[preset] ||= { roles: {} };
  db.presets[preset].roles ||= {};
  db.presets[preset].roles[role] = name;
  saveNamesDb(db);
  jsonOut({ ok: true, preset, role, name, file: namesFile() });
}

function nowIso() {
  return new Date().toISOString();
}

function roleIndex(presetDef) {
  const m = new Map();
  for (const r of presetDef.roles || []) m.set(r.key, r);
  return m;
}

function routingPlan(presetDef) {
  // B-recommended: planner + researcher in parallel (if both exist), then builder, then reviewer/security, then operator.
  const keys = (presetDef.roles || []).map(r => r.key);
  const has = k => keys.includes(k);
  const steps = [];

  const parallel = [];
  if (has("planner")) parallel.push("planner");
  if (has("researcher")) parallel.push("researcher");
  if (parallel.length) steps.push({ kind: "parallel", roles: parallel });

  if (has("builder")) steps.push({ kind: "sequential", roles: ["builder"] });

  const review = [];
  if (has("reviewer")) review.push("reviewer");
  if (has("security")) review.push("security");
  if (review.length) steps.push({ kind: "sequential", roles: review });

  if (has("operator")) steps.push({ kind: "sequential", roles: ["operator"] });

  // Fallback: if preset has unknown roles, append them as sequential at the end.
  const used = new Set(steps.flatMap(s => s.roles));
  const remaining = keys.filter(k => !used.has(k));
  if (remaining.length) steps.push({ kind: "sequential", roles: remaining });

  return { kind: "routing.v0.1", steps };
}

function buildDemoChecklistContent(task) {
  const safe = String(task).trim();
  return [
    "# Launch Checklist",
    "",
    `Task: ${safe}`,
    "",
    "## Steps",
    "- [ ] Define success criteria",
    "- [ ] Create demo script",
    "- [ ] Record a short demo clip",
    "- [ ] Write README + usage",
    "- [ ] Run security gate",
    "- [ ] Publish + announce",
    ""
  ].join("\n");
}

function unifiedDiffForCreate(relPath, content) {
  const lines = content.split("\n");
  const header = [
    "--- /dev/null",
    `+++ b/${relPath}`,
    `@@ -0,0 +1,${lines.length} @@`
  ];
  const body = lines.map(l => `+${l}`);
  return [...header, ...body, ""].join("\n");
}

function unifiedDiffForModify(relPath, beforeContent, afterContent) {
  const beforeLines = beforeContent.split("\n");
  const afterLines = afterContent.split("\n");
  const header = [
    `--- a/${relPath}`,
    `+++ b/${relPath}`,
    `@@ -1,${beforeLines.length} +1,${afterLines.length} @@`
  ];
  const body = [
    ...beforeLines.map(l => `-${l}`),
    ...afterLines.map(l => `+${l}`),
    ""
  ];
  return [...header, ...body].join("\n");
}

function stableStringify(obj) {
  // payload is flat; sort keys for deterministic signing
  const keys = Object.keys(obj).sort();
  const out = {};
  for (const k of keys) out[k] = obj[k];
  return JSON.stringify(out);
}

function loadLicense(pathOverride) {
  const fp = pathOverride || path.join(os.homedir(), ".openclaw", "licenses", "aoi_pro_beta.json");
  if (!fs.existsSync(fp)) return { ok: false, mode: "lite", reason: "license_missing", fp };
  try {
    const lic = JSON.parse(fs.readFileSync(fp, "utf8"));
    return { ok: true, license: lic, fp };
  } catch (e) {
    return { ok: false, mode: "lite", reason: "license_invalid_json", fp };
  }
}

function verifyLicenseEd25519({ license, wallet, requiredFeatures = [] }) {
  try {
    const pubPath = path.join(__dirname, "assets", "aoi_license_pubkey.pem");
    const pubPem = fs.readFileSync(pubPath, "utf8");

    const sigB64 = String(license.signature || "");
    if (!sigB64) return { ok: false, mode: "lite", reason: "signature_missing" };

    const payload = { ...license };
    delete payload.signature;

    const msg = Buffer.from(stableStringify(payload), "utf8");
    const sig = Buffer.from(sigB64, "base64");

    const okSig = crypto.verify(null, msg, pubPem, sig);
    if (!okSig) return { ok: false, mode: "lite", reason: "signature_mismatch" };

    const licWallet = String(license.wallet || "").toLowerCase();
    if (!wallet) return { ok: false, mode: "lite", reason: "wallet_env_missing" };
    if (!licWallet || licWallet !== String(wallet).toLowerCase()) return { ok: false, mode: "lite", reason: "wallet_mismatch" };

    const expiresAt = license.expires_at ? new Date(String(license.expires_at)) : null;
    if (expiresAt && Number.isFinite(expiresAt.getTime())) {
      if (Date.now() >= expiresAt.getTime()) return { ok: false, mode: "lite", reason: "expired", expires_at: license.expires_at };

      // warn if <=7 days
      const days = Math.ceil((expiresAt.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
      if (days <= 7) {
        // best-effort warning; do not fail
        // (printed later in output)
      }
    }

    const feats = Array.isArray(license.features) ? license.features : [];
    const missing = requiredFeatures.filter(f => !feats.includes(f));
    if (missing.length) return { ok: false, mode: "lite", reason: `missing_features:${missing.join(",")}` };

    return { ok: true, mode: "pro", reason: "ok", expires_at: license.expires_at };
  } catch (e) {
    return { ok: false, mode: "lite", reason: "verify_error" };
  }
}

function getExecutionMode() {
  const wantPro = String(process.env.AOI_ORCHESTRATOR_MODE || "").toLowerCase() === "pro";
  const wallet = String(process.env.AOI_WALLET_ADDRESS || "").trim();
  const licLoad = loadLicense();
  if (!wantPro) return { mode: "lite", reason: "mode_env_not_pro" };
  if (!licLoad.ok) return { mode: "lite", reason: licLoad.reason };

  const vr = verifyLicenseEd25519({
    license: licLoad.license,
    wallet,
    requiredFeatures: ["ORCH_PRO"],
  });
  return vr.ok ? { mode: "pro", reason: "ok", expires_at: vr.expires_at } : { mode: "lite", reason: vr.reason };
}

function runCmd(args) {
  const presetName = args.preset;
  const task = args.task || "";
  const demoMode = String(args.demo ?? "create"); // create|modify|false
  if (!presetName) return fail("Missing --preset");
  if (!task) return fail("Missing --task");

  const got = getPresetDef(presetName);
  if (!got.preset) return fail(`Unknown preset: ${presetName}`);

  // Ensure stable pseudonyms
  const teamNames = getOrInitTeam(presetName, got.preset).team;

  const started = nowIso();
  const execMode = getExecutionMode();
  const ended = nowIso();
  const runId = `run_${Date.now()}`;

  const routing = routingPlan(got.preset);

  // Role outputs (M4): execution-oriented, sequential generation with cross-role context (template-based).
  const roleOutputs = {};

  function classifyTask(t) {
    const s = String(t || "").toLowerCase();
    if (s.includes("readme") || s.includes("docs") || s.includes("documentation") || s.includes("guide")) return "docs";
    if (s.includes("release") || s.includes("publish") || s.includes("ship") || s.includes("launch")) return "release";
    if (s.includes("bug") || s.includes("error") || s.includes("fail") || s.includes("crash")) return "debug";
    if (s.includes("security") || s.includes("audit") || s.includes("vulnerability")) return "security";
    return "general";
  }

  const taskType = classifyTask(task);

  function plannerOutput(t) {
    const tt = taskType;
    const deliverablesByType = {
      docs: ["Doc outline + final markdown", "Examples/CLI snippets", "Proof: updated file path"],
      release: ["Release checklist", "Changelog bullets", "Proof: links + run log"],
      debug: ["Repro steps", "Minimal fix plan", "Proof: before/after behavior"],
      security: ["Threat checklist", "Mitigation plan", "Proof: gate results"],
      general: ["Checklist (markdown)", "Runnable command sequence", "Proof artifact (file/log/url)"]
    };

    return [
      "## Plan (P0→P2)",
      `**Task type:** ${tt}`,
      "",
      "### P0 (must)",
      `- Define success criteria for: **${t}**`,
      "- Identify constraints (time, scope, safety gates)",
      "- Produce a minimal deliverable + proof artifact",
      "",
      "### P1 (should)",
      "- Improve quality (examples, docs, edge cases)",
      "- Add automation hooks (logs, repeatable commands)",
      "",
      "### P2 (nice)",
      "- Polish (UX, naming, refactors)",
      "",
      "### Deliverables",
      ...(deliverablesByType[tt] || deliverablesByType.general).map(x => `- ${x}`)
    ].join("\n");
  }

  function researcherOutput(t) {
    const tt = taskType;
    const qByType = {
      docs: [
        "Who is the reader (beginner vs advanced)?",
        "What are the minimal examples to include?",
        "What common mistakes should we warn about?"
      ],
      release: [
        "What are the breaking changes (if any)?",
        "What proof links should be included?",
        "What is the rollback plan?"
      ],
      debug: [
        "Can we reproduce reliably?",
        "What environment variables/versions matter?",
        "What is the smallest change that fixes it?"
      ],
      security: [
        "Any secrets/paths exposed?",
        "Any privilege escalation?",
        "Any unsafe network behavior?"
      ],
      general: [
        "What is the simplest done state?",
        "What can break? (paths, permissions, formats)",
        "What proof can we generate? (file, log, URL)"
      ]
    };

    return [
      "## Research / Verification",
      `**Task type:** ${tt}`,
      "",
      "### Assumptions to verify",
      "- Target user + environment (OS/runtime)",
      "- Inputs/outputs expected",
      "- Safety constraints (no secrets, no external side effects)",
      "",
      "### Quick questions",
      ...((qByType[tt] || qByType.general).map(q => `- ${q}`)),
      "",
      `- What is the simplest **done** for: **${t}**?`
    ].join("\n");
  }

  function writerOutput(t) {
    return [
      "## User-facing copy (draft)",
      "",
      `- **What:** ${t}`,
      "- **Who:** builders who want a repeatable workflow",
      "- **Why:** reduce manual steps and mistakes",
      "- **How:** preset → run → approve (diff) → evidence"
    ].join("\n");
  }

  function summarizeBullets(md, maxBullets = 3) {
    const lines = String(md || "").split("\n");
    const bullets = [];
    for (const ln of lines) {
      const m = ln.match(/^[-*]\s+(.*)$/);
      if (m) bullets.push(m[1].trim());
    }
    return bullets.slice(0, maxBullets);
  }

  function builderOutput(t, ctx) {
    const plannerTop = summarizeBullets(ctx.planner, 3);
    const researcherTop = summarizeBullets(ctx.researcher, 3);

    const templates = {
      docs: {
        artifact: "README/DOC section draft + examples",
        proof: "Modified markdown file + run log",
        steps: [
          "Outline doc sections (install/usage/examples)",
          "Write minimal examples + expected outputs",
          "Add troubleshooting + safety scope",
          "Emit modify approval_request for README.md"
        ]
      },
      release: {
        artifact: "Release checklist + changelog bullets",
        proof: "Run log + link list",
        steps: [
          "Generate release checklist (gates + smoke tests)",
          "Draft changelog bullets (what/why)",
          "Emit create approval_request for docs/LAUNCH_CHECKLIST.md",
          "Prepare announcement links (ClawHub/GitHub)"
        ]
      },
      debug: {
        artifact: "Repro steps + fix plan",
        proof: "Before/after notes + run log",
        steps: [
          "Write deterministic repro steps",
          "Isolate smallest fix",
          "Add guardrails/tests",
          "Emit modify approval_request for README.md (Known Issues)"
        ]
      },
      security: {
        artifact: "Threat checklist + mitigations",
        proof: "Gate output + run log",
        steps: [
          "Enumerate attack surfaces",
          "Check for secrets/paths exposure",
          "Confirm approvals constraints",
          "Emit create approval_request for docs/SECURITY_NOTES.md"
        ]
      },
      general: {
        artifact: "Minimal deliverable + proof",
        proof: "Run log + artifact path",
        steps: [
          "Parse task + constraints",
          "Use Planner/Researcher notes to shape the draft",
          "Produce a minimal artifact + proof",
          "If a file is needed, emit approval_request with unified diff"
        ]
      }
    };

    const tt = taskType;
    const cfg = templates[tt] || templates.general;

    return [
      "## Build plan",
      `**Task type:** ${tt}`,
      "",
      "### Inputs (compressed)",
      "- From Planner:",
      ...(plannerTop.length ? plannerTop.map(b => `  - ${b}`) : ["  - (none)"]),
      "- From Researcher:",
      ...(researcherTop.length ? researcherTop.map(b => `  - ${b}`) : ["  - (none)"]),
      "",
      "### Steps",
      ...cfg.steps.map((s, i) => `${i + 1}) ${s}`),
      "",
      "### Artifact",
      `- ${cfg.artifact}`,
      "",
      "### Proof",
      `- ${cfg.proof}`,
      "",
      "### Output contract",
      "- Schema: `aoi.squad.report.v0.1` (unchanged)",
      "- No internal nicknames in product output",
      "- Any file change via diff-first approval",
      "",
      `**Build target:** ${t}`
    ].join("\n");
  }

  function reviewerOutput(ctx) {
    return [
      "## Review",
      "",
      "### Checks",
      "- Output schema unchanged (`aoi.squad.report.v0.1`)",
      "- No internal nicknames in outputs",
      "- No absolute paths or secrets",
      "- Approvals are single-file only (v0.1)",
      "",
      "### Potential gaps",
      "- Ensure sha256_before enforced for modify",
      "- Ensure deny_globs blocks `.env` / `vault/` / `.git/` / `node_modules/`"
    ].join("\n");
  }

  function securityOutput() {
    return [
      "## Security",
      "",
      "### Policy",
      "- Default: no external calls",
      "- File writes only via diff-first approval",
      "- Block suspicious paths and traversal",
      "- Cap bytes and line counts"
    ].join("\n");
  }

  function operatorOutput(t) {
    const tt = taskType;
    const runCmd = tt === "docs" || tt === "debug" ? "--demo=modify" : (tt === "security" ? "--demo=false" : "--demo=create");
    return [
      "## Operator / Runbook",
      `**Task type:** ${tt}`,
      "",
      "### Run",
      `- Run: \`node skills/aoi-squad-pro/skill.js run --preset ${presetName} --task \"${t.replace(/\"/g, "'")}\" ${runCmd}\``,
      "",
      "### Approve (if requested)",
      "- From repo root:",
      "  - `node skills/aoi-squad-pro/skill.js approve --run <run_id> --id <approval_request_id> --root .`",
      "",
      "### Verify",
      "- Check VCP proof lines in the report_markdown",
      "- Ensure run log exists: `~/.openclaw/aoi/runs/<run_id>.json`",
      "",
      "### Target",
      `- ${t}`
    ].join("\n");
  }

  // Generate in routing order (planner+researcher first)
  const roleKeys = (got.preset.roles || []).map(r => r.key);
  if (roleKeys.includes("planner")) roleOutputs.planner = plannerOutput(task);
  if (roleKeys.includes("researcher")) roleOutputs.researcher = researcherOutput(task);
  if (roleKeys.includes("writer")) roleOutputs.writer = writerOutput(task);
  if (roleKeys.includes("builder")) roleOutputs.builder = builderOutput(task, roleOutputs);
  if (roleKeys.includes("reviewer")) roleOutputs.reviewer = reviewerOutput(roleOutputs);
  if (roleKeys.includes("security")) roleOutputs.security = securityOutput();
  if (roleKeys.includes("operator")) roleOutputs.operator = operatorOutput(task);

  const team = (got.preset.roles || []).map(r => {
    const display = teamNames[r.key] || `${r.archetype} Member`;
    return {
      nickname: display,
      role: r.archetype,
      objective: `Execute as ${r.key} (execution-first).`,
      output: roleOutputs[r.key] || `No output for role '${r.key}'.`,
      artifacts: []
    };
  });

  const approval_requests = [];

  function proposeCreateFile(relPath, content, reason, highlights) {
    const violation = violatesConstraints(relPath, DEFAULT_APPROVAL_CONSTRAINTS);
    if (violation) return fail(`Proposed path violates constraints: ${violation}`);

    const afterHash = sha256Hex(Buffer.from(content, "utf8"));
    const diff = unifiedDiffForCreate(relPath, content);

    approval_requests.push({
      id: `ar_${Date.now()}_01`,
      type: "file_patch",
      reason,
      risk_flags: ["writes_file"],
      files: [
        {
          path: relPath,
          op: "create",
          encoding: "utf-8",
          diff_unified: diff,
          sha256_before: null,
          sha256_after: afterHash,
          line_count_after: content.split("\n").length
        }
      ],
      v0_1_single_file_rule: V0_1_SINGLE_FILE_APPROVAL,
      constraints: DEFAULT_APPROVAL_CONSTRAINTS,
      preview: {
        summary: `Create ${relPath} (${content.split("\n").length} lines)`,
        highlights
      }
    });
  }

  function proposeModifyFile(relPath, afterContent, reason, highlights) {
    const violation = violatesConstraints(relPath, DEFAULT_APPROVAL_CONSTRAINTS);
    if (violation) return fail(`Proposed path violates constraints: ${violation}`);

    const abs = path.join(process.cwd(), relPath);
    if (!fs.existsSync(abs)) return fail(`Modify target not found: ${relPath} (run from repo root or set --demo=false)`);

    const before = fs.readFileSync(abs, "utf8");
    const beforeHash = sha256Hex(Buffer.from(before, "utf8"));

    const after = afterContent;
    const afterHash = sha256Hex(Buffer.from(after, "utf8"));
    const diff = unifiedDiffForModify(relPath, before, after);

    approval_requests.push({
      id: `ar_${Date.now()}_01`,
      type: "file_patch",
      reason,
      risk_flags: ["writes_file"],
      files: [
        {
          path: relPath,
          op: "modify",
          encoding: "utf-8",
          diff_unified: diff,
          sha256_before: beforeHash,
          sha256_after: afterHash,
          line_count_after: after.split("\n").length
        }
      ],
      v0_1_single_file_rule: V0_1_SINGLE_FILE_APPROVAL,
      constraints: DEFAULT_APPROVAL_CONSTRAINTS,
      preview: {
        summary: `Modify ${relPath} (${after.split("\n").length} lines)`,
        highlights
      }
    });
  }

  if (demoMode !== "false") {
    // Task-type aware defaults (still overridable via --demo)
    const tt = taskType;
    const effectiveDemo = demoMode === "create" || demoMode === "modify" ? demoMode : (tt === "docs" || tt === "debug" ? "modify" : "create");

    if (effectiveDemo === "create") {
      const relPath = tt === "security" ? "docs/SECURITY_NOTES.md" : "docs/LAUNCH_CHECKLIST.md";
      const content = relPath.endsWith("SECURITY_NOTES.md")
        ? ["# Security Notes", "", `Task: ${task}`, "", "## Checklist", "- [ ] No secrets", "- [ ] No absolute paths", "- [ ] Diff-first approvals only", ""].join("\n")
        : buildDemoChecklistContent(task);

      proposeCreateFile(relPath, content, tt === "security" ? "Create security notes demo file" : "Create a launch checklist demo file", ["Task-type aware proposal", "No external side effects"]);

    } else if (effectiveDemo === "modify") {
      const relPath = "README.md";
      const before = fs.existsSync(path.join(process.cwd(), relPath)) ? fs.readFileSync(path.join(process.cwd(), relPath), "utf8") : "";
      const sectionTitle = tt === "docs" ? "## Docs update" : "## Debug notes";
      const addition = ["", sectionTitle, `Task: ${task}`, ""].join("\n");
      const after = before.includes(sectionTitle) ? before : (before.trimEnd() + addition + "\n");

      proposeModifyFile(relPath, after, "Modify README.md (task-type demo patch)", ["Task-type aware proposal", "No external side effects"]);

    } else {
      return fail(`Unknown --demo mode: ${demoMode} (use create|modify|false)`);
    }
  }

  const oneLine = `Pro run '${presetName}' completed: ${task.slice(0, 80)}${task.length > 80 ? "…" : ""}`;

  // Builder synthesis helpers
  const plannerTop = roleOutputs.planner ? roleOutputs.planner.split("\n").filter(l => l.trim().startsWith("- ")).slice(0, 3).map(l => l.replace(/^[-]\s+/, "")) : [];
  const researcherTop = roleOutputs.researcher ? roleOutputs.researcher.split("\n").filter(l => l.trim().startsWith("- ")).slice(0, 3).map(l => l.replace(/^[-]\s+/, "")) : [];

  function reportMarkdown(outObj) {
    const lines = [];

    const p0 = (outObj.synthesis?.next_actions || []).filter(a => a.priority === "P0");
    const p1 = (outObj.synthesis?.next_actions || []).filter(a => a.priority === "P1");

    lines.push(`# AOI Squad Pro Report (v0.1)`);
    lines.push(`- Preset: ${outObj.run.preset} | Run: ${outObj.run.run_id}`);
    lines.push("");

    // TL;DR block (execution-first)
    lines.push("## TL;DR");
    lines.push(`- ${outObj.synthesis.one_line_summary}`);
    if (p0.length) {
      lines.push("- P0:");
      for (const a of p0.slice(0, 3)) lines.push(`  - ${a.action}`);
    }
    lines.push("");

    // Proof up top
    if (outObj.synthesis.vcp_proof?.length) {
      lines.push("## VCP proof");
      for (const p of outObj.synthesis.vcp_proof) lines.push(`- ${p.label}: ${p.url}`);
      lines.push("");
    }

    lines.push("## Task");
    lines.push(outObj.task.input);
    lines.push("");

    lines.push("## Next actions");
    for (const a of [...p0, ...p1].slice(0, 6)) {
      lines.push(`- [${a.priority}] ${a.action} (Owner: ${a.owner})`);
    }
    lines.push("");

    if (outObj.synthesis.risks?.length) {
      lines.push("## Risks");
      for (const r of outObj.synthesis.risks.slice(0, 5)) lines.push(`- [${r.severity}] ${r.risk} → ${r.mitigation}`);
      lines.push("");
    }

    // Detailed outputs (collapsed at bottom)
    lines.push("## Team outputs (details)");
    for (const m of outObj.team) {
      lines.push(`### ${m.nickname} (${m.role})`);
      lines.push(m.output);
      lines.push("");
    }

    return lines.join("\n");
  }

  const out = {
    ok: true,
    schema_version: REPORT_SCHEMA_VERSION,
    run: {
      run_id: runId,
      preset: presetName,
      started_at: started,
      ended_at: ended,
      exec_mode: execMode.mode,
      exec_mode_reason: execMode.reason,
      limits: {
        max_roles: (got.preset.roles || []).length,
        max_turns: 10,
        max_wall_time_sec: 300,
        max_tokens: 16000
      }
    },
    task: {
      title: task.split("\n")[0].slice(0, 120),
      input: task,
      constraints: []
    },
    team,
    synthesis: {
      one_line_summary: oneLine,
      decision: [
        { item: "Use diff-first approvals for any local file changes", reason: "Reduces accidental side effects and creates an audit trail", confidence: 0.78 },
        { item: "Build minimal proof-first deliverable", reason: "Keeps scope tight and makes progress measurable", confidence: 0.72 }
      ],
      risks: [
        { risk: "User runs approve with wrong --root", severity: "med", mitigation: "Require running from repo root or pass --root explicitly" },
        { risk: "Patch applied after file changed", severity: "low", mitigation: "Enforce sha256_before for modify" }
      ],
      next_actions: [
        ...(plannerTop.length ? [{ action: `Planner focus: ${plannerTop[0]}`, owner: "user", priority: "P0" }] : []),
        ...(researcherTop.length ? [{ action: `Researcher focus: ${researcherTop[0]}`, owner: "user", priority: "P0" }] : []),
        { action: "Run with --demo=create and inspect approval_requests", owner: "user", priority: "P1" },
        { action: "Approve the proposed patch from repo root", owner: "user", priority: "P1" }
      ],
      vcp_proof: []
    },
    report_markdown: "", 
    meta: {
      notes: ["Pro M4.2: builder compresses Planner/Researcher inputs; synthesis pulls top priorities into next_actions."],
      warnings: execMode.mode === "pro" ? [] : [`PRO disabled → Lite fallback (${execMode.reason})`]
    },
    pro: {
      routing,
      approval_requests,
      approvals: [],
      audit: {
        stored_run_file: null
      }
    }
  };

  const stored = writeRun(runId, out);
  out.pro.audit.stored_run_file = stored;

  // Operator VCP auto-fill (v0.1, cleaner): always include run log; if pending approvals exist, include explicit request info.
  out.synthesis.vcp_proof ||= [];
  out.synthesis.vcp_proof.push({ label: "Run log", url: `file://${stored}` });
  const pending = out.pro.approval_requests || [];
  if (pending.length) {
    const r0 = pending[0];
    const f0 = (r0.files || [])[0];
    out.synthesis.vcp_proof.push({ label: "Approval request id", url: String(r0.id) });
    if (f0?.path) out.synthesis.vcp_proof.push({ label: "Proposed file", url: String(f0.path) });
    if (f0?.op) out.synthesis.vcp_proof.push({ label: "Proposed op", url: String(f0.op) });
  }

  // Fill report_markdown for humans
  out.report_markdown = reportMarkdown(out);

  // Persist the updated run file (so VCP + markdown stay consistent)
  fs.writeFileSync(stored, JSON.stringify(out, null, 2) + "\n", "utf8");

  jsonOut(out);
}

function extractCreateContentFromUnifiedDiff(diff) {
  const lines = String(diff || "").split("\n");
  const out = [];
  for (const ln of lines) {
    if (ln.startsWith("+++ ") || ln.startsWith("--- ") || ln.startsWith("@@")) continue;
    if (ln.startsWith("+")) out.push(ln.slice(1));
  }
  // drop possible trailing empty line from diff generator
  return out.join("\n");
}

function applySingleFilePatch(req, repoRoot) {
  if (req.type !== "file_patch") throw new Error("Only file_patch is supported in v0.1");
  const files = req.files || [];
  if (V0_1_SINGLE_FILE_APPROVAL && files.length !== 1) throw new Error("v0.1 requires exactly 1 file per approval request");
  const f = files[0];

  const constraints = req.constraints || DEFAULT_APPROVAL_CONSTRAINTS;
  const violation = violatesConstraints(f.path, constraints);
  if (violation) throw new Error(`Constraint violation: ${violation}`);

  const abs = path.join(repoRoot, f.path);
  const exists = fs.existsSync(abs);

  if (f.op === "create" && exists) throw new Error(`File already exists: ${f.path}`);
  if (f.op === "modify" && !exists) throw new Error(`File does not exist for modify: ${f.path}`);

  if (f.op === "modify") {
    const before = fs.readFileSync(abs);
    const beforeHash = sha256Hex(before);
    if (f.sha256_before && beforeHash !== f.sha256_before) throw new Error("sha256_before mismatch (file changed since proposal)");
  }

  const content = extractCreateContentFromUnifiedDiff(f.diff_unified);
  const after = sha256Hex(Buffer.from(content, "utf8"));
  if (f.sha256_after && after !== f.sha256_after) throw new Error("sha256_after mismatch");

  // size limit
  if (Buffer.byteLength(content, "utf8") > (constraints.max_total_bytes || 200000)) {
    throw new Error("Patch exceeds max_total_bytes");
  }

  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content, "utf8");

  return { path: f.path, op: f.op, bytes: Buffer.byteLength(content, "utf8"), sha256_after: after };
}

function approveCmd(args) {
  const runId = args.run;
  const reqId = args.id;
  const repoRoot = args.root || process.cwd();
  if (!runId) return fail("Missing --run");
  if (!reqId) return fail("Missing --id");

  const { fp, obj } = readRun(runId);
  const reqs = obj?.pro?.approval_requests || [];
  const req = reqs.find(r => r.id === reqId);
  if (!req) return fail(`Approval request not found: ${reqId}`);

  const applied = applySingleFilePatch(req, repoRoot);

  obj.pro.approvals ||= [];
  obj.pro.approvals.push({
    approval_request_id: reqId,
    status: "approved",
    approved_by: "user",
    approved_at: nowIso(),
    note: ""
  });

  obj.synthesis.vcp_proof ||= [];
  // remove any stale proposal entries
  obj.synthesis.vcp_proof = (obj.synthesis.vcp_proof || []).filter(p => !["Approval request id","Proposed file","Proposed op"].includes(p.label));
  obj.synthesis.vcp_proof.push({
    label: "Applied file",
    url: `file://${path.join(repoRoot, applied.path)}`
  });
  obj.synthesis.vcp_proof.push({
    label: "Approval",
    url: `approved ${reqId} at ${obj.pro.approvals[obj.pro.approvals.length - 1].approved_at}`
  });

  // remove the request once approved
  obj.pro.approval_requests = reqs.filter(r => r.id !== reqId);

  // persist
  fs.writeFileSync(fp, JSON.stringify(obj, null, 2) + "\n", "utf8");

  jsonOut({ ok: true, run: runId, request_id: reqId, applied, run_file: fp });
}

function rejectCmd(args) {
  const runId = args.run;
  const reqId = args.id;
  const note = args.note || "";
  if (!runId) return fail("Missing --run");
  if (!reqId) return fail("Missing --id");

  const { fp, obj } = readRun(runId);
  const reqs = obj?.pro?.approval_requests || [];
  const req = reqs.find(r => r.id === reqId);
  if (!req) return fail(`Approval request not found: ${reqId}`);

  obj.pro.approvals ||= [];
  obj.pro.approvals.push({
    approval_request_id: reqId,
    status: "rejected",
    approved_by: "user",
    approved_at: nowIso(),
    note
  });
  obj.pro.approval_requests = reqs.filter(r => r.id !== reqId);

  fs.writeFileSync(fp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  jsonOut({ ok: true, run: runId, request_id: reqId, status: "rejected", run_file: fp });
}

function main() {
  const argv = process.argv.slice(2);
  const cmd = argv[0];
  const sub = argv[1];
  const args = parseArgs(argv.slice(1));

  try {
    if (cmd === "preset" && sub === "list") return listPresets();
    if (cmd === "preset" && sub === "show") return showPreset(args);
    if (cmd === "preset" && sub === "clone") return clonePreset(args);
    if (cmd === "team" && sub === "show") return teamShow(args);
    if (cmd === "team" && sub === "rename") return teamRename(args);
    if (cmd === "run") return runCmd(parseArgs(argv.slice(1)));
    if (cmd === "approve") return approveCmd(parseArgs(argv.slice(1)));
    if (cmd === "reject") return rejectCmd(parseArgs(argv.slice(1)));

    return fail("Unknown command", {
      usage: [
        "aoi-squad-pro preset list",
        "aoi-squad-pro preset show --name <preset>",
        "aoi-squad-pro preset clone --from <preset> --to <new>",
        "aoi-squad-pro team show --preset <preset>",
        "aoi-squad-pro team rename --preset <preset> --role <role> --name \"Name\"",
        "aoi-squad-pro run --preset <preset> --task \"...\" [--demo=create|modify|false]",
        "aoi-squad-pro approve --run <run_id> --id <approval_request_id> [--root <repoRoot>]",
        "aoi-squad-pro reject --run <run_id> --id <approval_request_id> [--note \"...\"]"
      ]
    });
  } catch (e) {
    return fail(e?.message || String(e));
  }
}

main();
