# ADR-004: LLM Wiki 패턴 (lint + index) — 정합성 헬스체크 + 산출물 카탈로그

> Feature: F009 — Phase 5 LLM Wiki 패턴 (lint + index)
> 작성: architect 에이전트 | 날짜: 2026-05-20

## 상태

`Accepted` — 본 ADR은 Karpathy LLM Wiki gist 의 3원칙 (sources/wiki/schema + ingest/query/lint
+ index.md/log.md) 중 우리 컨텍스트에 적용 가능한 **Top 3** (`docs/index.md` 단일 카탈로그,
`/project:lint` 헬스체크, `claude-progress.txt` prefix 표준) 을 **모듈 분리 Python 헬퍼 +
2 세션 분할**로 도입한다. F005 Brain · F006 host_adapters · F007 design-review ·
F008 qa-browser 의 hook-failure-tolerance + 외부 의존성 0 + 옵셔널 보장 정책을 그대로
일관 유지한다.

---

## 컨텍스트

### F009 의 본질적 질문 — "LLM Wiki" 를 메타-하네스에 어떻게 매핑하는가

Karpathy 의 LLM Wiki gist 는 **RAG 의 대안**으로 LLM 이 점진적으로 markdown wiki 를
구축·유지하는 패턴을 제시한다:

| LLM Wiki 원개념 | 우리 컨텍스트 매핑 가능성 |
|---|---|
| `sources/` (raw 자료) | 다운스트림 프로젝트의 코드/문서 — **하네스 자체엔 불필요** |
| `wiki/` (LLM 가공 본문) | `docs/adr/`, `docs/design/`, `CLAUDE.md`, `.claude/skills/` — **이미 존재** |
| `schema/` (라벨/링크 규약) | feature_list.json, 학습 type enum, ADR 헤더 — **이미 존재 (부분)** |
| `ingest` (외부 → wiki) | F005 Brain `sync` + handoff.md 의 학습 append — **이미 존재** |
| `query` (wiki 조회) | F005 Brain `search` + grep — **이미 존재** |
| `lint` (정합성 검사) | **❌ 미존재 — F009 도입 대상** |
| `index.md` (전 wiki 카탈로그) | **❌ 미존재 — F009 도입 대상** |
| `log.md` (변경 이력) | `claude-progress.txt` — **부분 존재, prefix 표준화 필요** |

이미 합의된 Top 3 는 위 매핑의 **빈칸 3개** 를 정확히 채운다:

1. **`docs/index.md`** — 산출물 단일 카탈로그 (LLM Wiki `index.md` 대응)
2. **`/project:lint`** — 정합성 헬스체크 (LLM Wiki `lint` 연산 대응)
3. **`claude-progress.txt` prefix 표준** (`## [YYYY-MM-DD HH:MM] event | title`) — log 규약

### F007 design-review · F008 qa-browser 와의 책임 경계 우려

F007 셀프 모드의 IA-S/CON-S 항목 (CLAUDE.md 트리 ↔ 실제 파일, ADR 경로 유효성, gstack
미러 동기화) 은 **lint 가 검사할 항목과 일부 중첩**된다. F008 qa-browser 셀프 모드도
정의 dry-run 을 수행한다. 세 도구가 동일 영역을 중복 검사하면 사용자가 어느 도구를
호출해야 할지 혼동한다. **F007/F008/lint 의 역할 경계가 명확해야 한다.**

### 4변형 동기화 정책의 적용 범위

CLAUDE.md "harness_template 동기화 정책" 섹션은 다음을 명시한다:

- `claude.gstack/harness/` ⓑ — 메인. 전체 미러 대상.
- `claude/harness/` ⓐ — Phase 0 baseline. 동결. **예외**: Karpathy 4원칙 같은 phase-agnostic
  보편 디시플린은 baseline 동기화.
- `openai/harness/.codex/` ⓒ — F006 세션 2 수동 산출물. codex 어댑터 실구현 전엔 수동.
  **예외**: Karpathy 4원칙 같은 보편 디시플린은 수동 동기화.

F009 의 lint 가 "Karpathy 4원칙" 처럼 phase-agnostic 보편 디시플린에 속하는가? 이 판단이
ⓐ baseline 과 ⓒ openai 변형 동기화 여부를 결정한다.

### 제약

- **외부 의존성 0**: F005~F008 정책 일관 (Python stdlib + bash 만, argparse + json + re
  + pathlib + datetime + difflib 만 허용)
- **무회귀**: F001~F008 의 동작은 한 비트도 바뀌지 않는다
- **에이전트 신설 금지**: F007 결정 3 · F008 결정 4 일관
- **`feature_list.json` `passes` 필드 절대 수정 불가**: QA 에이전트 단독 권한 (F008 결정 4)
- **`.claude/settings.json` 무수정**: Claude Code 공식 스키마 격리 (F006 ADR-001 결정 1)
- **옵셔널 보장**: 호출하지 않으면 하네스 동작에 영향 없음 (F005 Brain 패턴) — AC7 명시
- **세션 수**: estimated_sessions=2 (feature_list.json)

---

## 결정

### 결정 1 — `lint.py` 구조: **단일 파일 + 서브커맨드 + 검사기 모듈 함수** (F005 Brain 패턴)

**채택**: `.claude/bin/lint.py` 단일 Python 파일. 검사 항목은 모듈 내부 함수로 분리.
F006 처럼 별도 `lint_checkers/` 패키지를 만들지 않는다.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) F005 Brain 패턴 — 단일 파일 (`lint.py` 한 파일에 모든 검사기) | 진입점 단순, 외부 의존성 0 유지 용이, 호출 한 줄로 끝, F005 와 일관 | 파일 비대화 (~800줄 예상 — F008 qa_browser.py 와 동급) | **채택** |
| (B) F006 host_adapters 패턴 — `lint.py` + `lint_checkers/` 디렉토리 | 검사기 추가 시 격리, 단위 테스트 용이 | 파일 7개 증가 (`__init__.py` + 검사기 6개), 검사기가 어댑터처럼 다양하지 않음 (모두 동일 인터페이스), 호스트 어댑터처럼 동적 로드 불필요 | 과함 |
| (C) bash 스크립트 | hook 과 일관 | 정합성 검사는 JSON/regex 처리 — bash 비효율, F005·F006·F008 패턴 일관성 깨짐 | 부적합 |

**근거**: lint 의 검사기 6종은 **모두 동일 호출 시그니처** (`run() -> List[LintIssue]`) 로
충분하다 — 호스트 어댑터처럼 다형성·동적 로드가 필요 없다. F005 Brain 의 `sync_*` /
`search_*` / `stats_*` 함수처럼 단일 파일 내부 함수로 정리하는 게 자연스럽다.

**서브커맨드 인터페이스** (verb-based, F005·F006·F008 일관):

```
python3 .claude/bin/lint.py check              # 기본 — 6 카테고리 전체 검사
python3 .claude/bin/lint.py check --category=feature_list  # 특정 카테고리만
python3 .claude/bin/lint.py regenerate-index   # docs/index.md 재생성
python3 .claude/bin/lint.py report             # 마지막 실행 결과 요약 (캐시)
python3 .claude/bin/lint.py self               # 셀프 dry-run (F007/F008 셀프 모드 양식 일관)
```

**옵션**:

```
--format=human|json    출력 형식 (기본 human, 머신 통합 시 json)
--strict               BLOCK 발견 시 exit 1 (CI gate 용도, 기본 OFF — 결정 6 참조)
--category=<name>      특정 검사기만 실행
--quiet                BLOCK 만 출력 (CONCERN/INFO 생략)
```

**출력 정책**: 사람용 (마크다운 표) 기본 + `--format=json` 옵션 시 머신용. 둘 다 지원.
근거: F007 design-review 가 마크다운 표를, F005 Brain 이 JSON 을 사용 — **lint 는 두
방식 모두 필요** (사람 호출 + 향후 retro/ship 통합에서 머신 파싱).

