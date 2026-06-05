# /project:wiki — LLM Wiki 지식 그래프

프로젝트 산출물(feature/ADR/learning/wiki 페이지)을 Obsidian vault 노드/엣지로
변환·관리한다. Karpathy LLM Wiki 가스트의 ingest/query/lint/graph 패턴 완전 구현.

**사용 가능 변형**: `claude.gstack.auto.design.wiki/` 만 (ADR-007 결정 1 + 결정 8).
**외부 의존성 예외**: Obsidian / qmd / Marp 허용 (다른 5 변형은 외부 의존성 0).
**옵셔널**: 호출하지 않으면 하네스 동작에 영향 없음 (F005~F011 일관).

---

## 사용법

```
/project:wiki ingest                         # 모든 산출물 일괄 ingest + index 갱신
/project:wiki ingest --source=adr            # ADR 만 ingest
/project:wiki ingest --source=features       # features 만 ingest
/project:wiki ingest --source=learnings      # learnings 만 ingest
/project:wiki ingest --source-file=<path>    # 외부 .md 를 source 노드로
/project:wiki query "<검색어>"               # vault 검색 (qmd 있으면 BM25, 없으면 grep)
/project:wiki lint                           # vault 정합성 점검 (고아·끊긴링크·stale·frontmatter)
/project:wiki lint --strict                  # dead-link 있으면 exit 1
/project:wiki graph                          # mermaid 텍스트 그래프 (기본)
/project:wiki graph --format=dot             # DOT 텍스트 그래프
/project:wiki graph --output=wiki/graph.md   # 파일 저장
/project:wiki self                           # 의존성·graceful degrade 상태 점검

# 외부 도구 설치 (선택 — 검색·시각화 향상)
bash .claude/bin/wiki-setup.sh               # qmd/marp 자동 설치
                                             # (autonomous 모드: 각 설치마다 사용자 ESCALATE 승인)
```

직접 Python 실행:

```bash
python3 .claude/bin/wiki.py ingest all
python3 .claude/bin/wiki.py query "지식 그래프"
python3 .claude/bin/wiki.py lint
python3 .claude/bin/wiki.py lint --strict
python3 .claude/bin/wiki.py graph --format mermaid
python3 .claude/bin/wiki.py graph --format dot --output wiki/graph.md
python3 .claude/bin/wiki.py self
```

---

## 5 서브커맨드

| 서브커맨드 | 동작 | LLM 호출 |
|---|---|---|
| **ingest** | 산출물(feature/ADR/learning) 또는 외부 .md → vault 노드 (결정론적 매핑) | 없음 (정적). `--enrich-llm` 플래그 시만 LLM 보강 (옵트인) |
| **query `<검색어>`** | vault 검색. qmd 있으면 BM25, 없으면 stdlib grep fallback (graceful degrade) | 없음 |
| **lint** | vault 정합성 점검 (WIKI-ORPHAN / WIKI-DEAD-LINK / WIKI-STALE / WIKI-FRONTMATTER) | 없음 |
| **graph** | vault 그래프를 mermaid (기본) 또는 DOT / JSON 텍스트로 출력 | 없음 |
| **self** | 셀프 dry-run (vault 디렉토리 존재 / 외부 도구 감지 / graceful degrade 상태) | 없음 |

---

## 전역 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--vault PATH` | `<project-root>/wiki/` | vault 위치 override (테스트용) |
| `--strict` | OFF | BLOCK 1건이라도 있으면 exit 1 (CI gate) |
| `--format human\|json` | human | 출력 포맷 |

---

## Obsidian vault 구조

```
wiki/                          # Obsidian vault 루트 (git 추적 권장)
├── README.md                  # vault 소개 (Obsidian 첫 페이지)
├── index.md                   # 콘텐츠 카탈로그 (wiki.py ingest --rebuild-index 갱신)
├── log.md                     # ingest/query/lint 이벤트 로그 (F009 prefix 컨벤션)
├── features/                  # feature_list.json 항목 → 노드
├── adrs/                      # docs/adr/*.md → 노드
├── learnings/                 # .claude/state/learnings.jsonl → 노드
├── pages/                     # 사람 + LLM 이 작성한 자유 wiki 페이지
└── sources/                   # 외부 자료 ingest (Karpathy 가스트 등)
```

**엣지 이중 표현**: frontmatter `related: [F001, ADR-007]` (결정론적) + 본문 `[[wikilink]]` (Obsidian graph view).

---

## wiki 호출 기준

다음 중 하나라도 해당되면 `/project:wiki ingest` 실행을 권장한다:

- 새 feature 추가 또는 완료 시 (feature_list.json 변경 후)
- 새 ADR 작성 시 (docs/adr/ 변경 후)
- 외부 자료(논문·가스트·회의록)를 프로젝트 지식 베이스에 정리할 때
- 기존 산출물의 cross-reference 가 누락된 것 같을 때

`/project:wiki lint` 호출 시점:

- handoff 직전 (F009 `/project:lint` 와 함께 실행 권장)
- 새 노드 추가 후 cross-reference 검증

