---
name: planning
description: |
  프로젝트 기획 및 feature_list.json 관리 스킬. Planner 에이전트가 사용한다.
  요구사항을 검증 가능한 기능 목록으로 변환하는 방법을 안내한다.
---

# Planning Skill

## 요구사항 → 기능 분해 방법

### 1. 사용자 스토리 작성

```
[역할]로서, 나는 [행동]을 원한다. 왜냐하면 [목적] 때문이다.
```

예시:
- ❌ "로그인 기능 구현" (모호)
- ✅ "일반 사용자로서, 이메일과 비밀번호로 로그인하고 싶다. 왜냐하면 내 계정에 접근해야 하기 때문이다."

### 2. 기능 분해 기준

**하나의 Feature = 하나의 검증 가능한 결과물**

분해가 필요한 신호:
- "그리고" 접속사가 포함됨 → 2개로 분리
- 구현에 3 세션 이상 예상 → 더 작게 분리
- 검증 기준이 5개 초과 → 더 작게 분리

### 3. 우선순위 결정 기준

| Priority | 기준 |
|---|---|
| Critical | 이게 없으면 앱이 작동 안 함 |
| High | 핵심 비즈니스 가치 제공 |
| Medium | 사용성 향상, 있으면 좋음 |
| Low | 나중에 해도 됨, 선택 사항 |

### 4. 의존성 관리

```
F001 (환경 설정)
  └── F002 (회원가입)
        └── F003 (로그인)
              └── F004 (프로필 조회)
              └── F005 (대시보드)
```

의존성이 없는 것부터 시작.
병렬 가능한 Feature는 dependencies를 같은 레벨로 설정.

## feature_list.json 관리 규칙

```json
// ✅ QA 에이전트만 변경 가능
{ "passes": false }  →  { "passes": true }

// ✅ 각 에이전트가 작업 흐름에 따라 변경
{ "status": "todo" }
  → "in-progress"  (Developer/Architect 시작 시)
  → "review"       (Developer 구현 완료 시)
  → "qa"           (Reviewer APPROVED 시)
  → "done"         (QA PASS 시, passes: true와 동시에)

// ❌ 절대 금지
- 기존 항목 삭제
- id 변경
- acceptance_criteria 약화
- passes: true 직접 설정 (QA 에이전트 전용)
```