---

### 결정 2 — lint 검사 6 항목 카테고리화 + 라벨 표준

**채택**: AC2 의 6항목을 **F007 design-review 라벨 (BLOCK/CONCERN/INFO + PASS)** 과
일관되게 분류한다. 신규 라벨을 도입하지 않는다.

| # | 카테고리 ID | 검사 항목 | BLOCK 기준 | CONCERN 기준 | INFO 기준 |
|---|---|---|---|---|---|
| 1 | `LINT-FL` | feature_list 정합성 (status×passes) | `passes=true` 인데 `status≠done`, 또는 `status=done` 인데 `passes=false` | dependencies 가 가리키는 ID 가 존재하지 않음 | priority 미설정, estimated_sessions 미설정 |
| 2 | `LINT-STALE` | stale `in-progress` (>30일) | 30일 초과 | 14~30일 | 7~14일 |
| 3 | `LINT-ADR` | ADR ↔ feature 연결성 | `acceptance_criteria` 가 ADR 을 명시 참조하는데 해당 ADR 파일이 없음 | ADR 본문에서 참조한 파일 경로가 무효 | ADR-NNN 번호 gap (001, 002, 004 — 003 누락 등) |
| 4 | `LINT-LEARN` | learnings 모순 | 같은 `key` 인데 tombstone 없이 정반대 `insight` (예: "X 사용" + "X 금지") | confidence 미설정, source 미설정 | tombstone 비율 > 50% |
| 5 | `LINT-AC` | acceptance_criteria 누락/모호 | feature 가 `acceptance_criteria` 배열 자체 부재 | 배열이 있으나 항목 < 2개, 또는 "구현" / "잘 동작" 등 모호 키워드만 포함 | 단일 항목인데 "TODO" 포함 |
| 6 | `LINT-MIRROR` | 미러링 diff (4변형) | `.claude/` 와 `claude.gstack/harness/.claude/` 의 미러 대상 파일이 diff (단, `__pycache__`, `state/` 제외) | `claude/harness/.claude/` baseline 에 Karpathy 4원칙 파일이 누락 (예외 동기화 정책) | `openai/harness/.codex/` 변형 diff (codex 어댑터 stub 이므로 현 phase 에선 INFO) |

**라벨 의미** (F007 ADR-002 결정 4 그대로 차용):

| 라벨 | 의미 | 액션 |
|---|---|---|
| **BLOCK** | 머지/배포 차단 — 즉시 수정 필요 | Developer 위임 또는 사용자 결정 |
| **CONCERN** | 권장 — 우선순위 따라 수정 | 일괄 보고만, 자동 위임 X |
| **INFO** | 정보성 — 의도된 상태일 수 있음 | 보고만, 액션 강제 X |
| **PASS** | 검사 항목 명시적 통과 | — |

**왜 새 라벨 (예: ERROR/WARN/NOTICE) 을 만들지 않는가**: 사용자가 도구 간 라벨을 학습해야
하는 비용 ↑. F007 (design-review) + F008 (qa-browser) + F009 (lint) 가 모두 동일 라벨을
쓰면 라벨 의미가 누적 학습된다.

**F007 design-review · F008 qa-browser 와의 책임 경계** (중복 영역 우려 해소):

| 영역 | design-review (F007) | qa-browser (F008) | **lint (F009)** |
|---|---|---|---|
| 검사 대상 | UI 코드/문서 (downstream) + 하네스 정합성 (self) | 실행 중인 페이지 + 정의 dry-run | **거버넌스 (feature/ADR/learning/mirror)** |
| 검사 방식 | 텍스트 정적 분석 (grep) | 동적 브라우저 (Playwright) | **JSON/마크다운 메타데이터 분석** |
| 핵심 가치 | IA / A11Y / 일관성 | E2E 동작 검증 | **거버넌스 정합성** (LINT-FL/STALE/ADR/LEARN/AC/MIRROR) |
| 자체 정합성 (CLAUDE.md 트리 등) | ✅ IA-S 항목 (self 모드) | ❌ | ✅ LINT-MIRROR + LINT-ADR (중첩) |
| feature_list × passes | ❌ | ❌ | ✅ **단독 담당** (LINT-FL) |
| stale 탐지 | ❌ | ❌ | ✅ **단독 담당** (LINT-STALE) |
| learnings 모순 | ❌ | ❌ | ✅ **단독 담당** (LINT-LEARN) |

**중첩 해소** — `LINT-MIRROR` 와 design-review IA-S3/CON-S3 의 차이:
- design-review IA-S3: **ADR 본문에서 참조한 파일 경로 유효성** (사람의 글쓰기 검사)
- design-review CON-S3: **claude.gstack 미러 동기화 점검** (디자인 일관성 차원)
- **lint LINT-MIRROR**: **4변형 (ⓐ/ⓑ/ⓒ + 원본) 전체 diff** (거버넌스/배포 차원)

→ design-review 는 **사람의 문서 디자인 품질**, lint 는 **자동화된 거버넌스 정합성**.
관점이 다르므로 둘 다 존재해도 가치 있다. 단, **호출 순서** 는 결정 6 에서 명시.

---

### 결정 3 — `docs/index.md` 스키마 + 위치 + 자동 생성 정책

**채택**: `docs/index.md` 위치 (현 `docs/` 디렉토리 재사용) + **자동 생성 + 헤더에
"자동 생성 — 직접 수정 금지" 명시 + 사람 편집 영역은 별도 frontmatter 섹션으로 분리**.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) `INDEX.md` 루트 배치 | 발견성 최고 (루트 가시), GitHub README 형식 일관 | 루트에 추가 파일 증가, docs/ 디렉토리 의미 약화 | 매력적이나 단점 우세 |
| **(B) `docs/index.md`** | 기존 `docs/{adr,design}/` 와 같은 디렉토리, 미러 정책 동일 (`docs/adr/*.md` 미러 대상) | 루트 가시성 ↓ — CLAUDE.md "빠른 시작" 섹션에서 명시적 안내 필요 | **채택** |
| (C) `.claude/state/index.md` | 자동 생성물 격리 | docs 카탈로그가 state 에 있는 건 의미 충돌 (state 는 세션 로컬, index 는 영구) | 부적합 |

**근거**: Karpathy 가스트의 `index.md` 는 wiki 디렉토리 안에 있다. 우리 `docs/` 가
wiki 역할이므로 `docs/index.md` 가 의미적으로 가장 가깝다. 루트 가시성은 CLAUDE.md
"빠른 시작" 에 한 줄로 보강 (예: `/project:lint regenerate-index → docs/index.md 생성`).

**파일 위치**: `/home/obigo/project/oss/harness_update_agent/docs/index.md`

**스키마**:

```markdown
<!-- 자동 생성 파일 — 직접 수정 금지 -->
<!-- 생성: python3 .claude/bin/lint.py regenerate-index -->
<!-- 마지막 갱신: 2026-05-20T10:00:00+09:00 -->
<!-- 생성 대상: ADR + design + features + agents + commands + skills + learnings 통계 -->

---

# 하네스 산출물 카탈로그

> 이 파일은 `.claude/bin/lint.py regenerate-index` 가 자동 생성합니다.
> 직접 수정하지 마세요. 변경 사항은 다음 regenerate 시 덮어씌워집니다.
> 사람 편집 영역이 필요하면 `docs/index.notes.md` 를 별도로 만들어 사용하세요.

---

## 1. ADR (아키텍처 결정 기록)

| ID | 제목 | 상태 | 관련 Feature | 파일 |
|---|---|---|---|---|
| ADR-001 | 멀티 호스트 아키텍처 준비 | Accepted | F006 | docs/adr/ADR-001-multi-host-architecture.md |
| ADR-002 | Design Review 강화 (단계 1) | Accepted | F007 | docs/adr/ADR-002-design-review.md |
| ADR-003 | QA 브라우저 자동화 (Playwright) | Accepted | F008 | docs/adr/ADR-003-qa-browser.md |
| ADR-004 | LLM Wiki 패턴 (lint + index) | Accepted | F009 | docs/adr/ADR-004-lint-and-index.md |

## 2. 상세 설계 (docs/design/)

| Feature | 제목 | 파일 |
|---|---|---|
| F007 | design-review 체크리스트 | docs/design/F007-design-review-checklist.md |
| F008 | qa-browser 슬롯 카탈로그 | docs/design/F008-qa-browser-templates.md |

## 3. 기능 목록 (feature_list.json)

| ID | 상태 | passes | 제목 | 의존성 |
|---|---|---|---|---|
| F001 | done | ✅ | Phase 1 — Safety Guards + ... | — |
| ...  | ...  | ...  | ...  | ... |
| F009 | todo | ❌ | Phase 5 — LLM Wiki 패턴 | F001, F005 |

**진행률**: 8/9 완료 (89%)

## 4. 에이전트 (.claude/agents/)

| 이름 | 역할 | 파일 |
|---|---|---|
| planner | 기능 분해·우선순위 | .claude/agents/planner.md |
| architect | 시스템 설계·ADR | .claude/agents/architect.md |
| developer | 구현·테스트 | .claude/agents/developer.md |
| reviewer | 코드 품질·보안·성능 | .claude/agents/reviewer.md |
| qa | E2E·passes 권한 | .claude/agents/qa.md |

## 5. 슬래시 커맨드 (.claude/commands/)

| 커맨드 | 설명 | 파일 |
|---|---|---|
| /project:init | 프로젝트 초기화 | .claude/commands/init-project.md |
| /project:start-session | 세션 시작 | .claude/commands/start-session.md |
| ... | ... | ... |
| /project:lint | 정합성 헬스체크 (F009) | .claude/commands/lint.md |

## 6. 스킬 (.claude/skills/)

| 이름 | 설명 | 파일 |
|---|---|---|
| planning | 기능 분해 가이드 | .claude/skills/planning/SKILL.md |
| coding | 구현 가이드 | .claude/skills/coding/SKILL.md |
| testing | 테스트 가이드 | .claude/skills/testing/SKILL.md |
| design-review | 디자인 감사 (F007) | .claude/skills/design-review/SKILL.md |
| qa-browser | QA 자동화 (F008) | .claude/skills/qa-browser/SKILL.md |

## 7. 학습 통계 (`.claude/state/learnings.jsonl`)

- 총 학습: NN건
- type별: architecture NN / pattern NN / pitfall NN / improvement NN
- 최근 5건:
  - 2026-05-12 [architecture] Karpathy 4원칙은 baseline + openai 변형에도 동기화...
  - ...

## 8. 메타

- 4변형 동기화 상태: ✅ (`.claude/` ↔ `claude.gstack/harness/.claude/`)
- baseline 동결 정책: ⓐ `claude/` 동결, Karpathy 예외만 동기화
- 호스트: claude-code (default)
- 다음 ADR 번호: ADR-005
- 다음 Feature 번호: F010

---

*생성: lint.py regenerate-index | 모든 항목은 LINT-FL/STALE/ADR 검사로 자동 검증됨*
```

**자동 생성 vs 사람 편집**: **순수 자동 생성**. 사람 편집 영역이 필요하면 `docs/index.notes.md`
별도 파일로 분리. LLM Wiki gist 패턴과 일치 (`index.md` 는 LLM 이 소유).

**frontmatter 강제 여부**: ADR/design 문서는 **이미 첫 줄 형식이 일관** (`> Feature:
... | 작성: ... | 날짜: ...`). YAML frontmatter 를 새로 강제하지 않고, **첫 줄 정규식
파싱** 으로 메타데이터 추출.

```
ADR 메타 추출 정규식:
  ^# ADR-(\d+): (.+)$                          # 제목 라인에서 ID + 제목
  ^> Feature: (F\d+)                           # Feature 연결
  ^## 상태\s*\n\s*`?(\w+)`?                    # 상태 (Accepted/Proposed/Deprecated)
```

agents/commands/skills 의 frontmatter (`name:`, `description:`) 는 이미 존재 — 그대로 활용.
신규 frontmatter 강제 없음 — **무회귀 보장**.

---

### 결정 4 — `claude-progress.txt` log prefix 컨벤션

**채택**: **신규 항목부터만 적용**. 기존 항목은 마이그레이션하지 않는다.
prefix 형식은 **현재 구조의 확장** 으로 자연스럽게 진화한다.

**현재 형식** (`claude-progress.txt` 실제 샘플):

```
============================================================
[2026-04-30] QA: F006 PASSED
============================================================
```

**신규 표준 형식** (Karpathy gist `log.md` 영감):

```
============================================================
## [2026-05-20 10:00] developer | F009 session 1 — lint.py 코어 + check 서브커맨드 완료
============================================================
```

**구성 요소**:

| 요소 | 형식 | 예시 | 비고 |
|---|---|---|---|
| 헤더 마커 | `## ` (Markdown H2) | `## ` | grep 패턴 단순화, marker 라인과 결합 |
| 날짜·시간 | `[YYYY-MM-DD HH:MM]` (분 단위) | `[2026-05-20 10:00]` | 기존 `[YYYY-MM-DD]` 확장 (시간 추가) |
| agent | 소문자 enum: `planner` / `architect` / `developer` / `reviewer` / `qa` / `user` | `developer` | 기존 `Developer:` 대문자에서 소문자로 정규화 |
| 구분자 | ` \| ` (pipe with spaces) | ` \| ` | 콜론 대신 — agent 명에 콜론이 들어가는 변형 회피 |
| 제목 | feature_id + 짧은 한 줄 요약 | `F009 session 1 — lint.py 코어 ...` | 기존 형식 그대로 |

**정규식** (lint.py 가 검증할 패턴):

```python
LOG_PREFIX_RE = re.compile(
    r"^##\s+\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]\s+"
    r"(planner|architect|developer|reviewer|qa|user)\s+\|\s+"
    r"(.+)$"
)
```

**마이그레이션 정책** (3 옵션 비교):

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 일괄 마이그레이션 (기존 모든 항목 변환) | 일관성 100%, 검색·통계 즉시 향상 | 기존 항목 38개 수동 변환 → 작업량 大, **기존 인계 컨텍스트를 손상시킬 위험** | ❌ |
| **(B) 신규 항목부터만** | 무회귀, 작업량 0, 점진 진화 | 한동안 두 형식 공존 | **채택** |
| (C) 일괄 + 백업 | 안전 마이그레이션 | 작업량 大 + 백업 파일 1개 추가 | 과함 |

**handoff.md 가이드 변경**: handoff 스킬/커맨드는 **권장만**, 강제 아님 (옵셔널 보장
원칙). 신규 prefix 형식을 사용하면 lint LINT-LOG (선택 검사기, AC 외) 가 통계를 더
정확히 뽑을 수 있다는 안내만 추가.

**왜 prefix 자동 부여 hook 을 만들지 않는가**: F005 Brain hook-failure-tolerance 원칙
+ 옵셔널 보장 (AC7). 사용자가 직접 prefix 를 적는 게 자연스럽다. lint 가 prefix 누락
시 INFO 라벨로 알릴 뿐 차단 X.

**검사 라벨**: prefix 형식 검증은 **LINT-LOG (선택 검사기)** 로, **AC2 의 6항목 밖**
이므로 기본 `check` 에서 INFO 만 출력. AC2 6항목 검사기에 포함하지 않는 이유: AC 가
명시하지 않음 + 마이그레이션 정책 (B) 와 일관 (기존 형식도 정상으로 인정).

---

### 결정 5 — 4변형 동기화 전략: **`.claude/bin/lint.py` 는 gstack 만 미러, baseline + openai 은 미동기화**

