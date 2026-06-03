# ADR-007: LLM Wiki 지식 그래프 + `claude.gstack.auto.design.wiki` 변형 + 외부 의존성 정책 예외

> Feature: F012 — Phase 8 claude.gstack.auto.design.wiki 변형 (LLM Wiki 지식 그래프)
> 작성: architect 에이전트 | 날짜: 2026-06-03

## 상태

`Proposed` — 본 ADR 은 사용자가 AskUserQuestion 으로 확정한 3 가지 선결 결정
(그래프 의미 = 노드/엣지 지식 그래프 / 저장 기술 = Obsidian vault + `[[wikilink]]` /
의존성 = setup 스크립트 자동화) 위에 9 개 결정을 명시한다.
F005~F011 의 **단일 파일 헬퍼 + 서브커맨드 + 변형 미러 + 셀프 모드 + 옵셔널 +
hook-failure-tolerance** 패턴을 유지하되, **외부 의존성 0 정책에 변형별 예외**라는
새 카테고리를 도입한다 — 이는 본 ADR 의 핵심 정책 변화점이다.

---

## 컨텍스트

### F012 의 본질적 질문 — "지식 그래프는 어디서 시작되어 어디서 끝나는가"

Karpathy LLM Wiki 가스트 (`/tmp/gist_ww.txt`) 는 다음을 제안한다:

1. **Ingest**: 새 소스를 wiki 노드로 정리 (요약 + cross-reference + index 갱신)
2. **Query**: wiki 페이지 검색 + 합성 답변. 좋은 답은 신규 wiki 페이지로 되먹임
3. **Lint**: 모순 / stale / 고아 / 끊긴 cross-reference 점검
4. **Index + Log**: index.md (콘텐츠 카탈로그) + log.md (시간순 변경 로그)
5. **Obsidian** (UI), **qmd** (검색), **Marp** (슬라이드) 같은 외부 도구 옵션

F009 phase 에서는 **lint + index + log prefix 컨벤션만** 이식 (외부 의존성 0 유지).
F012 는 ingest + query + graph 까지 가스트의 정신 그대로 구현하되, **외부 도구 옵션을 처음
허용**한다 — 단, 변형별 격리.

### 사용자 사전 결정 (확정 — AskUserQuestion)

| 질문 | 결정 |
|---|---|
| 그래프 의미 | **지식 그래프** (노드 = feature/ADR/learning/wiki 페이지, 엣지 = 참조·의존성) |
| 저장 기술 | **Obsidian vault + `[[wikilink]]`** (LLM Wiki 가스트 원본 방식, graph view 시각화) |
| 의존성 설치 | **setup 스크립트 자동화** (`wiki-setup.sh`). 단 autonomous 규칙 #3-B 와 조율 필요 |

### 현재 5 변형 매트릭스 (F011 완료 후)

| 변형 | 정체성 | 자율 | 디자인 |
|---|---|---|---|
| ⓐ `claude/` (baseline) | Phase 0 동결 + Karpathy 4원칙 | ❌ | ❌ |
| ⓑ `claude.gstack/` (표준) | F001~F011 풀, 사용자 승인 | ❌ | ❌ |
| ⓑ′ `claude.gstack.auto/` (자율) | ⓑ + 자율 오버레이 | ✅ | ❌ |
| ⓑ″ `claude.gstack.auto.design/` (자율+디자인) | ⓑ′ + 디자인 오버레이 | ✅ | ✅ |
| ⓒ `openai/.codex/` (codex stub) | Karpathy 만 | ❌ | ❌ |

F012 추가:

| 변형 | 정체성 |
|---|---|
| **ⓑ‴ `claude.gstack.auto.design.wiki/` (자율+디자인+wiki)** | ⓑ″ + wiki 오버레이 (wiki.py / `/project:wiki` / Obsidian vault / wiki-setup.sh) + **외부 의존성 허용 — 정책 예외 변형 1호** |

### 제약 (F005~F011 일관 + 본 ADR 신설)

- **외부 의존성 0**: ⓐ/ⓑ/ⓑ′/ⓑ″/ⓒ 5 변형은 절대 유지 — 본 ADR 이전 정책 그대로
- **외부 의존성 허용**: ⓑ‴ wiki 변형만 — Obsidian / qmd / Marp 3 도구 한정 (결정 1)
- **graceful degrade 의무**: wiki 핵심 기능 (ingest, .md + wikilink 생성·읽기, mermaid 텍스트 그래프) 은
  stdlib 만으로 동작. 외부 도구는 검색·시각화 향상만 (결정 5)
- **무회귀**: F001~F011 의 동작 무수정 — `.claude/settings.json` / 기존 7 에이전트 / brain.py /
  host.py / lint.py / backup.py / qa_browser.py / design_pick.py 어떤 비트도 변경 안 함
- **`feature_list.json` `passes` 절대 미수정**: QA 단독 권한
- **`.claude/settings.json` 무수정**: Claude Code 공식 스키마 격리 (F006 ADR-001 결정 1)

---

## 결정

### 결정 1 — 외부 의존성 0 정책 예외 범위: **wiki 변형만 + 3 도구 한정 (Obsidian / qmd / Marp) + 격리 강제**

**채택**: 외부 의존성 0 정책의 변형별 격리. `claude.gstack.auto.design.wiki/` 만 정책 예외를
가지며, 허용 도구는 **Obsidian, qmd, Marp** 3 가지로 한정. 다른 5 변형은 절대 외부 의존성 X.
격리는 LINT-MR 검사기로 자동 강제 (결정 8).

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 외부 도구 완전 금지 (현 정책 유지) | F005~F011 일관성 100% | LLM Wiki 가스트의 graph view·BM25 검색 이식 불가 — F012 가치 50% 손실 | 기각 |
| **(B) wiki 변형만 정책 예외 + 3 도구 한정** | 5 변형 정책 보존, wiki 변형 사용자만 외부 도구 부담 감수, F005~F011 미러 패턴 100% 유지 | "외부 의존성 0" 슬로건이 변형별 분기 — 학습 비용 1 | **채택** |
| (C) 모든 변형에 외부 도구 옵션 허용 | wiki 패턴을 더 넓게 활용 가능 | F005~F011 의 핵심 가치 (외부 의존성 0) 가 무너짐, 다운스트림이 의도 없이 외부 도구 의존 | 기각 |
| (D) wiki 변형 + 모든 외부 도구 허용 (도구 한정 없음) | 사용자 자유 ↑ | "허용 도구 카탈로그" 가 무한 확장 → 검증 부담 ↑ + 정책 흐릿 | 기각 |

#### 허용 도구 카탈로그 (wiki 변형 한정)

| 도구 | 목적 | graceful degrade | 미설치 시 동작 |
|---|---|---|---|
| **Obsidian** | vault graph view 시각화 (사람 사용) | ✅ | wiki.py 가 mermaid 텍스트 그래프 출력 — 사람이 직접 읽음 |
| **qmd** | 로컬 BM25/vector 검색 (LLM tool / CLI) | ✅ | wiki.py query 가 stdlib grep 으로 fallback |
| **Marp** | wiki 페이지 → 슬라이드 변환 | ✅ | wiki.py 가 .md 그대로 제공 (Marp frontmatter 만 추가) — 사용자가 별도 변환 안 함 |

**근거**:

- **LLM Wiki 가스트 정신 충실**: 가스트가 명시한 도구 옵션 (Obsidian / qmd / Marp) 그대로. 임의
  확장 없음.
- **5 변형 정책 무손**: 외부 도구 부담을 원하지 않는 사용자는 ⓐ~ⓒ 변형 사용. wiki 변형 선택은
  "외부 도구 감수" 의 명시 동의.
- **F005~F011 미러 패턴 일관**: 변형별 오버레이 격리는 이미 자율 오버레이 (F006~F010) / 디자인
  오버레이 (F011) 로 검증된 패턴. wiki 오버레이가 세 번째.

#### coding-standards.md 문서화 형식

`.claude/rules/coding-standards.md` 의 "Simplicity First" 섹션 직후에 새 섹션 추가:

```markdown
## 외부 의존성 정책 (변형별)

| 변형 | 외부 의존성 | 허용 카탈로그 | 격리 강제 |
|---|---|---|---|
| `claude/` (baseline) | 0 | — | LINT-MR-7 |
| `claude.gstack/` | 0 | — | LINT-MR-7 |
| `claude.gstack.auto/` | 0 | — | LINT-MR-7 |
| `claude.gstack.auto.design/` | 0 | — | LINT-MR-7 |
| **`claude.gstack.auto.design.wiki/`** | **허용** | Obsidian / qmd / Marp | LINT-MR-7 (반대 방향 — 허용 확인) |
| `openai/.codex/` | 0 | — | LINT-MR-7 |

**계약**: wiki 변형을 가져가는 다운스트림은 외부 도구 설치를 감수한다 (자동 / 수동 무관).
graceful degrade 가 의무 (결정 5) — 도구 없이도 핵심 기능은 동작한다.
```

**영향받는 AC**: AC2 (외부 의존성 0 정책 예외 명시 — coding-standards.md 문서화)

---

### 결정 2 — Obsidian vault 디렉토리 위치 및 구조: **`wiki/` 프로젝트 루트 + 노드 타입별 하위 디렉토리**

