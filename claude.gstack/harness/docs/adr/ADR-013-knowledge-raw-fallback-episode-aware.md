# ADR-013 Knowledge raw-fallback 의 episode-aware 화 — gaps-and-islands 의 events CTE 이식

| 항목 | 내용 |
|---|---|
| 상태 | Proposed |
| 날짜 | 2026-06-10 |
| 작성자 | Architect 에이전트 |
| 관련 Feature | F033 |
| 관련 ADR | ADR-005 (formula 보안 화이트리스트), ADR-006 (Knowledge 변수 치환), ADR-008 (정의 파라미터화), ADR-011 (vehicle/user 필터 — 무회귀 대상), **ADR-012 (F030 episode 검출 — 본 ADR 의 알고리즘 원본)** |

> **번호 결정**: ADR-011=분석조건확장, ADR-012=F030 episode 가 이미 점유. 다음 가용 번호인 **ADR-013** 부여.
> **저장 위치 확인**: `docs/adr/` (하네스 루트). 동일 위치에 ADR-001~ADR-012 존재 확인 — git tracked.
> **본 ADR 의 범위**: F033 의 ② "Knowledge raw-fallback 의 episode-aware 화" 만 다룬다. ① "Event 페이지 기본값 point→episode 전환" 은 UI 기본값 1줄 변경이라 설계 산출물 불필요 — Developer 가 acceptance_criteria 1번 항목 그대로 구현.

---

## 1. 컨텍스트

### 1.1 현재 동작 (확인됨)

`knowledge_calculator.calculate()` 가 Event 변수 (`{event}_횟수`, `{event}_시간`) 를 산출하는 두 경로:

| 경로 | 트리거 | duration_sec 의미 | detection_mode 반영 |
|---|---|---|---|
| **A. 저장 parquet** | `event_root/<name>/*.parquet` 존재 + 메타 컬럼 정상 | parquet 안의 값 (point=1, episode=실제 지속시간) | **반영됨** — F030/ADR-012 가 저장 시점에 모드 적용 |
| **B. raw fallback** | parquet 없음 + 정의 JSON 존재 + `definitions_root` 인자 전달됨 | **1 (하드코딩)** — `_build_event_raw_fallback()` L271-279 | **미반영** — 정의가 episode 여도 행 단위 계수 |

### 1.2 문제

F030/ADR-012 가 episode 검출을 정의 스키마 + 저장 경로까지 구현했지만, **Knowledge 의 raw fallback 경로는 여전히 point 방식** 으로만 동작한다. 이는 다음 상황에서 명백한 오계수를 만든다:

1. 사용자가 episode 정의를 만들고 "정의만 저장" (event parquet 미생성) 한 직후 Knowledge 페이지에서 해당 정의를 참조 → fallback 진입 → 매칭 raw 행마다 1건씩 카운트되어 **샘플레이트만큼 부풀려진 횟수** + **항상 `횟수 == 시간`** 인 비정상 결과.
2. ADR-012 §7 의 v2 후속 작업 항목 ("Raw fallback 경로의 episode 정확도") 그대로 — F033 가 이를 해소한다.

### 1.3 코드 위치 (앵커)

| 파일 | 핵심 심볼 | 줄 |
|---|---|---|
| `core/knowledge_calculator.py` | `_build_event_raw_fallback()` | L183~281 |
| `core/knowledge_calculator.py` | `_build_sql()` events CTE 조립 (raw fallback 진입 분기) | L477~514 |
| `core/knowledge_calculator.py` | `_build_sql_raw_only()` (raw-only 경로 — 본 ADR 영향 없음) | L671~836 |
| `core/episode_detector.py` | `_build_episode_sql()` (gaps-and-islands 5단 CTE — **원본**) | L123~228 |
| `core/episode_detector.py` | `_suggest_peak_agg()` (peak_agg 자동 추론) | L87~120 |
| `core/event_definitions.py` | `load_definition()`, `_validate_definition_schema()` (episode 스키마) | — |

### 1.4 events CTE 의 계약 (knowledge_calculator 가 fallback subquery 에 요구하는 출력)

```sql
SELECT
  '<event_name>'    AS event_type,    -- 상수 리터럴
  vehicle_id        AS vehicle_id,
  "<timestamp_col>" AS "<timestamp_col>",
  <bigint or num>   AS duration_sec
FROM ...
```

후속 SELECT 절에서:
- `{event}_횟수 = COUNT(CASE WHEN e.event_type='<name>' THEN 1 END)`
- `{event}_시간 = SUM(CASE WHEN e.event_type='<name>' THEN e.duration_sec END)`

→ episode 모드에서는 **에피소드당 1행 emit + duration_sec=실제 지속시간** 이면 두 식이 자동 정상화된다.

---

## 2. 결정 (요약)

`_build_event_raw_fallback()` 을 `detection_mode` 분기 함수로 만들고, episode 분기는 ADR-012 의 gaps-and-islands 5단 CTE 를 **events CTE 의 UNION ALL 안에 끼울 수 있는 하나의 SELECT subquery** 로 인라인 이식한다.