**채택**: lint 는 **Karpathy 4원칙 같은 phase-agnostic 보편 디시플린이 아니다**
(거버넌스 도구). 따라서 다음 정책:

| 변형 | 동기화 여부 | 근거 |
|---|---|---|
| ⓑ `claude.gstack/harness/.claude/` | ✅ **전체 미러** | 메인 — 모든 phase 산출물 정합 사본. F005/F006/F007/F008 의 bin/ 파일이 이미 여기에 있음. |
| ⓐ `claude/harness/.claude/` (baseline) | ❌ **동기화 안 함** | Phase 0 동결. lint 는 phase 5 산출물 — Karpathy 4원칙처럼 phase-agnostic 보편 디시플린이 아니다. F005 Brain·F006 host_adapters 도 baseline 에 동기화하지 않음 — **일관성 유지**. |
| ⓒ `openai/harness/.codex/` | ❌ **동기화 안 함** | codex 어댑터 stub 상태 (F006 ADR-001 결정 4). prompt/스킬은 코드 어댑터 실구현 후 자동 재생성 (F006 후속). 현 phase 에서 lint 는 prompt 형태로도 제공하지 않음 — AC6 의 "codex 는 prompt 만" 표현은 docs/index.md 와 lint 결과 양식을 prompt 로 표현 가능하다는 의미이지, F009 가 codex prompt 산출물을 만들어야 한다는 강제가 아니다 (결정 7 참조). |

**근거 비교**:

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 3변형 모두 미러 (ⓑ + ⓐ + ⓒ) | 일관성 100% | baseline 동결 정책 위배, F005/F006 패턴 일관성 깨짐 (F005 도 baseline 에 brain.py 없음) | ❌ |
| **(B) ⓑ gstack 만 미러 (현재 정책)** | F005/F006/F008 패턴 100% 일관, baseline 동결 유지, codex stub 정책 일관 | ⓐ 와 ⓒ 에서 lint 호출 불가 — 그러나 baseline 은 Phase 0 스냅샷이므로 lint 가 필요 없고, openai 은 codex 어댑터 실구현 후속 phase 까지 대기 | **채택** |
| (C) ⓑ + ⓐ 만 미러 | "보편 디시플린" 확장 적용 | lint 는 거버넌스 도구 — Karpathy 4원칙 같은 사고 원칙이 아님 | 부적합 |

**AC6 "codex 는 prompt 만 (실행은 후속 phase)" 해석**:

AC 의 표현이 모호하다. 두 가지 해석 가능:

1. **(해석 1)** F009 가 codex 호스트용 prompt 형태로 lint 결과를 제공해야 한다
2. **(해석 2)** F009 는 lint 를 Python 으로 만들고, codex 어댑터가 실구현되면 그때
   해당 prompt 산출물이 자동 재생성된다 (F006 정책 일관)

→ **해석 2 채택**. 근거: F006 ADR-001 결정 4 의 "stub 어댑터는 차단하지 않고 안내만"
정책. codex 어댑터가 stub 인 현 phase 에서 F009 가 별도로 codex prompt 를 수동 작성하면
F006/F008 의 정책 일관성이 깨진다. codex 어댑터 실구현 후속 phase 에서 `render-skills`
가 자동 재생성한다.

**미러링 명령** (CLAUDE.md 권장 명령 그대로 사용):

```bash
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  .claude/ src/harness_template/claude.gstack/harness/.claude/
```

`docs/adr/ADR-004-*.md` + `docs/design/F009-*.md` (있다면) 도 미러.

---

### 결정 6 — 옵셔널 보장 + exit code 정책: **항상 exit 0 + `--strict` 플래그**

**채택**: 기본 exit code 는 **항상 0** (F005 Brain · F006 host · F007 design-review ·
F008 qa-browser 의 hook-failure-tolerance 일관). 단 `--strict` 플래그 시 BLOCK 발견 →
exit 1 (CI gate 용).

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 항상 exit 0 | hook-failure-tolerance 일관, 호출자 차단 X | CI gate 용도엔 부족 | 기본 |
| (B) BLOCK 시 항상 exit 1 | CI gate 용도 직관적 | hook-failure-tolerance 위배 (lint 호출이 handoff 훅 등에서 실패 시 차단), F005~F008 정책 일관성 깨짐 | ❌ |
| **(C) 기본 exit 0 + `--strict` 옵션으로 exit 1** | 양쪽 장점, 사용자가 명시적으로 strict 모드 활성화 | 옵션 1 개 증가 | **채택** |

**옵셔널 보장 메커니즘** (AC7 명시):

- **자동 호출 트리거 추가 안 함** — handoff hook · session-end hook · pre-bash hook
  어디서도 lint 를 호출하지 않는다.
- `/project:handoff` 커맨드 산문에 **"lint 실행 권장" 안내 한 줄만** 추가 (강제 X).
- 호출자가 lint 를 한 번도 호출하지 않으면 하네스는 F008 까지의 동작 그대로.

**근거**: F005 Brain 의 옵셔널 패턴 (사용자가 brain-sync 를 호출 안 하면 brain.db 자체가
없음 — 어떤 영향도 없음) 과 동일.

---

### 결정 7 — F009 세션 분할: **2 세션** (feature_list.json estimated_sessions=2 일치)

**권장 분할**:

| 세션 | 범위 | 산출물 | AC 충족 |
|---|---|---|---|
| **세션 1** | `lint.py` 코어 + 검사기 3종 (`LINT-FL` / `LINT-STALE` / `LINT-AC`) + `check` 서브커맨드 + `/project:lint` 커맨드 골격 + ADR-004 미러 | `.claude/bin/lint.py`, `.claude/commands/lint.md`, 자체 dry-run 결과, claude.gstack 미러 | AC1 (커맨드 + lint.py 골격), AC2 (3/6 검사기), AC7 (옵셔널) |
| **세션 2** | 검사기 3종 추가 (`LINT-ADR` / `LINT-LEARN` / `LINT-MIRROR`) + `regenerate-index` 서브커맨드 + `docs/index.md` 생성 + CLAUDE.md 통합 + log prefix 가이드 추가 + handoff 안내 추가 | `docs/index.md`, CLAUDE.md 빠른 시작 + 호출 기준 + 디렉토리 트리, `.claude/commands/handoff.md` 안내, 학습 jsonl, 미러 동기화 | AC2 (6/6 검사기), AC3 (index.md), AC4 (regenerate-index 서브커맨드), AC5 (CLAUDE.md + prefix 가이드), AC6 (4변형 미러 — ⓑ만, ⓐ·ⓒ 미동기화 명시), AC7 (옵셔널 보강) |

**분할 근거**:

- 세션 1 의 검사기 3종 (`LINT-FL` / `LINT-STALE` / `LINT-AC`) 은 **모두 `feature_list.json`
  만 읽는다** — 단일 입력 소스 → 세션 응집도 ↑
- 세션 2 의 검사기 3종 (`LINT-ADR` / `LINT-LEARN` / `LINT-MIRROR`) 은 **다중 입력 소스
  (ADR 디렉토리 + learnings.jsonl + 4변형 diff)** → 세션 2 에 모으는 게 자연스럽다
- 세션 2 에서 `regenerate-index` + CLAUDE.md 통합을 함께 처리 — F006/F007/F008 모두
  마지막 세션에서 통합·문서·미러링·핸드오프를 수행하는 패턴 일관

**왜 3 세션 (F008 같은 분할) 이 아닌가**: F009 는 외부 의존성 분기가 없다 (Playwright
같은 옵셔널 의존성이 lint 에는 없음) → F008 의 세션 2 (실제 실행) 같은 의존성 분리
필요 없음. 2 세션이 적절.

---

