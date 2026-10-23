# ADR-016 Trip Segmentation Enabler — 대시보드 Knowledge calculator 에 실제 trip 경계 도입

| 항목 | 내용 |
|---|---|
| 상태 | Proposed |
| 날짜 | 2026-06-16 |
| 작성자 | Architect 에이전트 |
| 관련 Feature | F052 (본 ADR로 정의 — enabler), 하류 F053 (F048 unblock), F054 (일평균주행횟수 unblock) |
| 관련 ADR | ADR-006 (Knowledge 변수 치환), ADR-009 (Knowledge 스키마 확장), ADR-010 (집계 수식 통합), ADR-014 §2.6 L3 (mode=series + vehicle_trip), ADR-015 (codegen) |

> **번호 결정**: ADR-015 까지 점유. 가용 다음 번호 **ADR-016**.
> **범위 한정**: 본 ADR 은 대시보드 `knowledge_calculator.py` 의 **trip 경계 식별 규칙**과
> 이를 `aggregation="vehicle_trip"` 산출 경로에서 사용하는 방법, 그리고 codegen Polars 패리티
> 만 다룬다. 새 Knowledge 정의(F048/일평균주행횟수)·새 UI 는 후속 Feature.
> 파이프라인(SSOT) 코드는 **읽기 전용** — 본 ADR 의 어떤 결정도 `obigo-data-pipeline/` 수정을
> 요구하지 않는다.

---

## 1. 컨텍스트

### 1.1 현재 막혀 있는 두 산출물

| 산출물 | 현재 상태 | 막힌 원인 |
|---|---|---|
| F048 **최근주행 거리·시간** (`recent_n=1`) | `aggregation=vehicle_trip, mode=series, source_events=[], formula='거리_km'` 정의가 `ValueError` 로 거부됨 | `knowledge_calculator._build_trip_scores_sql` 의 raw-only 분기에서 명시적으로 `"mode='series' (vehicle_trip) 는 source_events 또는 raw_aggregations 가 events CTE 경로를 통해야 합니다"` 를 raise (lines 1342–1345) |
| 일평균 주행횟수 (F042 정의 acceptance) | `aggregation=vehicle_day, formula='총_트립_수'` 가 산식상 동작은 함 — 그러나 의미가 깨짐 | 빌트인 `총_트립_수 = COUNT(DISTINCT DATE(Timestamp))` 가 `vehicle_day` GROUP BY 안에서는 항상 **1**. "하루에 trip 1번" 로 가정되어 일평균이 의미를 잃음 |

두 문제의 공통 근본 원인 = **대시보드에 실제 trip 경계 신호가 없음**. 현재
`_calculate_series` 가 `TripId` 컬럼 존재만 보고 있고 (raw 에 없음) → `DATE(Timestamp)` 로
fallback → "trip ≈ day" 로 퇴화한다.

### 1.2 실측한 데이터 사실 (재확인)

- raw parquet 컬럼 검증 (notebook 샘플 + dashboard `data/raw/` 60 파일 동일):
  - `TripId` **없음** — 이 컬럼은 ingestion 이후 단계에서 부여되는 식별자.
  - `Vehicle.TripDuration` **있음** — 라이브 trip 일 때 `0`, trip 종료 후 누적값.
  - `Vehicle.TraveledDistanceSinceStart` **있음** (alias `DrvDistance`).
  - `Vehicle.TraveledTimeSinceStart` **있음** (alias `TraveledTime`).
  - `Vehicle.StartTime` 있으나 **값이 손상** (1970 epoch) — 사용 금지.
- vehicle 23210 검증: SinceStart-reset 카운트 기준 trip 수는 06-04 8건 / 06-05 2건 /
  06-08 2건 — `StartTime` distinct 카운트와 동일.

### 1.3 파이프라인의 trip 분할 SSOT (read-only 확인 완료)

읽은 파일:

- `obigo-data-pipeline/onprem/.../ingestion/rules/trip_boundary.py`
  → 본 ADR 의 핵심 SSOT
- `obigo-data-pipeline/onprem/.../ingestion/infrastructure/open_trip_repository.py`
  → open-trip 상태 머신 (Postgres `open_trip_state` 테이블)
- `obigo-data-pipeline/onprem/.../ingestion/infrastructure/trip_raw_segment_repository.py`
  → trip_id ↔ raw csv 매핑 (`trip_raw_segments`)
