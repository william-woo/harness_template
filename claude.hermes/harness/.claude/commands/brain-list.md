# /project:brain-list — 등록된 프로젝트 목록

`~/.harness/brain.db` 의 projects 테이블에 등록된 모든 프로젝트 표시.

## 사용

```
/project:brain-list
```

## 실행

```bash
python3 .claude/bin/brain.py list
```

## 출력 예시

```
🧠 BRAIN PROJECTS (3)
═══════════════════════════════════════

• harness_update_agent
    path:   /home/obigo/project/oss/harness_update_agent
    remote: git@github.com:william-woo/harness_update_agent.git
    first:  2026-04-25T01:50:00
    last:   2026-04-25T09:15:00

• web-frontend
    path:   /home/obigo/project/web-frontend
    remote: git@github.com:obigo-team/web-frontend.git
    first:  2026-04-20T10:00:00
    last:   2026-04-24T18:30:00

• payment-service
    path:   (디렉토리가 이동됨 — sync 시 자동 갱신)
    remote: git@github.com:obigo-team/payment-service.git
    first:  2026-04-15T14:00:00
    last:   2026-04-20T11:00:00
```

## 컬럼 설명

- **path**: 마지막 sync 시점의 절대 경로 (이동되면 다음 sync 시 갱신)
- **remote**: git remote origin URL (없으면 표시 안 됨)
- **first**: 처음 등록 시각
- **last**: 마지막 sync 시각 — 활동 빈도 추측 가능

## 활용

- 어떤 프로젝트들이 brain 에 등록되어 있는지 일별로 확인
- `/project:brain-search --project <slug>` 의 slug 후보 확인
- 마지막 sync 가 오래된 프로젝트는 stale 가능성 → 다시 sync 권장
