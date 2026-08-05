---
description: "등록된 프로젝트 목록"
---

# /brain-list — 등록된 프로젝트 목록

`~/.harness/brain.db` 의 projects 테이블에 등록된 모든 프로젝트 표시.

## 사용

```
/brain-list
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
- `/brain-search --project <slug>` 의 slug 후보 확인
- 마지막 sync 가 오래된 프로젝트는 stale 가능성 → 다시 sync 권장

---

사용자 인자 (없으면 무시): $ARGUMENTS

---

> **로컬 LLM 실행 힌트**: 이 커맨드의 동작은 위 문서의 bash 명령을 **그대로 실행**하는 것이다. 문서에 `python3 .claude/bin/...` 또는 bash 블록이 있으면 추측·재해석하지 말고 그 명령을 bash 도구로 즉시 실행하고, 그 출력을 요약해 보고하라. bash 도구 호출 시 `command` 와 `description` **두 인자를 모두** 채워라 (description 누락 = 스키마 에러). 파일이 없거나 실패하면 문서의 안내 문구를 따르고 사용자에게 질문하지 마라.