- `obigo-data-pipeline/onprem/.../trip_insights/{workflow,providers,contracts}.py`
  → 산출 단계는 segment 들을 `read_raw_trip_frame_for_trip` 으로 `trip_id` 기준 로드만 함
  (trip 경계는 ingestion 단계에서 이미 확정).
- `obigo-data-pipeline/onprem/.../trip_insights/rules/events/driving_session.py`
  → `StartTime` 기반 별도 클러스터링은 **insights 도메인 내부의 low/high resolution 정렬용**
  (이번 enabler 와 무관, ingestion trip_id 와는 별 경로).

**파이프라인의 trip 정의 (확정)** — `TripBoundaryManager.process_chunk`:

1. boundary 신호는 **`Vehicle.TripDuration`** 컬럼. 행 단위 분류:
   - `TripDuration == 0` ⇒ **driving 행** (engine on, trip 진행 중)
   - `TripDuration != 0` (and not null) ⇒ **non-driving 행** (trip 종료 시점)
2. 상태 전이는 차량(`user_id × vehicle_model_id`) 단위 open-trip 상태 머신:
   - non-driving → driving: **trip 시작** (timestamp = 해당 driving 행의 `Timestamp`,
     `trip_start_distance = Vehicle.TraveledDistanceSinceStart`)
   - driving → non-driving: **trip 종료** (`trip_end_distance` 측정 → distance = end-start)
3. `trip_id` 포맷: `trip#{user_id}#{vehicle_model_id}#{trip_start_time_utc_iso(replace ':' → '-')}`
   — UUID 가 아니라 deterministic 식별자.
4. trip 이 ingestion 청크를 넘어 이어질 수 있음 → `open_trip_state` 에 `(user_id, vehicle_model_id)`
   당 1개의 open-trip 을 영속화. 같은 trip 의 distinct raw 파일들은 `trip_raw_segments` 테이블로
   `(trip_id, raw_uri)` 매핑.

**즉, 파이프라인의 진짜 trip 경계는 SinceStart 리셋이 아니라 `TripDuration` 전이.**
SinceStart 리셋은 통상 같은 순간에 일어나지만 (둘 다 trip 시작 시점에 0 으로 리셋),
**`TripDuration`** 이 1차 SSOT 다.

### 1.4 대시보드가 가진 한계와 결정의 함의

대시보드는:

- 파이프라인의 Postgres (`open_trip_state` / `trip_raw_segments`) 에 접근 불가 — 단독 stateless 실행.
- raw 파일은 같은 raw 이지만 **이미 ingestion 이 끝난 결과 (S3 동기화)** — `TripDuration` 컬럼은
  파이프라인이 본 것과 동일한 데이터.
- 즉, 대시보드는 **파이프라인이 ingestion 단계에서 한 분류를 동일 원천 컬럼으로 재현**할 수 있다
  (open-trip cross-chunk 영속화는 분석 기간 윈도우 내에 boundary 가 들어오면 동등한 결과를
  내며, 분석 기간 경계에서 trip 이 잘리는 케이스만 손해 — §3.4 참조).

→ **본 ADR 의 결정**: 대시보드도 `TripDuration` 전이를 1차 trip 경계로 사용한다.
파이프라인이 ingestion 으로 부여한 deterministic `trip_id` 와 **동일한 시점들**에서
trip 이 시작·종료된다. trip 식별자(파이프라인의 `trip#user#vehicle#ts`)를 그대로
재구성하지 않고 **`trip_ordinal`** (vehicle 별 0-based 누적 카운트) 으로 대체한다 —
산출물의 의미(트립 단위 점수·거리·시간)는 동일하다.

`SinceStart` 리셋은 **fallback 신호**로만 사용한다 (`TripDuration` 컬럼이 없는 raw
스키마 변종이 들어왔을 때).

---

## 2. 결정 (요약)

