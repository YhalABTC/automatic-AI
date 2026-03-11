#!/usr/bin/env python3
"""AOI Council Web Pilot (async queue, safe for traffic).

A lightweight web wrapper for AOI Council that executes policy checks and
council runs asynchronously in a bounded worker pool.

Flow:
- POST /api/council/run       -> returns task_id immediately
- GET  /api/council/task/<id> -> poll status and get result
- Pro request mode can be: direct / request / off

Other endpoints:
- GET  /                     : UI
- GET  /health
- GET  /api/profiles
- GET  /api/council/run/<run_id> : read manifest by run id from output dir
- GET  /api/council/pro-requests     : admin-only list pending/approved/rejected
- POST /api/council/pro-requests/resolve : admin-only approve/reject (approve triggers async run)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
COUNCIL_RUNNER = ROOT / "aoi_council_run.py"
POLICY_CONFIG_DEFAULT = REPO_ROOT / "context" / "AOI_COUNCIL_POLICY_ENGINE_CONFIG_V0_1.json"
POLICY_CONFIG_DIR = REPO_ROOT / "context"


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AOI Council Pilot</title>
  <style>
    :root { --bg:#07132b; --line:#263b63; --text:#eaf0ff; --muted:#a8b6d4; --ok:#4ade80; --warn:#f59e0b; --bad:#ef4444; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: radial-gradient(circle at 20% 10%, #132647, var(--bg)); color: var(--text); padding:24px; }
    .wrap { max-width: 980px; margin: 0 auto; }
    h1 { margin: 0 0 8px; }
    p.lead { color: var(--muted); margin-top: 0; }
    .panel { background: rgba(255,255,255,0.04); border: 1px solid var(--line); border-radius: 12px; padding: 18px; margin-bottom: 16px; }
    label { display: block; font-weight: 600; margin: 10px 0 6px; }
    input, textarea, select { width: 100%; border: 1px solid #28416f; background: #0f1d3d; color: var(--text); border-radius: 8px; padding: 10px; }
    textarea { min-height: 100px; resize: vertical; }
    button { margin-top: 12px; border:0; border-radius:8px; padding:10px 16px; color:#001; background: linear-gradient(180deg, #6ea9ff, #4f8de9); font-weight:700; cursor:pointer; }
    button[disabled]{ opacity:.6; cursor:not-allowed; }
    .row { display: grid; grid-template-columns:1fr 1fr; gap:12px; }
    .meta { color: var(--muted); font-size:13px; }
    .status { margin-top: 10px; font-weight:700; }
    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .grid2 { display: grid; grid-template-columns:1fr 1fr; gap:12px; }
    .card-title { margin-top:0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; }
    pre { background:#041127; border:1px solid #21406a; border-radius:8px; padding:10px; max-height:260px; overflow:auto; }
    .pill { display:inline-block; border-radius:999px; padding:4px 10px; margin-right:8px; margin-bottom:6px; background:#12274a; border:1px solid #2a4f82; color:#d7e4ff; }
    .tiny { font-size:12px; color: var(--muted); }
    .chat-box { min-height: 220px; display:flex; flex-direction:column; gap: 8px; background: rgba(0,0,0,0.2); border:1px solid #243d66; border-radius: 12px; padding:12px; }
    .msg { border-radius: 10px; padding: 10px 12px; max-width: 92%; line-height:1.45; }
    .msg.user { background: #15315f; margin-left:auto; border:1px solid #2d5ca0; }
    .msg.dissent { border:1px solid #9a3412; background:#34130f; box-shadow: 0 0 0 1px #ef4444 inset; }
    .msg.warning { border:1px solid #854d0e; background:#2b1d0a; }
    .msg.assistant { background: #102949; margin-right:auto; border:1px solid #1e456e; }
    .msg.meta { background:#17314f; color:#9fc0e2; border:1px dashed #35527a; font-size:12px; }
    .msg .title { font-weight:700; font-size:12px; color:#9cbcff; margin-bottom:4px; }
    .chat-scroll { max-height: 280px; overflow:auto; }
    .copy-line { margin-top: 8px; }
    .copy-line button {
      border: 1px solid #315ea8;
      background: rgba(62, 114, 196, 0.24);
      color: #d9e8ff;
      border-radius: 8px;
      padding: 4px 8px;
      font-size: 12px;
      cursor: pointer;
    }
    .copy-line button:hover { background: rgba(62, 114, 196, 0.4); }
    .copy-toast {
      position: fixed;
      left: 50%;
      transform: translateX(-50%);
      bottom: 18px;
      background: #101f3b;
      border: 1px solid #3b5faa;
      color: #d7e4ff;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 12px;
      line-height: 1.35;
      max-width: min(90vw, 460px);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      opacity: 0;
      pointer-events: none;
      transition: opacity 160ms;
      z-index: 50;
    }
    .copy-toast.show { opacity: 1; }

    @media (max-width: 640px) {
      .wrap {
        padding: 0 4px;
      }
      .panel { padding: 14px; }
      .row { grid-template-columns: 1fr; }
      .chat-box { max-height: 320px; }
      .chat-scroll { max-height: 320px; }
      .msg {
        font-size: 14px;
        line-height: 1.65;
      }
      .msg .title {
        font-size: 14px;
      }
      .msg.meta {
        font-size: 12px;
      }
      .copy-line button {
        font-size: 14px;
        width: 100%;
      }
      .copy-toast {
        max-width: calc(100vw - 24px);
        font-size: 12px;
        left: 12px;
        right: 12px;
        transform: none;
        white-space: normal;
      }
    }
    .evidence-item { list-style: none; margin-left: -16px; margin-top: 4px; }
    .evidence-item summary { cursor: pointer; color: #9cc5ff; }
    .evidence-item .toggle-label { color: #f59e0b; margin-left: 8px; font-size: 11px; opacity: 0.95; }
    .evidence-item[open] .toggle-label::before { content: "(접기)"; }
    .evidence-item:not([open]) .toggle-label::before { content: "(더보기)"; }
    .evidence-item[open] summary { color: #f0f0f0; }
    .evidence-item summary::marker { color: #94a3b8; }
    .evidence-item .full-evidence { display: block; margin-top: 4px; color: #d4e1ff; white-space: pre-wrap; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>AOI Council Pilot</h1>
    <p class="lead">AOI Core 하위 AOI Council Lite/Pro의 웹 시험판(비동기 실행). 동접이 많아도 큐 기반으로 버텨요.</p>

    <div class="panel">
      <form id="cForm">
        <div class="row">
          <div>
            <label>Topic *</label>
            <textarea id="topic" placeholder="질문/주제를 입력하세요"></textarea>
          </div>
          <div>
            <label>Context</label>
            <textarea id="context" placeholder="배경/범위/제약사항"></textarea>
            <label>Mode</label>
            <select id="mode"><option value="lite" selected>Lite</option><option value="pro">Pro (요청형 승인 포함)</option></select>
            <label>Policy profile</label>
            <select id="profile"></select>
          </div>
        </div>
        <label>Constraints</label>
        <input id="constraints" value="L1/L2 only. No money/wallet/on-chain signing/external posting. STEALTH/Top secret not for public." />
        <button id="runBtn" type="submit">Run Council</button>
        <div class="meta">Pro는 설정에 따라 승인 큐/오프/직행 처리됩니다.</div>
      </form>
      <div id="status" class="status"></div>
      <div id="copy-toast" class="copy-toast" role="status" aria-live="polite"></div>
    </div>

    <div class="panel">
      <h3 class="card-title">Conversation</h3>
      <div id="chat" class="chat-box chat-scroll">
        <div class="msg assistant meta">AOI Council에 오신 걸 환영합니다. 질문을 넣으면 실시간으로 작업 상태와 결과를 반환할게요.</div>
      </div>
    </div>

    <div class="panel" id="result" hidden>
      <h3 class="card-title">Result</h3>
      <div id="summary"></div>
      <div class="grid2">
        <div><h4 class="card-title">Policy scorecard</h4><div id="policy"></div></div>
        <div><h4 class="card-title">Artifacts</h4><div id="artifacts" class="tiny"></div></div>
      </div>
      <h4 class="card-title">Verdict</h4>
      <pre id="verdict" class="mono"></pre>
      <h4 class="card-title">Report snapshot</h4>
      <pre id="report" class="mono"></pre>
    </div>
  </div>

<script>
function fetchProfiles() {
  const select = document.getElementById('profile');
  fetch('/api/profiles').then(r=>r.json()).then(j=>{
    const profiles = j.profiles || [];
    const opt = document.createElement('option');
    opt.value='default'; opt.textContent='default';
    select.appendChild(opt);
    for (const p of profiles) {
      const o = document.createElement('option');
      o.value = p;
      o.textContent = p.replace('.json', '');
      select.appendChild(o);
    }
  }).catch(()=>{
    const o = document.createElement('option');
    o.value='default'; o.textContent='default';
    select.appendChild(o);
  });
}

function setStatus(msg, cls='') {
  const el = document.getElementById('status');
  el.className = 'status ' + cls;
  el.textContent = msg;
}

function addMsg(kind, title, text) {
  const chat = document.getElementById('chat');
  const div = document.createElement('div');
  div.className = `msg ${kind}`;
  const safeTitle = escapeHtml(title || '');
  const safeText = text === undefined || text === null ? '' : escapeHtml(String(text));
  div.innerHTML = `<div class="title">${safeTitle}</div><div>${safeText}</div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(v) {
  return String(v).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

function copyText(btn) {
  const show = (msg, isErr = false) => {
    const t = document.getElementById('copy-toast');
    if (!t) {
      return;
    }
    t.textContent = msg;
    t.style.borderColor = isErr ? '#ef4444' : '#3b82f6';
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1700);
  };

  try {
    const card = btn && btn.closest('.msg');
    const txt = card ? (card.getAttribute('data-copy-text') || '') : '';
    if (!txt) {
      show('복사할 텍스트가 없습니다.', true);
      return;
    }

    const done = () => {
      const old = btn.textContent;
      btn.textContent = '복사됨';
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = old || '요약복제 복사';
        btn.disabled = false;
      }, 1400);
      show('요약 복사 완료');
    };

    const fallback = () => {
      const input = document.createElement('textarea');
      input.value = txt;
      input.style.position = 'fixed';
      input.style.opacity = '0';
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      done();
    };

    if (!btn) {
      show('복사 버튼 참조 실패', true);
      return;
    }

    if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(done).catch(fallback);
    } else {
      fallback();
    }
  } catch (_) {
    show('복사 중 오류 발생', true);
  }
}

const taskLastStatus = {};

function shortText(v, maxLen = 160) {
  const s = String(v || '').replace(/\s+/g, ' ').trim();
  return s.length > maxLen ? `${s.slice(0, maxLen - 1).trim()}…` : s;
}

function lineWithToggle(line, maxLen = 140) {
  const text = String(line || '').trim();
  const safe = escapeHtml(text);
  if (text.length <= maxLen) {
    return `<span>${safe}</span>`;
  }
  const short = escapeHtml(text.slice(0, maxLen).trim() + '…');
  return `<details class="evidence-item"><summary>${short}<span class="toggle-label"> </span></summary><span class="full-evidence">${safe}</span></details>`;
}

function addAdviceCard(role, lines, topicText, tone = 'normal', extraLines = []) {
  if (!lines.length) {
    lines.push('근거가 충분하지 않습니다.');
  }
  const titleTone = tone === 'dissent' ? '💥' : '💬';
  const summaryLines = [
    `추천: ${role}`,
    `주제: ${topicText}`,
    ...lines,
  ];
  if (Array.isArray(extraLines) && extraLines.length > 0) {
    for (const extra of extraLines) {
      summaryLines.push(`추가: ${extra}`);
    }
  }
  const html = [
    `<div class="title">${titleTone} ${escapeHtml(role)}</div>`,
    `<div><strong>${escapeHtml(topicText)}</strong></div>`,
    `<ul style="margin:8px 0 4px 16px; padding:0;">`,
    ...lines.map((x) => `<li>${lineWithToggle(x, 140)}</li>`),
    `</ul>`,
    `<div class="copy-line"><button type="button" onclick="copyText(this)">요약복제 복사</button></div>`,
  ].join('');
  const chat = document.getElementById('chat');
  const div = document.createElement('div');
  div.className = tone === 'dissent' ? 'msg assistant dissent' : 'msg assistant';
  div.setAttribute('data-copy-text', summaryLines.join('\n'));
  div.innerHTML = html;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function createPill(v) {
  const s = document.createElement('span');
  s.className = 'pill';
  s.textContent = v;
  return s;
}

function pollTask(taskId, showResult, topicText) {
  const timer = setInterval(async ()=>{
    try {
      const r = await fetch('/api/council/task/' + encodeURIComponent(taskId));
      const j = await r.json();
      if (!j.ok) {
        addMsg('assistant', '시스템', j.error || '작업 상태 조회 실패');
        setStatus(j.error || 'task error', 'bad');
        clearInterval(timer);
        return;
      }
      const status = j.status;
      const q = j.queue_position !== undefined ? `queue: ${j.queue_position}` : '';
      if (taskLastStatus[taskId] !== status) {
        taskLastStatus[taskId] = status;
        setStatus(`Task ${taskId}: ${status}` + (q ? ` (${q})` : ''), status === 'completed' ? 'ok' : 'warn');
        if (status === 'queued' || status === 'running') {
          addMsg('assistant', '상태 업데이트', `${status === 'queued' ? '대기중' : '실행중'} · ${escapeHtml(topicText)}`);
        } else if (status === 'failed') {
          addMsg('assistant', '실행 오류', j.error || 'task failed');
          setStatus(j.error || 'task failed', 'bad');
          clearInterval(timer);
        }
      }
      if (status === 'completed') {
        addMsg('assistant', '최종 답변', '판단 완료했습니다.');
        showResult(j);
        clearInterval(timer);
      }
    } catch (_) {
      addMsg('assistant', '시스템', '폴링 중 네트워크 오류');
      clearInterval(timer);
      setStatus('poll failed', 'bad');
    }
  }, 900);
}

function pickRoleEvidence(roles, maxLines = 2) {
  const lines = [];
  if (!Array.isArray(roles)) {
    return lines;
  }
  for (const r of roles) {
    const text = (r.output || '').toString().trim();
    if (!text) {
      continue;
    }
    const label = r.label || r.id || 'role';
    lines.push(`${label}: ${shortText(text, 120)}`);
    if (lines.length >= maxLines) {
      break;
    }
  }
  return lines;
}

function formatPassVotes(votes) {
  if (!votes || typeof votes !== 'object') {
    return [];
  }
  const entries = Object.entries(votes)
    .map(([k, v]) => ({ k, v: Number(v) || 0 }))
    .filter((x) => x.v > 0)
    .sort((a, b) => b.v - a.v || a.k.localeCompare(b.k));
  return entries.map((x) => `${x.k}: ${x.v}`);
}

function buildEvidenceLines(manifest) {
  const synthesis = manifest.synthesis || {};
  const policyChecks = manifest.policy_check || {};
  const out = [];

  const gateDigest = buildGateDigest(manifest);
  for (const g of gateDigest) {
    out.push(g);
    if (out.length >= 2) {
      break;
    }
  }

  if (Array.isArray(synthesis.assumptions) && synthesis.assumptions.length) {
    out.push(`Assumption: ${shortText(synthesis.assumptions[0], 100)}`);
  }

  if (Array.isArray(synthesis.dissent) && synthesis.dissent.length) {
    out.push(`Dissent: ${synthesis.dissent.slice(0, 2).join(', ')}`);
  }

  if (synthesis.conflict) {
    out.push(`Conflict: ${shortText(synthesis.conflict, 100)}`);
  }

  const votes = formatPassVotes(synthesis.pass_votes);
  for (const v of votes) {
    if (out.length >= 3) {
      break;
    }
    out.push(`투표: ${v}`);
  }

  const checks = policyChecks.checks || [];
  for (const c of checks) {
    if (out.length >= 3) {
      break;
    }
    if (c.note && c.status && c.status !== 'PASS') {
      out.push(`${c.id}: ${shortText(c.note, 100)}`);
    }
  }

  if (out.length < 3) {
    for (const line of pickRoleEvidence(manifest.roles, 3 - out.length)) {
      out.push(shortText(line, 120));
    }
  }
  return out.slice(0, 3);
}

function buildPolicyDigest(summary, checks) {
  if (!summary) {
    return [];
  }
  const policyStatus = summary.status || 'PASS';
  const parts = [`정책: ${policyStatus} / score=${summary.score ?? 0} / warn=${summary.warn_count ?? 0} / fail=${summary.fail_count ?? 0}`];
  if (Array.isArray(checks)) {
    for (const c of checks) {
      if (String(c.status).toUpperCase() !== 'PASS') {
        parts.push(`${c.id}: ${c.status}`);
      }
    }
  }
  return parts;
}

function buildGateDigest(manifest) {
  const verdict = manifest.verdict || {};
  const permission = verdict.permission || {};
  const cost = verdict.cost_governor || {};
  const action = verdict.action || (manifest.synthesis || {}).action_decision || 'REVIEW';
  const evidence = verdict.evidence_id || '없음';
  return [
    `Action 게이트: ${action}`,
    `정책 evidence: ${evidence}`,
    `Permission: ${permission.status || '-'} / ${permission.decision || '-'}`,
    `Cost: ${cost.status || '-'} / ${cost.decision || '-'} (${cost.auto_action || '-'})`,
    `Cost 사유: ${cost.reason || '-'}`,
  ];
}

function renderAdviceDigest(manifest, reportPreview) {
  const synthesis = manifest.synthesis || {};
  const topic = manifest.inputs?.topic || 'topic';
  const policySummary = manifest.policy_check?.summary || {};
  const policyStatus = (policySummary.status || 'PASS').toUpperCase();
  const policyAdjustments = (synthesis.policy_adjustments || []).map((x) => `${x}`);
  const title = `${synthesis.recommendation || 'UNKNOWN'} / 신뢰도 ${synthesis.confidence || '-'} / 리스크 ${synthesis.risk || '-'}`;

  const policyDigest = buildPolicyDigest(policySummary, manifest.policy_check?.checks || []);
  const evidence = [
    ...(synthesis.assumptions?.slice(0, 1) || []),
    ...policyDigest,
    ...buildEvidenceLines(manifest),
  ];

  const cards = [
    shortText(synthesis.consensus || synthesis.recommendation || '조언 요약이 생성되지 않았습니다.', 220),
    '근거 1: ' + shortText((evidence[0] || '근거가 부족합니다.'), 140),
    '근거 2: ' + shortText((evidence[1] || '근거가 부족합니다.'), 140),
    '근거 3: ' + shortText((evidence[2] || '근거가 부족합니다.'), 140),
  ];

  if (policyAdjustments.length > 0) {
    cards.push('제약 반영: ' + policyAdjustments.join(', '));
  }

  if (policyStatus === 'FAIL' || Number(policySummary.fail_count || 0) > 0) {
    cards.push('정책 게이트: FAIL(강제 보류)');
  } else if (policyStatus === 'WARN' || Number(policySummary.warn_count || 0) > 0) {
    cards.push('정책 게이트: WARN(주의)');
  } else {
    cards.push('정책 게이트: PASS');
  }

  const dissent = Array.isArray(synthesis.dissent) ? synthesis.dissent : [];
  const tone = (dissent && dissent.length > 0) ? 'dissent' : 'normal';
  const cardTitle = title + (tone === 'dissent' ? ' / ⚠️ Dissent 존재' : '');
  const policyAdjustText = policyAdjustments.join(', ');
  const copyExtras = [
    `정책 게이트: ${policyStatus} / score=${policySummary.score ?? 0} / warn=${policySummary.warn_count ?? 0} / fail=${policySummary.fail_count ?? 0}`,
    `근거 합산: ${cards.slice(0, 3).length}개`,
  ];
  if (policyAdjustText) {
    copyExtras.push(`제약 반영: ${policyAdjustText}`);
  }
  if (cards[3]) {
    copyExtras.push(cards[3]);
  }
  addAdviceCard(cardTitle, cards.slice(0, 4), topic, tone, copyExtras);

  const verdict = manifest.verdict || {};
  const permission = verdict.permission || {};
  const cost = verdict.cost_governor || {};
  document.getElementById('verdict').textContent = JSON.stringify({
    synthesis: {
      recommendation: synthesis.recommendation || 'UNKNOWN',
      confidence: synthesis.confidence || 'Unknown',
      risk: synthesis.risk || 'Unknown',
      consensus: synthesis.consensus || '',
      conflict: synthesis.conflict || '',
      dissent: synthesis.dissent || [],
      assumptions: synthesis.assumptions || [],
      pass_votes: synthesis.pass_votes || {},
      policy_adjustments: synthesis.policy_adjustments || [],
      action_decision: synthesis.action_decision || '-',
    },
    policy_summary: policySummary,
    verdict: {
      action: verdict.action || '-',
      evidence_id: verdict.evidence_id || '-',
      permission: {
        status: permission.status || '-',
        decision: permission.decision || '-',
        permission_id: permission.permission_id || '-',
      },
      cost_governor: {
        status: cost.status || '-',
        decision: cost.decision || '-',
        auto_action: cost.auto_action || '-',
        reason: cost.reason || '-',
      },
    },
    checks: {
      policy: manifest.policy_check || {},
      permission_scope: manifest.permission_scope_check || {},
      cost_governor: manifest.cost_governor_check || {},
    },
  }, null, 2);

  document.getElementById('report').textContent = reportPreview || '(no report preview)';
}



function showResult(data) {
  const manifest = data.manifest || {};
  const policy = manifest.policy_check?.summary || {};
  const synthesis = manifest.synthesis || {};

  const summary = document.getElementById('summary');
  const verdict = manifest.verdict || {};
  const permission = verdict.permission || {};
  const cost = verdict.cost_governor || {};
  const action = verdict.action || synthesis.action_decision || '-';
  const evidenceId = verdict.evidence_id || '-';
  summary.innerHTML = '';
  [
    createPill(`mode: ${manifest.executor || 'n/a'}`),
    createPill(`action: ${action}`),
    createPill(`recommendation: ${synthesis.recommendation || '-'}`),
    createPill(`confidence: ${synthesis.confidence || '-'}`),
    createPill(`risk: ${synthesis.risk || '-'}`),
    createPill(`policy status: ${policy.status || '-'}`),
    createPill(`score: ${policy.score ?? 0}`),
    createPill(`evidence: ${evidenceId}`),
    createPill(`permission: ${permission.status || '-'} / ${permission.decision || '-'}`),
    createPill(`cost: ${cost.status || '-'} / ${cost.decision || '-'} (${cost.auto_action || '-'})`),
  ].forEach(x=>summary.appendChild(x));

  const policyEl = document.getElementById('policy');
  policyEl.innerHTML = '';
  const breakdown = policy.weighted_breakdown || [];
  const summaryText = `status=${policy.status||'PASS'}, score=${policy.score ?? 0}, warn=${policy.warn_count ?? 0}, fail=${policy.fail_count ?? 0}`;
  policyEl.appendChild(document.createTextNode(summaryText));
  if (breakdown.length) {
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(breakdown, null, 2);
    policyEl.appendChild(pre);
  }

  renderAdviceDigest(manifest, data.report_preview);

  const arts = document.getElementById('artifacts');
  arts.innerHTML = '';
  const outputs = manifest.outputs || {};
  for (const [k,v] of Object.entries(outputs)) {
    const d = document.createElement('div');
    d.innerHTML = `<span style="color:#8db1ff">${k}</span> : ${v}`;
    arts.appendChild(d);
  }
  document.getElementById('result').hidden = false;
}

fetchProfiles();

document.getElementById('cForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const topic = document.getElementById('topic').value.trim();
  const context = document.getElementById('context').value.trim();
  const mode = document.getElementById('mode').value;
  const profile = document.getElementById('profile').value || 'default';
  const constraints = document.getElementById('constraints').value.trim();
  if (!topic) {
    addMsg('assistant', '시스템', 'Topic is required.');
    return;
  }

  document.getElementById('runBtn').disabled = true;
  const shortTopic = topic.length > 100 ? topic.slice(0, 100) + '...' : topic;
  addMsg('user', '질문자', shortTopic);
  addMsg('assistant', '상태 업데이트', '요청 접수됨. 작업 생성 중...');
  document.getElementById('result').hidden = true;

  try {
    const r = await fetch('/api/council/run', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({topic, context, mode, profile, constraints})
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      addMsg('assistant', '시스템', data.error || 'Failed to submit');
      setStatus(data.error || 'Failed to submit', 'bad');
      return;
    }
    if (data.status === 'approval_required') {
      const msg = `Pro 승인 대기 중입니다. request_id=${data.request_id}`;
      addMsg('assistant', '승인', msg);
      setStatus(msg, 'warn');
      return;
    }
    if (!data.task_id) {
      addMsg('assistant', '시스템', '작업 ID가 안 떨어졌어.');
      setStatus('No task id returned', 'bad');
      return;
    }
    setStatus(`Task accepted: ${data.task_id}`, 'warn');
    addMsg('assistant', '상태 업데이트', `Task ${data.task_id} 생성됨. 실행 로그를 폴링합니다.`);
    pollTask(data.task_id, showResult, shortTopic);
  } finally {
    document.getElementById('runBtn').disabled = false;
  }
});
</script>
</body>
</html>
"""





