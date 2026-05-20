# /project:lint — 거버넌스 정합성 헬스체크

하네스 거버넌스 산출물(feature_list · ADR · learnings · mirror)을 **읽기 전용**으로
검사한다. F007 design-review(UI/문서 디자인 품질)·F008 qa-browser(동적 E2E 검증)와
역할이 다르다 — lint는 **메타데이터 정합성**에 집중한다.

**HARD GATE: lint는 파일을 수정하지 않는다. BLOCK 수정은 Developer에 위임.**

## 사용법

```
/project:lint                                    # 전체 검사기 실행
/project:lint --strict                           # BLOCK 있으면 exit 1 (CI gate)
/project:lint --only=LINT-FL                     # 특정 검사기만
/project:lint --only=LINT-FL,LINT-AC             # 복수 지정
/project:lint --json                             # 머신용 JSON 출력
/project:lint report                             # 마지막 실행 결과 표시
/project:lint regenerate-index                   # docs/index.md 갱신 (세션 2)
```

직접 Python 실행:

```bash
python3 .claude/bin/lint.py check
python3 .claude/bin/lint.py check --strict
python3 .claude/bin/lint.py check --only=LINT-FL
python3 .claude/bin/lint.py check --json
python3 .claude/bin/lint.py report
```

## 검사기 목록

| ID | 설명 | BLOCK 기준 | CONCERN 기준 | INFO 기준 |
|---|---|---|---|---|
| **LINT-FL** | feature_list 정합성 | passes=true & status≠done, 존재하지 않는 dependency ID | 의존 feature가 passes=false인데 본인 in-progress 이상 | priority/estimated_sessions 누락 |
| **LINT-STALE** | 오래된 in-progress | 60일 이상 경과 | 30~60일 경과 | 0~30일 또는 checkpoint 없음 |
| **LINT-AC** | acceptance_criteria 누락·모호 | 배열 없거나 비어있음 | 모호 키워드 포함 ("잘 동작", "적절히" 등) | 단일 항목 (분해 부족 가능성) |
| LINT-ADR | ADR ↔ feature 연결성 | AC가 ADR 참조하는데 파일 없음 | ADR 본문 파일 경로 무효 | ADR 번호 gap |
| LINT-LEARN | learnings 모순 | tombstone 없이 정반대 insight 동일 key | confidence/source 미설정 | tombstone 비율 > 50% |
| LINT-MIRROR | 미러링 diff (4변형) | .claude/ vs claude.gstack/ diff 발생 | baseline Karpathy 파일 누락 | openai/.codex/ 변형 diff |

> **LINT-ADR / LINT-LEARN / LINT-MIRROR**: 세션 2에서 구현 예정.

## 라벨 의미 (F007 design-review 일관)

| 라벨 | 의미 | 액션 |
|---|---|---|
| **BLOCK** | 즉시 수정 필요 | Developer 에이전트에 1건씩 위임 |
| **CONCERN** | 권장 수정 | 사용자가 처리 여부 결정 |
| **INFO** | 정보성 | 액션 강제 없음 |
| **PASS** | 명시적 통과 | — |

## 다른 도구와의 역할 경계

| 영역 | Reviewer (코드 품질) | design-review (F007, IA/A11Y/일관성) | **lint (거버넌스)** | qa-browser (F008, E2E) |
|---|---|---|---|---|
| feature_list × passes | ❌ | ❌ | ✅ **LINT-FL 단독** | ❌ |
| stale 탐지 | ❌ | ❌ | ✅ **LINT-STALE 단독** | ❌ |
| learnings 모순 | ❌ | ❌ | ✅ **LINT-LEARN 단독** | ❌ |
| AC 누락·모호 | ❌ | ❌ | ✅ **LINT-AC 단독** | ❌ |
| 미러링 diff | ❌ | ✅ CON-S3 (디자인 차원) | ✅ LINT-MIRROR (거버넌스 차원) | ❌ |

**호출 순서 권장**: Reviewer → design-review → lint → qa-browser

## 실행 절차

```bash
# 1. 전체 검사 실행
python3 .claude/bin/lint.py check

# 2. 결과 확인 — BLOCK이 있으면 Developer에 1건씩 위임
#    (design-review 원자적 루프 패턴 동일)

# 3. CONCERN 목록 사용자에게 보고 → 처리 여부 결정

# 4. CI gate (옵셔널)
python3 .claude/bin/lint.py check --strict && echo "OK" || echo "BLOCK 있음"
```

## BLOCK 처리 루프 (세션 2에서 상세화 예정)

```
BLOCK 이슈가 있으면:
  for each BLOCK:
    1. Developer 에이전트에 1건만 위임:
       "수정 대상 1건: [BLOCK 상세, 파일:줄번호]
        다른 이슈는 건드리지 말 것"
    2. 수정 완료 후 재실행:
       python3 .claude/bin/lint.py check --only=LINT-FL  # 해당 검사기만
    3. PASS → 다음 BLOCK
```

## 출력 형식

### 기본 (human)

```
=== F009 Lint Report — 2026-05-20 14:30 ===

LINT-FL (feature_list 정합성)
| # | 라벨 | 항목 | 메시지 |
| 1 | PASS | F001 | passes×status 정합성 OK |
...

LINT-STALE (오래된 in-progress)
| # | 라벨 | 항목 | 메시지 |
| 1 | INFO | feature_list.json | in-progress feature 없음 — 검사 대상 0건 |

LINT-AC (acceptance_criteria 누락·모호)
| # | 라벨 | 항목 | 메시지 |
| 1 | PASS | F001 | acceptance_criteria 8건 — 모호 키워드 없음 |
...

요약: 0 BLOCK, 0 CONCERN, 1 INFO, 22 PASS
```

### --json 출력

```json
{
  "ts": "2026-05-20T14:30:00+09:00",
  "results": [
    {"id": "LINT-FL", "label": "PASS", "target": "F001", "message": "..."},
    ...
  ],
  "summary": {"BLOCK": 0, "CONCERN": 0, "INFO": 1, "PASS": 22}
}
```

## 안전성

- lint는 파일을 **읽기만** 한다 (Write/Edit 도구 사용 금지)
- 외부 패키지 없음 (Python stdlib only)
- 모든 검사기는 try/except → 부분 실패 시 해당 항목만 INFO로 보고, 다른 검사기 계속
- 최상위 try/except → 예기치 못한 예외도 stderr 로그 + exit 0 (hook-failure-tolerance)
- `--strict` 없으면 항상 exit 0

## 캐시

- 실행 결과는 `.claude/state/lint-last.json` 에 자동 저장 (atomic write)
- `report` 서브커맨드로 마지막 결과 요약 확인 가능 (세션 2에서 완전 구현)

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/commands/lint.md` | 이 파일 — 진입점·실행 절차 |
| `.claude/bin/lint.py` | 검사기 구현 (코어 + LINT-FL/STALE/AC) |
| `.claude/state/lint-last.json` | 마지막 실행 캐시 (자동 생성) |
| `docs/adr/ADR-004-lint-and-index.md` | 설계 결정 근거 |