| 결정 | 내용 |
|---|---|
| D1 | `knowledge_calculator.py` 에 **공용 trip-segmentation CTE 빌더**를 추가 — `WITH ... rows_with_trip_ord AS (...)` 형태로 vehicle 별 `trip_ordinal` 과 `trip_start_ts` 를 derive |
| D2 | 1차 경계 신호 = `Vehicle.TripDuration`. 사용 가능 시 `TripDuration != 0` (또는 NULL) 에서 `TripDuration == 0` 으로 떨어지는 transition 을 trip 시작으로 본다 |
| D3 | 2차(fallback) 신호 = `Vehicle.TraveledTimeSinceStart` (alias `TraveledTime`) 리셋 — 현재 행 값 < 직전 행 값 OR 직전 NULL → trip 시작. `TripDuration` 가 없을 때만 사용 |
| D4 | 3차(legacy) fallback = `DATE(Timestamp)` (현행 동작). 위 두 컬럼 모두 부재 시. 경고 로그 |
| D5 | `_build_trip_scores_sql` 의 **raw-only 분기 ValueError 를 제거** — events CTE 없이도 `rows_with_trip_ord` CTE 위에서 trip 단위 raw_agg 가 가능하도록 경로 추가 |
| D6 | **신규 빌트인 변수 `주행_트립_수`** = `COUNT(DISTINCT trip_ordinal)` 도입. `aggregation=vehicle_day` 와 결합하면 "그 날 시작된 trip 수" 산출 가능 → 일평균주행횟수 unblock |
| D7 | `총_트립_수` / `주행일수` 빌트인은 **현행 정의 유지** (`COUNT(DISTINCT DATE(Timestamp))`). 의미가 다른 분모 (일수 vs 트립 수) 이므로 별도 변수로 공존 — 무회귀 |
| D8 | 기존 `안전운전점수_v1_series` / `_v2` 정의 (이미 `vehicle_trip + ema`)는 **자동으로 실제 trip 경계로 전환** — DATE 근사 → 실제 trip. 골든 fixture 는 갱신 필요 (§5) |
| D9 | codegen Polars 는 동일 의미의 `trip_ordinal` 컬럼을 입력 `raw_df` 에 미리 보장 (한 헬퍼 함수). dashboard 와 동일 우선순위 (TripDuration > TraveledTime reset > Date) |
| D10 | 분석 기간 경계에서 잘리는 trip 은 잘린 채로 1 trip — 파이프라인의 open-trip 영속화와 의도적 차이. description/`_pipeline_note` 명시 |

---

## 3. 상세 설계

### 3.1 trip-segmentation SQL CTE — `_build_trip_segmentation_cte`

신규 함수. 입력: `raw_glob`, `start`, `end_exclusive`, `timestamp_col`, `vehicle_ids`, `user_ids`,
boundary mode (auto/td/tt/date). 출력: 한 줄 SQL fragment + params.

런타임 컬럼 감지 — `_check_raw_has_column(raw_glob, "Vehicle.TripDuration")` /
`_check_raw_has_column(raw_glob, "Vehicle.TraveledTimeSinceStart")` 결과로
boundary mode 선택. 결정 트리:

| 감지 | 채택 mode | 비고 |
|---|---|---|
| TripDuration 있음 | `td` | 1차 — 파이프라인 SSOT 동일 |
| TripDuration 없음 + TraveledTimeSinceStart 있음 | `tt_reset` | 2차 — 데이터 사실 검증된 동등 신호 |
| 둘 다 없음 | `date` | 3차 — 현행 fallback, 경고 로그 (legacy 무회귀) |

**Mode `td` 의 핵심 CTE** (timestamp_col=`Timestamp` 일 때 예시):

```sql
rows_with_trip_ord AS (
  SELECT
    *,
    SUM(_is_trip_start) OVER (
      PARTITION BY vehicle_id
      ORDER BY "Timestamp"
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS trip_ordinal
  FROM (
    SELECT
      *,
      CASE
        WHEN "Vehicle.TripDuration" = 0
         AND (
           LAG("Vehicle.TripDuration") OVER (
             PARTITION BY vehicle_id ORDER BY "Timestamp"
           ) IS NULL
           OR LAG("Vehicle.TripDuration") OVER (
             PARTITION BY vehicle_id ORDER BY "Timestamp"
           ) != 0
         )
        THEN 1 ELSE 0
      END AS _is_trip_start
    FROM read_parquet(?)
    WHERE "Timestamp" >= ? AND "Timestamp" < ?
      AND "Vehicle.TripDuration" IS NOT NULL
      {vehicle_user_filter_with_AND_prefix}
  )
)
```

설명:
- `_is_trip_start = 1` 인 행은 driving 행이면서 직전 행이 non-driving (또는 첫 행).
  ⇒ trip 시작 행.
- `trip_ordinal` 은 vehicle 별 누적 카운트 — 1, 2, 3, ... (driving 행만 진행, non-driving
  행은 직전 trip_ordinal 유지).