## 대안 검토

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| lint 를 bash 스크립트로 (예: `lint.sh`) | hook 과 일관 | JSON/markdown 파싱 비효율, F005~F008 Python 패턴 일관성 깨짐 | 결정 1 |
| `lint_checkers/` 패키지 분리 (F006 host_adapters 패턴) | 검사기 격리 | 검사기가 다형성 필요 없음 (동일 시그니처), 파일 7개 증가 | 결정 1 |
| `INDEX.md` 루트 배치 | 발견성 ↑ | docs/ 디렉토리 의미 약화 | 결정 3 |
| YAML frontmatter 일괄 도입 (모든 ADR/design 에 강제) | 메타데이터 추출 강건 | 기존 8개 파일 수동 마이그레이션 + 무회귀 위배 | 결정 3 |
| log prefix 일괄 마이그레이션 | 검색·통계 즉시 향상 | 기존 38개 항목 변환 → 인계 컨텍스트 손상 위험 | 결정 4 |
| handoff hook 에서 lint 자동 호출 | 자동 헬스체크 | 옵셔널 보장 위배 (AC7 위배) | 결정 6 |
| BLOCK 시 항상 exit 1 | CI gate 직관적 | hook-failure-tolerance 위배 | 결정 6 |
| 4변형 모두 미러 (ⓐ·ⓑ·ⓒ) | 일관성 100% | baseline 동결 + codex stub 정책 위배 | 결정 5 |
| F007 design-review 에 lint 통합 | 도구 1개 통합 | 책임 영역 다름 (정적 분석 vs 거버넌스), F007 ADR-002 결정 6 (외부 의존성 0) 와 다른 입력 (JSON/jsonl) | 결정 2 |
| F005 Brain 에 lint 통합 | brain.py 한 파일 | Brain 은 cross-project 지식 베이스 — lint 는 single-project 거버넌스. 책임 다름 | 부적합 |
| docs/index.md 를 사람이 직접 편집 | 자유도 ↑ | LLM Wiki 패턴 위배 (gist 가 명시: index 는 LLM 이 소유), 동기화 누락 시 정보 신뢰성 ↓ | 결정 3 |
| 3 세션 분할 (F008 패턴) | 세션 부하 ↓ | 외부 의존성 분기 없으므로 세션 2 의미 약함, feature_list estimated=2 와 불일치 | 결정 7 |

---

## 결과

### 긍정적 영향

- **F009 모든 AC 충족**:
  - AC1 — `/project:lint` 커맨드 + `.claude/bin/lint.py` (외부 의존성 0)
  - AC2 — 6개 검사기 (LINT-FL/STALE/ADR/LEARN/AC/MIRROR)
  - AC3 — `docs/index.md` 자동 생성/갱신 (8 섹션)
  - AC4 — `regenerate-index` 서브커맨드
  - AC5 — CLAUDE.md 가이드 + claude-progress.txt prefix 컨벤션
  - AC6 — 4변형 미러링 (ⓑ 만, ⓐ·ⓒ 정책 명시)
  - AC7 — 옵셔널 보장 (자동 호출 트리거 0)
- **외부 의존성 0 정책 일관**
- **무회귀**: F001~F008 의 동작 무수정, settings.json/host.json/QA 에이전트 무수정
- **명확한 역할 경계**: F007 design-review (IA/A11Y/CON) ↔ F008 qa-browser (E2E) ↔
  F009 lint (거버넌스). 셀프 모드 중첩은 관점 차이로 정당화 + 호출 순서 명시
- **F007/F008 패턴 일관**: 단일 파일 헬퍼 + 서브커맨드 + 옵셔널 + exit 0 + 라벨 표준
- **점진적 진화**: log prefix 는 신규 항목부터, frontmatter 강제 없음 — 무회귀 보장
- **거버넌스 가시성**: `docs/index.md` 로 모든 산출물 (ADR/design/feature/agent/command/skill/
  learning) 이 한 곳에서 보임 → LLM Wiki 가스트의 핵심 가치 실현

### 부정적 영향 / 트레이드오프

- 신규 파일 4개 (`.claude/bin/lint.py`, `.claude/commands/lint.md`, `docs/index.md`,
  `docs/adr/ADR-004-*.md`) + 가능하면 `docs/design/F009-lint-checkers.md` (선택, 검사기
  raw 정의 단일 소스 — F007/F008 패턴 일관)
- `docs/index.md` 가 자동 생성물 — 사람이 실수로 편집하면 다음 regenerate 시 손실
  (mitigation: 헤더에 명시 + `docs/index.notes.md` 안내)
- claude-progress.txt 두 형식 공존 (기존 + 신규) → 통계 도구는 양쪽 모두 파싱해야 함
- `LINT-MIRROR` 검사기는 실제로 4변형 diff 를 매번 수행 → I/O 비용 ↑ (mitigation:
  `--category=mirror` 로 분리 호출, 캐시 옵션은 후속)
- 옵셔널 보장으로 인해 **호출 안 하면 정합성 검사가 일어나지 않음** — 사용자 책임. handoff
  안내 한 줄로 권장만 (의도된 트레이드오프)
- baseline (ⓐ) + openai (ⓒ) 에 lint 가 없음 — 향후 codex 어댑터 실구현 시 마이그레이션
  필요 (결정 5 후속 조치)

### 후속 조치

- [ ] (F009 세션 1) lint.py 코어 + 검사기 3종 + check 서브커맨드 + 커맨드 골격
- [ ] (F009 세션 2) 검사기 3종 추가 + regenerate-index + docs/index.md + CLAUDE.md 통합
- [ ] (F009 QA) 자체 dry-run — `/project:lint check` + `--scope=self` 1회 실행 → 본 ADR
  자체가 LINT-ADR PASS 되어야 함
- [ ] (F010 가칭 — 후속) handoff 안내를 더 강제 (예: handoff 시 자동 lint 권장 표시 강화)
- [ ] (F011 가칭 — 후속) codex 어댑터 실구현 시 lint 결과 양식을 codex prompt 로
  자동 변환 (`render-skills` 확장)
- [ ] (F006 후속) baseline (ⓐ) 동기화 정책 재검토 — lint 가 phase-agnostic 으로 승격되면
  baseline 동기화 (Karpathy 예외 일관)
- [ ] (F003 ship.md) lint 카테고리 추가 — feature_list.json 변경 시 lint 제안 (세션 2)

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성 (세션 1)**:

```
.claude/bin/lint.py                                  # 단일 파일 헬퍼 (검사기 + index 재생성 + dry-run)
.claude/commands/lint.md                             # /project:lint 슬래시 커맨드
docs/design/F009-lint-checkers.md                    # (선택) 검사기 raw 정의 (단일 소스 — F007/F008 패턴 일관)
```

**신규 생성 (세션 2)**:

```
docs/index.md                                        # 자동 생성 카탈로그 (regenerate-index 출력)
```

**수정 (세션 1~2)**:

```
CLAUDE.md                                            # "빠른 시작" 섹션에 /project:lint
                                                     # "에이전트 역할 분담" 표 아래 lint vs design-review vs qa-browser 경계 박스
                                                     # 디렉토리 트리에 bin/lint.py, commands/lint.md, docs/index.md, docs/design/F009 추가
                                                     # "lint 호출 기준" 박스 (design-review/qa-browser 호출 기준과 같은 형식)
                                                     # "claude-progress.txt prefix 컨벤션" 신규 섹션 (결정 4 표 그대로)
.claude/commands/handoff.md                          # "lint 실행 권장" 안내 한 줄 (강제 X)
.claude/commands/ship.md                             # lint 카테고리 추가 (feature_list 변경 시)
feature_list.json                                    # F009 status: in-progress → review (Developer 작업 끝)
.claude/state/learnings.jsonl                        # 새 학습 append (architecture 1 + pattern 1 + pitfall 1)
```

**미러링 (claude.gstack 만 — 결정 5)**:

