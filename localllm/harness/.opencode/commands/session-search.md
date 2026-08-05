---
description: "FTS5 세션 검색 (claude.hermes 전용)"
---

# /session-search — FTS5 세션 검색 (claude.hermes 전용)

과거 세션 로그(claude-progress.txt)와 체크포인트를 SQLite FTS5 로 전문 검색한다.
Hermes Agent 의 "cross-session recall" 패턴 (ADR-010).

## 사용법

```bash
python3 .claude/bin/session_search.py index               # 색인 (재구축)
python3 .claude/bin/session_search.py search "<질의>"      # FTS5 검색
python3 .claude/bin/session_search.py search "a OR b" --limit 5
python3 .claude/bin/session_search.py self                 # FTS5 지원·색인 점검
```

## 호출 기준

다음 중 하나면 `session-search` 권장:

- "예전에 이거 어떻게 처리했더라" — 과거 세션의 결정·함정 회상
- 세션 시작 시(`/start-session`) 관련 키워드로 직전 맥락 복원
- 같은 버그/패턴이 재발한 것 같을 때 과거 기록 대조

## 동작

- 색인 대상: `claude-progress.txt` 세션 블록(신규 `## [..]` + 레거시 `====` 형식 모두) +
  `.claude/state/checkpoints/*.md`
- 엔진: SQLite FTS5 (stdlib). 미지원 빌드면 `grep` 대체 안내 (graceful degrade).
- DB: `.claude/state/sessions.db` (gitignore — 로컬 캐시, 언제든 재색인 가능)

> **claude.hermes 계보 전용** (hermes/productmgr/productnw/loope/localllm) — 그 외 변형엔 session_search.py 가 없다 (LINT-MR-10 격리).
> wiki 의 `/wiki query`(지식 노드 검색)와 책임 분리: session-search 는 **세션 이력** 검색.

---

사용자 인자 (없으면 무시): $ARGUMENTS

---

> **로컬 LLM 실행 힌트**: 이 커맨드의 동작은 위 문서의 bash 명령을 **그대로 실행**하는 것이다. 문서에 `python3 .claude/bin/...` 또는 bash 블록이 있으면 추측·재해석하지 말고 그 명령을 bash 도구로 즉시 실행하고, 그 출력을 요약해 보고하라. bash 도구 호출 시 `command` 와 `description` **두 인자를 모두** 채워라 (description 누락 = 스키마 에러). 파일이 없거나 실패하면 문서의 안내 문구를 따르고 사용자에게 질문하지 마라.