| 결정 항목 | 채택 안 |
|---|---|
| 분기 지점 | `_build_event_raw_fallback()` 입구에서 정의의 `detection_mode` 를 보고 point/episode 빌더 dispatch. point 는 기존 본문 그대로. |
| episode SQL 형태 | gaps-and-islands 5단 CTE 를 **인라인 서브쿼리** 로 감싸 단일 SELECT 로 표현 (즉 `SELECT '<name>' AS event_type, vehicle_id, "<ts>", duration_sec FROM (WITH matched AS … SELECT …) ep`). DuckDB 는 inline `WITH` 를 지원하므로 가능. |
| 알고리즘 재사용 | `episode_detector._build_episode_sql()` 의 SQL **본문은 그대로 재사용** — 다만 events CTE 계약에 맞게 (a) `start_ts → "<ts>"`, `duration_sec→duration_sec`, 나머지 컬럼 (peak/sample/end_ts/output) 은 outer SELECT 에서 드롭, (b) `output_cols=[]`, `has_user_id=False` 로 호출 (Knowledge fallback 은 peak/output 불필요). |
| 코드 위치 | **knowledge_calculator 내부에 신규 private helper** `_build_event_raw_fallback_episode()` 추가. `episode_detector._build_episode_sql()` 을 호출하여 SQL 골격을 받고, 그 위에 outer SELECT 를 씌운다. 모듈 간 결합도는 낮게 (Helper 1개 호출만). 별도 모듈로 분리하지 않는다 (이 SQL 은 Knowledge 의 events CTE 계약에 종속). |
| 파라미터 바인딩 순서 | episode_detector 의 바인딩 순서 `[glob, start, end_exclusive, *vuf_params, max_gap_sec, min_duration_sec]` 를 그대로 따른다 — UNION ALL 의 각 SELECT subquery 가 독립적으로 자기 params 를 갖고, 전체 SQL 의 `?` 순서는 events 조각 합성 순서와 일치하도록 호출자가 `event_params.extend(_fallback_param)` 한다 (기존 로직 그대로 동작). |
| episode 파라미터 소싱 | 정의 JSON 의 `episode` 객체에서 그대로 가져옴: `min_duration_sec`, `max_gap_sec`, `peak_column`, `peak_agg`. 누락 시 ADR-012 기본값 (0.0 / 1.0 / `_suggest_peak_agg`). `peak_column` 누락이면 **fallback 더미** 로 전환 (Knowledge 산출이 차단되지는 않음 — 0건). |
| `peak_column` 처리 | episode SQL 은 peak 컬럼을 SELECT 해야 하지만, Knowledge 출력엔 불필요. **그대로 SELECT 한 뒤 outer 에서 드롭**. peak_column 검증 (`validate_column_name`) 은 유지. |
| Phase 2 파라미터 치환 | 기존 point fallback 과 동일하게 `substitute_parameters` 후 `validate_where_expr` 재검증. 미치환 placeholder 잔존이면 더미 (`WHERE FALSE` SELECT) 로 폴백. |
| alias 치환 | 기존 point fallback 과 동일하게 `column_aliases.resolve()` 로 `where_expr` 치환 + `peak_column` 단일 식별자 매핑 (`episode_detector.detect_episodes` 와 동일 패턴). |
| vehicle/user 필터 | ADR-011 의 `_build_vehicle_user_filter()` 재사용 — matched CTE 내 `extra_where` 부분에 IN 절 삽입. 기존 point fallback 과 동일 정책. |
| 보안 | F004 화이트리스트 (`validate_where_expr`) + `validate_column_name` (timestamp/peak/output) + 파라미터 `?` 바인딩 (max_gap/min_duration/glob/start/end/vuf) 모두 유지. ADR-005 무회귀. |
| 무회귀 경계 | (a) point 정의 → 기존 단일 SELECT 그대로. (b) 저장 parquet 존재 → fallback 미진입 (기존). (c) `detection_mode` 누락 → point. (d) `definitions_root=None` → 기존 더미 SELECT. (e) `episode` 객체 누락/`peak_column` 누락 → 더미 SELECT (계산 차단하지 않고 0건 emit). |
| 테스트 전략 | 합성 raw + episode 정의(미저장) → Knowledge 산출 검증 + point 정의 무회귀 + max_gap 병합·min_duration 필터가 Knowledge 계수에 반영되는지 검증. |

---

## 3. 상세 결정

### 3.1 dispatch 지점

기존 `_build_event_raw_fallback()` 시그니처는 **유지** (event_name, raw_glob, start, end_exclusive, timestamp_col, aliases, definitions_root, vehicle_ids, user_ids). 본문 시작부에 detection_mode 분기 추가:

```python
def _build_event_raw_fallback(...) -> tuple[str, list]:
    # ... 기존 dummy 변수 정의 ...
    try:
        defn = load_definition(event_name, definitions_root)
    except (FileNotFoundError, ValueError):
        return dummy, []

    det_mode = defn.get("detection_mode", "point")  # ← 신규 분기

    if det_mode == "episode":
        return _build_event_raw_fallback_episode(
            event_name=event_name,
            defn=defn,
            raw_glob=raw_glob,
            start=start,
            end_exclusive=end_exclusive,
            timestamp_col=timestamp_col,
            aliases=aliases,
            vehicle_ids=vehicle_ids,
            user_ids=user_ids,
        )

    # ── 기존 point 경로 (변경 없음) ────────────────────────────
    event_formula: str = defn.get("formula", "")
    if not event_formula.strip():
        return dummy, []
    # ... 기존 본문 그대로 ...
```