```
src/harness_template/claude.gstack/harness/CLAUDE.md
src/harness_template/claude.gstack/harness/docs/adr/ADR-004-lint-and-index.md
src/harness_template/claude.gstack/harness/docs/index.md
src/harness_template/claude.gstack/harness/docs/design/F009-lint-checkers.md
src/harness_template/claude.gstack/harness/.claude/bin/lint.py
src/harness_template/claude.gstack/harness/.claude/commands/lint.md
src/harness_template/claude.gstack/harness/.claude/commands/handoff.md
src/harness_template/claude.gstack/harness/.claude/commands/ship.md
```

**의도적 미수정 (제약 준수)**:

```
.claude/settings.json                                # Claude Code 스키마 격리
.claude/host.json                                    # F006 격리
.claude/agents/*.md                                  # 모든 에이전트 정의 무수정 (F007/F008 일관)
.claude/bin/brain.py                                 # F005 격리
.claude/bin/host.py, host_adapters/*.py              # F006 격리
.claude/bin/qa_browser.py                            # F008 격리
.claude/skills/*/SKILL.md                            # F007 결정 (.template 마이그레이션은 후속)
docs/adr/ADR-001*.md ~ ADR-003*.md                   # 기존 ADR 무수정
src/harness_template/claude/                         # baseline 동결 (결정 5)
src/harness_template/openai/                         # codex stub (결정 5)
```

**`__pycache__` 제외 처리**: 미러링 명령에 `--exclude='__pycache__' --exclude='*.pyc'`
유지 (F008 부록 A Nit 4 일관).

### 단계별 작업 순서

#### 세션 1 — lint.py 코어 + 검사기 3종 + check + /project:lint

**Step 1.1 — `docs/design/F009-lint-checkers.md` 작성** (선택, 강력 권장)
- 결정 2 의 6 카테고리 표를 그대로 옮겨 정형화
- 각 검사기별 입력 경로 + 라벨 기준 + 출력 형식 의사코드 명시
- 단일 소스 (lint.py 와 SKILL/commands 가 모두 이 문서를 참조)
- F007/F008 패턴 일관

**Step 1.2 — `.claude/bin/lint.py` 코어 골격 작성**
- F005 Brain `brain.py` 의 헤더 docstring 형식 모방
- argparse 서브커맨드: `check`, `regenerate-index`, `report`, `self` (4개)
- 옵션: `--format=human|json`, `--strict`, `--category=<name>`, `--quiet`
- 모든 핸들러 try/except 로 감싸 항상 exit 0 (단, `--strict` + BLOCK 시 exit 1)
- 경로 상수: `_PROJECT_ROOT`, `_FEATURE_LIST`, `_ADR_DIR`, `_DESIGN_DIR`, `_LEARNINGS`,
  `_PROGRESS`, `_GSTACK_DIR`, `_INDEX_MD`

**Step 1.3 — `LintIssue` 데이터 클래스 + `LintResult` 컨테이너 정의**
- `LintIssue`: `(category, id, label, message, file, line, fix_hint)` — 7 필드
- `LintResult`: `(check_id, label, issues: List[LintIssue], duration_ms)`
- `--format=json` 출력 시 dataclasses.asdict 또는 수동 dict 변환
- 라벨 enum: `"BLOCK" | "CONCERN" | "INFO" | "PASS"`

**Step 1.4 — 검사기 3종 구현** (`LINT-FL`, `LINT-STALE`, `LINT-AC`)

- **`check_feature_list_consistency()` → LintResult**
  - `feature_list.json` 로드
  - 각 feature 의 (status, passes) 조합 검증:
    - `passes=true` + `status != "done"` → BLOCK
    - `status="done"` + `passes=false` → BLOCK
    - dependencies 가 가리키는 ID 부재 → CONCERN
    - priority 미설정 / estimated_sessions 미설정 → INFO

- **`check_stale_in_progress()` → LintResult**
  - 각 feature 의 status="in-progress" 항목 식별
  - 마지막 변경 시점 추정: claude-progress.txt 에서 해당 feature_id 가 마지막으로
    언급된 [YYYY-MM-DD] 또는 [YYYY-MM-DD HH:MM] 파싱 (신규 + 기존 형식 모두 지원)
  - 30일 초과 → BLOCK, 14~30일 → CONCERN, 7~14일 → INFO
  - 파싱 실패 시 INFO (날짜 없음 — 차단하지 않음)

- **`check_acceptance_criteria()` → LintResult`
  - 각 feature 의 `acceptance_criteria` 배열 검증:
    - 배열 자체 부재 → BLOCK
    - 항목 < 2개 → CONCERN
    - 모호 키워드 ("구현", "잘 동작", "적절히" 등) 만 포함 → CONCERN
    - 단일 항목인데 "TODO" 포함 → INFO

**Step 1.5 — `cmd_check()` 핸들러 + 출력 양식**
- `--category` 미지정 시 6 카테고리 전체 (세션 1 에서는 3 카테고리만 실행)
- `--format=human` (기본):
  ```
  # /project:lint check

  ## LINT-FL: feature_list 정합성 (PASS)
  | # | feature | label | message |
  ...

  ## 결론
  - BLOCK: N건
  - CONCERN: N건
  - INFO: N건
  - 액션: BLOCK 처리 후 lint 재실행 권장
  ```
- `--format=json`: `{"results": [LintResult, ...], "summary": {...}}`

**Step 1.6 — `commands/lint.md` 작성**
- 다른 commands/*.md 와 동일 구조
- 사용법, 실행, 출력 예시
- 본문에서 `python3 .claude/bin/lint.py <subcmd>` 호출
- 옵셔널 보장 명시: "lint 를 호출하지 않으면 하네스 동작에 영향 없음"

**Step 1.7 — ADR-004 + lint.py + commands/lint.md 미러링**
- gstack 만 미러 (결정 5)
- `rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
    .claude/ src/harness_template/claude.gstack/harness/.claude/`
- ADR + design 파일 cp

**Step 1.8 — 세션 1 자체 검증**
- `python3 .claude/bin/lint.py check --category=feature_list` 실행 → F009 자신이
  status="todo" + passes=false 이므로 INFO 출력 기대
- `python3 .claude/bin/lint.py check --format=json | jq .` 실행 → JSON 파싱 가능 확인
- exit 0 확인

**Step 1.9 — 세션 1 핸드오프**
- `feature_list.json` F009 는 그대로 `in-progress` 유지 (세션 2 진행 표시)
- `/project:context-save "F009 세션 1 — lint.py 코어 + 검사기 3종 완료"`

#### 세션 2 — 검사기 3종 추가 + regenerate-index + CLAUDE.md 통합

**Step 2.1 — 검사기 3종 추가** (`LINT-ADR`, `LINT-LEARN`, `LINT-MIRROR`)

- **`check_adr_feature_linkage()` → LintResult**
  - `docs/adr/ADR-*.md` 디렉토리 스캔
  - 각 ADR 헤더의 `> Feature: F(\d+)` 정규식으로 feature_id 추출
  - 해당 feature 가 feature_list.json 에 존재하지 않으면 BLOCK
  - ADR 본문에서 참조한 파일 경로 (예: `.claude/bin/foo.py`) 추출 → 존재 안 함 → CONCERN
  - ADR-NNN 번호 gap 탐지 (예: 001, 002, 004 — 003 누락) → INFO

- **`check_learnings_contradictions()` → LintResult**
  - `.claude/state/learnings.jsonl` 라인별 파싱
  - 같은 `key` 인데 tombstone 없이 정반대 `insight` (예: "X 사용" + "X 금지") → BLOCK
  - 휴리스틱: insight 텍스트의 "금지|metadata|never" 패턴 vs "사용|use|always" 패턴 충돌
  - confidence 미설정 / source 미설정 → CONCERN
  - tombstone 비율 > 50% → INFO

- **`check_mirror_diff()` → LintResult**
  - `.claude/` 와 `src/harness_template/claude.gstack/harness/.claude/` 의 미러 대상 파일 diff
  - 제외: `__pycache__/`, `*.pyc`, `state/`
  - diff 발견 시 BLOCK + 파일 경로 + 사이즈 차이 보고
  - baseline (ⓐ) 의 Karpathy 4원칙 파일 누락 → CONCERN (예외 동기화 정책)
  - openai (ⓒ) diff → INFO (codex 어댑터 stub — 현재는 미동기화)
  - `difflib.unified_diff` 사용 가능 (stdlib)

**Step 2.2 — `cmd_regenerate_index()` 핸들러 + `docs/index.md` 생성 로직**
- 8 섹션 자동 생성 (ADR / design / features / agents / commands / skills / learnings 통계 / 메타)
- ADR 메타: 첫 줄 정규식 파싱 (`# ADR-(\d+): (.+)` + `> Feature: (F\d+)` + `## 상태\s*\n\s*`?(\w+)``)
- agents/commands/skills 메타: 파일명 + frontmatter `name:`, `description:` 파싱
- features: feature_list.json 그대로 표화
- learnings 통계: learnings.jsonl 의 type 별 카운트 + 최근 5건
- 메타: 4변형 동기화 상태 (LINT-MIRROR 결과 요약) + 다음 ADR 번호 + 다음 Feature 번호
- 헤더에 `<!-- 자동 생성 파일 — 직접 수정 금지 -->` 명시 + 마지막 갱신 ISO 타임스탬프