- `WHERE TripDuration IS NOT NULL` 로 노이즈 row 배제 (파이프라인 동일).
- 분석 기간 (`start..end_exclusive`) 안에서만 segmentation 진행 → 기간 경계 잘림은 §3.4 참조.

**Mode `tt_reset` 의 핵심 CTE** (fallback — alias `TraveledTime` 으로 alias resolve 적용):

```sql
rows_with_trip_ord AS (
  SELECT
    *,
    SUM(_is_trip_start) OVER (
      PARTITION BY vehicle_id ORDER BY "Timestamp"
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS trip_ordinal
  FROM (
    SELECT
      *,
      CASE
        WHEN LAG("Vehicle.TraveledTimeSinceStart") OVER (
              PARTITION BY vehicle_id ORDER BY "Timestamp"
            ) IS NULL
          OR "Vehicle.TraveledTimeSinceStart" <
             LAG("Vehicle.TraveledTimeSinceStart") OVER (
               PARTITION BY vehicle_id ORDER BY "Timestamp"
             )
        THEN 1 ELSE 0
      END AS _is_trip_start
    FROM read_parquet(?)
    WHERE "Timestamp" >= ? AND "Timestamp" < ?
      {vehicle_user_filter_with_AND_prefix}
  )
)
```

`TraveledTimeSinceStart` 는 매 trip 시작에 0 으로 리셋되므로, 현재 값 < 직전 값 (또는
직전이 없음) 인 행이 trip 시작이다. **검증된 데이터 사실**: vehicle 23210 06-04 8 trip 수와
일치.

**Mode `date` (legacy)**: 별도 CTE 없이 기존 코드 경로 (`trip_key_col = 'DATE("Timestamp")'`)
재사용 — 무회귀.

### 3.2 `_build_trip_scores_sql` 의 변경

```text
입력  : trip_key_col  → 제거 (외부에서 결정하지 않음)
대신  : trip_segmentation 정보를 _build_trip_segmentation_cte 가 결정
출력  : 동일 — vehicle_id, trip_key, trip_start_ts, <knowledge_name>
       trip_key = trip_ordinal (정수) 또는 DATE(Timestamp) (legacy)
```

조립 절차:

1. **세그멘테이션 CTE 생성** — `_build_trip_segmentation_cte(...)` → `seg_cte_sql`, `seg_params`.
2. **events CTE 경로** (기존 `_build_sql` 재사용 — source_events 또는 raw fallback event 존재 시):
   `_build_sql` 결과의 `GROUP BY e.vehicle_id` 를 `GROUP BY e.vehicle_id, e.trip_ordinal`
   로 확장 — **단, events CTE 의 각 SELECT 가 `vehicle_id` 옆에 `trip_ordinal` 컬럼을 갖고
   있어야 함**. 이를 위해 events CTE 생성 단계에서 `JOIN rows_with_trip_ord USING (vehicle_id, "Timestamp")`
   를 each event SELECT 에 추가하거나 (event parquet 경로), raw fallback 경로의 episode
   SELECT 출력에 `trip_ordinal` 컬럼을 함께 emit 한다. 이 두 변형의 공통화를 위해
   "events CTE → events_with_trip CTE" 형태로 한 단계 더 wrap 한다:

   ```sql
   events_with_trip AS (
     SELECT e.*, s.trip_ordinal
     FROM events e
     LEFT JOIN rows_with_trip_ord s
       ON s.vehicle_id = e.vehicle_id AND s."Timestamp" = e."Timestamp"
   )
   ```

   이후 GROUP BY 는 `events_with_trip.vehicle_id, events_with_trip.trip_ordinal`.
   `MIN(e."Timestamp")` 를 그대로 `trip_start_ts` 로 사용.

3. **raw-only 경로** (D5 핵심 변경): 기존에 `ValueError` 였던 분기.
   `_build_sql_raw_only` 를 호출하되 `aggregation="vehicle_trip"` 시그널을 새로 추가.
   raw_agg CTE 는 `rows_with_trip_ord` 위에서 `GROUP BY vehicle_id, trip_ordinal` 로 집계,
   `MIN("Timestamp") AS trip_start_ts` 컬럼을 추가한다. F048 (formula=`거리_km`) 이 이
   경로로 진입.

   ```sql
   WITH
     rows_with_trip_ord AS (...),
     raw_agg AS (
       SELECT
         vehicle_id,
         trip_ordinal,
         MIN("Timestamp") AS trip_start_ts,
         MAX(DrvDistance) - MIN(DrvDistance) AS "거리_km"   -- builtin SQL
       FROM rows_with_trip_ord
       WHERE trip_ordinal >= 1    -- 첫 시작 전 noise 제외 (선택)
       GROUP BY vehicle_id, trip_ordinal
     )
   SELECT
     vehicle_id,
     trip_ordinal AS trip_key,
     trip_start_ts,
     ("거리_km") AS "최근주행거리"
   FROM raw_agg
   ```

