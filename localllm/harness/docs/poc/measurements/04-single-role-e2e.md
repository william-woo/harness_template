# PoC 측정 04 — 단일역할 E2E (변환된 .opencode/agent/ + 로컬 14B)

- **측정일**: 2026-06-08
- **환경**: OpenCode 1.16.2 + Ollama 0.30.5 (172.16.10.217, RTX 4500) / qwen2.5:14b-instruct-q8_0
- **전제**: F015 세션 2 변환기로 `.claude/agents/*.md` → `.opencode/agent/*.md` 생성 완료
- **목표**: 변환된 에이전트로 단일역할(developer) 코딩 작업이 로컬 14B 에서 end-to-end 동작하는가

## 측정 항목 + 결과

| # | 측정 | 결과 | 판정 |
|---|---|---|---|
| 1 | 변환된 8 agent `opencode agent list` 인식 | architect/designer/developer/gatekeeper/planner/qa/researcher/reviewer 전부 인식 | ✅ PASS |
| 2 | `mode: subagent` 직접 호출 (`opencode run --agent developer`) | "not a primary agent → Falling back to default agent" | ❌ 직접 진입 불가 |
| 3 | `mode: all` 직접 호출 | 헤더 `> developer` — fallback 없이 developer agent 로 실행 | ✅ PASS |
| 4 | developer agent 단일파일 코딩 (add.js) | JSDoc + `console.assert(add(2,3)===5)` 생성, `node` 실행 assert 통과 | ✅ PASS |
| 5 | developer agent 단일파일 코딩 (sub.js) | JSDoc + `console.assert(sub(5,2)===3)` 생성, `node` 실행 assert 통과 | ✅ PASS |
| 6 | 상대경로 준수 (`src/*.js`) | 절대경로 임의 생성 없이 상대경로로 파일 생성 | ✅ PASS |

## 핵심 발견 — mode 보정 (subagent → all)

**가장 값진 발견**: ADR-009 세션 2 변환기는 7/8 에이전트를 `mode: subagent` 로 변환했으나,
OpenCode 에서 **subagent 는 `opencode run --agent <name>` 직접 진입점이 될 수 없다**
("not a primary agent → fallback"). 이는 d-2 의 **주 사용 사례인 단일역할 직접 호출을 막는다**.

→ 변환기를 **`mode: all`** 로 보정 (opencode.py `_format_opencode_agent`).
`mode: all` 은 primary(직접 진입) + subagent(task spawn) **겸용 상위집합**이므로:
- 단일역할 직접 호출 (`opencode run --agent developer "..."`) ✅ — 14B 주 사용 사례
- orchestrate 의 task 도구 spawn ✅ — 멀티 에이전트 흐름도 그대로 유지

재현:

```
# subagent → 막힘
$ opencode run --agent developer ...
! agent "developer" is a subagent, not a primary agent. Falling back to default agent

# all → 직접 동작
$ opencode run --agent developer ...
> developer · qwen2.5:14b-instruct-q8_0
← Write src/sub.js  →  Wrote file successfully.
```

## 부수 발견

- **14B 도구호출 변동성**: sub.js 1차 시도에서 도구 호출 없이 대화형 응답으로 종료(파일 미생성).
  "반드시 파일을 생성하라" 명시 후 정상 동작. → 단일역할도 **명령형·구체 지시**가 14B 신뢰도를 높인다.
- **Write 도구 런타임 존재**: 변환기는 write→edit 융합을 적용하나, OpenCode 런타임 로그는
  `Write src/add.js` 를 표시 — write 도구가 런타임엔 존재. edit 융합은 **보수적이지만 무해**
  (permission deny-list 에 write 부재 = 허용, 파일 생성 정상). 융합 유지 (측정 02 edit PASS 근거).

## 잠정 결론

**단일역할(developer) 코딩은 변환된 `.opencode/agent/` + 로컬 14B 로 end-to-end 동작한다** —
파일 생성·JSDoc·동작하는 테스트까지. 단, 에이전트가 직접 진입점이 되려면 **`mode: all`** 이어야 한다
(측정 04 보정 적용 완료). 멀티스텝 오케스트레이션(G4/G5)은 측정 03b 대로 여전히 14B 한계 — 32B+ 권장.

→ d-2 단일역할 작업(developer/reviewer/qa)은 **지금 로컬 14B 로 사용 가능**. (docs/poc/MODEL-GRADES.md)