**Step 2.3 — `cmd_self()` 핸들러 (셀프 dry-run, F007/F008 일관)**
- Playwright 같은 외부 의존성 감지 dry-run 은 lint 에 없음 — 대신:
  - `feature_list.json` 로드 가능 확인
  - `docs/adr/` 디렉토리 스캔 가능 확인
  - `learnings.jsonl` 파싱 가능 확인
  - `claude.gstack/harness/` 디렉토리 존재 확인
  - 모두 try/except → 결과 양식대로 출력 → exit 0

**Step 2.4 — `cmd_report()` 핸들러 (마지막 실행 캐시)**
- 마지막 `check` 결과를 `.claude/state/lint-last.json` 에 캐싱
- `report` 호출 시 캐시 파일 읽어 요약 출력
- 캐시 부재 시 안내 + exit 0

**Step 2.5 — CLAUDE.md 업데이트**

- "빠른 시작" 섹션에 신규 블록 추가:
  ```
  ### 정합성 헬스체크 (Phase 5 업그레이드 — F009)

  /project:lint                                # 6 카테고리 정합성 검사
  /project:lint check --category=feature_list  # 특정 카테고리만
  /project:lint regenerate-index               # docs/index.md 갱신
  /project:lint self                           # 셀프 dry-run

  > lint 는 옵셔널 — 호출 안 하면 하네스 동작에 영향 없음 (hook-failure-tolerance).
  > 산출물 카탈로그: docs/index.md (regenerate-index 가 자동 생성).
  > CI gate 용도: --strict 옵션 시 BLOCK 발견 → exit 1.
  ```

- "에이전트 역할 분담" 표 아래에 박스 추가:
  ```
  > **lint vs design-review vs qa-browser 분리**:
  > - lint (F009): 거버넌스 (feature_list × passes, stale, ADR↔feature, learnings 모순, AC 누락, 미러 diff)
  > - design-review (F007): IA / A11Y / 일관성 (텍스트 정적 분석)
  > - qa-browser (F008): E2E 동작 검증 (Playwright 동적)
  > 호출 순서 권장: Reviewer → design-review → lint → qa-browser
  ```

- "상태 파일" 표에 `.claude/state/lint-last.json` 행 추가 (커밋 대상 X — gitignore)

- 디렉토리 트리에 `bin/lint.py`, `commands/lint.md`, `docs/index.md`, `docs/design/F009-...` 추가

- "lint 호출 기준" 박스 (design-review/qa-browser 호출 기준과 같은 형식)

- **"claude-progress.txt prefix 컨벤션" 신규 섹션** (결정 4 표 그대로):
  ```
  ## claude-progress.txt prefix 표준 (F009)

  신규 인계 항목부터 다음 형식 권장 (강제 X):

  ## [YYYY-MM-DD HH:MM] agent | feature_id 짧은 요약

  - 헤더 마커: ## (Markdown H2)
  - 날짜·시간: [YYYY-MM-DD HH:MM] (분 단위)
  - agent: planner / architect / developer / reviewer / qa / user (소문자 enum)
  - 구분자: | (pipe with spaces)
  - 제목: feature_id + 한 줄 요약

  > 기존 [YYYY-MM-DD] 형식도 계속 인정 — 마이그레이션 불필요.
  > lint 가 신규 형식을 권장하지만 강제하지 않음 (옵셔널 보장).
  ```

**Step 2.6 — `commands/handoff.md` 안내 추가**
- "lint 실행 권장" 한 줄 추가 (강제 X)
- 예: `> 인계 직전에 \`/project:lint check\` 1회 권장 — 정합성 헬스체크 (옵셔널).`

**Step 2.7 — `commands/ship.md` 카테고리 추가**
- feature_list.json / .claude/state/learnings.jsonl 변경 시 lint 제안 항목 추가
- F003 ship.md 의 design-review/qa-browser 카테고리 추가 패턴 일관

**Step 2.8 — `regenerate-index` 실행 + docs/index.md 생성**
- `python3 .claude/bin/lint.py regenerate-index` 호출
- 생성된 `docs/index.md` 확인
- 헤더의 마지막 갱신 타임스탬프 확인

**Step 2.9 — 최종 미러링 동기화**
- gstack 만 미러 (결정 5)
- `__pycache__` 제외 적용
- `diff -r .claude/ src/harness_template/claude.gstack/harness/.claude/` 로 누락 확인

**Step 2.10 — 자체 정합성 검증** (F009 자신을 lint 로 검사)
- `/project:lint check` → 모든 카테고리 실행 → 6 카테고리 결과 확인
- F009 가 status="in-progress" 일 때 LINT-FL 은 INFO (정상)
- ADR-004 ↔ F009 연결성 LINT-ADR 은 PASS 되어야 함
- learnings.jsonl 모순 없으면 LINT-LEARN PASS
- 미러 diff 없으면 LINT-MIRROR PASS

**Step 2.11 — 학습 누적**
- `learnings.jsonl` append:
  - **architecture**: "lint 는 거버넌스 도구 — design-review (IA/A11Y/CON) + qa-browser (E2E) 와 책임 영역 분리"
  - **pattern**: "LLM Wiki 가스트의 index.md/lint 패턴을 메타-하네스에 적용 — 자동 생성 카탈로그 + 6 카테고리 검사기 + log prefix 컨벤션"
  - **pitfall**: "log prefix 일괄 마이그레이션은 기존 인계 컨텍스트 손상 위험 — 신규 항목부터만 적용"

**Step 2.12 — 핸드오프**
- `feature_list.json` F009: `status: "in-progress" → "review"`
- Reviewer 에이전트 호출 → APPROVED → `status: "review" → "qa"`
- QA 에이전트 호출 → 본 도구를 활용하여 자체 검증 (메타) → `passes: true`
- `/project:context-save "F009 세션 2 — lint 6 검사기 + index.md + CLAUDE.md 통합 완료"`

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| **AC1** `/project:lint` + `.claude/bin/lint.py` 단일 Python (외부 의존성 0) | 세션 1 Step 1.2, 1.6 | lint.py 단일 파일, commands/lint.md, argparse + stdlib 만 |
| **AC2** 6 카테고리 검사 (LINT-FL/STALE/ADR/LEARN/AC/MIRROR) | 세션 1 Step 1.4 (3종) + 세션 2 Step 2.1 (3종) | 결정 2 의 카테고리 표 그대로. 라벨 BLOCK/CONCERN/INFO/PASS |
| **AC3** `docs/index.md` 자동 생성 (ADR+design+features+agents+commands+skills+learnings 통계) | 세션 2 Step 2.2, 2.8 | regenerate-index 핸들러, 8 섹션, 자동 생성 헤더 명시 |
| **AC4** `--regenerate-index` 서브커맨드 | 세션 2 Step 2.2 | argparse 서브커맨드 |
| **AC5** CLAUDE.md 호출 가이드 + claude-progress.txt prefix 컨벤션 | 세션 2 Step 2.5 | "빠른 시작" + "prefix 표준" 신규 섹션 |
| **AC6** 4변형 동기화 — codex 는 prompt 만 (실행 후속) | 결정 5, 세션 1 Step 1.7 + 세션 2 Step 2.9 | gstack 만 미러, baseline + openai 미동기화 명시 (codex 어댑터 실구현 후속) |
| **AC7** 호출 안 하면 영향 없음 (hook-failure-tolerance) | 결정 6, 모든 세션 | 자동 호출 트리거 0, 모든 핸들러 try/except → exit 0 |