해당 없으면 (빠른 버그 수정, 1회성 변경) wiki 호출 스킵 가능.

**wiki 는 옵셔널** — 호출하지 않아도 하네스 동작에 영향 없음.

---

## graceful degrade 매트릭스

| 기능 | 외부 도구 없이 동작 여부 | 외부 도구 향상 |
|---|---|---|
| **노드 생성 (ingest)** | ✅ (Python stdlib only) | (없음 — stdlib 충분) |
| **검색 (query)** | ✅ (grep fallback) | qmd (BM25 + vector 검색) |
| **그래프 (graph)** | ✅ (mermaid / DOT 텍스트) | Obsidian graph view (시각화) |
| **lint** | ✅ (정규식 + frontmatter 파싱) | (없음 — stdlib 충분) |
| **슬라이드** | ✅ (Marp frontmatter .md) | Marp CLI (.md → PDF/PPTX) |

---

## 외부 의존성 정책 (wiki 변형 한정)

이 변형만 외부 도구 허용. 다른 5 변형은 외부 의존성 0 정책 유지 (LINT-MR-7 강제).

| 도구 | 목적 | 설치 방법 |
|---|---|---|
| **Obsidian** | vault graph view 시각화 (사람) | https://obsidian.md/download (수동) |
| **qmd** | BM25/vector 검색 (CLI) | `cargo install qmd` 또는 `brew install qmd` |
| **Marp CLI** | .md → 슬라이드 변환 | `npm install -g @marp-team/marp-cli` |

```bash
# 일괄 설치 (autonomous 모드 — 각 도구마다 ESCALATE 승인 필요)
bash .claude/bin/wiki-setup.sh

# 설치 결과 확인
python3 .claude/bin/wiki.py self
```

**계약**: wiki 변형을 가져가는 다운스트림은 외부 도구 설치를 감수한다.
graceful degrade 가 의무 — 도구 없이도 핵심 기능(ingest/lint/graph + grep query)은 동작.

---

## lint 항목 (WIKI-*)

| 항목 | 심각도 | 설명 |
|---|---|---|
| WIKI-DEAD-LINK | BLOCK | 본문 `[[X]]` 가 X.md 파일로 resolve 불가 |
| WIKI-FRONTMATTER | INFO | frontmatter 누락 또는 `type` / `created` 필수 필드 부재 (메타 불완전, 그래프 깨짐 아님) |
| WIKI-ORPHAN | CONCERN | 다른 노드에서 in-degree 0 (참조되지 않는 노드) |
| WIKI-STALE | CONCERN | frontmatter `status: stale` 또는 90일 이상 미수정 |

`wiki.py lint` 는 F009 `lint.py` 와 독립 — vault 정합성만 담당 (ADR-007 결정 7).

---

## 권장 호출 흐름

```
1. (wiki 변형 도입 초기) 외부 도구 설치
   bash .claude/bin/wiki-setup.sh

2. 환경 점검
   /project:wiki self

3. 산출물 ingest
   /project:wiki ingest

4. vault 탐색
   /project:wiki query "검색어"
   # Obsidian 설치 시: wiki/ 를 vault로 열어 graph view 확인

5. 정합 점검 (handoff 직전)
   /project:wiki lint
   /project:lint --only=LINT-MR   # LINT-MR-6/MR-7 포함 — 변형 격리 확인
```

---

## 다른 도구와의 역할 경계

| 도구 | 책임 |
|---|---|
| **wiki.py ingest** | 산출물 → vault 노드 (결정론적 자동 변환) |
| **wiki.py query** | vault 내부 검색 |
| **wiki.py lint** | vault 정합성 (고아·끊긴링크·stale·frontmatter) |
| **lint.py LINT-MR** | 변형 미러 정합 (MR-6 wiki 오버레이 격리 + MR-7 외부 의존성 격리) |
| **design-review** | IA/A11Y/일관성 (wiki 와 다른 책임) |

---

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/commands/wiki.md` | 이 파일 — 슬래시 커맨드 진입점 |
| `.claude/bin/wiki.py` | 헬퍼 구현 (5 서브커맨드) |
| `.claude/bin/wiki-setup.sh` | 외부 도구 자동 설치 스크립트 |
| `wiki/` | Obsidian vault (git 추적 권장) |
| `wiki/index.md` | vault 콘텐츠 카탈로그 (wiki.py ingest 갱신) |
| `wiki/log.md` | ingest/lint/query 이벤트 로그 |

---

## 관련 참조

- ADR-007 결정 1 (외부 의존성 정책 예외 범위)
- ADR-007 결정 2 (vault 디렉토리 구조)
- ADR-007 결정 4 (5 서브커맨드)
- ADR-007 결정 5 (graceful degrade)
- ADR-007 결정 7 (F009 lint vs wiki lint 책임 분리)
- ADR-007 결정 8 (LINT-MR 6변형 확장 — MR-6/MR-7)
- `.claude/rules/coding-standards.md` 외부 의존성 정책 (변형별) 표
