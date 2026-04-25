# /project:handoff — 세션 인계

작업 세션을 마무리하고 다음 에이전트/세션에 깔끔하게 인계한다.

## 실행 순서

```bash
# 1. 코드 상태 확인
npm test              # 테스트 모두 통과 확인
npm run lint          # 린트 오류 없음 확인
git status            # 커밋되지 않은 변경사항 확인

# 2. 모든 변경사항 커밋 (미완성이면 wip 커밋)
git add -A
git commit -m "wip(FXXX): [현재까지 작업 내용]"
# 또는 완료 시:
# git commit -m "feat(FXXX): [구현 내용]"

# 3. feature_list.json의 status 업데이트
# 상황에 따라 적절한 status로 변경:
# "in-progress" → 구현 중
# "review"      → 구현 완료, Reviewer 대기
# "qa"          → 리뷰 통과, QA 대기
# "done"        → QA 통과 (passes: true와 동시에)

# 4. claude-progress.txt 업데이트 (아래 형식 사용)
```

## claude-progress.txt 업데이트 형식

```
============================================================
[YYYY-MM-DD HH:MM] [에이전트명]: [작업 요약]
============================================================
작업한 Feature: [FXXX]
작업 내용:
  - [구체적으로 한 일 1]
  - [구체적으로 한 일 2]

현재 상태: [in-progress | review | qa | done]
feature status: [변경 전] → [변경 후]

파일 변경:
  - 추가: [파일 목록]
  - 수정: [파일 목록]

다음 세션 할 일:
  - [ ] [구체적인 다음 작업]

주의사항:
  - [알아야 할 중요 정보나 함정]
============================================================
```

## 인계 조건

| 상황 | feature status | 다음 에이전트 |
|---|---|---|
| 구현 완료, 테스트 통과 | `review` | Reviewer 에이전트 |
| 리뷰 APPROVED | `qa` | QA 에이전트 |
| QA PASS | `done` + passes:true | Planner (다음 기능) |
| 설계 필요 | `in-progress` | Architect 에이전트 |
| 리뷰 NEEDS REVISION | `in-progress` | Developer 에이전트 |

## 리뷰 반복 에스컬레이션 규칙

같은 Feature에서 NEEDS REVISION이 **3회 이상** 반복되면:
- `claude-progress.txt`에 `ESCALATION` 태그 기록
- Planner + Architect 에이전트를 호출하여 설계 재검토
- Feature를 더 작은 단위로 분해할지 검토

## 체크리스트

- [ ] 모든 변경사항 커밋됨
- [ ] 테스트 실패 없음
- [ ] feature_list.json status 업데이트 완료
- [ ] claude-progress.txt 업데이트 완료
- [ ] 다음 작업 명확히 기술됨