### 테스트 방법

**방식 1 — 6 카테고리 일괄 실행 (즉시 가능)**

```
python3 .claude/bin/lint.py check

# 기대:
#   - 6 카테고리 모두 실행
#   - 마크다운 표 출력 (라벨 BLOCK/CONCERN/INFO/PASS)
#   - 결론 요약 (BLOCK N건, CONCERN N건, INFO N건)
#   - exit 0
```

**방식 2 — JSON 출력 (CI 파싱 검증)**

```
python3 .claude/bin/lint.py check --format=json | python3 -m json.tool

# 기대:
#   - 유효한 JSON 출력
#   - results 배열 + summary 객체
#   - exit 0
```

**방식 3 — `--strict` 모드 (CI gate)**

```
# (1) BLOCK 발견 시
python3 .claude/bin/lint.py check --strict
echo "exit code: $?"

# 기대:
#   - BLOCK 있으면 exit 1
#   - BLOCK 없으면 exit 0
```

**방식 4 — `regenerate-index` (docs/index.md 생성)**

```
python3 .claude/bin/lint.py regenerate-index
cat docs/index.md | head -50

# 기대:
#   - 자동 생성 헤더 (`<!-- 자동 생성 ... -->`)
#   - 8 섹션 (ADR / design / features / agents / commands / skills / learnings / 메타)
#   - 마지막 갱신 ISO 타임스탬프
#   - exit 0
```

**방식 5 — 셀프 dry-run**

```
python3 .claude/bin/lint.py self

# 기대:
#   - feature_list.json / docs/adr/ / learnings.jsonl / claude.gstack/ 접근 가능 확인
#   - 모두 try/except → 결과 양식대로 출력
#   - exit 0
```

**방식 6 — 카테고리 격리 실행**

```
python3 .claude/bin/lint.py check --category=feature_list
python3 .claude/bin/lint.py check --category=mirror
python3 .claude/bin/lint.py check --category=adr

# 기대:
#   - 해당 카테고리만 실행
#   - 다른 카테고리 결과 미포함
#   - exit 0
```

**방식 7 — 모순 학습 인위적 주입 → LINT-LEARN BLOCK 확인 (후속)**

```
# (옵션) /tmp/learnings-fake.jsonl 에 모순 학습 2건 주입
# lint.py 가 --learnings-path 옵션으로 외부 파일 수용 시 검증 (구현 재량)
```

**방식 8 — 옵셔널 보장 검증**

```
# (1) lint 한 번도 호출 안 한 상태에서 handoff 정상 동작 확인
/project:handoff
# 기대: lint 호출 안 했어도 정상 핸드오프

# (2) lint.py 자체를 삭제 후 다른 커맨드 정상 동작 확인
mv .claude/bin/lint.py /tmp/lint.py.bak
/project:status
# 기대: status 정상 출력 (lint 의존 없음)
# 복원: mv /tmp/lint.py.bak .claude/bin/lint.py
```

**모든 단계가 exit 0 으로 종료되는지** 확인 (Brain hook-failure-tolerance 원칙 일관).

### 피해야 할 패턴

- ❌ `lint_checkers/` 패키지 분리 (결정 1 — F005 단일 파일 패턴 일관)
- ❌ bash 스크립트로 구현 (결정 1 — F005~F008 Python 패턴 일관성 깨짐)
- ❌ 새 에이전트 `.claude/agents/linter.md` 신설 (F007/F008 일관)
- ❌ QA 에이전트 정의 변경 (제약 — qa.md 무수정)
- ❌ `passes: true` 권한 행사 (QA 에이전트 단독)
- ❌ `docs/index.md` 를 사람이 직접 편집 (결정 3 — LLM Wiki 패턴 위배)
- ❌ `INDEX.md` 루트 배치 (결정 3 — docs/ 일관)
- ❌ YAML frontmatter 일괄 강제 (결정 3 — 무회귀)
- ❌ claude-progress.txt 일괄 마이그레이션 (결정 4 — 인계 컨텍스트 손상 위험)
- ❌ handoff hook 에서 lint 자동 호출 (결정 6 — 옵셔널 보장 위배)
- ❌ BLOCK 시 항상 exit 1 (결정 6 — hook-failure-tolerance 위배)
- ❌ 외부 패키지 추가 (Pydantic·jsonschema·rich 등 — stdlib 만)
- ❌ baseline (`src/harness_template/claude/`) 수정 (결정 5 — 동결 정책)
- ❌ openai/ 수정 (결정 5 — codex stub 정책)
- ❌ `host.json`/`settings.json` 수정 (F006 격리)
- ❌ F007 design-review 의 IA-S/CON-S 와 LINT-MIRROR 검사 결과 중복 보고 (관점 차이로
  정당화되지만, 결과 양식에서 명시적으로 "design-review CON-S3 과 중첩 영역" 메모 권장)
- ❌ LLM Wiki 가스트의 sources/wiki/schema 3계층을 그대로 강제 도입 (메타-하네스에는
  sources 가 없음 — 결정 1 컨텍스트 참조)

---

## 부록 — 세션별 작업 분해 요약 표

| 세션 | 핵심 결과물 | 검증 기준 | 종료 조건 |
|---|---|---|---|
| **세션 1** | `.claude/bin/lint.py` (코어 + 검사기 3종) + `.claude/commands/lint.md` + (선택) `docs/design/F009-lint-checkers.md` + ADR-004 + gstack 미러 | `python3 .claude/bin/lint.py check --category=feature_list` 정상 출력 + `--format=json` 파싱 가능 + 모든 핸들러 exit 0 + `diff -r .claude/ src/harness_template/claude.gstack/harness/.claude/` 동기화 OK | F009 `status: "in-progress"` 유지, `/project:context-save` 체크포인트 |
| **세션 2** | 검사기 3종 추가 + `regenerate-index` + `docs/index.md` 생성 + CLAUDE.md 통합 + handoff/ship 안내 + 학습 jsonl + 최종 미러 | `python3 .claude/bin/lint.py check` 6 카테고리 전체 실행 + `regenerate-index` 후 `docs/index.md` 8 섹션 + CLAUDE.md 빠른 시작 lint 섹션 + prefix 컨벤션 섹션 + 자체 검증 (LINT-ADR PASS for ADR-004 ↔ F009) + 미러 diff 0 | F009 `status: "in-progress" → "review"`, Reviewer 호출 → QA 호출 → `passes: true`, `/project:context-save` 체크포인트 |

각 세션의 산출물은 **세션 종료 시 mergeable** 상태 (CLAUDE.md 코딩 규칙). 세션 1 만
머지된 상태에서도 `python3 .claude/bin/lint.py check --category=feature_list` 가 동작
가능하며 다른 카테고리는 "미구현 — 세션 2 에서 추가 예정" 안내 출력 + exit 0.

---

*작성: architect 에이전트 | 날짜: 2026-05-20 | 상태: Accepted*