4. **결과 schema**: 기존과 동일 — `vehicle_id, trip_key, trip_start_ts, <knowledge_name>`.
   downstream `_apply_recent_n / _apply_ema / _apply_lag / _apply_rolling` 무변경.

### 3.3 신규 빌트인 변수 `주행_트립_수`

`_BUILTIN_VARS` 에 한 항목 추가:

```python
# F052 (ADR-016) — 실제 trip 수 (TripDuration 전이 카운트)
# 단, 이 빌트인은 segmentation CTE 가 활성일 때만 의미 — knowledge_calculator 가
# 다음을 보장: raw_agg CTE 의 source 가 rows_with_trip_ord 일 때만 trip_ordinal 컬럼이
# 존재. 그 외 경로는 ValueError (knowledge_definitions.absorb_builtin_vars 가 차단).
"주행_트립_수": "COUNT(DISTINCT trip_ordinal)",
```

추가 처리 — `knowledge_calculator.calculate()` 의 시작부에서:

- `주행_트립_수` 가 parsed.builtin_refs 에 있으면 **트립 세그멘테이션 CTE 강제 활성** 플래그를
  세팅. 즉 raw_agg CTE 가 `read_parquet(...)` 가 아니라 `rows_with_trip_ord` 를 FROM 으로
  쓰도록 분기.
- `aggregation=vehicle_day` 와 결합 시, `GROUP BY vehicle_id, DATE("Timestamp")` 에서
  `COUNT(DISTINCT trip_ordinal)` 가 "그 날 시작·통과한 distinct trip 수" 산출.
- 분모 = `주행_트립_수`, 분자 = `거리_km` 등 시나리오로 자유 조합 가능.

**일평균주행횟수 (F054, F042 의 일평균주행횟수.json) 의 정의 갱신 안**:

| 필드 | 값 |
|---|---|
| `aggregation` | `vehicle_day` |
| `formula` | `주행_트립_수` *(was `총_트립_수`)* |
| `builtin_vars` | `["주행_트립_수"]` |
| `description` | "파이프라인 avgDailyTripCount 와 동일 — Vehicle.TripDuration 전이를 trip 으로 카운트. TripDuration 미존재 raw 는 TraveledTimeSinceStart 리셋, 그것도 미존재면 DATE fallback (description 에 표기됨)" |

UI 평균 표시 (vehicle_day → 평균) 는 F042 의 UI 책임 그대로 유지.

### 3.4 분석 기간 경계 트립 처리 — 파이프라인과의 의도적 차이

파이프라인은 `open_trip_state` 로 ingestion chunk 를 넘어 trip 을 이어 붙인다. 대시보드는
stateless / 분석 기간 한정이라 다음 의미 차이가 발생한다:

| 시나리오 | 파이프라인 | 대시보드 (본 ADR) |
|---|---|---|
| trip 이 `start` 이전에 시작 → `start..end` 내에 종료 | trip 전체를 1 trip 으로 집계 (영속 trip_id) | `start..end` 안의 부분만 1 trip 으로 집계 (시작 거리·시간 절단) |
| trip 이 `start..end` 내에 시작 → `end` 이후 종료 | 영속 trip, 후속 ingestion 에서 종료 | `start..end` 안의 부분만 1 trip 으로 집계 (종료 절단) |
| trip 이 `start..end` 안에서 완결 | 1 trip | 1 trip — 동일 |

**의사결정**: 이 차이는 **수용**한다. 이유:
- 대시보드는 인사이트 탐색 도구지 운영 ETL 아님.
- 사용자가 보는 기간은 보통 day/week/month 단위 → 경계 잘림 비율은 1% 미만 (vehicle 23210 06-04 데이터
  기준 추정).
- 파이프라인과의 EXACT 일치가 필요하면 codegen 산출물(파이프라인 _generated/) 을 사용한다
  — 그것이 ADR-015 의 책임.

description 과 `_pipeline_note` (정의 JSON 의 optional 필드) 에 명시한다.

