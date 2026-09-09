# 하네스 도구 인벤토리

> 이 하네스가 **정의하는 도구**와 **의존하는 외부 도구**의 전체 목록.
> 실제 파일에서 뽑은 것이며, 마지막 갱신: 2026-08-11 (F029 시점, 14 변형).
> 재생성 명령은 문서 끝 [재생성](#재생성) 참조 — 인벤토리는 쉽게 낡으므로 수치는 다시 뽑아 확인한다.

## 설계 원칙 두 가지

1. **자체 도구는 Python 표준 라이브러리만 쓴다.** `pip install` 이 필요한 패키지가 하나도 없다.
   `requirements.txt` 도 없다. 다운스트림이 어떤 환경에서 클론해도 `python3` 만 있으면 동작한다.
2. **외부 도구는 향상재일 뿐이다.** 없으면 `shutil.which()` / `command -v` 로 감지해 안내 후
   정상 종료한다 (graceful degrade). 외부 도구 부재가 하네스를 막지 않는다.

LINT-MR-7 이 변형별 외부 의존성 계약을 강제한다 — `claude`~`design` 4 변형은 외부 의존성 0,
`wiki` 이상은 허용 카탈로그(Obsidian/qmd/Marp)만.

---

## 계층 1 — 자체 CLI 도구 (`.claude/bin/`)

메인(= `claude.loope`)에 12개, 변형 전용 4개가 더 있다.

| 도구 | 줄수 | 역할 | 최소 변형 |
|---|--:|---|---|
| `lint.py` | 2465 | 거버넌스 정합성 검사 (LINT-MR-1~14 변형 격리 포함) | gstack |
| `wiki.py` | 2065 | wikilink 지식 그래프 — ingest/query/lint/graph | wiki |
| `backup.py` | 1437 | 다운스트림 백업 동기화 (공유 리포 + 프로젝트별 브랜치) | gstack |
| `design_pick.py` | 1078 | 4 브랜드 디자인 토큰 선택 → `tokens.json` | design |
| `qa_browser.py` | 816 | acceptance_criteria → Playwright 변환·실행 | gstack |
| `host.py` | 687 | 멀티 호스트 관리 + render-agents / render-commands | gstack |
| `brain.py` | 568 | cross-project 지식베이스 (`~/.harness/brain.db`) | gstack |
| `skill_forge.py` | 495 | 스킬 자동생성·self-improve (draft→approve 게이트) | hermes |
| `verify_loop.py` | 282 | Loop 2 검증 루프 — rubric·재시도·에스컬레이션 | loope |
| `session_search.py` | 280 | FTS5 세션 전문 검색 | hermes |
| `hill_climb.py` | 216 | Loop 4 신호 집계 (auto-apply 금지) | loope |
| `wiki-setup.sh` | 101 | wiki 외부 도구 설치 스크립트 | wiki |

### 변형 전용 도구

| 도구 | 역할 | 보유 변형 | 근거 |
|---|---|---|---|
| `cycle_driver.py` | 결정론 supervisor — SDLC 무인 드라이버 | localllm 계열 | ADR-018 |
| `autoresearch.py` | 자가 실험 루프 — 스위트를 적합도 함수로 | localllm 계열 | ADR-019 |
| `aif_judge.py` | 항목형 rubric 판정 — 증거·앙상블·UNCERTAIN | aif 계열 | ADR-020 |
| `consortium.py` | 팀 간 메시지 계약·로스터·로컬 큐 | productnw | ADR-012 |
| `opencode-setup.sh` | OpenCode + Ollama 환경 설정 | localllm 계열 | ADR-009 |

---

## 계층 2 — 에이전트 9종 (`.claude/agents/`)

| 에이전트 | 책임 | 최소 변형 |
|---|---|---|
| `planner` | 요구 분석, feature_list 관리, 우선순위 | gstack |
| `architect` | 시스템 설계, 기술 선택, ADR 작성 | gstack |
| `developer` | 구현, 단위 테스트, 버그 수정 | gstack |
| `reviewer` | 코드 품질·보안·성능 리뷰 | gstack |
| `qa` | E2E 검증, 인수 판정 (`passes` 권한 단독) | gstack |
| `gatekeeper` | 자율 모드 경계 판정 (PROCEED/CONSULT/ESCALATE) | auto |
| `designer` | 디자인 토큰 비교·추천 | design |
| `researcher` | 내부·외부 리서치 종합 | orch |
| `product-manager` | 제품 발견·성공지표 + 라이프사이클 supervisor | productmgr |

---

## 계층 3 — 슬래시 커맨드 30개 (`.claude/commands/`)

| 묶음 | 커맨드 |
|---|---|
| 세션 관리 | `init-project` `start-session` `handoff` `status` `context-save` `context-restore` |
| 자동화 체인 | `plan-full` `ship` `retro` `orchestrate` `product-cycle` |
| 안전 | `freeze` `unfreeze` `guard` |
| 지식 | `learn` `brain-sync` `brain-search` `brain-stats` `brain-list` `wiki` `session-search` |
| 검증 | `lint` `design-review` `qa-browser` `verify-loop` `hill-climb` |
| 기타 | `host` `design-pick` `backup-sync` `skill-forge` |

변형 전용 커맨드는 위 목록 밖에 있다 — `aif-judge`(aif) · `consortium`(productnw) ·
`autoresearch`(localllm).

---

## 계층 4 — 훅 6개 + 스킬 5개

**훅** (`.claude/hooks/`) — `pre-bash-check` · `pre-bash-auto-boundary-check`(자율 경계 차단) ·
`pre-write-check` · `pre-edit-freeze-check` · `post-write-check` · `session-end`

> 훅은 **hook-failure-tolerance** 정책을 따른다 — 훅 자체 오류가 작업을 막지 않는다.

**스킬** (`.claude/skills/`) — `planning` · `coding` · `testing` · `design-review` · `qa-browser`

---

## 계층 5 — 호스트 어댑터 (`.claude/bin/host_adapters/`)

| 어댑터 | 상태 | 비고 |
|---|---|---|
| `claude_code` | 실동작 | 기본값 |
| `opencode` | 실동작 | localllm 계열 — render-agents/commands 지원 |
| `codex` | stub | 안내만 출력, 차단하지 않음 |
| `openclaw` | stub | 좌동 |

`base.py` 가 추상 베이스 + 토큰 카탈로그를 제공한다.
감지 우선순위: `HARNESS_AGENT_TYPE` > `.claude/host.json` > 기본값 `claude-code`.

---

## 외부 도구

코드가 의존하는 외부 실행 파일은 7개다. 괄호는 **문자열 등장 수**(실행·감지·안내 메시지 포함)이며
호출 지점 수가 아니다 — 대부분 `cmd` 변수를 조립해 실행하므로 등장 수로만 셀 수 있다.

| 외부 도구 | 쓰는 곳 | 필수성 | 미설치 시 |
|---|---|---|---|
| `git` (14) | backup · lint · cycle_driver | **사실상 필수** | 커밋·백업 불가 |
| `qmd` (6) | wiki 검색 (BM25) | 선택 | grep 폴백 |
| `opencode` (5) | localllm 구동 | **localllm 필수** | 사이클 불가 |
| `marp` (4) | wiki 슬라이드 | 선택 | 기능 스킵 |
| `playwright` / `npx` / `node` (2/2/1) | qa-browser E2E | 선택 | 템플릿 생성 후 exit 0 |
| `obsidian` (2) | wiki graph view | 선택 | 텍스트 그래프로 대체 |
| `ollama` | localllm 추론 (opencode 경유) | **localllm 필수** | 사이클 불가 |

> **주의 — 문자열 매칭의 함정**: `"claude"` 는 `.claude/bin/*.py` 에 16회 나오지만 **바이너리 호출이
> 아니다**. `design_pick.py` 의 브랜드명(4 브랜드 중 하나)과 `lint.py` 의 baseline 변형
> 디렉토리명이다. `claude` 바이너리를 실제로 실행하는 곳은 `localllm` 의 `cycle_driver.py`
> (호스트 비교 측정 경로, F029) 하나뿐이다.

> `gh`(GitHub CLI) 는 코드가 아니라 **에이전트 행동 규칙**에서 쓰인다 (`gh pr create` 는
> autonomous #3-C 승인 경계).

### 사용하는 Python 표준 라이브러리

**메인 `.claude/bin/*.py`** — `argparse` `collections` `datetime` `difflib` `fnmatch` `json`
`os` `pathlib` `re` `shutil` `sqlite3` `subprocess` `sys` `tempfile` `traceback` `typing`
(+ `__future__` 지시자)

**변형 전용 도구** (`cycle_driver` / `autoresearch` / `aif_judge`) — 위에 `hashlib` `time` 추가

무인 스위트(`tests/suite/run_suite.py`)는 `ast` 를 추가로 쓴다 (docstring 판정 — 측정 11).

`sqlite3` 로 brain DB 와 FTS5 세션 검색을 구현한다 — 외부 DB 가 필요 없는 이유다.

---

## 변형별 도구 가용 매트릭스

| 도구군 | gstack | auto | design | wiki | orch | hermes | productmgr | productnw | loope | aif | localllm | localllm.aif |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| lint · brain · backup · qa_browser · host | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| gatekeeper (자율) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| design_pick · designer | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| wiki | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| researcher · orchestrate | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| session_search · skill_forge | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| product-manager · product-cycle | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| consortium | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| verify_loop · hill_climb · rubrics | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| aif_judge · items rubric | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| cycle_driver · autoresearch · 무인 스위트 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| **외부 의존성 허용** | 0 | 0 | 0 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 |

`claude/`(baseline)·`openai/.codex/`(stub)는 동결 변형이라 표에서 제외했다.

---

## 재생성

인벤토리는 낡는다. 아래 명령으로 현재 상태를 다시 뽑아 이 문서와 대조한다.

```bash
# 계층 1 — bin 도구 + 줄수
for f in .claude/bin/*.py .claude/bin/*.sh; do printf "%-24s %5s\n" "$(basename $f)" "$(wc -l < $f)"; done

# 계층 2~5 — 개수와 목록
ls .claude/agents/ .claude/commands/ .claude/skills/ .claude/hooks/ .claude/bin/host_adapters/

# 외부 도구 문자열 등장 수 (호출·감지·메시지 포함 — 호출 지점 수가 아니다)
# 주의: 브랜드명·디렉토리명과 겹치는 토큰("claude" 등)은 오탐이므로 grep -rn 으로 문맥을 본다
grep -rhoE '"(git|gh|npx|npm|node|opencode|ollama|qmd|marp|obsidian|playwright)"' \
  .claude/bin/*.py | sort | uniq -c | sort -rn

# 외부 도구 감지 로직 (graceful degrade 확인)
grep -rhoE "which\(['\"][a-z0-9-]+['\"]\)" .claude/bin/*.py | sort -u
grep -ohE "command -v [a-z0-9-]+" .claude/bin/*.sh | sort -u

# zero-dep 확인 — 전부 표준 라이브러리여야 한다
grep -rhE "^import |^from " .claude/bin/*.py | awk '{print $2}' | cut -d. -f1 | sort -u

# 변형 전용 도구 (메인에 없는 것)
for v in localllm localllm.aif claude.aif claude.productnw; do
  echo "$v: $(comm -13 <(ls .claude/bin/ | sort) \
    <(ls src/harness_template/$v/harness/.claude/bin/ | sort) | tr '\n' ' ')"
done

# 변형 격리 정합성
python3 .claude/bin/lint.py check --only=LINT-MR
```

## 관련 문서

- [CLAUDE.md](../CLAUDE.md) — 각 도구의 호출 기준과 14 변형 미러 정책
- [README.md](../README.md) — 변형 계보와 선택 가이드
- [docs/adr/](./adr/) — 각 도구를 도입한 결정 기록
- [.claude/rules/coding-standards.md](../.claude/rules/coding-standards.md) — 변형별 외부 의존성 계약
