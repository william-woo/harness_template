# /project:brain-sync — 현재 프로젝트를 영구 지식베이스에 동기화

`.claude/state/learnings.jsonl`, `feature_list.json`, `docs/adr/*.md` 를 읽어
사용자 홈의 `~/.harness/brain.db` (SQLite, Python stdlib만 사용)에 동기화한다.

여러 프로젝트를 오가며 작업할 때 cross-project 검색을 위한 인프라.

**HARD GATE: 코드 수정 없음. 읽기 전용 sync 만 수행.**

## 사용

```
/project:brain-sync                        # 현재 디렉토리 sync
/project:brain-sync --project-dir <path>   # 특정 디렉토리
```

## 실행

```bash
python3 .claude/bin/brain.py sync
```

## 동작

1. **프로젝트 식별**: `git remote get-url origin` 의 repo 이름, 없으면 디렉토리 basename
2. **projects 테이블 upsert**: slug, path, remote_url, last_seen 갱신
3. **learnings**: 모든 entry 를 INSERT OR REPLACE. `tombstone` 엔트리는 건너뜀
4. **features**: feature_list.json 의 모든 항목을 INSERT OR REPLACE
5. **ADRs**: `docs/adr/ADR-*.md` 파일명에서 ID 추출, 본문에서 title/status/decision 파싱

기존 데이터를 덮어쓰지만, 다른 프로젝트의 데이터는 영향 없음 (project_slug 격리).

## 출력 예시

```
📦 프로젝트: harness_update_agent  (git@github.com:.../harness_update_agent.git)
  • learnings: 18 (tombstone 제외 0)
  • features:  8
  • ADRs:      0
```

## 호출 시점

- **Phase 완료 직후**: Phase 1·2·3 등 큰 작업 마치면 한 번 sync
- **Feature done 처리 후**: feature_list 업데이트 후 sync 하면 stats 정확
- **세션 종료 전**: handoff 와 함께 묶어도 됨 (선택)

자동 호출은 하지 않는다 (handoff·learn add 가 매번 sync 하면 무겁다).
사용자가 명시적으로 부를 때만.

## 안전성

- DB 위치 `~/.harness/brain.db` 는 **git 미포함** (사용자별 머신 로컬)
- sync 실패해도 호출자 차단하지 않음 (`brain.py` 가 항상 exit 0)
- 동일 프로젝트 재 sync 시 idempotent (PK: project_slug+ts+key 등)
- `~/.harness/` 디렉토리가 없으면 자동 생성

## 체크리스트

- [ ] `.claude/state/learnings.jsonl` 존재 (없으면 0건만 sync 됨)
- [ ] `feature_list.json` 유효한 JSON 배열
- [ ] sync 후 `/project:brain-stats` 로 카운트 확인