### 3.5 codegen Polars 패리티 (ADR-015 후속)

`knowledge_codegen.py` 가 생성하는 Polars 함수 (`compute_<name>(raw_df, events_df, *, aggregation)`)
는 입력 `raw_df` 에 `trip_ordinal` 컬럼이 이미 있을 수도, 없을 수도 있다.

**규칙**: codegen 은 `aggregation=vehicle_trip` 또는 `주행_트립_수` 빌트인 사용 시
`raw_df` 에 `trip_ordinal` 컬럼을 보장하는 헬퍼를 emit 한다. SSOT 분기 동일.

Polars 헬퍼 시그니처 (코드 생성기에 embed 되는 상수 문자열):

```python
def _ensure_trip_ordinal(raw_df: pl.DataFrame) -> pl.DataFrame:
    """trip_ordinal 컬럼 보장 — TripDuration > TraveledTime reset > Date fallback.

    파이프라인 trip_boundary.TripBoundaryManager 와 동일 분류 (TripDuration==0 ⇒ driving).
    """
    if "trip_ordinal" in raw_df.columns:
        return raw_df

    cols = set(raw_df.columns)

    # 1차: Vehicle.TripDuration
    if "Vehicle.TripDuration" in cols:
        td = pl.col("Vehicle.TripDuration")
        prev_td = td.shift(1).over("vehicle_id", order_by="Timestamp")
        is_start = (
            (td == 0) & ((prev_td.is_null()) | (prev_td != 0))
        ).cast(pl.Int64)
    elif "Vehicle.TraveledTimeSinceStart" in cols:
        # 2차: TraveledTime reset
        tt = pl.col("Vehicle.TraveledTimeSinceStart")
        prev_tt = tt.shift(1).over("vehicle_id", order_by="Timestamp")
        is_start = ((prev_tt.is_null()) | (tt < prev_tt)).cast(pl.Int64)
    else:
        # 3차: Date fallback
        return raw_df.with_columns(
            pl.col("Timestamp").dt.date().alias("trip_ordinal")
        )

    return raw_df.sort(["vehicle_id", "Timestamp"]).with_columns(
        is_start.alias("_is_trip_start")
    ).with_columns(
        pl.col("_is_trip_start")
        .cum_sum()
        .over("vehicle_id")
        .alias("trip_ordinal")
    ).drop("_is_trip_start")
```

`vehicle_trip` aggregation 의 group_keys 에 `trip_ordinal` 을 추가하고 (`_GROUP_KEYS_BY_AGG`
확장), compute 함수 본문 시작부에서 `raw_df = _ensure_trip_ordinal(raw_df)` 를 호출한다.
`주행_트립_수` 는 빌트인 카탈로그(`POLARS_BUILTIN_VARS`)에 `pl.col("trip_ordinal").n_unique()`
로 등록한다.

이 codegen 변경은 본 ADR 의 enabler 변경이 머지된 다음 동일 phase 내에 적용한다 (F052
acceptance 의 한 항목).

### 3.6 보안 무회귀

- 새로 추가되는 SQL fragment 는 전부 **사용자 입력이 아닌 코드 상수** (window 함수·LAG·CASE
  WHEN). ADR-005 의 boundary (formula validate_where_expr) 통과 후 결정되는 path 이므로
  토큰 검증 0 변화.
- `Vehicle.TripDuration` / `Vehicle.TraveledTimeSinceStart` 식별자는 raw VSS dotted —
  `validate_column_name` 기존 정책 통과 (점 포함 허용).
- raw_glob 경로 검증, vehicle_ids/user_ids 파라미터 바인딩 모두 기존 함수
  (`resolve_in_root`, `_build_vehicle_user_filter`) 재사용. **새 진입점 없음**.

---

