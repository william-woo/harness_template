# /project:plan-full — 자동 기획 파이프라인 (Autoplan)

Planner → Architect(조건부) → Reviewer(설계 감사)를 자동으로 체이닝해서,
**Developer가 구현을 시작하기 전에** 계획과 설계를 검증한다.

gstack의 `/autoplan` (CEO → design → engineering 리뷰 파이프라인)에서 아이디어를
가져왔되, 우리 하네스의 feature-centric 모델에 맞춰 재설계한 버전.

## 사용

```
/project:plan-full <요구사항 또는 기능 설명>
```

예:
```
/project:plan-full 팀 할일 관리 앱 - 회원가입/로그인, 태스크 CRUD, 공유 기능
/project:plan-full F002 Autoplan 커맨드를 구현하고 싶다
/project:plan-full 결제 시스템을 추가하고 싶다 (토스페이먼츠 연동)
```

## 파이프라인 단계

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  사용자     │ ──▶│  Planner     │ ──▶│  Architect   │ ──▶│ Reviewer │
│  요구사항   │     │  분해        │     │  (조건부)    │     │ (설계)   │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────┘
                    feature_list.json    docs/adr/ADR-*.md    리뷰 결과
```

### Step 0: 사전 조회 (learn + context-restore)

구현 시작 전 누적 지식 활용:

```bash
# 관련 학습 검색
/project:learn search <요구사항에서 추출한 키워드>

# 최근 체크포인트가 있으면 이어받기
/project:context-restore
```

관련 pitfall·architecture가 있으면 Step 1 Planner에 전달한다.

### Step 1: Planner 에이전트 실행

```
Use the planner agent to break down: <요구사항>
```

Planner는 다음을 수행:
1. 요구사항 구체화 (모호한 부분은 AskUserQuestion)
2. Feature 분해 — 각 Feature ID/카테고리/우선순위/인수기준/의존성
3. `feature_list.json` 업데이트 (append, 삭제·변경 금지)
4. `claude-progress.txt`에 기획 요약 기록

**출력**: Feature 목록 (신규 ID + title + priority + 설계 필요 여부)

### Step 2: "설계 필요" 판별

Planner 출력을 받아, 각 Feature에 대해 **설계 필요 여부** 자동 판정:

| 조건 | 설계 필요 |
|---|---|
| 새로운 DB 테이블/스키마 | ✅ |
| 새로운 외부 API/서비스 연동 | ✅ |
| 인증/권한/결제 등 보안 관련 | ✅ |
| 3개 이상 파일 걸쳐 구조 변경 | ✅ |
| 모듈 간 의존성 방향 변경 | ✅ |
| 기존 패턴 복제 + 작은 추가 | ❌ |
| 순수 UI/스타일 변경 | ❌ |
| 단순 버그 수정 | ❌ |

판정은 Feature의 `description` + `category` + `acceptance_criteria` 키워드로.
**의심스러우면 설계 필요로 판정** (실수 비용이 더 크다).

### Step 3: Architect 에이전트 실행 (조건부)

Step 2에서 설계 필요로 판정된 각 Feature에 대해 순차 실행:

```
Use the architect agent to design the F00X <title>
```

Architect는:
1. 관련 learnings 조회 (`/project:learn search <feature 키워드>`)
2. `docs/adr/ADR-XXX-<slug>.md` 작성 — 배경, 결정, 대안, 영향
3. Feature의 `status`는 변경하지 않음 (여전히 `todo`)
4. Developer 구현 가이드를 ADR 하단에 포함

**복수 Feature일 때**: ADR 번호는 연속 할당, 공통 의존성이 있으면 `related_adrs`로 링크.

### Step 4: Reviewer 에이전트 (설계 감사 모드)

Step 3에서 생성된 모든 ADR에 대해 **설계 단계** 리뷰:

```
Use the reviewer agent to audit the design of F00X (ADR-XXX)
```

읽기 전용 설계 리뷰 체크리스트:
- 아키텍처 결정이 `acceptance_criteria`를 달성 가능한가?
- 고려하지 않은 엣지 케이스·실패 모드는?
- 기존 모듈과 의존성 방향이 합리적인가?
- 보안·성능·관찰가능성 관점에서 결정 근거가 명확한가?
- **gstack `slop-scan` 아이디어**: 불필요한 추상화·YAGNI 요소는 없는가?

출력: APPROVED / NEEDS REVISION + 구체적 수정 제안.

**NEEDS REVISION**: Architect 재호출 (최대 2회), 여전히 실패하면 `[ESCALATION]`
태그 달고 Planner에 Feature 재분해 요청.

### Step 5: 파이프라인 결과 요약

완료 시 다음 출력:

```
📋 AUTOPLAN 완료
════════════════════════════════════════
신규 Feature: 3
  ✓ F002 Autoplan (설계 불필요)
  ✓ F003 Review Readiness → ADR-002 APPROVED
  ⚠ F004 Retro+Analytics → ADR-003 NEEDS REVISION (재작업 필요)

기존 Feature 영향: 없음

다음 단계 추천:
  1. F002 Developer 에이전트로 즉시 구현 시작 가능
  2. F003 Developer 에이전트로 구현 시작 (ADR-002 참조)
  3. F004 ADR-003 재작업 먼저 (Architect 재호출)
════════════════════════════════════════
```

### Step 6: 학습 기록 (자동)

파이프라인에서 발견한 의사결정은 자동 학습 기록:

```bash
# Architect가 핵심 ADR 결정 내린 경우
/project:learn add
# type: architecture, source: architect, feature_id: F00X
# insight: ADR-XXX 결정의 1문장 요약
```

## 충돌·오류 대응

### Planner가 Feature 분해 못 할 때
요구사항이 너무 모호 → Planner가 AskUserQuestion 으로 명확화 요청.
사용자 응답 대기 → 응답 받으면 이어서 진행.

### Architect가 설계 못 할 때
3회 이상 반복 시도 실패 → Feature 재분해 요청 (Planner에 에스컬레이션).
`claude-progress.txt`에 `[ESCALATION] F00X 설계 실패` 태그.

### Reviewer NEEDS REVISION 2회 반복
ADR 재설계해도 통과 못 함 → Planner에 Feature 재분해 요청.

## 사용하지 말아야 하는 경우

- **단순 버그 수정**: Planner 개입 오버헤드. 직접 Developer 호출.
- **1줄 문구 변경·typo**: 불필요.
- **긴급 hotfix**: 지연 비용이 파이프라인 이득보다 큼.

이런 경우는 기존 `/project:start-session` → Developer 경로를 유지.

## 체크리스트

- [ ] 관련 learnings 조회 완료
- [ ] feature_list.json 업데이트 완료 (append only)
- [ ] 설계 필요 판정 완료
- [ ] 필요한 ADR 모두 작성 + Reviewer 통과
- [ ] claude-progress.txt에 파이프라인 요약 기록
- [ ] 핵심 결정 learnings.jsonl에 append