**중요**: episode 분기 진입 시 `defn` 자체를 helper 에 넘긴다 (formula, parameters, episode 객체를 한 함수 안에서 모두 다룸).

### 3.2 episode fallback helper 시그니처

```python
def _build_event_raw_fallback_episode(
    *,
    event_name: str,
    defn: dict,                       # load_definition 결과 (episode 객체 포함)
    raw_glob: str,
    start: str,
    end_exclusive: str,
    timestamp_col: str,
    aliases: dict[str, str] | None,
    vehicle_ids: list | None,
    user_ids: list | None,
) -> tuple[str, list]:
    """episode 정의를 raw 에 직접 적용해 events CTE 호환 SELECT 조각을 반환.

    Returns:
        (sql_fragment, param_list)
            sql_fragment: outer SELECT 가 episode subquery 를 감싼 단일 SELECT 문자열.
                          UNION ALL 의 한 조각으로 직접 삽입 가능.
            param_list:   [raw_glob, start, end_exclusive, *vuf_params, max_gap_sec, min_duration_sec]
                          (episode_detector._build_episode_sql 의 바인딩 순서 그대로)
        episode/peak_column 누락 또는 formula 검증 실패 시 (dummy, []) 반환.
    """
```

### 3.3 episode SQL 골격

`episode_detector._build_episode_sql()` 의 5단 CTE 를 **그대로 호출** 하되 다음 옵션으로:

| 옵션 | 값 | 사유 |
|---|---|---|
| `glob_str` | raw_glob | (호출자 전달) |
| `resolved_expr` | episode WHERE — formula (parameters 치환 + validate_where_expr 재검증 + alias resolve 완료) | point fallback 과 동일 패턴 |
| `timestamp_col` | 인자 그대로 | events CTE 의 timestamp 컬럼명 유지 |
| `peak_column` | `defn["episode"]["peak_column"]` (alias resolve 적용) | episode_detector 가 요구 |
| `peak_agg` | `defn["episode"].get("peak_agg")` 또는 `_suggest_peak_agg(formula, peak_column)` | ADR-012 §3.3 |
| `output_cols` | `None` 또는 `[]` | Knowledge fallback 은 peak-row 추가 컬럼 불필요 |
| `has_user_id` | `False` (보수적) | Knowledge events CTE 는 vehicle_id 만 요구. user 집계 경로는 raw-only 로 빠지므로 fallback events 에 user_id 불필요 (3.7 무회귀 항목 참조) |

그 결과 `_build_episode_sql` 이 반환하는 SQL 은 `episodes` 라는 마지막 CTE 까지 정의한 뒤 `SELECT * FROM episodes ORDER BY vehicle_id, start_ts` 로 끝난다. 이걸 그대로 subquery 로 감싸 events CTE 의 한 조각을 만든다:

```sql
SELECT
  '<event_name>' AS event_type,
  ep.vehicle_id  AS vehicle_id,
  ep.start_ts    AS "<timestamp_col>",
  ep.duration_sec AS duration_sec
FROM (
  WITH
    matched AS ( … ),
    gapped AS ( … ),
    flagged AS ( … ),
    numbered AS ( … ),
    episodes AS (
      SELECT vehicle_id,
             MIN(ts) AS start_ts, MAX(ts) AS end_ts,
             CAST(EPOCH(MAX(ts)) - EPOCH(MIN(ts)) AS BIGINT) AS duration_sec,
             MAX(peak_val) AS peak_value,
             COUNT(*) AS sample_count
      FROM numbered
      GROUP BY vehicle_id, episode_id
      HAVING CAST(EPOCH(MAX(ts)) - EPOCH(MIN(ts)) AS BIGINT) >= ?
    )
  SELECT * FROM episodes
) ep
```

**키 트릭**: DuckDB 는 `FROM (WITH … SELECT …) alias` 형태의 **inline WITH** 를 허용한다. 따라서 events CTE 의 UNION ALL 안에 episode 의 5단 CTE 가 통째로 들어가도 문법 위배 없음. (검증: DuckDB SQL grammar 의 `table_expression` 에 inline `WITH … SELECT` 허용 — 동일 패턴은 기존 코드베이스 `_build_sql_raw_only` 의 total 경로에서 `FROM (SELECT … FROM raw_agg)` 로 이미 사용 중.)

> **대안 비교**: outer scope 의 `WITH events AS (SELECT … UNION ALL SELECT …)` 위에 별도 CTE (예: `WITH ep_acc AS (…), events AS (… UNION ALL SELECT … FROM ep_acc)`) 를 두는 방법도 가능하지만, 다음 사유로 **인라인** 채택:
> - knowledge_calculator 의 events CTE 조립이 "각 event 가 자기 조각을 만들어 UNION ALL 한다" 패턴이라 helper 가 **자체 완결된 단일 SELECT** 를 반환하는 것이 결합도 최소.
> - 별도 CTE 방식은 여러 episode event 가 있을 때 이름 충돌 (`ep_acc_<name>`) 회피 로직이 추가로 필요 → 복잡도 증가.
> - DuckDB 의 inline WITH 는 같은 쿼리 안에서 여러 번 등장해도 독립 스코프이므로 충돌 없음.

### 3.4 outer SELECT 의 ORDER BY 처리

