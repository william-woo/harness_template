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
→ **단, 아래 후속 데모로 보정됨**: "생성형"은 14B OK, "검증형(reviewer/qa)"은 멀티스텝이라 14B 불안정.

---

## 후속 데모 (2026-06-10) — reviewer 검증형 역할은 14B 불안정 (생성형 ≠ 검증형)

측정 04 직후, 같은 buggy 산출물(developer 가 만든 `slugify.js` — 정규식 `[\\^\w-]` 오타로
부정 클래스가 풀려 `slugify('Hello World!') → "!"`, assert 2개 모두 실패)을
**reviewer 에이전트(로컬 14B)** 에게 리뷰시켜 "검증형 단일역할"을 측정.

| 시도 | 시간 | 결과 |
|---|---|---|
| 1 | 34s | `src/slugify.js` read + `node` 실행 → **"Assertion failed" ×2 직접 목격** (증거 수집 ✅) / 판정 미합성 |
| 2 | 6.8s | `/src/slugify.js` **절대경로** 시도 → external_directory 가드 auto-reject → 무산 |
| 3 | 4.2s | 상대경로 read OK / `node` bash 가 headless 권한 auto-reject → 무산 |
| 4 | **5min 타임아웃** | 출력 0바이트 — 완전 hang (exit 124) |

→ **4회 중 깔끔한 APPROVED/NEEDS REVISION 판정 0회.** developer(생성형)는 23초에 파일을 만든 반면,
reviewer 는 한 번도 판정을 못 냄.

### 핵심 발견 — "단일역할"에도 난이도 그라데이션이 있다

| 구분 | 작업 성격 | 홉 수 | 14B |
|---|---|---|---|
| **생성형** (developer/architect/designer) | 프롬프트 → 산출 | 1홉 | ✅ (산출물은 "초안", 버그 가능) |
| **검증형** (reviewer/qa) | read → 실행 → 해석 → 추론 → 판정 | 다홉 | ❌ 측정 03b 의 멀티스텝 한계에 근접 |

검증형은 본질적으로 멀티스텝이라, 단일 에이전트 호출이어도 G4(멀티스텝 값 전달) 성격을 띤다.

### 부수 재현
- **절대경로 습관(시도 2)**: `/src/...` 로 읽으려다 안전가드 차단 — "상대경로 우선" 스킬 보강이 겨냥한
  바로 그 문제. AGENTS.md 안내가 있어도 14B 가 지키지 못함.
- **headless 권한 마찰(시도 3)**: `opencode run`(비대화) 에서 bash(node) 실행이 실행마다 들쭉날쭉
  auto-reject. 안정 사용엔 OpenCode permission 설정/플러그인 보강 필요 (F017 인접 영역).

### 함의
로컬 14B 로 "developer 가 짜고 reviewer 가 검증"하는 자가 루프를 돌리려는 그림은 **reviewer 가 약한 고리**.
→ **하이브리드 권장**: 생성(developer)은 로컬 14B, **검증(reviewer/qa)은 32B+ 또는 Claude Code(메인 하네스)/사람**.
이는 메인 하네스가 QA passes 게이트를 자동 수치가 아닌 별도 검증으로 둔 설계의 정당성과 일치
(autoresearch 의 "결과는 shipped improvement 가 아니라 starting hypothesis" 와 같은 정신).
