# LLM Wiki 지식 그래프 Vault

> **변형**: `claude.gstack.auto.design.wiki` 전용 — 다른 변형에는 없음.
> **외부 의존성**: Obsidian / qmd / Marp (선택적 — graceful degrade, 미설치 시 핵심 기능 동작).

이 디렉토리는 Karpathy LLM Wiki 패턴을 구현한 **Obsidian vault** 입니다.
프로젝트 산출물(feature/ADR/learning)을 `[[wikilink]]` 지식 그래프 노드로 변환하여
시간 흐름에 따른 합성 지식을 누적합니다.

---

## 빠른 시작

### 1. 외부 도구 설치 (선택)

```bash
# 외부 도구 자동 설치 (autonomous 모드에서 각 설치마다 사용자 승인)
bash .claude/bin/wiki-setup.sh

# 설치 결과 확인
python3 .claude/bin/wiki.py self
```

### 2. 산출물 → 노드 변환

```bash
# 모든 산출물 일괄 ingest (feature_list.json + docs/adr/*.md + learnings.jsonl)
python3 .claude/bin/wiki.py ingest all

# 또는 특정 소스만
python3 .claude/bin/wiki.py ingest features
python3 .claude/bin/wiki.py ingest adrs
python3 .claude/bin/wiki.py ingest learnings
```

### 3. Obsidian 으로 열기

1. Obsidian 앱 실행
2. "Open folder as vault" 클릭
3. 이 `wiki/` 디렉토리 선택
4. Graph view (Ctrl+G / Cmd+G) 로 지식 그래프 시각화

### 4. 검색

```bash
python3 .claude/bin/wiki.py query "지식 그래프"
# qmd 설치 시: BM25 검색
# 미설치 시: stdlib grep fallback (자동 감지)
```

### 5. vault 정합성 점검

```bash
python3 .claude/bin/wiki.py lint
```

---

## 디렉토리 구조

```
wiki/
├── README.md          # 이 파일 (vault 사용법 안내)
├── index.md           # 콘텐츠 카탈로그 (wiki.py ingest 가 자동 갱신)
├── log.md             # 시간순 ingest/query/lint 로그
├── features/          # feature_list.json 노드 (F001.md, F002.md, ...)
├── adrs/              # docs/adr/*.md 노드 (ADR-001.md, ...)
├── learnings/         # learnings.jsonl 노드 (YYYY-MM-DD-slug.md)
├── pages/             # 사용자가 직접 작성한 wiki 페이지
├── sources/           # 외부 자료 노드 (논문, 가스트, 회의록 등)
└── .obsidian/         # Obsidian 설정 (graph view 등)
```

---

## 노드 frontmatter 스키마

모든 노드 `.md` 파일은 다음 frontmatter 를 가진다:

```yaml
---
type: feature | adr | learning | page | source
id: <노드 ID = 파일명>
created: 2026-06-03T09:00:00+09:00
source_ref: feature_list.json#F001   # 원본 산출물 경로 (Obsidian 외부 SSoT)
tags: [phase-8, wiki, knowledge-graph]
related: [F002, ADR-007]             # 엣지 명시 (frontmatter 1차 표현)
status: draft | active | stale       # wiki.py lint 대상
---
```

엣지 표현은 이중으로:
1. frontmatter `related: [...]` — 결정론적 엣지 (wiki.py ingest 자동 생성)
2. 본문 `[[wikilink]]` — Obsidian graph view 표시 + 자유 텍스트 인용

---

## 외부 도구 미설치 시 동작 (graceful degrade)

| 기능 | 외부 도구 없을 때 | 외부 도구 있을 때 |
|---|---|---|
| ingest (노드 생성) | stdlib only (완전 동작) | 동일 |
| query (검색) | stdlib grep fallback (동작) | qmd BM25/vector 검색 |
| graph (시각화) | mermaid 텍스트 출력 (동작) | Obsidian graph view |
| lint (정합성) | stdlib only (완전 동작) | 동일 |
| 슬라이드 export | .md 직접 제공 | Marp CLI 변환 |

핵심 기능(ingest/lint/graph + grep query)은 외부 도구 없이도 **완전히 동작**합니다.

---

## 참고

- **ADR-007**: `docs/adr/ADR-007-llm-wiki-knowledge-graph.md` — 설계 결정 9개
- **wiki.py**: `.claude/bin/wiki.py` — 헬퍼 스크립트 (ingest/query/lint/graph/self)
- **wiki-setup.sh**: `.claude/bin/wiki-setup.sh` — 외부 도구 자동 설치 (세션 2)
- **Karpathy LLM Wiki 가스트**: 이 vault 의 정신적 원본