## 4. 대안 검토

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| (A) SinceStart 리셋 only (현재 사용자가 검증한 신호) | 데이터 사실 검증됨, 간단 | 파이프라인 SSOT 와 boundary 신호가 다름 (TripDuration vs TraveledTime) — 둘이 거의 동시 리셋이지만 엣지에서 1행 어긋날 수 있음 | 1차 SSOT 정합성 손해. 단 fallback 으로는 유지 |
| (B) `Vehicle.StartTime` 클러스터링 | 명시적 trip 식별자 같음 | 실측 데이터 손상(1970 epoch) — 사용 불가 | 데이터 사실로 거부 |
| (C) 파이프라인 Postgres `open_trip_state` 조회 | EXACT 일치 | 대시보드를 stateless 가 아니게 만들고 DB 의존 추가. 또한 운영 DB 에 분석 도구가 read 접근하는 것은 아키텍처 경계 위반 | 결합도 폭증 |
| (D) 새 사전 ETL 단계로 `trip_id` 컬럼을 raw 에 미리 주입 | 산출 시점 빠름 (window 함수 없음) | dashboard 자체적으로 raw 를 수정하는 흐름이 됨 (S3 동기화 후처리 단계 신설). 운영 부담 증가. ADR-015 의 codegen 정합성도 해쳐짐 | 운영 복잡도 ↑ |
| (E) 본 ADR 채택 — TripDuration 1차 + TraveledTime 2차 + Date 3차 | 파이프라인 SSOT 와 1차 신호 동일, fallback 으로 무회귀, 추가 운영 의존 0 | 분석 기간 경계 잘림 (§3.4) 의도적 수용 | (채택) |

---

## 5. 무회귀 전략 & 영향 분석

### 5.1 기존 정의 영향

| 정의 | 현재 동작 | 본 ADR 후 동작 | 권장 조치 |
|---|---|---|---|
| `안전운전점수_v1_series` | `vehicle_trip + ema`, `trip_key=TripId` → 컬럼 없음 → DATE fallback (1 trip = 1 day) | TripDuration mode 활성 → 실제 trip 1건씩 점수 산출 + EMA 누적. 점수 분포가 의미를 가짐 | **default 로 실제 trip 전환**. 골든 fixture (`codegen/golden/knowledge_series/raw_sample.parquet`) 는 이미 `TripId` 컬럼을 가지고 있으므로 영향 받지 않음 — 신규 fixture (TripDuration 보유) 별도 추가 필요 |
| `안전운전점수_v2` | 동일 (DATE fallback) | 동일하게 실제 trip 으로 전환 | 동일 |
| `총_트립_수` | `vehicle` aggregation 에서 `COUNT(DISTINCT DATE(Timestamp))` → "주행한 일수" 가 사실상 답 | **무변경** — 의미가 "주행일수" 임이 이미 description 에 명시. 일자별 trip 수가 필요하면 신규 `주행_트립_수` 사용 | 변경 없음 (의도적 공존) |
| `주행일수` | 동일 (별칭) | 동일 | 변경 없음 |
| `일평균주행거리`, `일평균주행시간_초` | `vehicle_day + formula='거리_km'/'총주행시간'` | 무변경 — `vehicle_day` aggregation 은 본 enabler 무관 | 변경 없음 |
| 일평균주행횟수 (F042 acceptance) | 정의 파일 아직 미생성 | 신규 정의 시 `formula='주행_트립_수'` 사용 권장 | F054 에서 정의 생성 |

### 5.2 테스트 무회귀 약속

- 본 enabler PR 의 변경 범위는 다음 두 함수의 추가 + 두 함수의 분기 추가:
  - 신규: `_build_trip_segmentation_cte`, `_ensure_trip_ordinal` (Polars helper)
  - 수정: `_calculate_series` 의 trip_key 결정 분기 (auto-detect)
  - 수정: `_build_trip_scores_sql` 의 raw-only ValueError 제거 + segmentation CTE wrap
- `aggregation in {vehicle, vehicle_day, vehicle_week, vehicle_month, user, total}` 경로는
  코드 상 분기 변경 없음 → 기존 2715 테스트 영향 0 예상.
- `aggregation=vehicle_trip` 경로의 기존 테스트는:
  - 만약 fixture 에 `TripId` 컬럼이 있고 그것으로 group 되어 있다면 → `TripId` 컬럼 감지가
    우선되도록 `series.trip_key` 가 명시되었을 때만 컬럼명 그대로 사용하는 분기를 유지
    (backward compat). 즉 `series.trip_key="TripId"` + 컬럼 존재 시 기존 동작 100% 유지.
  - fixture 에 `TripId` 없고 DATE fallback 동작 중이었다면 → 신규 동작 (TripDuration mode)
    으로 결과 변화 가능. 골든 비교 테스트가 있다면 fixture 또는 expected 갱신.