**채택**: vault 는 프로젝트 루트의 `wiki/` 디렉토리에 위치. 노드 타입별 하위 디렉토리로 정리.
`.claude/wiki/` 가 아닌 이유는 LLM Wiki 가스트의 정신상 vault 가 **사람이 직접 보는 산출물**
이기 때문 (Obsidian 으로 열어서 graph view 확인) — 하네스 내부 도구가 아닌 프로젝트의 정식
지식 베이스로 자리매김.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) `.claude/wiki/` | 하네스 내부 정리 일관 (.claude/state/, .claude/design/ 패턴) | Obsidian 사용자가 `.claude/` 를 직접 열어야 함 — 하네스 도구 위치와 사람의 지식 베이스가 혼재 | 부적합 — 사람의 산출물 위치로 부자연 |
| **(B) 프로젝트 루트 `wiki/`** | Obsidian vault 자연스러운 위치, 사람이 직접 의식, LLM Wiki 가스트 가이드와 일관 (가스트는 vault 위치를 사용자 자유로 둠 — 일반적으로 루트), gitignore 부담 0 (.claude/state 와 달리 vault 는 git 추적 권장) | 프로젝트 루트에 새 디렉토리 1 개 — 다운스트림 README 영향 가능 | **채택** |
| (C) `docs/wiki/` | docs/ 하위라 정합 | docs/adr, docs/design 과 의미론적 분기 흐릿 — wiki 는 ADR / design 과 다른 카테고리 (시간 흐름 따라 자라는 지식 vs 결정 시점 동결 문서) | 부분 매력적이나 단점 우세 |

#### vault 디렉토리 구조

```
<project-root>/
└── wiki/                          # Obsidian vault 루트 — 사람이 직접 열어 graph view 확인
    ├── README.md                  # vault 소개 (사람용 — Obsidian 안에서 첫 페이지)
    ├── index.md                   # 콘텐츠 카탈로그 (LLM Wiki 가스트 — wiki 전용, F009 docs/index.md 와 분리)
    ├── log.md                     # 시간순 ingest/query/lint 로그 (F009 prefix 컨벤션 일관)
    ├── features/                  # feature_list.json → 노드
    │   ├── F001.md
    │   ├── F002.md
    │   └── ...
    ├── adrs/                      # docs/adr/*.md → 노드 (frontmatter + 본문 발췌)
    │   ├── ADR-001.md
    │   └── ...
    ├── learnings/                 # learnings.jsonl 엔트리 → 노드
    │   ├── 2026-04-12-architecture-mirror-pattern.md
    │   └── ...
    ├── pages/                     # 사용자가 LLM 과 함께 생성한 자유 wiki 페이지 (가스트 정신)
    │   ├── concept-knowledge-graph.md
    │   └── ...
    └── sources/                   # 외부 자료 ingest (Karpathy 가스트 같은 원본)
        ├── 2026-05-30-karpathy-llm-wiki-gist.md
        └── ...
```

#### 노드 ID 규칙

- 파일명 (확장자 제외) = 노드 ID
- features: feature_list.id 그대로 (`F001`)
- adrs: ADR-NNN (`ADR-001`)
- learnings: `YYYY-MM-DD-<category>-<slug>` (jsonl 의 ts + category + 본문 요약)
- pages: 자유 slug (`concept-knowledge-graph`)
- sources: `YYYY-MM-DD-<slug>` (ingest 시점 + 출처 slug)

#### frontmatter 스키마 (모든 노드 공통)

```yaml
---
type: feature | adr | learning | page | source
created: 2026-06-03T14:30:00+09:00
source_ref: feature_list.json#F012      # 원본 위치 (Obsidian 외부 SSoT)
tags: [phase-8, wiki, knowledge-graph]
related: [F009, F011, ADR-007]          # 엣지 명시 (frontmatter 1 차 표현)
status: draft | active | stale          # 자동 lint 대상
---
```

#### 엣지 표현 — 이중 표현 (frontmatter `related` + 본문 `[[wikilink]]`)

| 표현 | 장점 | 단점 | 용도 |
|---|---|---|---|
| frontmatter `related: [A, B, C]` | 결정론적 (lint 파싱 용이), Obsidian Dataview 쿼리 가능 | Obsidian graph view 에는 본문 wikilink 만 표시 (frontmatter 는 부분 지원) | 정형 엣지 (feature dependency, ADR 참조) |
| 본문 `[[wikilink]]` | Obsidian graph view 표시, 자연 텍스트 흐름 안에서 인용 | 정규식 파싱 (덜 결정론적) | 자유 형식 본문 인용 |

**채택**: **둘 다 사용**. frontmatter `related` 는 결정론적 엣지 (ingest 자동 생성),
본문 `[[wikilink]]` 는 사용자 / LLM 이 자유롭게 본문에 인용. lint 가 둘 다 점검.

#### F009 docs/index.md 와의 분리

| 도구 | index.md 위치 | 카탈로그 대상 |
|---|---|---|
| F009 lint.py `regenerate-index` | `docs/index.md` (프로젝트 루트) | ADR + design + features + agents + commands + skills (전체 산출물 카탈로그) |
| F012 wiki.py `lint` 또는 `ingest --rebuild-index` | `wiki/index.md` (vault 루트) | wiki 노드 (features/adrs/learnings/pages/sources) 만 — vault 내부 카탈로그 |

→ 두 index 는 **물리적으로 다른 파일** + **목적이 다름**. 충돌 없음.

**영향받는 AC**: AC3 (Obsidian vault 구조)

---

### 결정 3 — 산출물 → 지식 그래프 변환 (ingest): **결정론적 매핑 + 선택적 LLM 보강**