@dataclass
class Job:
    task_id: str
    status: str
    mode: str
    topic: str
    context: str
    profile: str
    constraints: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    run_id: str | None = None
    manifest: dict[str, Any] | None = None
    report_preview: str = ""
    error: str | None = None
    queue_position: int = 0


@dataclass
class ServerConfig:
    host: str
    port: int
    out_dir: Path
    pro_access: str
    pro_request_file: Path
    admin_token: str | None
    max_topic_length: int
    max_context_length: int
    max_workers: int
    max_queue: int
    max_tasks_per_minute: int
    pro_tasks_per_minute: int


@dataclass
class PilotRuntime:
    config: ServerConfig
    executor: concurrent.futures.ThreadPoolExecutor
    jobs: dict[str, Job] = field(default_factory=dict)
    rate_hits: dict[str, deque] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    shutdown: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> float:
    return time.time()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _count_recent(hits: deque, window_sec: int) -> int:
    now = now_ts()
    while hits and now - hits[0] > window_sec:
        hits.popleft()
    return len(hits)


class RequestHandler(http.server.BaseHTTPRequestHandler):
    runtime: PilotRuntime

    def _set_json(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._set_json(status)
        self.wfile.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        try:
            self.wfile.flush()
        except Exception:
            pass

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")
        self.end_headers()

    # ---- helpers ----
    def _client_key(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        host = self.client_address[0] if self.client_address else "unknown"
        return host

    def _rate_limit_hit(self, mode: str) -> bool:
        key = self._client_key()
        window = 60  # sec
        with self.runtime.lock:
            if key not in self.runtime.rate_hits:
                self.runtime.rate_hits[key] = deque()
            dq = self.runtime.rate_hits[key]
            _count_recent(dq, window)
            limit = self.runtime.config.max_tasks_per_minute
            if mode == "pro":
                limit = self.runtime.config.pro_tasks_per_minute
            if len(dq) >= limit:
                return True
            dq.append(now_ts())
            return False

    def _require_admin(self) -> bool:
        token = self.headers.get("X-Admin-Token", "")
        return bool(self.runtime.config.admin_token) and token == self.runtime.config.admin_token

    def _sanitize_text(self, value: str | None, max_len: int) -> str:
        if not value:
            return ""
        return str(value).strip().replace("\x00", "")[:max_len]

    def _read_json(self) -> dict[str, Any] | None:
        if self.headers.get("Content-Type", "") != "application/json":
            self._send_json(400, {"ok": False, "error": "Content-Type must be application/json"})
            return None
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "invalid json"})
            return None

    # ---- request store/queue ----
    def _request_queue_path(self) -> Path:
        return self.runtime.config.pro_request_file

    def _load_requests(self) -> list[dict[str, Any]]:
        p = self._request_queue_path()
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

    def _save_requests(self, reqs: list[dict[str, Any]]) -> None:
        p = self._request_queue_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in reqs), encoding="utf-8")

    def _append_request(self, payload: dict[str, Any]) -> str:
        req_id = f"proreq_{int(now_ts())}_{uuid.uuid4().hex[:8]}"
        req = {
            "request_id": req_id,
            "status": "pending",
            "created_at": now_iso(),
            "topic": payload.get("topic", ""),
            "context": payload.get("context", ""),
            "profile": payload.get("profile", "default"),
            "constraints": payload.get("constraints", ""),
            "mode": "pro",
        }
        reqs = self._load_requests()
        reqs.append(req)
        self._save_requests(reqs)
        return req_id

    def _set_request_status(self, request_id: str, status: str) -> dict[str, Any] | None:
        reqs = self._load_requests()
        target = None
        for item in reqs:
            if item.get("request_id") == request_id:
                target = item
                break
        if target is None:
            return None
        if target.get("status") != "pending":
            return target
        target["status"] = status
        target["resolved_at"] = now_iso()
        self._save_requests(reqs)
        return target

    def _queue_stats(self) -> tuple[int, int]:
        # returns (running, queued)
        running = 0
        queued = 0
        for j in self.runtime.jobs.values():
            if j.status == "running":
                running += 1
            elif j.status == "queued":
                queued += 1
        return running, queued

    # ---- council runner ----
    def _run_council(self, topic: str, context: str, mode: str, profile: str, constraints: str) -> dict[str, Any]:
        cmd = [
            sys.executable,
            str(COUNCIL_RUNNER),
            "--mode",
            "decision",
            "--topic",
            topic,
            "--context",
            context,
            "--out-dir",
            str(self.runtime.config.out_dir),
        ]
        if mode == "pro":
            cmd.append("--pro")

        env = os.environ.copy()
        if profile and profile.lower() != "default":
            selected = POLICY_CONFIG_DIR / profile
            if selected.exists():
                env["AOI_COUNCIL_POLICY_CONFIG"] = str(selected)

        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            check=True,
            text=True,
            capture_output=True,
            env=env,
            timeout=180,
        )
        _ = result

        candidates = sorted((self.runtime.config.out_dir).glob("council_*/"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise RuntimeError("run output not found")

        latest = candidates[0]
        manifest_path = latest / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("manifest missing")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report_preview = ""
        report_path = latest / "report.md"
        if report_path.exists():
            report_preview = report_path.read_text(encoding="utf-8", errors="ignore")[:4000]

        return {
            "run_id": latest.name,
            "manifest": manifest,
            "report_preview": report_preview,
        }

    def _job_runner(self, job_id: str) -> None:
        with self.runtime.lock:
            job = self.runtime.jobs.get(job_id)
            if not job:
                return
            if job.status != "queued":
                return
            job.status = "running"
            job.started_at = now_ts()
            # update queue positions cheaply
            queued = [j for j in self.runtime.jobs.values() if j.status in {"queued", "running"}]
            queued = sorted(queued, key=lambda x: x.created_at)
            for idx, j in enumerate(queued):
                j.queue_position = max(0, idx)

        try:
            result = self._run_council(job.topic, job.context, job.mode, job.profile, job.constraints)
            with self.runtime.lock:
                job.status = "completed"
                job.finished_at = now_ts()
                job.run_id = result["run_id"]
                job.manifest = result["manifest"]
                job.report_preview = result["report_preview"]
        except subprocess.TimeoutExpired:
            with self.runtime.lock:
                job.status = "failed"
                job.error = "runner_timeout"
                job.finished_at = now_ts()
        except subprocess.CalledProcessError as exc:
            with self.runtime.lock:
                job.status = "failed"
                job.error = f"runner_failed: {exc.stderr or exc.stdout}"
                job.finished_at = now_ts()
        except Exception as exc:
            with self.runtime.lock:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = now_ts()
        finally:
            # finalize queue positions
            with self.runtime.lock:
                active = [j for j in self.runtime.jobs.values() if j.status in {"queued", "running"}]
                active = sorted(active, key=lambda x: x.created_at)
                for idx, j in enumerate(active):
                    j.queue_position = idx

    def _submit_job(self, topic: str, context: str, mode: str, profile: str, constraints: str) -> tuple[bool, str, str | None]:
        if self._rate_limit_hit(mode):
            return False, "rate_limited", None

        with self.runtime.lock:
            _, queued = self._queue_stats()
            if queued >= self.runtime.config.max_queue:
                return False, "queue_full", None

            task_id = f"task_{int(now_ts())}_{uuid.uuid4().hex[:8]}"
            job = Job(
                task_id=task_id,
                status="queued",
                mode=mode,
                topic=topic,
                context=context,
                profile=profile,
                constraints=constraints,
                created_at=now_ts(),
            )
            self.runtime.jobs[task_id] = job
            self.runtime.executor.submit(self._job_runner, task_id)
            pos = len([j for j in self.runtime.jobs.values() if j.status in {"queued", "running"}])
            job.queue_position = pos
            return True, task_id, None

    # ---- handlers ----
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))
            return

        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "ts": now_iso()})
            return

        if parsed.path == "/api/profiles":
            profiles = []
            if POLICY_CONFIG_DIR.exists():
                for p in sorted(POLICY_CONFIG_DIR.glob("AOI_COUNCIL_POLICY_ENGINE_PROFILE_*.json")):
                    profiles.append(p.name)
            self._send_json(200, {"ok": True, "profiles": profiles})
            return

        if parsed.path == "/api/council/pro-requests":
            if not self._require_admin():
                self._send_json(403, {"ok": False, "error": "admin token required"})
                return
            qs = parse_qs(parsed.query)
            status = (qs.get("status", [""])[0] or "").strip()
            reqs = self._load_requests()
            if status:
                reqs = [r for r in reqs if r.get("status") == status]
            self._send_json(200, {"ok": True, "requests": reqs})
            return

        # task status
        m = re.match(r"^/api/council/task/([^/]+)$", parsed.path)
        if m:
            task_id = m.group(1)
            with self.runtime.lock:
                job = self.runtime.jobs.get(task_id)
                if not job:
                    self._send_json(404, {"ok": False, "error": "task not found"})
                    return
                payload = {
                    "ok": True,
                    "task_id": task_id,
                    "status": job.status,
                    "mode": job.mode,
                    "queue_position": job.queue_position,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "finished_at": job.finished_at,
                    "run_id": job.run_id,
                    "manifest": job.manifest,
                    "report_preview": job.report_preview,
                    "error": job.error,
                }
                self._send_json(200, payload)
                return

        # run-id manifest lookup
        m = re.match(r"^/api/council/run/([^/]+)$", parsed.path)
        if m:
            run_id = m.group(1)
            manifest_path = self.runtime.config.out_dir / run_id / "manifest.json"
            if not manifest_path.exists():
                self._send_json(404, {"ok": False, "error": "run_id not found"})
                return
            self._send_json(200, {"ok": True, "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))})
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        if self.path == "/api/council/run":
            self._handle_run()
            return
        if self.path == "/api/council/pro-requests/resolve":
            self._handle_resolve()
            return
        self.send_error(404, "Not found")

    def _handle_run(self) -> None:
        payload = self._read_json()
        if payload is None:
            return

        topic = self._sanitize_text(payload.get("topic", ""), self.runtime.config.max_topic_length)
        context = self._sanitize_text(payload.get("context", ""), self.runtime.config.max_context_length)
        constraints = self._sanitize_text(payload.get("constraints", ""), 600)
        profile = self._sanitize_text(payload.get("profile", "default"), 200) or "default"
        mode = str(payload.get("mode", "lite")).lower()

        if not topic:
            self._send_json(400, {"ok": False, "error": "topic is required"})
            return

        # Pro access gating
        if mode == "pro":
            if self.runtime.config.pro_access == "off":
                self._send_json(403, {"ok": False, "error": "Pro is disabled"})
                return
            if self.runtime.config.pro_access == "request":
                req_id = self._append_request({
                    "topic": topic,
                    "context": context,
                    "profile": profile,
                    "constraints": constraints,
                })
                self._send_json(200, {
                    "ok": True,
                    "status": "approval_required",
                    "request_id": req_id,
                    "message": "Pro request queued. Await manual approval.",
                })
                return

        success, task_id, err = self._submit_job(topic, context, mode, profile, constraints)
        if not success:
            status_code = 429 if err in {"rate_limited", "queue_full"} else 500
            if err == "rate_limited":
                msg = "Too many requests. Please slow down."
            elif err == "queue_full":
                msg = "Queue is full. Please retry later."
            else:
                msg = "Failed to submit"
            self._send_json(status_code, {"ok": False, "error": msg})
            return

        self._send_json(202, {
            "ok": True,
            "status": "accepted",
            "task_id": task_id,
            "message": "Task submitted; poll /api/council/task/{task_id}",
        })

    def _handle_resolve(self) -> None:
        if not self._require_admin():
            self._send_json(403, {"ok": False, "error": "admin token required"})
            return

        payload = self._read_json()
        if payload is None:
            return

        request_id = self._sanitize_text(payload.get("request_id", ""), 120)
        action = (payload.get("action") or "").strip().lower()
        if action not in {"approve", "reject"} or not request_id:
            self._send_json(400, {"ok": False, "error": "request_id and action required"})
            return

        req = self._set_request_status(request_id, "approved" if action == "approve" else "rejected")
        if req is None:
            self._send_json(404, {"ok": False, "error": "request not found"})
            return

        run_payload = None
        if action == "approve":
            success, task_id, _ = self._submit_job(
                req.get("topic", ""),
                req.get("context", ""),
                "pro",
                req.get("profile", "default"),
                req.get("constraints", ""),
            )
            if not success:
                req["execution_status"] = "failed_submit"
            else:
                req["execution_status"] = "queued"
                req["task_id"] = task_id
                run_payload = {
                    "task_id": task_id,
                    "status": "accepted",
                }
        self._save_requests(self._load_requests())

        self._send_json(200, {
            "ok": True,
            "request_id": request_id,
            "status": req.get("status"),
            "request": req,
            "run": run_payload,
        })


def run_server(config: ServerConfig) -> None:
    runtime = PilotRuntime(
        config=config,
        executor=concurrent.futures.ThreadPoolExecutor(max_workers=config.max_workers),
    )
    RequestHandler.runtime = runtime

    with socketserver.TCPServer((config.host, config.port), RequestHandler) as httpd:
        print(f"AOI Council Pilot listening on http://{config.host}:{config.port}")
        print(f"Policy output dir: {config.out_dir}")
        print(f"Pro access: {config.pro_access}")
        try:
            httpd.serve_forever()
        finally:
            runtime.executor.shutdown(wait=False)


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--out-dir", default="/tmp/aoi-council-pilot")
    ap.add_argument("--pro-access", choices=["direct", "request", "off"], default="request")
    ap.add_argument("--pro-request-file", default="/tmp/council_pro_requests.jsonl")
    ap.add_argument("--pro-admin-token", default=os.environ.get("AOI_COUNCIL_PILOT_ADMIN_TOKEN", ""))
    ap.add_argument("--max-topic-length", type=int, default=600)
    ap.add_argument("--max-context-length", type=int, default=2000)
    ap.add_argument("--max-workers", type=int, default=2)
    ap.add_argument("--max-queue", type=int, default=20)
    ap.add_argument("--max-tasks-per-minute", type=int, default=30)
    ap.add_argument("--pro-tasks-per-minute", type=int, default=8)
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not COUNCIL_RUNNER.exists():
        raise FileNotFoundError(f"COUNCIL runner missing: {COUNCIL_RUNNER}")

    config = ServerConfig(
        host=args.host,
        port=args.port,
        out_dir=out_dir,
        pro_access=args.pro_access,
        pro_request_file=Path(args.pro_request_file),
        admin_token=args.pro_admin_token or None,
        max_topic_length=args.max_topic_length,
        max_context_length=args.max_context_length,
        max_workers=args.max_workers,
        max_queue=args.max_queue,
        max_tasks_per_minute=args.max_tasks_per_minute,
        pro_tasks_per_minute=args.pro_tasks_per_minute,
    )

    if not POLICY_CONFIG_DEFAULT.exists():
        print(f"[pilot] warning: default policy config not found: {POLICY_CONFIG_DEFAULT}")

    run_server(config)


if __name__ == "__main__":
    main()
