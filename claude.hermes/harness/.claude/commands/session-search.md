# /project:session-search — FTS5 세션 검색 (claude.hermes 전용)

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
- 세션 시작 시(`/project:start-session`) 관련 키워드로 직전 맥락 복원
- 같은 버그/패턴이 재발한 것 같을 때 과거 기록 대조

## 동작

- 색인 대상: `claude-progress.txt` 세션 블록(신규 `## [..]` + 레거시 `====` 형식 모두) +
  `.claude/state/checkpoints/*.md`
- 엔진: SQLite FTS5 (stdlib). 미지원 빌드면 `grep` 대체 안내 (graceful degrade).
- DB: `.claude/state/sessions.db` (gitignore — 로컬 캐시, 언제든 재색인 가능)

> **claude.hermes 변형 전용** — 다른 변형엔 session_search.py 가 없다 (LINT-MR-10 격리).
> wiki 의 `/project:wiki query`(지식 노드 검색)와 책임 분리: session-search 는 **세션 이력** 검색.
