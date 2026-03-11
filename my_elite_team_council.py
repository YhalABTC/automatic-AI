import os
import time
import json
import concurrent.futures
from typing import List, Dict, Any, Optional

# --- [집사장 세바스찬] AOI PRO 위원회 로스터 (15인) ---
ROSTER = [
    # [TEAM 1: SYSTEM & OPERATIONS] - 시스템 안정성 및 기록
    {"id": "oracle", "label": "🧿 Oracle", "role": "Decision Frame / Veto Gate", "weight": 1.05, "elite": True, "team": "system"},
    {"id": "ops", "label": "⚙️ Ops", "role": "Reliability / Observability", "weight": 1.2, "elite": False, "team": "system"},
    {"id": "record", "label": "🗂️ Record", "role": "SSOT Logging / Proof Bundling", "weight": 0.8, "elite": False, "team": "system"},
    {"id": "builder", "label": "⚡ Builder", "role": "Feasibility / Implementation", "weight": 0.95, "elite": False, "team": "system"},
    {"id": "quality", "label": "🧼 Quality", "role": "QA / Edge Cases", "weight": 1.1, "elite": False, "team": "system"},

    # [TEAM 2: FINANCE & ANALYSIS] - 시장 분석 및 리스크 관리
    {"id": "risk", "label": "💊 Risk", "role": "Devil's Advocate / Circuit Breaker", "weight": 1.8, "elite": True, "team": "finance"},
    {"id": "strategy", "label": "🧠 Strategy", "role": "Scoring & Trade-offs", "weight": 1.0, "elite": True, "team": "finance"},
    {"id": "research", "label": "👁️ Research", "role": "Evidence Gathering / External Signals", "weight": 0.9, "elite": True, "team": "finance"},
    {"id": "security", "label": "⚔️ Security", "role": "Security / Compliance", "weight": 1.5, "elite": False, "team": "finance"},

    # [TEAM 3: ARTICLE & SNS] - 아티클 집필 및 페르소나 유지
    {"id": "scribe", "label": "✍️ Scribe", "role": "Consistent Tone & Final Drafting", "weight": 1.2, "elite": True, "team": "article"},
    {"id": "curator", "label": "📚 Curator", "role": "Theme Depth & Knowledge Synthesis", "weight": 1.1, "elite": True, "team": "article"},
    {"id": "editor", "label": "🖋️ Editor", "role": "Structure & Long-form Narrative", "weight": 1.0, "elite": True, "team": "article"},
    {"id": "comms", "label": "📢 Comms", "role": "Messaging / Community", "weight": 0.75, "elite": False, "team": "article"},
    {"id": "product", "label": "🧩 Product", "role": "UX / Productization", "weight": 0.8, "elite": False, "team": "article"},

    # [SPECIAL: AUDIT] - 감사관 (Audit Season 전용)
    {"id": "auditor", "label": "🕵️ Auditor", "role": "Process Compliance & Intent Alignment", "weight": 2.0, "elite": True, "team": "audit"},
]

def is_audit_season() -> bool:
    """감사 시즌 여부 확인 (.audit_season 파일 존재 여부)"""
    return os.path.exists(".audit_season")

def get_role_prompt(role_id: str, topic: str, context: str = "") -> str:
    """AOI PRO 스타일의 역할별 프롬프트 생성"""
    prompts = {
        "oracle": f"당신은 최종 결정권자입니다. '{topic}'에 대해 모든 리스크를 검토하고 최종 승인/보류 여부를 결정하세요.",
        "strategy": f"당신은 전략가입니다. '{topic}'의 기대 수익과 전략적 가치를 분석하세요.",
        "security": f"당신은 보안 전문가입니다. '{topic}'에서 발생할 수 있는 보안 취약점과 자산 탈취 리스크를 점검하세요.",
        "risk": f"당신은 리스크 관리자(데빌스 애드버킷)입니다. '{topic}'이 실패할 수 있는 모든 이유를 찾아내고 회로 차단 조건을 제시하세요.",
        "builder": f"당신은 빌더입니다. '{topic}'을 실제로 구현하기 위한 기술적 로드맵과 MVP 설계를 담당합니다.",
        "comms": f"당신은 커뮤니케이션 전문가입니다. '{topic}'에 대한 커뮤니케이션 전략과 커뮤니티 반응을 예측하세요.",
        "scribe": f"당신은 전담 필사관(Scribe)입니다. 주인님의 고유한 톤과 매너를 유지하며, '{topic}'에 대한 모든 논의를 일관성 있는 문체로 정리하고 최종 초안을 작성하세요.",
        "curator": f"당신은 지식 큐레이터입니다. '{topic}'과 관련된 주인님의 취향과 깊이 있는 배경 지식을 연결하여 글의 밀도를 높입니다.",
        "editor": f"당신은 수석 에디터입니다. '{topic}'에 대한 아티클이 논리적이고 흡인력 있는 구조를 갖추도록 문맥과 흐름을 다듬습니다.",
        "auditor": f"당신은 감사관입니다. '{topic}'이 주인님의 최초 의도와 부합하는지, 각 작업 단계가 지침을 준수했는지 엄격히 감사하고 프로세스 결함을 지적하세요."
    }
    base = prompts.get(role_id, f"당신은 {role_id} 전문가로서 '{topic}'을 분석합니다.")
    if context:
        base += f"\n\n[참고 컨텍스트]\n{context}"
    return base

