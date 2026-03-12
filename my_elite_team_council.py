import os
import subprocess
import time
import json
import concurrent.futures
from typing import List, Dict, Any, Optional


# --- 에이전트 상태(컨텍스트) 유지 로직 ---
AGENT_STATE_DIR = "memory/agent_states"
os.makedirs(AGENT_STATE_DIR, exist_ok=True)

def save_agent_state(agent_id: str, state: dict):
    state_file = os.path.join(AGENT_STATE_DIR, f"{agent_id}.json")
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def load_agent_state(agent_id: str) -> dict:
    state_file = os.path.join(AGENT_STATE_DIR, f"{agent_id}.json")
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}
# ----------------------------------------

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


def delegate_to_servant(role_label: str, prompt: str) -> str:
    """openclaw agent CLI를 호출하여 실제 하인 세션을 스폰하고 결과를 반환"""
    import subprocess
    import uuid
    import time
    print(f"    [Servant Call] {role_label}님이 OpenClaw 하인 세션을 소집하여 실무를 지시 중입니다...")
    
    # 하인 세션 ID 생성 (디버깅 용이하도록 라벨 포함)
    role_name = role_label.split()[-1].lower() if " " in role_label else "agent"
    session_id = f"servant_{role_name}_{uuid.uuid4().hex[:4]}"
    
    # 프롬프트에 하인의 역할과 강제 출력 포맷 지정
    system_instruction = (
        f"당신은 {role_label}를 보좌하는 유능한 하인(서브 에이전트)입니다. "
        "주인님의 지시를 받아 철저하게 분석하고 논리적인 글을 작성하십시오. "
        "대화형 응답(예: 알겠습니다 등)을 생략하고 오직 결과물만 출력하세요. "
        "마지막 줄에는 반드시 [APPROVE], [HOLD], [CONDITIONAL] 중 하나를 판결로 명시하십시오.\\n"
        f"--- 지시사항 ---\\n{prompt}"
    )
    
    try:
        # Rate Limit 우회를 위해 에이전트 스폰 간 약간의 딜레이
        time.sleep(2.0)
        result = subprocess.run(
            ["openclaw", "agent", "--session-id", session_id, "-m", system_instruction],
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"[실패: {result.stderr.strip()}]"
    except Exception as e:
        return f"[오류: 하인 세션 스폰 실패 - {str(e)}]"

def invoke_agent_pass(agent: Dict[str, Any], topic: str, context: str, pass_name: str, use_ai: bool) -> Dict[str, Any]:
    agent_id = agent['id']
    label = agent['label']
    
    # 에이전트의 이전 기억(상태) 로드
    agent_state = load_agent_state(agent_id)
    past_memory = agent_state.get('memory', '이전 기억이 없습니다. 처음으로 발언합니다.')
    
    # Pass별 프롬프트 구성
    if pass_name == "Initial":
        prompt = get_role_prompt(agent_id, topic) + f"\n\n[당신의 지난 기억(Memory)]\n{past_memory}"
    elif pass_name == "Critique":
        prompt = f"당신은 {label}입니다. 다음 동료들의 의견을 비판적으로 검토하고 허점을 지적하세요.\n{context}\n\n[당신의 지난 기억(Memory)]\n{past_memory}"
    else: # Final
        prompt = f"당신은 {label}입니다. 받은 비판들을 수렴하여 최종 수정안과 결론(Approve/Conditional/Hold)을 내리세요.\n{context}\n\n[당신의 지난 기억(Memory)]\n{past_memory}"

    if use_ai:
        # 하인 세션을 호출하여 실제 LLM 답변을 받아옴
        servant_response = delegate_to_servant(label, prompt)
        
        # 하인 세션의 답변을 파싱하여 opinion과 recommendation 추출 (간이 파싱)
        opinion = f"[{agent_id.upper()}/{pass_name}] (하인 보고) {servant_response}"
        
        # 간단한 키워드 매칭으로 판결 추출
        upper_resp = servant_response.upper()
        if "APPROVE" in upper_resp: recommendation = "Approve"
        elif "HOLD" in upper_resp: recommendation = "Hold"
        else: recommendation = "Conditional"
    else:
        time.sleep(0.1)
        opinion = f"[{agent_id.upper()}/{pass_name}] (Stub: 이전 기억 유지 중) {agent['role']} 처리 중."
        recommendation = "Approve"

    # 발언을 마친 후 현재 의견을 기억(상태)으로 저장하여 다음번 소집 때 참고
    agent_state['memory'] = opinion
    save_agent_state(agent_id, agent_state)

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