`_build_episode_sql` 의 마지막 `SELECT * FROM episodes ORDER BY vehicle_id, start_ts` 는 events CTE 입장에서는 불필요 (UNION ALL 후 어차피 GROUP BY 됨). 그러나 SQL 표준상 `(SELECT … ORDER BY …)` 가 subquery 안에 있어도 DuckDB 가 거부하지 않으므로 **그대로 둔다** — `_build_episode_sql` 본문을 수정하지 않는다 (회귀 위험 0). 성능 차이는 episode 수 (수십~수백 수준) 라 무시 가능.

### 3.5 컬럼 매핑 (episode 출력 → events CTE 계약)

| episode_detector 출력 컬럼 | events CTE 계약 컬럼 | 처리 |
|---|---|---|
| `vehicle_id` | `vehicle_id` | 그대로 |
| `start_ts` | `"<timestamp_col>"` (예: `"timestamp"`) | `ep.start_ts AS "<ts>"` 별칭 부여 |
| `end_ts` | — | outer SELECT 에서 미선택 (드롭) |
| `duration_sec` | `duration_sec` | 그대로 (BIGINT) |
| `peak_value` | — | 드롭 |
| `sample_count` | — | 드롭 |

> events CTE 가 사용하는 컬럼은 후속 SELECT 의 `e.event_type / e.vehicle_id / e."<ts>" / e.duration_sec` 만이므로 위 4개로 충분.

### 3.6 파라미터 바인딩 순서 + 다중 event UNION ALL

여러 event 가 UNION ALL 될 때 (point + episode 혼합 또는 episode 다수), 각 fallback helper 의 반환값 `(sql_fragment, param_list)` 가 `event_params.extend(_fallback_param)` 으로 합쳐진다 (`_build_sql` L482-494 기존 로직). DuckDB 는 SQL 전체의 `?` 를 등장 순서대로 바인딩하므로:

```
events 조각 1 (point) params:    [glob, start, end_exclusive, *vuf_p]
events 조각 2 (episode) params:  [glob, start, end_exclusive, *vuf_p, max_gap, min_duration]
events 조각 3 (저장 parquet) params: [paths_list]
...
raw_agg params (있을 때):        [glob, start, end_exclusive, *vuf_p]
event filter params (e WHERE):   [start, end_exclusive, *evt_vuf_p]
```

→ 각 helper 가 자기 조각의 `?` 와 정확히 같은 길이/순서의 param list 를 반환하면 합산은 안전. **본 ADR 의 episode helper 는 episode_detector 의 바인딩 순서를 그대로 따른다** (예측 가능, 회귀 위험 0):

```
[raw_glob, start, end_exclusive, *vuf_params, max_gap_sec, min_duration_sec]
```

### 3.7 무회귀 경계 (명시)

| 시나리오 | 동작 | 보장 방식 |
|---|---|---|
| 저장 parquet 존재 | fallback 미진입 (`event_files[name]` 비어있지 않음) | `_build_sql` L477 `if not paths:` 분기 — 변경 없음 |
| `definitions_root=None` | 더미 SELECT (`WHERE FALSE`) | `_build_sql` L494-502 분기 — 변경 없음 |
| 정의 JSON 없음 (`FileNotFoundError`/`ValueError` from `load_definition`) | 더미 SELECT | `_build_event_raw_fallback` 본문 첫 try/except — 변경 없음 |
| 정의 JSON 의 `detection_mode` 누락 | point 분기 (`defn.get("detection_mode", "point")`) → 기존 본문 그대로 | 본 ADR §3.1 dispatch |
| 정의 JSON `detection_mode == "point"` | 기존 본문 그대로 | 동일 |
| 정의 JSON `detection_mode == "episode"` 인데 `episode` 객체 누락 | 더미 SELECT (계산 차단하지 않음) + 로그성 주석 — `_build_event_raw_fallback_episode` 가 (dummy, []) 반환 | 신규 helper 본문 |
| 정의 JSON `episode.peak_column` 누락 | 더미 SELECT | 동일 |
| 정의 JSON `formula` 가 빈 문자열 | 더미 SELECT | 신규 helper 에서 가드 |
| `formula` 가 `validate_where_expr` 실패 (치환 후 재검증) | 더미 SELECT | point 와 동일 패턴 |
| `aggregation == "user"` + has_raw_sources | raw-only 경로 (events CTE 미사용) | `_build_sql` L432-446 분기 — fallback 미진입, 본 ADR 영향 없음 |
| 기존 point fallback 의 모든 호출 경로 | 변경 없음 | dispatch 후 본문 동일 |
| event parquet 의 episode 모드 (저장 경로) | 변경 없음 | F030 가 이미 처리, fallback 미진입 |

### 3.8 보안 매트릭스 (회귀 없음)