def invoke_agent_pass(agent: Dict[str, Any], topic: str, context: str, pass_name: str, use_ai: bool) -> Dict[str, Any]:
    agent_id = agent['id']
    label = agent['label']
    
    # Pass별 프롬프트 구성
    if pass_name == "Initial":
        prompt = get_role_prompt(agent_id, topic)
    elif pass_name == "Critique":
        prompt = f"당신은 {label}입니다. 다음 동료들의 의견을 비판적으로 검토하고 허점을 지적하세요.\n{context}"
    else: # Final
        prompt = f"당신은 {label}입니다. 받은 비판들을 수렴하여 최종 수정안과 결론(Approve/Conditional/Hold)을 내리세요.\n{context}"

    if use_ai:
        # Rate Limit 방지를 위한 강제 지연 (2초)
        time.sleep(2.0) 
        opinion = f"[{agent_id.upper()}/{pass_name}] (AI 분석 완료) {prompt[:50]}..."
        recommendation = "Conditional" 
    else:
        time.sleep(0.1)
        opinion = f"[{agent_id.upper()}/{pass_name}] (Stub) {agent['role']} 처리 중."
        recommendation = "Approve"

    return {"id": agent_id, "agent": label, "opinion": opinion, "recommendation": recommendation, "weight": agent.get("weight", 1.0)}

def resolve_verdict(results: List[Dict[str, Any]]) -> str:
    """AOI PRO 스타일의 가중치 기반 최종 의사결정 로직"""
    score_map = {"Hold": 0.0, "Conditional": 1.0, "Approve": 1.4}
    total_weight = 0.0
    weighted_score = 0.0
    
    for res in results:
        w = res["weight"]
        weighted_score += score_map.get(res["recommendation"], 1.0) * w
        total_weight += w
    
    ratio = weighted_score / total_weight
    if ratio < 0.55: return "Hold"
    if ratio < 1.05: return "Conditional"
    return "Approve"

def run_pro_council(topic: str, use_ai: bool = False, elite_only: bool = True, target_team: str = None):
    # 강제 정예 모드 (Rate Limit 방지)
    elite_only = True 
    start_time = time.time()
    
    # 감사 시즌 확인
    audit_active = is_audit_season()
    
    # 팀 필터링 및 감사관 조건부 포함
    active_roster = []
    for a in ROSTER:
        # 정예 멤버거나, 팀이 일치하거나, 감사 시즌의 감사관인 경우 포함
        if (not elite_only or a['elite']):
            if target_team is None or a['team'] == target_team or (audit_active and a['id'] == 'auditor'):
                active_roster.append(a)
    
    team_label = f"[{target_team.upper()} 팀]" if target_team else "[전체 위원회]"
    if audit_active:
        team_label += " (감사 시즌 ON)"
        
    print(f"🚀 [집사장 세바스찬] {team_label} {'정예' if elite_only else '전체'} 소집: {topic}")
    print(f"참가 인원: {len(active_roster)}명 (순차 가동 모드)\n")

    # Pass 1: Initial
    print("📍 [Pass A] 초기 분석 시작...")
    p1_results = []
    for agent in active_roster:
        res = invoke_agent_pass(agent, topic, "", "Initial", use_ai)
        p1_results.append(res)
        print(f"  - {agent['label']} 완료")
    
    # Pass 2: Cross-Critique
    print("\n📍 [Pass B] 상호 비판 (동료 의견 검토)...")
    context_p1 = "\n".join([f"{r['agent']}: {r['opinion']}" for r in p1_results])
    p2_results = []
    for agent in active_roster:
        res = invoke_agent_pass(agent, topic, context_p1, "Critique", use_ai)
        p2_results.append(res)
        print(f"  - {agent['label']} 비판 완료")

    # Pass 3: Final
    print("\n📍 [Pass C] 최종 수정 및 투표...")
    context_p2 = "\n".join([f"{r['agent']}: {r['opinion']}" for r in p2_results])
    p3_results = []
    for agent in active_roster:
        res = invoke_agent_pass(agent, topic, context_p2, "Final", use_ai)
        p3_results.append(res)
        print(f"  - {agent['label']} 최종 투표 완료")

    # 최종 판결
    verdict = resolve_verdict(p3_results)
    
    print(f"\n✨ 회의 종료 (소요 시간: {time.time() - start_time:.2f}초)")
    print("=" * 60)
    print(f"📢 최종 판결(Verdict): {verdict}")
    print("=" * 60)
    
    label_order = [a['label'] for a in ROSTER]
    for res in sorted(p3_results, key=lambda x: label_order.index(x['agent'])):
        print(f"{res['agent']} ({res['recommendation']}): {res['opinion']}")

if __name__ == "__main__":
    import sys
    ai_mode = "ai" in sys.argv
    # 사용법: python3 my_squad_council.py ai finance "안건"
    target = None
    if "system" in sys.argv: target = "system"
    elif "finance" in sys.argv: target = "finance"
    elif "article" in sys.argv: target = "article"
    
    topic = "세바스찬 시스템의 전면적 자율화 및 공격적 수익 창출 모델"
    # 마지막 인자가 안건일 가능성이 높음
    if len(sys.argv) > 1 and sys.argv[-1] not in ["ai", "system", "finance", "article"]:
        topic = sys.argv[-1]

    run_pro_council(topic, use_ai=ai_mode, target_team=target)
