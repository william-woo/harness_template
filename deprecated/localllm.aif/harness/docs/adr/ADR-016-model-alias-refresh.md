# ADR-016: 모델 별칭 정책 + 신세대(Claude 5) 정합 리프레시

> Feature: F022 — 모델 별칭·구세대 잔재·프롬프트 관행 리프레시
> 상태: `Accepted` (구현 — main + 10 변형 일괄 적용, baseline/openai 동결 유지)
> 관련: ADR-015(main≡loope SSOT), ADR-009(opencode 어댑터), coding-standards.md 프롬프트 규율

## 맥락

deep review(2026-07-31)에서 harness_template 전체가 최신 모델(Opus 5 / Fable 5)에서
동작은 하지만 세 가지 부채가 확인됐다:

1. **모델 고정 핀 81곳** — `.claude/agents/*.md` frontmatter 가 `model: claude-*-4-*` 류
   구세대 전체 ID 로 고정되어, 호스트가 5세대여도 sub-agent 는 4.x 로 실행됐다.
2. **구세대 도구 잔재** — 현행 Claude Code 에서 제거된 `MultiEdit` 가 agents tools 목록·
   settings.json 권한·CLAUDE.md 산문에 잔존. sub-agent spawn 도구의 신명칭 `Agent`(구 `Task`)
   미반영. opencode 어댑터 도구 매핑에 `agent` 토큰 부재.
3. **관행 어긋남** — 신세대 모델은 지시를 문자 그대로 따르므로, reviewer 의 보수적 필터
   지시가 재현율을 떨어뜨리고, 강지시어("CRITICAL/반드시")·self-check 중복 지시가
   과잉 트리거·과잉 검증을 유발한다.

## 결정

### 결정 1 — 모델은 별칭(alias)으로 지정: 판정·디자인 = `fable`, 그 외 = `opus`
`.claude/agents/*.md` frontmatter 의 `model:` 을 전체 ID 대신 **별칭**으로 지정한다:

| 에이전트 | 별칭 | 근거 |
|---|---|---|
| **reviewer / qa / designer** | `fable` | 판정(judge) 품질과 디자인 감식안이 결과 게이트를 좌우 — 최상위 모델 |
| planner / architect / developer / researcher / product-manager / gatekeeper | `opus` | 실행·설계 역할 — Opus 등급으로 충분, 비용·지연 균형 |

별칭은 Claude Code 가 **세대 자동 추종**하므로 (예: `opus` → 현행 Opus 최신), 모델 세대가
바뀔 때마다 81곳을 재핀하는 유지보수를 제거한다. 전체 ID 고정은 재현성이 필요한
실험(localllm 측정 등)에만 예외적으로 사용한다.

### 결정 2 — 구세대 도구 잔재 제거 + 신명칭 반영
- `MultiEdit` 를 agents `tools:` 목록·settings.json 권한 패턴·CLAUDE.md 산문에서 제거
  (현행 Claude Code 에서 Edit 로 통합·제거됨. 잔존 시 무해하지만 오해 유발).
- sub-agent spawn 문서 표기를 `Agent 도구(구 Task)` 로 갱신 — 구명칭 병기로 하위 호환 유지.
- opencode 어댑터 `_CC_NORMALIZE` 에 `"agent": "task"` 매핑 추가 (OpenCode 측 토큰명은 task 유지).

### 결정 3 — 신세대 프롬프트 규율 성문화 (coding-standards.md)
"프롬프트 규율 (Claude 4.6+/5 세대)" 섹션 신설: ① 강지시어 절제(프로세스 규칙은 예외)
② self-check 중복 지시 금지 — 단 **프로세스 게이트(Reviewer→QA, verify-loop)는 프롬프트가
아니라 파이프라인이므로 유지** ③ De-prescribe(목표·제약 중심 서술).

### 결정 4 — reviewer 에 "커버리지 우선" 원칙 추가
발견 단계에서 확신도·심각도 낮은 항목을 걸러 침묵 탈락시키지 않고 **모두 보고 + 등급 표기**.
중요도 필터링은 다운스트림(judge/사용자) 몫. 신세대 모델이 보수적 필터 지시를 문자 그대로
따라 측정 재현율이 떨어지는 문제의 대응.

### 결정 5 — 적용 범위: main + 10 변형, baseline/openai 는 동결 유지
Karpathy 예외에 해당하지 않으므로 baseline(`claude/`)·`openai/.codex/` 는 손대지 않는다.
localllm 의 `.opencode/agent/*.md` 는 render-agents 로 재생성 (수동 편집 금지 — ADR-009).

## 대안 검토

- **전체 ID 재핀 (claude-opus-5 등)**: 다음 세대에서 같은 부채 재발 — 기각.
- **model: 필드 삭제 (호스트 상속)**: 역할별 모델 차등(판정=fable)이 불가능 — 기각.
- **전 에이전트 fable**: 판정·디자인 외 역할에는 비용·지연 대비 이득이 불명확 — 기각.

## 결과

- 모델 별칭화 85곳 (main+10 변형 × 최대 9 에이전트), MultiEdit 제거 (agents 11 파일 + settings 11 + CLAUDE.md), Task→Agent 표기 21곳, reviewer 원칙 11, 프롬프트 규율 섹션 11, opencode 매핑 11.
- 위생: 변형 측 `settings.local.json` ×10 + `state/lint-last.json` ×4 + `__pycache__` ×6 삭제
  (템플릿에 로컬/런타임 파일이 실리지 않도록 — ADR-015 결정 2 의 연장).
- 검증: 12 settings.json JSON 파스 통과, opencode.py 11 사본 py_compile 통과,
  localllm render-agents 8 파일 재생성 성공.