- 신규 테스트 (F052 acceptance):
  - synthetic raw — vehicle A 에 3 trip (TripDuration 0→non-zero 전이 2회) → `주행_트립_수` =
    3, `_calculate_series(recent_n=1, formula='거리_km')` 결과 = 마지막 trip 의 MAX-MIN
    DrvDistance.
  - vehicle A — TripDuration 컬럼 없는 fixture → TraveledTime 리셋 mode 자동 선택 → 동일
    결과.
  - vehicle A — 두 컬럼 모두 없는 fixture → DATE fallback → 현행 동작 유지 + 경고 로그.

### 5.3 codegen golden 영향

`dashboard/core/codegen/golden/knowledge_series/raw_sample.parquet` 은 현재 `TripId` 만
가지므로 본 ADR 의 신규 trip_ordinal 경로를 검증하지 못한다. F052 acceptance 에서
`golden/knowledge_series_td_mode/{raw_sample,expected}.parquet` 신규 fixture 1세트 추가
(TripDuration 컬럼 보유, 3 trip).

기존 golden 비교는 `compare_golden.py` 가 SHA 가 아닌 산출 동등성을 보므로 fixture 가 동일하면
변화 없음.

---

## 6. Feature 분해 (Planner 에 위임)

`feature_list.json` 다음 free ID = **F052**. 작업 단위 분해:

| ID | 제목 | 카테고리 | 의존 | 산출물 |
|---|---|---|---|---|
| **F052** | trip 세그멘테이션 enabler — knowledge_calculator + codegen Polars (ADR-016) | data | F038, F041 | `_build_trip_segmentation_cte` SQL 헬퍼, `_ensure_trip_ordinal` Polars 헬퍼, `_build_trip_scores_sql` raw-only 분기, 신규 빌트인 `주행_트립_수`, 신규 fixture + 테스트 |
| **F053** | F048 최근주행 거리·시간 정의 unblock — `최근주행거리.json` / `최근주행시간_초.json` | data | F052 | 정의 JSON 2개 + UI selectbox 검증 + 단위 테스트 |
| **F054** | 일평균주행횟수 정의 + UI — `일평균주행횟수.json` (`formula=주행_트립_수, aggregation=vehicle_day`) | data | F052, F042 (선행되어 있어도/안 되어 있어도 무관) | 정의 JSON 1개 + 단위 테스트 (`주행_트립_수` builtin 의미 검증) |
| (선택) F055 | 기존 `안전운전점수_v1_series` / `_v2` golden fixture 재생성 + 회귀 비교 | data | F052 | 신규 golden + compare_golden.py 통과 확인 |

F053·F054 는 enabler (F052) 머지 후 작은 정의-only PR 로 분리. F055 는 선택 — 기존
fixture 가 TripId 컬럼을 갖고 있어 본 enabler 와 충돌하지 않으면 생략 가능.

---

## 7. 결과

**긍정적 영향**

- 파이프라인 (SSOT) 의 trip 분류와 동일 1차 신호 사용 → 산출물 의미 정합 ↑
- F048 (최근주행거리/시간) unblock — `mode=series + recent_n=1` 이 raw-only 정의로 동작 가능
- 일평균주행횟수가 의미 있는 수치로 산출됨 (`주행_트립_수` 빌트인 도입)
- 기존 series 정의 (`안전운전점수_v1_series`/`_v2`) 가 자동으로 실제 trip 단위 EMA 가 됨 →
  점수 분포 의미 ↑
- 추가 외부 의존 0 (DB·새 ETL 단계 없음)

**부정적 영향 / 트레이드오프**

- 분석 기간 경계에서 잘리는 trip 의 의미 차이를 사용자에게 설명해야 함 (§3.4)
- DuckDB window 함수 (LAG, SUM OVER) 사용으로 raw 행 수가 많은 vehicle 의 query latency가
  소폭 증가 가능 — 1차 측정 후 필요 시 partition-pruning 또는 incremental cache 도입 (별도 phase)
- 기존 안전운전점수 series 결과 분포가 변할 수 있음 (DATE → TRIP 의 의미 차이) — 사용자 안내
  (changelog) 필요

**후속 조치**

- [ ] F052 구현 (Developer)
- [ ] F053·F054 정의 JSON 추가 (Developer)
- [ ] codegen Polars 패리티 검증 — `compare_golden.py` 통과
- [ ] description / changelog 에 §3.4 의미 차이 공지
- [ ] (선택) 파이프라인 `cumulative` Postgres 시드 + 대시보드의 분석 기간 경계 합의 — 별도 ADR

---

*작성: Architect 에이전트 | 날짜: 2026-06-16*