**채택**: ingest 의 90% 는 **결정론적 매핑** (feature_list.json / docs/adr/*.md / learnings.jsonl
파싱 → frontmatter + 본문 자동 생성). LLM 호출은 **본문 요약·연관 노드 추천 보강 단계에서만**
선택적 (사용자 명시 `--enrich-llm` 시).

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 100% 결정론적 (LLM 호출 0) | 재현성 100%, 토큰 비용 0, F005~F011 패턴 일관 (design_pick.py apply 도 결정론) | 본문 요약·합성 품질 낮음 (단순 truncate) | 부분 매력적 |
| **(B) 결정론적 매핑 + 선택적 LLM 보강** | 기본은 결정론 (재현성 보장), LLM 보강은 옵트인 (사용자 결정), F011 패턴 일관 (design_pick recommend = LLM 옵션) | 두 모드 학습 비용 1 — 사용자 매뉴얼 명시 필요 | **채택** |
| (C) 100% LLM 호출 | 본문 품질 높음 | 토큰 비용 ↑, 재현성 ↓, F005~F011 일관성 ↓ | 기각 |

#### ingest 대상 + 결정론적 매핑 규칙

| 소스 | 변환 규칙 | 엣지 자동 생성 |
|---|---|---|
| `feature_list.json` 각 항목 | `wiki/features/F<ID>.md` — frontmatter 채움 + 본문 = `description` + `acceptance_criteria` 표 + `dependencies` 본문 인용 | `related: [F<dep>, ADR-<관련>]` (dependencies + ADR 자동 감지) |
| `docs/adr/ADR-NNN-*.md` | `wiki/adrs/ADR-NNN.md` — frontmatter 채움 + 본문 = "결정" 섹션 + "결과" 섹션 발췌 | `related: [F<원본 feature>, F<후속 feature>]` (ADR 헤더의 "Feature:" 라인 파싱) |
| `learnings.jsonl` 각 엔트리 | `wiki/learnings/<ts>-<category>-<slug>.md` — frontmatter (category, tags) + 본문 = jsonl note 필드 | `related: [F<관련 feature 가 note 에서 언급된 경우>]` (정규식 `F\d{3}` grep) |
| 외부 `.md` 파일 (사용자 지정) | `wiki/sources/<ts>-<slug>.md` — 원본 그대로 + frontmatter `source_ref` = 원본 경로 | (사용자가 본문에 `[[wikilink]]` 직접 작성) |

#### 옵션 LLM 보강 (`--enrich-llm`)

- ingest 후 신규 노드에 대해 **연관 노드 추천** (graph 연결 강화)
- 본문 요약 품질 개선 (단순 발췌 → 자연어 요약)
- 호출 안 함이 기본 — 토큰 비용 회피
- 모드 활성 시 designer 에이전트 패턴 (F011) 일관 — wiki.py 가 LLM 위임 프롬프트만 출력,
  실제 호출은 Claude Code 가 Task 도구로 수행

#### LLM-driven vs 결정론 분리 (F011 패턴 일관)

| 단계 | 도구 | 결정론 / LLM |
|---|---|---|
| ingest (산출물 → 노드) | wiki.py ingest | 결정론 (90%) |
| query (검색) | wiki.py query | 결정론 (grep) + 선택적 LLM 합성 |
| lint (점검) | wiki.py lint | 결정론 100% |
| graph (출력) | wiki.py graph | 결정론 100% |
| **보강** | LLM (Task 위임) | 선택적 (사용자 옵트인) |

→ F011 의 design_pick.py (결정론) + designer 에이전트 (LLM) 분리 패턴 100% 일관.

**영향받는 AC**: AC3 (지식 그래프 변환), AC4 (wiki.py ingest)

---

### 결정 4 — `wiki.py` 헬퍼 서브커맨드 구조: **5 서브커맨드 (ingest / query / lint / graph / self)**

**채택**: F005 brain · F009 lint · F010 backup · F011 design_pick 의 verb-based 서브커맨드 패턴
100% 일관. 사용자가 옵션 3 (자동 추출) F011 후속 phase 와 분리한 것과 같은 정신으로,
F012 도 가스트의 4 핵심 동작 (ingest/query/lint/graph) + 셀프 dry-run 만 우선 구현.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 단일 명령 (인자로 모든 분기) | 진입점 단순 | F005~F011 패턴 위배, 도움말 비대 | 기각 |
| **(B) 5 서브커맨드 (ingest/query/lint/graph/self)** | F005~F011 100% 일관, 각 책임 명확, 셀프 dry-run 도구 일관성 | 본 phase 산출물 5 개 — 적정 | **채택** |
| (C) 더 많은 서브커맨드 (ingest/query/lint/graph/self/log/index/marp/...) | 가스트의 모든 옵션 노출 | F012 phase 부담 ↑, log·index 는 ingest 의 부수 효과로 충분 | 과도 — 후속 phase 분리 |

#### 서브커맨드 정의

| 서브커맨드 | 동작 | 옵션 |
|---|---|---|
| `ingest [source]` | 산출물 (feature_list / ADR / learnings) 또는 외부 .md 를 vault 노드로 변환. `source` 미지정 시 모든 산출물 일괄 ingest | `--source=feature\|adr\|learning\|all`, `--source-file=<path>`, `--enrich-llm`, `--rebuild-index` |
| `query <검색어>` | vault 검색. qmd 있으면 qmd, 없으면 stdlib grep (graceful degrade) | `--limit=<N>`, `--type=feature\|adr\|...`, `--format=human\|json` |
| `lint` | vault 정합성 점검 (고아 / stale / 끊긴 wikilink / frontmatter 누락) | `--strict`, `--format=human\|json` |
| `graph [출력형식]` | vault 그래프를 mermaid (기본) 또는 DOT 텍스트로 출력 | `--format=mermaid\|dot\|json`, `--node-type=<filter>` |
| `self` | 셀프 dry-run (vault 디렉토리 / 외부 도구 감지 / graceful degrade 상태) | (없음) |

#### 전역 옵션

| 옵션 | 의미 | 기본값 |
|---|---|---|
| `--vault=<path>` | vault 위치 override (테스트용) | `<project-root>/wiki/` |
| `--strict` | 오류 시 exit 1 (CI gate, F009 일관) | OFF (exit 0) |
| `--format=human\|json` | 출력 형식 (F009 lint / F011 design_pick 일관) | human |

#### 호출 예시

```
/project:wiki ingest                         # 모든 산출물 일괄 ingest + index 갱신
/project:wiki ingest --source=adr            # ADR 만 ingest
/project:wiki ingest --source-file=/tmp/article.md  # 외부 .md 를 source 노드로
/project:wiki ingest --enrich-llm            # LLM 보강 모드 (옵트인)
/project:wiki query "지식 그래프"             # vault 검색 (qmd 있으면 BM25, 없으면 grep)
/project:wiki lint                            # vault 정합성 점검
/project:wiki graph --format=mermaid          # mermaid 텍스트 그래프 출력
/project:wiki self                            # 셀프 dry-run (외부 도구 감지)
```

#### wiki.py 헤더 docstring (F005~F011 일관)

```python
"""wiki.py — LLM Wiki 지식 그래프 헬퍼 (F012).

claude.gstack.auto.design.wiki 변형 전용. 프로젝트 산출물 (feature/ADR/learning)
을 Obsidian vault + [[wikilink]] 지식 그래프로 변환·관리한다.

서브커맨드:
- ingest: 산출물 → vault 노드 (결정론적 매핑 + 옵션 LLM 보강)
- query: vault 검색 (qmd / stdlib grep 자동 분기)
- lint: vault 정합성 점검 (고아 / stale / 끊긴 wikilink / frontmatter)
- graph: vault 그래프 mermaid/DOT 텍스트 출력
- self: 셀프 dry-run (외부 도구 감지 + graceful degrade 상태)

외부 의존성 0 정책 예외:
- 핵심 기능 (ingest/lint/graph + query stdlib fallback) 은 Python stdlib 만
- 외부 도구 (Obsidian / qmd / Marp) 는 검색·시각화 향상용 (graceful degrade — 결정 5)
"""
```

**영향받는 AC**: AC4 (wiki.py 헬퍼 서브커맨드)

---

### 결정 5 — graceful degrade 전략: **핵심 기능 = stdlib / 외부 도구 = 향상만 / 자동 감지 + 명시 안내**

**채택**: wiki 변형 사용자는 외부 도구 설치를 감수하지만, **설치 안 해도 핵심 기능은 동작**해야
한다. 외부 도구는 검색 (qmd) · 시각화 (Obsidian graph view) · 슬라이드 (Marp) 향상만. wiki.py
는 도구 자동 감지 + 명시 안내 출력.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 외부 도구 필수 (없으면 exit 1) | 가스트 경험 100% 보장 | 가스트 정신 "옵셔널·모듈러" 위배, hook-failure-tolerance 정책 위배 | 기각 |
| **(B) 핵심 기능 = stdlib / 외부 도구 = 향상** | F005~F011 hook-failure-tolerance 정신 100% 일관, "wiki 변형 가져가도 외부 도구 설치 전엔 부분 동작" 보장 | 사용자 매뉴얼 명시 부담 — 어떤 기능이 어떤 도구에 의존하는지 | **채택** |
| (C) 모든 기능이 stdlib + 외부 도구 무의미 | 정책 단순 | 외부 도구 허용 의미 0 — wiki 변형 신설 의미 손실 | 기각 |

#### 도구별 분기 매트릭스

| 기능 | stdlib only | 외부 도구 향상 |
|---|---|---|
| **노드 생성** (ingest) | ✅ (.md + frontmatter + wikilink — Python stdlib) | (없음 — stdlib 충분) |
| **노드 읽기** | ✅ (Read tool) | Obsidian (사람이 graph view 와 함께) |
| **검색** (query) | ✅ (grep -r — re 모듈 + os.walk) | qmd (BM25 + vector + LLM rerank) |
| **그래프** (graph) | ✅ (mermaid / DOT 텍스트 — wikilink 정규식 파싱) | Obsidian graph view (텍스트 → 시각화) |
| **lint** | ✅ (정규식 + frontmatter 파싱) | (없음 — stdlib 충분) |
| **슬라이드** | (Marp frontmatter 추가만 — stdlib 텍스트 처리) | Marp CLI / Obsidian Marp 플러그인 (텍스트 → PDF/PPTX) |

#### 외부 도구 자동 감지 코드 흐름

```python
# wiki.py 내부
def detect_external_tools() -> dict:
    """외부 도구 설치 여부 자동 감지.

    Returns:
        dict: {tool: bool} — True 면 사용 가능, False 면 fallback 사용
    """
    tools = {
        "qmd": shutil.which("qmd") is not None,
        "obsidian": _detect_obsidian_vault(),  # vault 안에 .obsidian/ 폴더 존재 여부
        "marp": shutil.which("marp") is not None,
    }
    return tools

def cmd_query(args) -> int:
    tools = detect_external_tools()
    if tools["qmd"]:
        return _query_via_qmd(args)        # BM25/vector 검색
    else:
        return _query_via_grep(args)       # stdlib grep fallback

def cmd_self(args) -> int:
    """셀프 dry-run — 외부 도구 감지 + graceful degrade 상태 안내."""
    tools = detect_external_tools()
    print("🔍 wiki 변형 환경 점검:")
    for tool, present in tools.items():
        status = "✅ 사용 가능" if present else "ℹ️ 미설치 — stdlib fallback 활성"
        print(f"   - {tool}: {status}")
    if not all(tools.values()):
        print("")
        print("외부 도구 설치 (선택): bash .claude/bin/wiki-setup.sh")
    return 0
```

**근거**:

- **LLM Wiki 가스트 명시**: "Everything mentioned above is optional and modular — pick what's
  useful, ignore what isn't." — graceful degrade 가 가스트 정신 그 자체.
- **F005~F011 hook-failure-tolerance 정책 일관**: 호출 실패 → exit 0 + 친절 안내. wiki 도 같은 정신.
- **다운스트림 진입 장벽 ↓**: wiki 변형 가져간 사용자가 즉시 ingest/lint/graph 사용 가능 →
  외부 도구는 점진적 도입.

**영향받는 AC**: AC7 (graceful degrade)

---

### 결정 6 — `wiki-setup.sh` + autonomous 규칙 #3-B 조율: **B. 최초 1 회 사용자 승인 후 자동 설치 — autonomous ESCALATE 흐름 활용**

**채택**: `wiki-setup.sh` 는 외부 도구 설치 명령을 **실제로 실행한다**. 단, 자율 모드의
pre-bash-auto-boundary-check.sh 가 외부 패키지 fetch 패턴 (예: `pip install`, `npm install -g`,
`brew install`, `cargo install`) 을 감지 → **사용자에게 ESCALATE** → 사용자가 1 회 명시 승인 시
해당 세션 내에서 자동 설치 진행. 승인 거부 / 비대화 환경 / 설치 실패 시 **graceful degrade** —
안내 메시지 출력 + stdlib only 모드로 동작 (결정 5 안전망).

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) wiki 변형의 boundary 훅에 예외 추가 — wiki-setup.sh 실행 시 ESCALATE 안 함 | 사용자 1 회 클릭 ↓ | autonomous 정신 위배 (외부 패키지 fetch 는 본질적으로 외부 부수 효과), 훅 분기 학습 비용 ↑, 보안 약화 | 기각 |
| **(B) 최초 1 회 사용자 승인 후 자동 설치 — setup 은 항상 ESCALATE, 1 회 승인 시 그 세션 자동 진행** | 자동화 의도 (사용자가 setup 자동화를 원함) + 자율 모드 규칙 #3-B 보존 (ESCALATE 트리거 정상 작동) + 보안 (사용자 명시 승인) + graceful degrade 안전망 (승인 거부 시 stdlib only) 모두 만족 | 사용자 1 회 승인 UX 부담 — 단 어떤 패키지를·왜 설치하는지 명확히 안내하면 학습 비용 미미 | **채택** |
| (C) setup 은 안내만 — 자동 설치 X, 사용자가 수동 실행 | 자율 모드 정책 무변경 | 사용자가 명령 복사·실행 수동 부담 — "자동화" 의도와 어긋남 | 기각 (자동화 의도 우선) |

#### `wiki-setup.sh` 동작 (자동 설치 — autonomous ESCALATE 활용)

```bash
#!/usr/bin/env bash
# wiki-setup.sh — wiki 변형 외부 도구 자동 설치 (autonomous ESCALATE 활용)
#
# 자율 모드의 pre-bash-auto-boundary-check.sh 가 외부 패키지 fetch 패턴을 감지하면
# 사용자에게 ESCALATE → 1 회 승인 시 그 세션 안에서 자동 설치 진행.
# 승인 거부 / 비대화 환경 / 설치 실패 시 → 안내 출력 + graceful degrade (stdlib only).

set -u

echo "🌐 LLM Wiki 외부 도구 자동 설치"
echo ""
echo "wiki 변형은 외부 의존성 0 정책의 예외입니다."
echo "다음 3 도구를 설치하려고 합니다 — autonomous 모드에서는 각 설치 명령마다"
echo "사용자 승인 (ESCALATE) 이 필요합니다. 승인 거부 또는 설치 실패 시 graceful"
echo "degrade — wiki.py 핵심 기능 (ingest/lint/graph + grep 검색) 은 그대로 동작."
echo ""
echo "════════════════════════════════════════════════════════════"
echo "설치 대상 + 사유:"
echo ""
echo "1. qmd (로컬 BM25 검색) — wiki query 향상"
echo "   사유: vault 검색의 grep fallback 을 BM25/vector 검색으로 업그레이드"
echo "   명령: cargo install qmd   (또는 brew install qmd — 환경에 따라)"
echo ""
echo "2. Obsidian — vault GUI + graph view (사람 사용)"
echo "   사유: wiki 노드 연결을 시각적으로 탐색 (CLI 그래프는 mermaid 텍스트)"
echo "   명령: (OS 별 GUI 설치 — 자동 설치 어려움, 안내만 출력)"
echo "   참고: https://obsidian.md/download"
echo ""
echo "3. Marp CLI — .md → 슬라이드 변환"
echo "   사유: wiki 페이지를 발표 자료로 export"
echo "   명령: npm install -g @marp-team/marp-cli"
echo "════════════════════════════════════════════════════════════"
echo ""

# --- 자동 설치 시도 (autonomous 훅이 각 명령마다 ESCALATE) ---

install_qmd() {
    if command -v qmd >/dev/null 2>&1; then
        echo "✅ qmd: 이미 설치됨"
        return 0
    fi
    echo ""
    echo "▶ qmd 설치 시도 (autonomous 모드에서 사용자 승인 필요)"
    if command -v cargo >/dev/null 2>&1; then
        cargo install qmd && echo "✅ qmd 설치 성공" || echo "⚠️  qmd 설치 실패 — grep fallback 사용"
    elif command -v brew >/dev/null 2>&1; then
        brew install qmd && echo "✅ qmd 설치 성공" || echo "⚠️  qmd 설치 실패 — grep fallback 사용"
    else
        echo "ℹ️  cargo / brew 없음 — qmd 자동 설치 스킵 (수동 설치: https://github.com/tobi/qmd)"
    fi
}

install_marp() {
    if command -v marp >/dev/null 2>&1; then
        echo "✅ marp: 이미 설치됨"
        return 0
    fi
    echo ""
    echo "▶ Marp CLI 설치 시도 (autonomous 모드에서 사용자 승인 필요)"
    if command -v npm >/dev/null 2>&1; then
        npm install -g @marp-team/marp-cli && echo "✅ marp 설치 성공" \
            || echo "⚠️  marp 설치 실패 — .md 직접 사용"
    else
        echo "ℹ️  npm 없음 — Marp 자동 설치 스킵"
    fi
}

note_obsidian() {
    echo ""
    echo "▶ Obsidian (GUI) — CLI 자동 설치 어려움"
    echo "   다운로드: https://obsidian.md/download"
    echo "   vault 열기: 프로젝트 루트의 wiki/ 디렉토리를 vault 로 지정"
}

install_qmd
install_marp
note_obsidian

echo ""
echo "════════════════════════════════════════════════════════════"
echo "다음 단계:"
echo "  python3 .claude/bin/wiki.py self     # 설치 결과 감지"
echo ""
echo "승인 거부 / 설치 실패는 정상 — graceful degrade 로 핵심 기능 동작."
exit 0
```

**autonomous 흐름과의 상호작용**:

| 단계 | 동작 | 책임 |
|---|---|---|
| 1. 사용자가 `bash .claude/bin/wiki-setup.sh` 실행 | wiki-setup.sh 진입 — 안내 출력 | wiki-setup.sh |
| 2. wiki-setup.sh 내부 `cargo install qmd` 호출 | pre-bash-auto-boundary-check.sh 가 외부 fetch 패턴 (`cargo install`, `npm install -g`, `brew install`, `pip install`) 감지 → **ESCALATE** | autonomous 훅 |
| 3. 사용자에게 명확한 승인 요청 메시지 | "다음 명령을 실행하시겠습니까? — `cargo install qmd` (사유: vault 검색 BM25 업그레이드)" | autonomous 훅 + wiki-setup.sh 의 echo |
| 4-A. 사용자 승인 | 그 세션 내에서 설치 진행 | autonomous 훅 |
| 4-B. 사용자 거부 / 비대화 환경 | 설치 명령 실패 → wiki-setup.sh 의 `|| echo "⚠️ 실패"` 로 흡수 → 다음 도구로 진행 | wiki-setup.sh graceful |
| 5. 다음 도구 (marp) 도 동일 ESCALATE → 사용자 승인 / 거부 | (4-A / 4-B 반복) | autonomous 훅 |
| 6. setup 종료 | `wiki.py self` 로 결과 확인 권장 | 사용자 |

**근거**:

- **자동화 의도 충족**: 사용자가 "setup 자동화" 를 명시 선택 — wiki-setup.sh 가 실제 설치 명령을
  실행한다. 명령 복사·붙여넣기 부담 제거.
- **autonomous 규칙 #3-B 유지**: pre-bash-auto-boundary-check.sh 의 외부 fetch ESCATATE 정책은
  **변경하지 않는다**. wiki-setup.sh 가 setup 의 책임 (어떤 패키지를·왜) 을 명확히 출력하고,
  실제 설치 명령은 autonomous 훅이 정상적으로 가로채 사용자 승인을 받는다 — **보안 + 자동화 동시 달성**.
- **사용자 1 회 명시 승인**: ESCALATE 가 발생할 때마다 사용자가 어떤 패키지를·왜·어떤 명령으로
  설치하는지 확인하고 승인. 신설 캐시 / 영구 승인 저장 없음 — 세션마다 명시 승인 (보안 ↑).
- **graceful degrade 안전망 (결정 5 와 일관)**: 승인 거부 / 비대화 환경 / 설치 실패 시 wiki-setup.sh
  의 `|| echo "⚠️ 실패"` 패턴이 흡수 → wiki.py 가 외부 도구 부재를 자동 감지 → stdlib fallback 동작.
  사용자가 setup 안 해도, setup 실행 후 모두 거부해도, 일부만 승인해도 — 모든 경우에 wiki 핵심
  기능 (ingest / lint / graph / grep query) 동작.
- **F011 design_pick `recommend` 패턴 일관**: design_pick.py 의 recommend 도 사용자에게 위임 안내를
  명확히 출력. wiki-setup.sh 도 같은 정신 — "어떤 동작을·왜" 가 명확.
- **결정 6 ↔ 결정 5 관계**: graceful degrade 는 "승인 거부 시 fallback" 으로 본 결정의 안전망 역할.
  두 결정은 모순되지 않으며, 결정 5 가 결정 6 의 자동 설치 흐름 어떤 단계에서 실패해도 wiki 가
  동작하도록 보장.

**영향받는 AC**: AC6 (wiki-setup.sh + autonomous #3-B 조율 — 자동 설치 + ESCALATE + graceful degrade)

---

### 결정 7 — F009 lint vs wiki lint 책임 분리: **wiki.py 독립 lint — F009 lint.py 와 분리**

**채택**: F009 `lint.py` 는 거버넌스 정합성 (feature_list / ADR / learnings 모순 / 미러 정합).
F012 `wiki.py lint` 는 vault 정합성 (고아 노드 / 끊긴 wikilink / stale 페이지 / frontmatter
누락). 두 lint 의 경계 명확히 분리, wiki 변형만 vault lint 책임.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) wiki lint 를 F009 lint.py 에 통합 (LINT-WIKI 신설) | 호출 진입점 통일 (`/project:lint`), F009 패턴 일관 | F009 lint.py 가 모든 변형에 미러됨 — wiki 변형 없는 변형에선 LINT-WIKI 가 N/A (코드 복잡도 ↑), wiki 의존성 (frontmatter / wikilink 파싱) 이 F009 lint.py 본체에 침투 | 부분 매력적이나 단점 우세 |
| **(B) wiki.py 독립 lint** | 책임 분리 명확, wiki 변형 전용 lint 가 wiki 변형에만 존재 (다른 변형 lint.py 는 무변경), F011 design_pick.py self 패턴 일관 | 호출 진입점 2 개 (`/project:lint` + `/project:wiki lint`) — 학습 비용 1 | **채택** |
| (C) wiki lint 를 design-review 의 새 카테고리로 통합 | design-review 와 일관 | design-review 는 IA/A11Y/일관성 (시각·문서 정합), wiki 정합성과 의미론 다름 | 기각 |

#### 책임 매트릭스 (F009 lint vs F012 wiki lint vs design-review)

| 도구 | 책임 | 검사 카테고리 |
|---|---|---|
| F009 `lint.py` | **거버넌스** | LINT-FL (feature_list 정합) / LINT-STALE / LINT-AC / LINT-ADR / LINT-LEARN / LINT-MIRROR / LINT-MR (변형 미러) |
| F012 `wiki.py lint` | **vault 정합** | WIKI-ORPHAN (고아 노드) / WIKI-DEAD-LINK (끊긴 wikilink) / WIKI-STALE (오래된 페이지) / WIKI-FRONTMATTER (frontmatter 누락) |
| F007 `design-review` | **디자인 정합** | IA / A11Y / CON / D. TOKEN (F011) |

→ 책임 3 분립. wiki lint 가 거버넌스 lint 에 침투하지 않음.

#### `wiki.py lint` 검사 항목 (4 개 — 우선순위)

| # | 항목 | 검사 방법 | BLOCK / CONCERN / PASS |
|---|---|---|---|
| WIKI-ORPHAN | 고아 노드 (다른 노드에서 참조 0) | 모든 노드 파일을 순회 → `[[wikilink]]` + frontmatter `related` 그래프 구성 → in-degree 0 노드 추출 | CONCERN (BLOCK 아님 — 신규 노드는 일시적 고아 정상) |
| WIKI-DEAD-LINK | 끊긴 wikilink | 본문 `[[X]]` 추출 → X.md 파일 존재 여부 확인 | BLOCK (끊긴 링크는 오류) |
| WIKI-STALE | stale 페이지 (frontmatter `status: stale` 또는 90 일 이상 미수정 + source 변경) | frontmatter `status` 직접 검사 + git log 로 vault 외부 source 의 최근 변경 시각 비교 | CONCERN |
| WIKI-FRONTMATTER | frontmatter 누락·필수 필드 부재 | YAML 파싱 → `type` / `created` 필수 필드 확인 | BLOCK |

**근거**:

- **F011 design_pick.py self 패턴 일관**: design_pick self 가 design-review 와 별도로 디자인 자료
  정합성 점검. wiki lint 도 같은 정신 — 변형 전용 헬퍼가 자체 정합성 책임.
- **wiki 변형 자기 격리**: wiki 의존성 (frontmatter / wikilink 파싱) 이 F009 lint.py (모든 변형에 미러)
  에 침투하지 않음.
- **호출 학습 비용 1 미미**: `/project:wiki lint` 는 wiki 변형 사용자만 호출. 다른 변형 사용자는
  `/project:lint` 만 사용 — 분기 명확.

**영향받는 AC**: AC4 (wiki.py lint 서브커맨드)

---

### 결정 8 — LINT-MR 6 변형 확장: **MR-1 ~ MR-5 기존 유지 + MR-6 (wiki 오버레이 ⓑ‴ 한정 존재) + MR-7 (외부 의존성 허용 ⓑ‴ 한정)**

**채택**: F011 LINT-MR 의 MR-1 ~ MR-5 는 변형 매트릭스 확장 (5 → 6) 에 맞춰 검사 대상에
`claude.gstack.auto.design.wiki` 추가. **MR-6 (wiki 오버레이 부재/존재)** + **MR-7 (외부
의존성 격리)** 2 항목을 신설.

#### LINT-MR 항목 전체 (F011 의 5 → F012 의 7)

| # | 항목 | 검사 방법 | BLOCK / CONCERN |
|---|---|---|---|
| MR-1 | (F011) ⓑ 표준 변형에 자율 오버레이 부재 | (변경 없음) | (변경 없음) |
| MR-2 | (F011) ⓑ 표준 변형의 settings.json Bash(*) 미사용 | (변경 없음) | (변경 없음) |
| MR-3 | (F011) ⓑ 표준 변형의 CLAUDE.md Autonomous Mode 헤딩 부재 | (변경 없음) | (변경 없음) |
| MR-4 | (F011) ⓐ/ⓑ/ⓑ′ 변형에 디자인 오버레이 부재 | **검사 대상 변경**: ⓐ/ⓑ/ⓑ′ 3 변형 (ⓑ″ 와 ⓑ‴ 는 디자인 오버레이 보유) | (BLOCK 동일) |
| MR-5 | (F011) ⓑ″ 디자인 변형에 디자인 오버레이 모두 존재 | **검사 대상 추가**: ⓑ″ + ⓑ‴ (둘 다 디자인 오버레이 필수 — wiki 변형은 design 변형의 1:1 복사이므로) | (CONCERN 동일) |
| **MR-6** | **ⓐ/ⓑ/ⓑ′/ⓑ″ 4 변형에 wiki 오버레이 부재** | `wiki.py`, `wiki.md` (커맨드), `wiki-setup.sh`, `wiki/` 디렉토리 존재 여부 — 4 변형에 있으면 BLOCK | BLOCK |
| **MR-7** | **외부 의존성 격리 (wiki 변형만 허용)** | 5 변형 (ⓐ/ⓑ/ⓑ′/ⓑ″/ⓒ) 에 `wiki-setup.sh` / `requirements.txt` / `package.json` 같은 외부 도구 매니페스트 부재. wiki 변형 (ⓑ‴) 에는 `wiki-setup.sh` 존재 (graceful degrade 매뉴얼) | BLOCK (5 변형) + CONCERN (wiki 변형에 누락 시) |

#### lint.py 변경 범위 (추가만)

```python
# .claude/bin/lint.py — F012 추가 상수
_WIKI_OVERLAY_FILES = [
    "harness/.claude/bin/wiki.py",
    "harness/.claude/commands/wiki.md",
    "harness/.claude/bin/wiki-setup.sh",
]
_WIKI_OVERLAY_DIRS = [
    "harness/wiki",   # vault 디렉토리
]
_VARIANTS_NO_WIKI = ["claude", "claude.gstack", "claude.gstack.auto", "claude.gstack.auto.design"]
_VARIANTS_WITH_DESIGN = ["claude.gstack.auto.design", "claude.gstack.auto.design.wiki"]  # MR-4 / MR-5 수정

# check_mirror_regression() 함수에 MR-6 / MR-7 블록 추가
# 기존 MR-1 ~ MR-5 무수정 — MR-4 / MR-5 의 검사 대상 변수만 _VARIANTS_NO_DESIGN /
# _VARIANTS_WITH_DESIGN 으로 교체
```

#### F009 lint.py 미러 정책

F009 lint.py 는 모든 변형 (ⓐ 제외) 에 미러됨. MR-6 / MR-7 추가 후 미러 6 변형 모두에
일관된 lint.py 가 들어감 — 단, wiki 변형 (ⓑ‴) 의 lint.py 는 자기 자신의 wiki 오버레이를
점검 (자기 인식 BLOCK 아닌 PASS).

**근거**:

- **F011 LINT-MR 패턴 일관**: MR-1 ~ MR-5 는 기존 결정 7 의 정신 그대로 — F011 가 도입한 가드를
  6 변형 매트릭스로 확장.
- **MR-7 의 의의**: 외부 의존성 정책 예외가 wiki 변형에만 격리됨을 자동 검증 — 결정 1 의
  "다른 5 변형은 절대 외부 의존성 X" 를 자동 강제.
- **무회귀 보장**: 기존 MR-1 ~ MR-3 무수정. MR-4 / MR-5 는 검사 대상 변수만 교체 (의미 동일).

**영향받는 AC**: AC8 (LINT-MR 6 변형 확장)

---

### 결정 9 — F012 세션 분할: **3 세션 (사용자 estimated_sessions=3 일치)**

**채택**: feature_list.estimated_sessions=3 일관. 세션 1 이 변형 신설 + 외부 의존성 정책 예외
+ vault 구조 + wiki.py ingest, 세션 2 가 query/lint/graph + graceful degrade + wiki-setup.sh,
세션 3 이 /project:wiki + LINT-MR + CLAUDE.md + 미러 정합 (F011 세션 분할 정신 일관).

#### 세션 분할 표

| 세션 | 범위 | 산출물 | AC 충족 |
|---|---|---|---|
| **세션 1** — 변형 신설 + 정책 예외 문서화 + vault 구조 + wiki.py ingest | `claude.gstack.auto.design.wiki/` cp 신설, coding-standards.md 의 "외부 의존성 정책 (변형별)" 섹션 추가, `wiki/` vault 디렉토리 구조 + README.md + index.md 골격 + log.md 골격, `.claude/bin/wiki.py` 의 ingest + self 서브커맨드 구현, ADR-007 미러 (ⓑ + ⓑ′ + ⓑ″ + ⓑ‴) | claude.gstack.auto.design.wiki/ 디렉토리, coding-standards.md 갱신, wiki/ vault 골격, wiki.py ingest + self, ADR-007 | AC1 (변형 신설), AC2 (정책 예외), AC3 (vault 구조), AC4 (wiki.py ingest 부분) |
| **세션 2** — query/lint/graph + graceful degrade + wiki-setup.sh | wiki.py query / lint / graph 서브커맨드 + 외부 도구 자동 감지 + stdlib fallback, `wiki-setup.sh` **자동 설치 스크립트** (autonomous ESCALATE 흐름 활용 + 명확한 승인 요청 메시지 + 설치 실패 graceful degrade), 4 핵심 검사 항목 (WIKI-ORPHAN/DEAD-LINK/STALE/FRONTMATTER), mermaid/DOT 출력 | wiki.py 5 서브커맨드 완성, wiki-setup.sh, graceful degrade 동작 확인 | AC4 (wiki.py 5 서브커맨드), AC5 (`/project:wiki` 커맨드 준비), AC6 (wiki-setup.sh 자동 설치 + ESCALATE), AC7 (graceful degrade) |
| **세션 3** — /project:wiki + LINT-MR 6 변형 확장 + CLAUDE.md + 최종 미러 정합 | `.claude/commands/wiki.md` 슬래시 커맨드, `lint.py` LINT-MR-6 / LINT-MR-7 추가 + MR-4/MR-5 검사 대상 갱신, CLAUDE.md 빠른 시작 + 호출 기준 + 6 변형 매트릭스 + 디렉토리 트리, learnings 3 개 append, 최종 미러 동기화 (ⓑ + ⓑ′ + ⓑ″ + ⓑ‴) | wiki.md 커맨드, lint.py LINT-MR 6 변형 확장, CLAUDE.md 통합, learnings, 최종 미러 | AC5 (`/project:wiki` 커맨드), AC8 (LINT-MR 확장), AC9 (CLAUDE.md), AC10 (ADR-007 최종) |

#### 세션 분할 근거

- **세션 1 의 응집도**: 변형 신설 + 정책 예외 문서화 + vault 구조 + ingest 는 모두 "wiki 인프라
  구축" 카테고리. 한 세션 응집도 ↑. wiki.py 의 ingest 만 먼저 구현해도 사용자가 graceful
  degrade 안에서 검색·그래프 없이 ingest 시연 가능.
- **세션 2 의 응집도**: 4 핵심 서브커맨드 완성 + graceful degrade + wiki-setup.sh 안내. F011
  세션 2 (design_pick.py 5 서브커맨드 + tokens.json) 정신 일관.
- **세션 3 의 응집도**: 슬래시 커맨드 + LINT-MR 확장 + CLAUDE.md + 미러는 모두 "통합 + 가드 +
  문서화" 카테고리. F011 세션 3 정신 일관.

#### 대안 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) 3 세션 (사용자 estimated 일치)** | feature_list 일관, 세션별 응집도 ↑, F011 와 같은 호흡 | 세션 1 의 변형 신설이 큰 작업 — 디스크 사용량 ↑ | **채택** |
| (B) 2 세션 (압축) | 세션 수 ↓ | 세션 1 부하 ↑ + 회귀 위험 ↑ | 부담 ↑ |
| (C) 4 세션 (vault 구조 + wiki.py 분리) | 부하 최소 | feature_list 와 불일치, 과도 분할 | 과함 |

**근거**: F011 의 3 세션 분할 성공 패턴 일관. F012 도 변형 신설 → 코어 헬퍼 → 통합 흐름이
자연스러움.

**영향받는 AC**: 전체 진행 계획 (feature_list.estimated_sessions=3 유지)

---

## 대안 검토 (요약)

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| 외부 도구 완전 금지 (결정 1 A) | F005~F011 일관성 100% | F012 가치 50% 손실 | 결정 1 |
| 모든 변형에 외부 도구 허용 (결정 1 C) | wiki 패턴을 더 넓게 활용 | 5 변형 정책 무너짐 | 결정 1 |
| `.claude/wiki/` vault 위치 (결정 2 A) | 하네스 내부 정리 일관 | Obsidian 사용자가 `.claude/` 를 열어야 함 | 결정 2 |
| ingest 100% LLM 호출 (결정 3 C) | 본문 품질 ↑ | 토큰 비용 ↑ + 재현성 ↓ | 결정 3 |
| 단일 wiki 명령 (서브커맨드 없음, 결정 4 A) | 진입점 단순 | F005~F011 패턴 위배 | 결정 4 |
| 외부 도구 필수 (결정 5 A) | 가스트 경험 100% | hook-failure-tolerance 위배 | 결정 5 |
| wiki-setup.sh 자동 설치 + boundary 훅 예외 추가 (결정 6 A) | 사용자 ESCALATE 부담 ↓ | autonomous 보안 약화 + 훅 분기 학습 비용 ↑ | 결정 6 |
| wiki-setup.sh 안내만 — 자동 설치 X (결정 6 C) | 자율 모드 정책 무변경 | 사용자가 명령 복사·실행 수동 부담 — 자동화 의도와 어긋남 | 결정 6 |
| wiki lint 를 F009 lint.py 에 통합 (결정 7 A) | 호출 진입점 통일 | wiki 의존성이 F009 lint.py 본체에 침투 | 결정 7 |
| wiki lint 를 design-review 카테고리 통합 (결정 7 C) | design-review 일관 | 의미론 다름 | 결정 7 |
| 2 세션 분할 (결정 9 B) | 세션 수 ↓ | 세션 1 부하 ↑ + 회귀 위험 ↑ | 결정 9 |
| 4 세션 분할 (결정 9 C) | 부하 최소 | feature_list 불일치 | 결정 9 |

---

## 결과

### 긍정적 영향

- **F012 모든 AC 충족 예정** (AC1~AC10, 세션별 매핑은 결정 9 표 참조)
- **LLM Wiki 가스트의 ingest/query/lint/graph 4 핵심 동작 완전 구현** — F009 (lint + index +
  log prefix) 가 절반 이식이었다면 F012 가 풀 이식
- **외부 의존성 정책 예외 명시화**: 변형별 격리 패턴이 자율 오버레이 / 디자인 오버레이에 이어
  3 번째 — 패턴 일반성 확보. 향후 다른 외부 도구 변형 (예: GitHub Actions, sentry) 도입 시 동일
  패턴 재사용 가능
- **graceful degrade 의무화**: wiki 변형 사용자가 외부 도구 미설치 상태에서도 핵심 기능 보장 —
  hook-failure-tolerance 정책 일관
- **무회규**: F001~F011 의 동작 무수정. `.claude/settings.json` / 기존 7 에이전트 (planner/
  architect/developer/reviewer/qa/gatekeeper/designer) / brain.py / host.py / lint.py (추가만)
  / backup.py / qa_browser.py / design_pick.py 모두 그대로
- **F005~F011 패턴 100% 일관**: 단일 파일 헬퍼 (wiki.py) + 서브커맨드 (5 개) + 변형 미러
  (선별 포함) + 셀프 모드 (self) + 옵셔널 + exit 0 + hook-failure-tolerance
- **6 변형 매트릭스 명시화**: F011 의 5 변형 → 6 변형 확장 — LINT-MR-6/MR-7 가드로 격리 자동 강제
- **다운스트림 가치**: 프로젝트 산출물이 자동으로 지식 그래프로 변환되어 시간 흐름에 따른 합성
  지식 누적 — Karpathy 비전 (Memex) 실현
- **확장 경로 명시**: 후속 phase 에 옵션 (자동 보강 / Marp 슬라이드 통합 / qmd MCP 서버) 분리 가능

### 부정적 영향 / 트레이드오프

- **신규 변형 1개** (`claude.gstack.auto.design.wiki/`) — claude.gstack.auto.design 의 1:1 복사 +
  wiki 오버레이 ≈ 디스크 사용량 ↑ (≈ 1.3MB) + 미러링 시간 ↑
- **신규 파일 4~5 개** (`.claude/bin/wiki.py`, `.claude/bin/wiki-setup.sh`,
  `.claude/commands/wiki.md`, `wiki/README.md`, `docs/adr/ADR-007-*.md`)
- **`wiki/` 디렉토리 신설** — 프로젝트 루트에 새 디렉토리 (gitignore 안 함 — vault 자체는 git 추적
  권장. 단, vault 내부 `.obsidian/workspace.json` 같은 사용자별 캐시는 gitignore 권장)
- **`.claude/rules/coding-standards.md` 수정** (외부 의존성 정책 섹션 추가) — F005~F011 산출물
  변경. 단, 추가만 — Simplicity First 등 기존 섹션 무수정
- **`.claude/bin/lint.py` 수정** (LINT-MR-6 / MR-7 추가 + MR-4/MR-5 검사 대상 갱신) — F009/F011
  산출물 변경. 단, 추가 + 변수 교체만
- **CLAUDE.md 갱신** (빠른 시작 + 호출 기준 + 6 변형 매트릭스 표 + 디렉토리 트리) — 분량 ↑
  약 40~60 줄
- **외부 의존성 0 슬로건이 변형별 분기**: 학습 비용 1 — 본 ADR + coding-standards.md 표가 단일
  소스. wiki 변형 사용자가 "외부 도구 감수" 를 명시 동의해야 함
- **다운스트림이 wiki 변형을 가져갈 때 외부 도구 부담**: graceful degrade 가 안전망. 단, "wiki
  변형 = 외부 도구 권장" 임을 README / CLAUDE.md 빠른 시작에서 명시
- **wiki/ vault 와 F009 docs/index.md 분리 학습 비용 1**: 두 index 의 목적이 다름을 매뉴얼 명시
  필요 (결정 2 의 표가 단일 소스)
- **LLM 보강 모드 토큰 비용**: 옵트인 (`--enrich-llm`) — 기본 비활성. 사용자 명시 시에만 비용
  발생

### 후속 조치

- [ ] (F012 세션 1) 변형 신설 + coding-standards 정책 예외 + vault 골격 + wiki.py ingest + self + ADR-007 미러
- [ ] (F012 세션 2) wiki.py query/lint/graph + graceful degrade + wiki-setup.sh
- [ ] (F012 세션 3) `/project:wiki` 커맨드 + LINT-MR-6/MR-7 + CLAUDE.md + 최종 미러 정합
- [ ] (F012 QA) `/project:wiki self` + `/project:wiki ingest` + `/project:wiki lint` + `/project:lint --only=LINT-MR` 4 검증
- [ ] (F013 가칭 — 후속) qmd MCP 서버 통합 (LLM 이 wiki query 를 native tool 로 호출 — 가스트 옵션)
- [ ] (F014 가칭 — 후속) Marp 슬라이드 자동 변환 (wiki 페이지 → 발표 자료, frontmatter 자동 생성)
- [ ] (F015 가칭 — 후속) 옵션 `--enrich-llm` 모드 본격 구현 (designer 에이전트 패턴 — wiki-curator 에이전트 신설?)
- [ ] (F016 가칭 — 후속) 외부 도구 변형 카탈로그 일반화 — 다른 외부 도구 (예: sentry, gh-cli) 도
  변형별 격리 패턴 재사용

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성 (세션 1)**:

```
src/harness_template/claude.gstack.auto.design.wiki/                       # 변형 디렉토리 자체 (cp -r 신설)
.claude/bin/wiki.py                                                         # 단일 파일 헬퍼 (메인 SSoT — ingest + self 만)
wiki/                                                                       # vault 디렉토리 (메인 데모용)
wiki/README.md
wiki/index.md                                                               # 골격 (ingest 가 갱신)
wiki/log.md                                                                 # 골격 (F009 prefix 컨벤션)
wiki/features/.gitkeep
wiki/adrs/.gitkeep
wiki/learnings/.gitkeep
wiki/pages/.gitkeep
wiki/sources/.gitkeep
docs/adr/ADR-007-llm-wiki-knowledge-graph.md                                # 본 ADR
```

**신규 생성 (세션 2)**:

```
.claude/bin/wiki-setup.sh                                                   # 안내 전용 스크립트
```

**수정 (세션 1)**:

```
.claude/rules/coding-standards.md                                           # "외부 의존성 정책 (변형별)" 섹션 추가
feature_list.json                                                           # F012 status: in-progress (그대로)
```

**수정 (세션 2)**:

```
.claude/bin/wiki.py                                                         # query/lint/graph 서브커맨드 추가
```

**신규 생성 (세션 3)**:

```
.claude/commands/wiki.md                                                    # /project:wiki 슬래시 커맨드
```

**수정 (세션 3)**:

```
.claude/bin/lint.py                                                         # LINT-MR-6 / MR-7 추가 + MR-4/MR-5 검사 대상 갱신
CLAUDE.md                                                                   # 빠른 시작 + 호출 기준 + 6 변형 매트릭스 + 디렉토리 트리
feature_list.json                                                           # F012 status: in-progress → review
.claude/state/learnings.jsonl                                               # 새 학습 3 개
```

**미러링 (ⓑ + ⓑ′ + ⓑ″ + ⓑ‴ — 결정 8 의 선별 미러)**:

```
# ⓑ (claude.gstack) — 자율 + 디자인 + wiki 오버레이 제외
src/harness_template/claude.gstack/harness/.claude/rules/coding-standards.md  # 외부 의존성 정책 섹션 추가됨
src/harness_template/claude.gstack/harness/.claude/bin/lint.py                # LINT-MR-6/MR-7 추가
src/harness_template/claude.gstack/harness/CLAUDE.md                          # 빠른 시작 + 6 변형 매트릭스
src/harness_template/claude.gstack/harness/docs/adr/ADR-007-*.md

# ⓑ′ (claude.gstack.auto) — 디자인 + wiki 오버레이 제외 (자율 유지)
(상동)

# ⓑ″ (claude.gstack.auto.design) — wiki 오버레이만 제외 (디자인 유지)
(상동)

# ⓑ‴ (claude.gstack.auto.design.wiki) — 모든 오버레이 포함 (자율 + 디자인 + wiki)
src/harness_template/claude.gstack.auto.design.wiki/harness/.claude/bin/wiki.py
src/harness_template/claude.gstack.auto.design.wiki/harness/.claude/bin/wiki-setup.sh
src/harness_template/claude.gstack.auto.design.wiki/harness/.claude/commands/wiki.md
src/harness_template/claude.gstack.auto.design.wiki/harness/wiki/...
(나머지 상동)
```

**의도적 미수정 (제약 준수)**:

```
.claude/settings.json                                                      # Claude Code 스키마 격리 (F006)
.claude/agents/{planner,architect,developer,reviewer,qa,gatekeeper,designer}.md  # 기존 7 에이전트 무수정
.claude/bin/{brain,host,host_adapters,backup,qa_browser,design_pick}.py     # F005/F006/F010/F008/F011 격리
.claude/hooks/{pre-bash-check,pre-bash-auto-boundary-check,pre-edit-freeze-check,session-end}.sh  # 무수정
.claude/commands/{init-project,handoff,start-session,...}.md (F012 무관)   # 무수정
.claude/skills/{coding,planning,testing,qa-browser,design-review}/SKILL.md # 무수정 (wiki lint 는 wiki.py 독립)
docs/adr/ADR-001*.md ~ ADR-006*.md                                          # 기존 ADR 무수정
src/docs/design/ui/{apple,claude,spotify,tesla}-design.md                   # 메인 디자인 원본 무수정
src/harness_template/claude/                                                # baseline 동결
src/harness_template/openai/                                                # codex stub
```

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| AC1 — `claude.gstack.auto.design.wiki` 변형 신설 (claude.gstack.auto.design 1:1 + wiki 오버레이) | 세션 1 (cp -r) + 세션 3 (최종 미러 정합) | 결정 8 |
| AC2 — 외부 의존성 0 정책 예외 명시 (wiki 변형만 Obsidian/qmd/Marp 허용, coding-standards.md 문서화) | 세션 1 (coding-standards.md 수정) | 결정 1 |
| AC3 — Obsidian vault 구조 (.md + [[wikilink]], 산출물 → 지식 그래프 노드/엣지) | 세션 1 (vault 골격) + 세션 1 (ingest 결정론적 매핑) | 결정 2 + 결정 3 |
| AC4 — wiki.py 헬퍼 (ingest/query/lint/graph) | 세션 1 (ingest + self) + 세션 2 (query/lint/graph) | 결정 4 + 결정 7 |
| AC5 — `/project:wiki` 커맨드 | 세션 3 (wiki.md) | 결정 4 |
| AC6 — wiki-setup.sh + autonomous 규칙 #3-B 조율 | 세션 2 (wiki-setup.sh 자동 설치 + autonomous ESCALATE 활용 + graceful degrade fallback) | 결정 6 |
| AC7 — graceful degrade (핵심 stdlib, 검색·시각화만 외부 옵션) | 세션 2 (detect_external_tools + fallback) | 결정 5 |
| AC8 — LINT-MR 6 변형 확장 (wiki 의 외부 의존성 허용 정상 인식) | 세션 3 (lint.py LINT-MR-6 / MR-7) | 결정 8 |
| AC9 — CLAUDE.md 6 변형 미러 매트릭스 + wiki 호출 기준 | 세션 3 (CLAUDE.md 갱신) | 결정 1 + 결정 4 |
| AC10 — ADR-007 (LLM Wiki 외부 도구 정책 예외 + Obsidian 지식 그래프 설계 결정) | 본 문서 + 세션 1 미러 | 본 ADR |

### 피해야 할 패턴

- ❌ `.claude/settings.json` 수정 (F006 격리)
- ❌ `claude/` (baseline) 또는 `openai/.codex/` 에 wiki 오버레이 미러 (결정 8 위배 — Karpathy 만)
- ❌ `claude.gstack/` / `claude.gstack.auto/` / `claude.gstack.auto.design/` 에 wiki.py /
  wiki.md / wiki-setup.sh / `wiki/` 디렉토리 미러 (결정 8 위배)
- ❌ wiki 변형 외 다른 변형에 `requirements.txt` / `package.json` 같은 외부 도구 매니페스트
  추가 (LINT-MR-7 위배)
- ❌ wiki-setup.sh 가 ESCALATE 우회 — boundary 훅 예외 코드 추가 (결정 6 A 기각 — autonomous 규칙 #3-B 보존)
- ❌ pre-bash-auto-boundary-check.sh 에 wiki 변형 예외 추가 (결정 6 A 기각)
- ❌ 1 회 사용자 승인을 영구 캐시·파일에 저장 (보안 위험 — 매 세션 명시 승인 유지)
- ❌ wiki-setup.sh 가 단순 안내만 출력하고 실제 설치 명령 미실행 (결정 6 C 기각 — 자동화 의도와 어긋남)
- ❌ wiki-setup.sh 가 설치 실패 시 exit 1 (결정 5 + 결정 6 — graceful degrade 안전망 위배)
- ❌ wiki-setup.sh 가 ESCALATE 메시지 없이 패키지 설치 (사용자가 어떤 패키지를·왜 설치하는지 모름 — 보안)
- ❌ wiki.py lint 를 F009 lint.py 에 통합 (결정 7 — wiki.py 독립)
- ❌ wiki lint 를 design-review 카테고리에 통합 (결정 7 — 의미론 다름)
- ❌ ingest 가 100% LLM 호출 (결정 3 — 결정론적 매핑 기본 + LLM 보강 옵트인)
- ❌ wiki.py 단일 명령 (서브커맨드 없음) (결정 4 — 5 서브커맨드 패턴 일관)
- ❌ vault 위치 `.claude/wiki/` (결정 2 — 프로젝트 루트 `wiki/`)
- ❌ wiki 핵심 기능에 외부 도구 강제 (결정 5 — graceful degrade 의무)
- ❌ `wiki/index.md` 와 `docs/index.md` 혼동 (결정 2 — 분리)
- ❌ F009 lint.py 본체 수정 (LINT-MR-6/MR-7 은 추가만)
- ❌ `.claude/agents/` 의 기존 7 에이전트 정의 수정 (무회귀)
- ❌ F012 세션 1 ~ 3 동안 `feature_list.json` 의 `passes` 필드 수정 (QA 단독 권한)
- ❌ wiki-curator 같은 신규 에이전트 신설 (본 phase 범위 외 — 후속 F015 가칭)
- ❌ qmd MCP 서버 통합 (본 phase 범위 외 — 후속 F013 가칭)
- ❌ Marp 슬라이드 자동 변환 (본 phase 범위 외 — 후속 F014 가칭)
- ❌ frontmatter 만 엣지 표현 (결정 2 — 본문 wikilink + frontmatter `related` 이중)
- ❌ 본문 wikilink 만 엣지 표현 (결정 2 — frontmatter `related` 결정론 필수)
- ❌ wiki 변형의 외부 의존성을 다른 5 변형에 전파 (결정 1 — 격리 강제)

---

## 부록 A — 외부 의존성 정책 매트릭스 (단일 소스)

| 변형 | 외부 의존성 | 허용 도구 | 격리 검사 |
|---|---|---|---|
| ⓐ `claude/` (baseline) | **0** | — | LINT-MR-7 (없어야) |
| ⓑ `claude.gstack/` (표준) | **0** | — | LINT-MR-7 (없어야) |
| ⓑ′ `claude.gstack.auto/` (자율) | **0** | — | LINT-MR-7 (없어야) |
| ⓑ″ `claude.gstack.auto.design/` (자율+디자인) | **0** | — | LINT-MR-7 (없어야) |
| **ⓑ‴ `claude.gstack.auto.design.wiki/` (자율+디자인+wiki)** | **허용** | **Obsidian / qmd / Marp** | LINT-MR-7 (wiki-setup.sh 존재해야) |
| ⓒ `openai/.codex/` (codex stub) | **0** | — | LINT-MR-7 (없어야) |

→ wiki 변형의 외부 의존성 허용은 격리됨. 다른 5 변형은 절대 외부 의존성 X.

---

## 부록 B — 6 변형 매트릭스 산출물 분포표 (Developer / QA 참고)

| 산출물 | ⓐ `claude/` | ⓑ `claude.gstack/` | ⓑ′ `claude.gstack.auto/` | ⓑ″ `claude.gstack.auto.design/` | **ⓑ‴ `claude.gstack.auto.design.wiki/`** | ⓒ `openai/.codex/` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `.claude/agents/{planner,architect,developer,reviewer,qa}.md` | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/agents/gatekeeper.md` | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/agents/designer.md` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| `.claude/commands/{handoff,start-session,...}.md` (공통) | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/commands/design-pick.md` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **`.claude/commands/wiki.md` (F012)** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/commands/design-review.md` (F007) | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/{brain,host,lint,backup,qa_browser}.py` | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/design_pick.py` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **`.claude/bin/wiki.py` (F012)** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **`.claude/bin/wiki-setup.sh` (F012)** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/skills/design-review/SKILL.md` (F007 + F011 D. TOKEN) | ❌ | ✅ | ✅ | ✅ | ✅ | (Karpathy 만) |
| `docs/design-references/{apple,claude,spotify,tesla}-design.md` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| `docs/design/F011-tokens-schema.md` (F011) | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **`wiki/` (vault, F012)** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `docs/adr/ADR-006-*.md` (F011) | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **`docs/adr/ADR-007-*.md` (F012)** | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **외부 의존성 (Obsidian/qmd/Marp)** | ❌ | ❌ | ❌ | ❌ | **✅ (허용)** | ❌ |
| Karpathy 4원칙 (think/simplicity/surgical/goal) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

→ wiki 오버레이는 **ⓑ‴ 에만 존재**. 다른 5 변형은 자율 / 디자인 / 외부 의존성 0 정체성 보존.
ADR-007 본체는 ⓑ + ⓑ′ + ⓑ″ + ⓑ‴ 4 변형에 미러 (외부 의존성 정책 표 자체는 모든 변형이 알아야
하는 거버넌스 — Karpathy 4원칙 일관성과 같은 의미).

---

## 부록 C — wiki 라이프사이클 (Developer / QA / 사람 흐름)

| 단계 | 도구/에이전트 | 책임 | 호출 빈도 |
|---|---|---|---|
| **초기화** | `wiki-setup.sh` (사용자 1 회 호출) | 외부 도구 자동 설치 (autonomous ESCALATE 흐름으로 사용자 1 회 명시 승인 → 그 세션에서 설치 진행, 거부 시 graceful degrade) | wiki 변형 도입 시 1 회 |
| **자동 변환** | `wiki.py ingest` | 산출물 (feature/ADR/learning) → vault 노드 (결정론적) | feature 추가/완료 시, ADR 작성 시 |
| **자유 작성** | 사람 + Obsidian | `wiki/pages/`, `wiki/sources/` 에 자유 wiki 페이지 작성 (LLM 보강 옵션) | 수시 |
| **검색** | `wiki.py query` (또는 qmd / Obsidian search) | vault 검색 + 합성 답변 | 수시 |
| **시각화** | Obsidian graph view (또는 `wiki.py graph` 텍스트) | 노드 연결 시각화 | 수시 |
| **정합 점검** | `wiki.py lint` | vault 정합성 (고아 / 끊긴 wikilink / stale / frontmatter) | handoff 직전, 새 노드 추가 후 |
| **거버넌스 점검** | F009 `lint.py` (LINT-MR-6 + LINT-MR-7) | 변형 미러 정합 + 외부 의존성 격리 | handoff 직전 |
| **셀프 dry-run** | `wiki.py self` | vault 디렉토리 / 외부 도구 감지 / graceful degrade 상태 | 환경 변경 후 1 회 |

이 8 단계가 wiki 변형의 라이프사이클을 단일 SSoT 흐름으로 보장.

---

## 부록 D — wiki 변형 사용자 안내 메시지 (CLAUDE.md 빠른 시작 + 호출 기준 단일 소스)

CLAUDE.md 갱신 분량 (세션 3):

```markdown
### LLM Wiki 지식 그래프 (Phase 8 — F012)

> 사용 가능 변형: **claude.gstack.auto.design.wiki/** 만.
> 외부 도구 (Obsidian / qmd / Marp) 권장 — 미설치 시 graceful degrade.

/project:wiki ingest                         # 모든 산출물 일괄 ingest + index 갱신
/project:wiki ingest --source=adr            # ADR 만 ingest
/project:wiki ingest --source-file=<path>    # 외부 .md 를 source 노드로
/project:wiki query "<검색어>"               # vault 검색 (qmd 있으면 BM25, 없으면 grep)
/project:wiki lint                            # vault 정합성 점검
/project:wiki graph --format=mermaid          # mermaid 텍스트 그래프
/project:wiki self                            # 셀프 dry-run (외부 도구 감지)

> 외부 도구 설치: bash .claude/bin/wiki-setup.sh  (autonomous 모드 — 각 설치마다 사용자 승인)
> 핵심 기능 (ingest/lint/graph + stdlib grep query) 은 외부 도구 없이도 동작 (graceful degrade).

### wiki 호출 기준

다음 중 하나라도 해당되면 `/project:wiki ingest` 실행 권장:
- 새 feature 추가 또는 완료 시
- 새 ADR 작성 시
- 외부 자료 (논문, 가스트, 회의록) 를 프로젝트 지식 베이스에 정리할 때
- 기존 산출물의 cross-reference 가 누락된 것 같을 때

`/project:wiki lint` 호출 시점:
- handoff 직전 (F009 권장 시점에 추가)
- 새 노드 추가 후 (cross-reference 검증)

해당 없으면 (예: 빠른 버그 수정, 1 회성 변경) wiki 호출 스킵 가능.
**wiki 는 옵셔널** — 호출 안 해도 하네스 동작에 영향 없음.

### 6 변형 매트릭스 (F012 완료 후)

| 변형 | F005~F011 | 자율 오버레이 | 디자인 오버레이 | **wiki 오버레이** | **외부 의존성** | 미러 정책 |
|---|---|---|---|---|---|---|
| ⓐ `claude/` | ❌ | ❌ | ❌ | ❌ | 0 | Karpathy 만 |
| ⓑ `claude.gstack/` | ✅ | ❌ | ❌ | ❌ | 0 | 표준 SSoT 미러 |
| ⓑ′ `claude.gstack.auto/` | ✅ | ✅ | ❌ | ❌ | 0 | 자율 오버레이 포함 |
| ⓑ″ `claude.gstack.auto.design/` | ✅ | ✅ | ✅ | ❌ | 0 | 자율 + 디자인 |
| **ⓑ‴ `claude.gstack.auto.design.wiki/`** | ✅ | ✅ | ✅ | ✅ | **허용 (Obsidian/qmd/Marp)** | **자율 + 디자인 + wiki** |
| ⓒ `openai/.codex/` | ❌ | ❌ | ❌ | ❌ | 0 | Karpathy 만 (stub) |

> 미러 회귀 + 외부 의존성 격리 자동 감지: `/project:lint --only=LINT-MR` (F012)
```

---

*작성: architect 에이전트 | 날짜: 2026-06-03 | 상태: Proposed*
