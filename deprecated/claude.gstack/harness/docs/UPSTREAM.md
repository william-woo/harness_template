---
name: gstack-upstream
type: provenance
upstream_repo: git@github.com:garrytan/gstack.git
upstream_branch: main
upstream_commit: 62091639
upstream_version: v1.12.2.0
fetched_at: 2026-04-25T00:52:23+09:00
ingested_phases: [Phase 1, Phase 2, Phase 3]
ingested_by: harness_update_agent F001-F005
license_check_status: pending
last_audit: 2026-05-27
---

# Upstream Provenance — gstack

`claude.gstack/` 변형은 외부 프로젝트 **gstack** (`garrytan/gstack`)의 워크플로우 스킬 패턴을
이 하네스 컨텍스트로 **번역·재구현**한 결과물이다. 코드를 그대로 복사한 것은 아니며,
설계 아이디어와 명명 컨벤션을 차용했다.

## 적용된 gstack 버전 (스냅샷)

| 항목 | 값 |
|---|---|
| 원본 저장소 | `git@github.com:garrytan/gstack.git` |
| 브랜치 | `main` |
| 커밋 SHA | `62091639` |
| 버전 태그 | **v1.12.2.0** |
| 커밋 제목 | `fix: /setup-gbrain day-two fixes (MCP scope, version parse, gh repo create order, smoke test) (#1187)` |
| Fetch 일자 | 2026-04-25 KST |

로컬 참조 클론은 메인 프로젝트의 `src/gstack/` 디렉토리에 있다 (단, 이 디렉토리는 별도 git이며
`harness_template`/`claude.gstack`에는 미포함).

## 이식 범위 (Phase ↔ gstack 스킬 매핑)

| 하네스 Phase / Feature | gstack 원본 패턴 | 비고 |
|---|---|---|
| **F001** (Phase 1) — Safety + Learn + Context | `/careful`, `/freeze`, `/unfreeze`, `/guard`, `/learn`, context save/restore | 글로벌 상태(`$HOME/.gstack`) 대신 `.claude/state/` 프로젝트 로컬 채택 |
| **F002** (Phase 2) — Autoplan | `/autoplan` (Planner→Architect→Reviewer 체인) | CEO/Design/DevEx Review 선택지는 단순화 (스킵) |
| **F003** (Phase 2) — Ship Dashboard | `/ship` | git diff --stat 기반 분류 그대로 차용 |
| **F004** (Phase 2) — Retro + Analytics | `/retro` | analytics.jsonl 스키마는 독자 정의 |
| **F005** (Phase 3) — Brain Local | gstack의 GBrain (PGLite/Supabase 기반) | Python stdlib `sqlite3` 로 대체 — 외부 의존성 0 |

## 이식하지 않은 것 (의도된 비차용)

- **gstack SKILL.md preamble**: 첫 100+ 줄의 글로벌 상태/telemetry/upgrade 체크 로직.
  우리는 실제 스킬 로직만 번역해 가져왔다.
- **gstack 의존성 도구**: PGLite, Supabase, bun, Chrome MCP 등. 우리 정책은 외부 의존성 0.
- **/setup-gbrain, /gstack-upgrade**: 우리는 자기 자신을 배포하는 메타 하네스라 셋업/업그레이드
  플로우가 다르다.
- **/design-shotgun, /design-html (GPT Image API)**: F007 단계 1 범위에서 제외 (다음 phase).

## 동기화 정책

이 파일은 **수동 갱신**한다. 자동 sync 메커니즘 없음.

### gstack 업스트림 변경 추적이 필요해질 때

1. `src/gstack/` 에서 `git pull` (또는 fresh clone)
2. 새 commit/version 확인
3. 새 패턴/스킬 중 우리 컨텍스트에 적용 가능한 것 검토 (Planner)
4. 적용 결정 시 별도 Feature로 등록 (예: F010+)
5. 이 파일의 frontmatter `upstream_commit`, `upstream_version`, `last_audit` 갱신
6. ingested_phases / ingested_by 에 새 Feature 추가

### 라이선스 점검 (`license_check_status: pending`)

원본 gstack의 라이선스를 아직 명시적으로 점검하지 않았다. 외부 공개·배포가 임박하면
다음 작업이 필요하다:

- gstack 저장소의 `LICENSE` 파일 확인
- 차용 범위(아이디어/명명 vs 코드)에 따른 attribution 결정
- 필요 시 `THIRD_PARTY_NOTICES.md` 추가

## 관련 참조

- 메인 프로젝트 `CLAUDE.md` — `harness_template 동기화 정책` 섹션
- `feature_list.json` — F001 description 에 "gstack에서 ... 패턴을 추출" 명시
- `.claude/state/learnings.jsonl` — `gstack-preamble-bloat-skip` 학습 (이식 정책 근거)
- `src/gstack/` — 참조용 로컬 클론 (별도 git, 미러 제외)
- `docs/adr/ADR-000-template.md` — 후속 gstack 패턴 채택 시 ADR 작성 양식