| 항목 | 검증 함수 | 변경 |
|---|---|---|
| `formula` (where_expr) | `validate_where_expr` (F004 화이트리스트) — 치환 전 + 치환 후 2회 | 변경 없음 (point 와 동일 패턴 적용) |
| `peak_column` | `validate_column_name` | episode helper 가 episode_detector 호출 전에 호출 |
| `timestamp_col` | `validate_column_name` | knowledge_calculator 진입부에서 이미 이루어지지 않으면 helper 에서 추가 (현재 코드는 부재 — Developer 가 추가 권장. 단 `_build_event_raw_fallback` 도 마찬가지로 없음 → 변경 없이 두는 것도 가능. 권장: helper 에서 1줄 추가) |
| `min_duration_sec` / `max_gap_sec` | `validate_episode_params` (episode_detector) | helper 가 episode_detector 진입 전에 호출 |
| `peak_agg` | `{"max","min"}` 화이트리스트 | 동일 |
| `vehicle_ids` / `user_ids` | `?` placeholder 바인딩 | `_build_vehicle_user_filter` 재사용 |
| `raw_glob` | 호출자가 `allowed_raw_root` 로 `resolve_in_root` 통과 후 전달 | 변경 없음 |
| Phase 2 parameters 미치환 잔존 | `_PLACEHOLDER_RE.search` 차단 | point 와 동일 |

### 3.9 raw-only 경로와의 관계 (영향 없음)

`_build_sql_raw_only()` 는 **events CTE 자체를 만들지 않는다** — `source_events` 가 비어있거나 user 집계일 때 `raw_agg` 단독 SELECT 경로다. event_refs 가 formula 에 있어도 `_zero_out_event_exprs` 로 0 처리. 따라서:

- raw-only 경로에서 episode 정의 변수 (`{event}_횟수`, `{event}_시간`) 는 **여전히 0** (기존 동작 유지).
- 본 ADR 은 events CTE 경로 (B 분기) 의 fallback subquery 만 episode-aware 하게 만든다.
- 향후 raw-only 경로에서도 episode 평가가 필요해지면 별도 ADR 로 다룬다 (현 F033 범위 외).

### 3.10 episode 파라미터 기본값 정책

정의 JSON 의 `episode` 객체에서 누락된 필드는 다음 순서로 fallback 진입 시점에 결정:

| 필드 | 누락 시 처리 |
|---|---|
| `min_duration_sec` | `0.0` (ADR-012 기본) |
| `max_gap_sec` | `1.0` (ADR-012 기본) |
| `peak_column` | **더미 SELECT 로 폴백** — episode 의 핵심 정의가 부재한 셈이므로 무의미한 산출보다 0건 emit 이 안전. UI 단에서 episode 모드 저장 시 `peak_column` 필수화 (ADR-012 §3.1 #4) |
| `peak_agg` | `defn["episode"].get("peak_agg")` 또는 `_suggest_peak_agg(formula, peak_column)` 자동 추론 |

→ 이 정책은 ADR-012 와 일관 (UI 가 누락된 필드를 default 로 채워 저장하기 때문에 실제로는 모두 채워져 있을 것이지만, 방어적 코드 유지).

---

## 4. 대안 검토

| 대안 | 장점 | 단점 | 결론 |
|---|---|---|---|
| **A. 인라인 5단 CTE subquery (채택)** | events CTE 계약 그대로 유지. helper 1개 추가만으로 끝. 다른 event 와 독립 스코프 | events CTE 안에 큰 SQL 덩어리가 들어가 디버깅 시 가독성 다소 떨어짐 — 단계별 주석으로 완화 | ✅ |
| B. outer scope 에 별도 CTE (`ep_<name>` 등) | 가독성 약간 우수 | 다중 episode event 시 CTE 이름 충돌 회피 로직 필요. `_build_sql` 의 CTE 합성 코드 변경 폭이 커짐 (회귀 위험 증가) | ❌ |
| C. Python 단에서 `detect_episodes()` 를 미리 실행하고 결과 DataFrame 을 events CTE 에 register 한 임시 view 로 주입 | SQL 단순, 디버깅 쉬움 | DuckDB 세션이 `calculate()` 안에서만 생기므로 register 타이밍 복잡. 메모리 소비 ↑ (모든 episode 결과를 Python 으로 가져옴). 다른 event 와의 UNION ALL 도 어색. | ❌ |
| D. episode_detector 에 `build_events_cte_fragment(event_name, ...)` 같은 신규 public API 추가 | knowledge_calculator 가 SQL 조립을 안 함 — 책임 분리 | episode_detector 가 knowledge events CTE 계약을 알게 되어 역의존 발생. 한쪽이 변하면 양쪽 깨짐. | ❌ |
| E. raw-fallback 전체를 폐기하고 "저장 후 사용" 강제 | 일관성 ↑ | UX 후퇴. F033 acceptance "저장 여부와 무관하게 검출 모드 반영" 위배. | ❌ |

---

## 5. 결과

### 5.1 긍정적 영향

- episode 정의의 Knowledge `{event}_횟수 = 에피소드 수`, `{event}_시간 = duration 합` 이 **저장 여부와 무관하게** 정상 산출.
- 사용자가 "정의만 저장" 한 직후에도 Knowledge 미리보기가 직관과 일치.
- ADR-012 의 v2 후속 항목 (Raw fallback 정확도) 완료.
- F030 의 episode 모델이 시스템 전체로 일관됨.

### 5.2 부정적 영향 / 트레이드오프

- DuckDB 가 합성된 거대한 SQL 을 처리 — 다중 episode event 가 동시에 fallback 진입하면 SQL 본문 길이 증가. 그러나 events CTE 의 합성 SQL 은 어차피 UNION ALL 로 늘어나는 구조 (기존부터). 성능 prof: episode 검출이 raw 풀스캔 1회 + window 함수 1회이므로 point fallback (단순 WHERE) 대비 약간 더 무겁지만, 같은 raw glob 을 N event 가 각자 스캔하는 구조는 기존과 동일.
- 디버깅 시 SQL 가독성 — 단계별 주석 + helper 의 docstring 으로 완화.

### 5.3 무회규 보장 항목

| 항목 | 무회규 보장 |
|---|---|
| `calculate()` 시그니처 | 변경 없음 |
| `_build_event_raw_fallback()` 시그니처 | 변경 없음 (분기 추가만) |
| `_build_sql()` 본문 | 변경 없음 (helper 호출은 기존 위치 그대로) |
| `_build_sql_raw_only()` 본문 | 변경 없음 |
| `episode_detector._build_episode_sql()` | 변경 없음 (호출만 추가) |
| point 정의의 Knowledge 산출 결과 | 변경 없음 (분기 후 본문 동일) |
| 저장 parquet 경로의 Knowledge 산출 결과 | 변경 없음 (fallback 미진입) |
| `definitions_root=None` 경로 | 변경 없음 (기존 더미 유지) |
| 기존 pytest suite | 회귀 0 — 신규 테스트만 추가 |
| 보안 화이트리스트 (F004, ADR-005) | 동일 적용 |
| `_REQUIRED_FIELDS` (event_definitions) | 변경 없음 |
| Event parquet 저장 스키마 | 변경 없음 |

### 5.4 후속 조치 (Developer 가 따름)

- [ ] Developer: `knowledge_calculator.py` 에 `_build_event_raw_fallback_episode()` 추가 + `_build_event_raw_fallback()` 입구에 dispatch 추가 (단일 세션 완결)
- [ ] Developer: 합성 raw fixture + episode 정의(미저장) 기반 통합 테스트 (`tests/test_knowledge_calculator_episode_fallback.py`)
- [ ] Developer: point 무회귀 회귀 테스트 보강 (이미 1818 case 그린이지만 fallback 분기 명시 케이스 추가)
- [ ] Developer: `pages/2_Event_추출_분석.py` 에서 `evt_detection_mode` 기본값을 `"episode"` 로 변경 — F033 ① 항목 (단순 변경)
- [ ] QA: 합성 raw + episode 정의 → Knowledge 산출이 ADR-012 가 저장 parquet 으로 만든 값과 동일한지 cross-check
- [ ] 하네스 동기화: 본 ADR 을 `src/harness_template/claude.gstack/harness/docs/adr/` 에 미러링

---

## 6. Developer 용 파일별 구현 계획

> Developer 가 본 ADR 만 보고 구현할 수 있도록 구체적 함수 시그니처와 SQL 골격을 명시.

### 6.1 수정 파일

#### `src/data_analysis/dashboard/core/knowledge_calculator.py`

**A. 신규 import**

```python
from core.episode_detector import (
    _build_episode_sql,
    _suggest_peak_agg,
    validate_episode_params,
)
from core._sql_tokens import validate_column_name
```

(현재 import 에 episode_detector 가 없음 — 신규 추가. `validate_column_name` 은 옵션이지만 helper 내 방어 검증용으로 권장.)

**B. 신규 private helper** (기존 `_build_event_raw_fallback` 위 또는 아래에 배치):

```python
def _build_event_raw_fallback_episode(
    *,
    event_name: str,
    defn: dict,
    raw_glob: str,
    start: str,
    end_exclusive: str,
    timestamp_col: str,
    aliases: dict[str, str] | None,
    vehicle_ids: list | None,
    user_ids: list | None,
) -> tuple[str, list]:
    """episode 정의를 raw 에 직접 적용한 events CTE 호환 단일 SELECT 조각.

    Returns:
        (sql_fragment, param_list)
        sql_fragment 컬럼: event_type, vehicle_id, "<timestamp_col>", duration_sec.
        param_list 순서: [raw_glob, start, end_exclusive, *vuf_params, max_gap_sec, min_duration_sec].
        episode/peak_column 누락·formula 검증 실패 시 (dummy_sql, []) 반환 — 0건 emit.
    """
    ts = timestamp_col
    dummy = (
        f"SELECT '{event_name}' AS event_type, "
        f"CAST(NULL AS VARCHAR) AS vehicle_id, "
        f'CAST(NULL AS TIMESTAMP) AS "{ts}", '
        f"CAST(NULL AS BIGINT) AS duration_sec "
        f"WHERE FALSE"
    )

    # 1. formula 추출 + 검증
    event_formula: str = defn.get("formula", "")
    if not event_formula.strip():
        return dummy, []

    # 2. Phase 2 parameters 치환 + 재검증
    params_meta: dict = defn.get("parameters", {})
    if params_meta:
        default_values = {
            pname: pmeta.get("default")
            for pname, pmeta in params_meta.items()
            if pmeta.get("default") is not None
        }
        if default_values:
            event_formula = substitute_parameters(
                event_formula, default_values, param_meta=params_meta
            )
    if _PLACEHOLDER_RE.search(event_formula):
        return dummy, []
    try:
        validate_where_expr(event_formula)
    except ValueError:
        return dummy, []

    # 3. episode 객체에서 파라미터 추출 (누락 시 폴백)
    ep_meta = defn.get("episode") or {}
    peak_column = ep_meta.get("peak_column")
    if not peak_column:
        return dummy, []
    min_duration_sec = float(ep_meta.get("min_duration_sec", 0.0))
    max_gap_sec = float(ep_meta.get("max_gap_sec", 1.0))
    peak_agg = ep_meta.get("peak_agg") or _suggest_peak_agg(event_formula, peak_column)

    # 4. alias 치환 (where_expr + peak_column 단일 식별자)
    if aliases:
        event_formula = resolve_aliases(event_formula, aliases)
        peak_column = aliases.get(peak_column, peak_column)

    # 5. 보안 검증 (episode_detector 와 동일 정책)
    try:
        validate_column_name(peak_column)
        validate_episode_params(min_duration_sec, max_gap_sec, peak_column, peak_agg)
    except ValueError:
        return dummy, []

    # 6. vehicle/user 필터 (matched CTE extra_where 에 삽입)
    _vuf_sql, _vuf_params = _build_vehicle_user_filter(vehicle_ids, user_ids)
    extra_where = f"AND {_vuf_sql}" if _vuf_sql else ""

    # 7. episode SQL 골격 (episode_detector 재사용)
    sql_template, _ = _build_episode_sql(
        raw_glob,
        event_formula,
        timestamp_col=timestamp_col,
        peak_column=peak_column,
        peak_agg=peak_agg,
        output_cols=None,
        has_user_id=False,  # Knowledge events CTE 는 user_id 불필요
    )
    episode_sql = sql_template.replace("{extra_where}", extra_where)

    # 8. outer SELECT 로 감싸 events CTE 계약에 맞춤
    outer_sql = (
        f"SELECT '{event_name}' AS event_type, "
        f"ep.vehicle_id AS vehicle_id, "
        f'ep.start_ts AS "{ts}", '
        f"ep.duration_sec AS duration_sec "
        f"FROM (\n{episode_sql}\n) ep"
    )

    # 9. 바인딩 순서: episode_detector._build_episode_sql 계약 그대로
    params: list = (
        [raw_glob, start, end_exclusive]
        + _vuf_params
        + [max_gap_sec, min_duration_sec]
    )
    return outer_sql, params
```

**C. `_build_event_raw_fallback()` 입구에 dispatch 추가** (§3.1):

```python
def _build_event_raw_fallback(
    event_name: str,
    raw_glob: str,
    start: str,
    end_exclusive: str,
    timestamp_col: str,
    aliases: dict[str, str] | None,
    definitions_root: Path,
    vehicle_ids: list | None = None,
    user_ids: list | None = None,
) -> tuple[str, list]:
    ts = timestamp_col
    dummy = (
        f"SELECT '{event_name}' AS event_type, "
        f"CAST(NULL AS VARCHAR) AS vehicle_id, "
        f'CAST(NULL AS TIMESTAMP) AS "{ts}", '
        f"CAST(NULL AS BIGINT) AS duration_sec "
        f"WHERE FALSE"
    )
    try:
        defn = load_definition(event_name, definitions_root)
    except (FileNotFoundError, ValueError):
        return dummy, []

    # ── 신규 dispatch: detection_mode 별로 분기 ──
    if defn.get("detection_mode", "point") == "episode":
        return _build_event_raw_fallback_episode(
            event_name=event_name,
            defn=defn,
            raw_glob=raw_glob,
            start=start,
            end_exclusive=end_exclusive,
            timestamp_col=timestamp_col,
            aliases=aliases,
            vehicle_ids=vehicle_ids,
            user_ids=user_ids,
        )

    # ── 기존 point 본문 (변경 없음) ──
    event_formula: str = defn.get("formula", "")
    ...
```

**D. docstring 갱신**: 모듈 상단의 `Raw Fallback (신규)` 블록에 episode-aware 분기 1줄 추가 (참고용).

#### `src/data_analysis/dashboard/pages/2_Event_추출_분석.py` (F033 ① 항목)

**`evt_detection_mode` 의 기본값 변경** — 1줄 수준:

```python
# 기존
st.session_state.setdefault("evt_detection_mode", "point")
# 변경 후
st.session_state.setdefault("evt_detection_mode", "episode")
```

**위치**: page 초기화 블록 또는 `_EVT_PERSIST_KEYS` default 주입 부분. 정의 로드 분기 (`_def.get("detection_mode", ...)`) 는 그대로 유지 — 기존 정의 로드 시 저장된 값이 우선되므로 무회귀.

> Developer: 실제 코드를 grep 하여 default 주입 위치를 확인 후 1줄 수정. session_state 의 setdefault 이외에 라디오 위젯의 `index=0` 같은 곳에 별도 default 가 있다면 거기도 episode 가 첫번째가 되도록 조정. UI 라벨 순서·테스트 영향 확인.

### 6.2 신규 테스트 파일

#### `src/data_analysis/dashboard/tests/test_knowledge_calculator_episode_fallback.py` (신규)

| 케이스 그룹 | 시나리오 | 검증 |
|---|---|---|
| **E1. 단일 연속 매칭** | raw 20샘플 0.1초 간격 모두 임계 초과 + episode 정의 (`min_duration=0`, `max_gap=1.0`) 미저장 → `{event}_횟수`/`{event}_시간` | 횟수=1, 시간≈1.9초 (BIGINT cast 후 1 또는 2 — 동일 fixture 로 episode_detector 직접 호출 결과와 cross-check) |
| **E2. 두 episode 분리** | 10샘플 + gap 3초 + 8샘플 (max_gap=1.0) | 횟수=2 |
| **E3. 두 episode 병합** | 10샘플 + gap 0.5초 + 8샘플 (max_gap=1.0) | 횟수=1, sample 18개 분량의 duration |
| **E4. min_duration 필터** | 단일 스파이크 1샘플 + `min_duration_sec=0.5` | 횟수=0 (HAVING 제외) |
| **E5. 다중 vehicle** | vehicle A 10샘플 + vehicle B 10샘플, 시간 인접 | 횟수=2 (vehicle 별 1) |
| **E6. point 무회귀** | point 정의 + 동일 raw → 기존 행 단위 계수 결과 동일 | 분기 전 vs 후 결과 byte 동일 |
| **E7. dispatch 분기** | detection_mode 누락 정의 → point 경로 진입 (helper 미호출) | helper 호출 안 됨 (mock 으로 확인) |
| **E8. 저장 parquet 우선** | event parquet 존재 + 정의도 episode → fallback 미진입 | 결과는 저장 parquet 기준 |
| **E9. vehicle/user 필터** | vehicle_ids=[A] → vehicle A 만 카운트 | extra_where 가 matched CTE 에 적용 |
| **E10. 보안 회귀** | formula 에 화이트리스트 위반 토큰 → 더미 폴백 (예외 미전파) | 0건 결과 |
| **E11. peak_column 누락 episode 정의** | episode 객체에서 peak_column 제거 → 더미 폴백 | 0건 결과, 예외 없음 |
| **E12. Phase 2 parameters 미치환 placeholder 잔존** | default 없는 placeholder → 더미 폴백 | 0건 결과 |
| **E13. alias 치환** | column_aliases 있는 raw 컬럼 사용 정의 → resolve 적용 후 정상 검출 | E1 fixture 의 alias 버전 |

**fixture 전략**: ADR-012 §3.10 의 S1~S5 fixture 를 그대로 재사용하되, **event parquet 저장은 하지 않고** Knowledge calculate() 만 직접 호출. 동일 fixture 로 `episode_detector.count_episodes()` 도 호출해 cross-check (저장 경로 ↔ fallback 경로 결과 일치 검증 — 핵심 acceptance).

### 6.3 보안 회귀 (별도 테스트 불필요)

기존 `test_event_extractor_security.py`, `test_episode_detector_security.py`, `test_knowledge_calculator_*` 가 이미 보안 화이트리스트를 커버하므로 본 helper 는 동일 검증 함수를 재사용해 **회귀 0**. 6.2 의 E10/E11/E12 가 분기 단에서 더미 폴백을 검증.

### 6.4 ruff / 포매팅

- 신규 함수는 기존 `knowledge_calculator.py` 스타일 일치 (4 space indent, 한국어 docstring, `from __future__ import annotations`).
- `ruff check src/data_analysis/dashboard` + `ruff format src/data_analysis/dashboard` clean.

### 6.5 git 커밋 메시지 (제안)

```
feat(F033): Knowledge raw-fallback 의 episode-aware 화

ADR-013 결정에 따라 _build_event_raw_fallback() 에 detection_mode
dispatch 를 추가하고, episode 분기는 ADR-012 의 gaps-and-islands
5단 CTE 를 events CTE 호환 단일 SELECT 로 인라인 이식한다.

저장 parquet 미존재 + episode 정의 시 Knowledge {event}_횟수=
에피소드 수, {event}_시간=duration 합 으로 정상화. 저장 경로와
동일 결과 보장. point 정의·저장 parquet 경로 100% 무회귀.

추가로 Event 페이지의 evt_detection_mode 기본값을 point→episode
로 변경 (F033 ① — 기존 정의 로드는 저장값 우선이므로 무회귀).

수정: core/knowledge_calculator.py (dispatch + helper),
      pages/2_Event_추출_분석.py (기본값 1줄)
미수정: core/episode_detector.py, core/event_definitions.py,
        core/event_extractor.py (시그니처 무회규)
테스트: 신규 ~13 케이스 — fallback episode 동작/dispatch/
        무회귀/보안 폴백/parquet 우선/cross-check
```

---

## 7. 미해결 / v2 후속

- raw-only 경로 (`_build_sql_raw_only`) 의 event_refs 도 episode-aware 하게 산출하려면 별도 ADR 필요 — 현재는 `_zero_out_event_exprs` 로 0. 사용자가 user 집계로 episode 변수를 평가하려면 사전 저장 필요.
- DuckDB inline `WITH … SELECT` 의 옵티마이저 동작 — 다중 episode event 합성 SQL 이 매우 길어질 때 (예: 10개 episode event 동시) 쿼리 플랜이 비대해질 수 있음. 측정은 v2.
- `peak_column` 이 raw 에 실존하지 않을 때 — 현재는 episode_detector 단의 Binder Error 로 떨어짐. UI 단에서 사전 검증 (ADR-012 §3.7) 이 이미 있으므로 fallback 경로는 신뢰 입력. 추가 방어가 필요하면 helper 진입 시 raw schema 조회 (1회 DESCRIBE) v2.

---

*작성: Architect 에이전트 | 날짜: 2026-06-10*
