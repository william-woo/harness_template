# ADR-012 에피소드(윈도우) 기반 이벤트 검출 — point 무회귀 + episode 모드 추가

| 항목 | 내용 |
|---|---|
| 상태 | Proposed |
| 날짜 | 2026-06-08 |
| 작성자 | Architect 에이전트 |
| 관련 Feature | F030 |
| 관련 ADR | ADR-005 (formula 보안 — 화이트리스트 유지), ADR-008 (정의 파라미터화), ADR-009 (스키마 확장), ADR-011 (vehicle/user 필터 — 무회귀 대상) |

> **ADR 번호 주의**: F030 acceptance_criteria 에는 "ADR-011 작성" 으로 적혀있으나,
> ADR-011 은 이미 *분석 조건 확장 (vehicle_id/user_id 필터)* 으로 점유되어 있어
> 다음 가용 번호인 **ADR-012** 를 부여한다. 의미상으로는 F030 의 동일 acceptance 를 충족한다.
> Developer 는 본 ADR-012 를 F030 의 ADR 산출물로 간주하고 구현한다.

---

## 1. 컨텍스트

### 1.1 현황 (확인된 동작)

| 위치 | 동작 |
|---|---|
| `core/formula_runner.run_where()` | Raw parquet + WHERE 표현식 → 조건 참인 **행 전체** 반환 (ORDER BY timestamp) |
| `core/event_extractor.count_matches()` | 조건 참인 **행 수** 반환 (미리보기 메트릭) |
| `core/event_extractor.save_event_data()` | 행 단위 Parquet 저장, `duration_sec=1` 하드코딩 (L262-264) |
| `core/knowledge_calculator.calculate()` | event parquet 의 `vehicle_id + duration_sec` 컬럼을 가정 — `{Event}_횟수 = COUNT(event_type)`, `{Event}_시간 = SUM(duration_sec)` |
| 정의 JSON 스키마 | `{name, raw_columns, formula, output_columns, parameters, created_at, updated_at}` — `detection_mode` 없음 |

### 1.2 문제점 (요구사항 배경)

고주파 시계열 raw 에서 연속 신호 임계값 이벤트 (`Vehicle.Acceleration.Longitudinal > 3.0`, `Speed2 > 80`, ...) 는 **조건 참인 연속 N샘플 = 이벤트 1건** 이어야 하는데, 현재 모델은 **N건** 으로 과대 계수한다:

1. **샘플링레이트 종속**: 같은 주행을 10Hz/20Hz 로 기록하면 횟수가 2배 차이
2. **duration_sec 의미 상실**: 1초 고정 → Knowledge `{event}_시간 == {event}_횟수` 동일값
3. **노이즈 민감**: 임계값 근처에서 1샘플 진동 → 다수의 미세 이벤트로 카운트

### 1.3 도메인 분류

| 분류 | 예시 정의 | 적합 모드 |
|---|---|---|
| **연속 신호 임계값** | 급가속, 급감속, 과속, 코너링_강함, 급조향, 고RPM | episode |
| **이산 상태/플래그** | 안전벨트미착용 (`DrvSeatBelt = false`), AEB경고, 방향지시등_사용, 콜드스타트 | point (유지) |
| **타이어공기압 / 배터리 상태 등** | 단일 시점 분류 (정상/주의/위험) | point (유지) — 사용자 선택 가능 |

---

## 2. 결정 (요약)

연속 신호 임계값 이벤트를 "조건 참인 연속 구간 = 이벤트 1건" 으로 검출하는 **episode 모드** 를 추가한다.

| 결정 항목 | 채택 안 |
|---|---|
| 정의 스키마 | `detection_mode: "point" \| "episode"` 추가 (기본 `"point"`), episode 시 `episode` 객체 (`min_duration_sec`, `max_gap_sec`, `peak_column`, `peak_agg`) |
| 누락 시 동작 | `detection_mode` 키 없으면 `"point"` 로 해석 — **기존 33개 정의 JSON 무회귀 보장** |
| SQL 알고리즘 | DuckDB **gaps-and-islands** — `LAG(ts) OVER (PARTITION BY vehicle_id ORDER BY ts)` → 간격 > `max_gap_sec` 이면 새 island flag → 누적합 `episode_id` → `GROUP BY` |
| timestamp 변환 | `EPOCH(...)` (DuckDB) 로 초 변환 → `MAX(EPOCH(ts)) - MIN(EPOCH(ts))` 로 duration 초 계산 — TIMESTAMP/문자열/epoch 입력 모두 처리 |
| 단일 샘플 episode | `duration_sec = 0` 으로 둠 (공칭 샘플간격 추정 없음). `min_duration_sec > 0` 이면 자동 필터됨 |
| 출력 parquet 스키마 | `vehicle_id, timestamp(=start_ts), end_ts, duration_sec(int64), peak_value(double), sample_count(int64)` + `user_id` 옵션 + `output_cols` 의 peak 행 값 |
| 함수 인터페이스 | 신규 `core/episode_detector.py` 모듈 추가. 기존 `run_where/count_matches/save_event_data` 는 시그니처 **유지** + episode 분기만 추가 (point 경로 무회귀 최우선) |
| 보안 | `peak_column`, `timestamp_col` → `validate_column_name` 통과 필수. `formula` → `validate_where_expr` (F004) 유지. `min_duration_sec`/`max_gap_sec` → 0 이상, 86400 이하 정수 검증 |
| UI 흐름 | Event 페이지에 `detection_mode` 라디오 추가 — episode 선택 시 파라미터 expander 표시 + 미리보기 표가 에피소드 단위로 렌더 |
| 테스트 전략 | 합성 raw fixture 5종 + point 무회귀 회귀세트 + 정의 round-trip + Knowledge end-to-end |

---

## 3. 상세 결정

### 3.1 정의 스키마 확장 (하위호환)

#### 신규 필드

```json
{
  "name": "급가속",
  "raw_columns": ["Vehicle.Acceleration.Longitudinal", "Vehicle.Speed", ...],
  "formula": "Vehicle.Acceleration.Longitudinal > 3.0",
  "output_columns": [...],
  "detection_mode": "episode",
  "episode": {
    "min_duration_sec": 0.5,
    "max_gap_sec": 0.5,
    "peak_column": "Vehicle.Acceleration.Longitudinal",
    "peak_agg": "max"
  },
  "parameters": { ... },
  "created_at": "...",
  "updated_at": "..."
}
```

#### 필드 명세

| 필드 | 타입 | 기본값 | 검증 | 설명 |
|---|---|---|---|---|
| `detection_mode` | str | `"point"` | `{"point","episode"}` | 검출 모드 |
| `episode.min_duration_sec` | float \| int | `0.0` | `0 ≤ x ≤ 86400` | 이 값 미만 episode 는 필터 — 단일 스파이크 제거 |
| `episode.max_gap_sec` | float \| int | `1.0` | `0 ≤ x ≤ 3600` | 두 연속 매칭 행 간격이 이 값 이하면 같은 episode 로 병합 |
| `episode.peak_column` | str | (필수) | `validate_column_name` + raw 스키마 존재 검사 | episode 의 peak 값을 산출할 raw 컬럼명 |
| `episode.peak_agg` | str | (선택) | `{"max","min"}` | peak 집계 방향. 누락 시 자동 결정 (3.3절) |

#### 누락 / 잘못된 값 처리

1. 정의 JSON 에 `detection_mode` 키 없음 → 메모리상 `"point"` 로 해석 (load 시 보강 안 함 — 원본 파일 변경 없음).
2. `detection_mode == "episode"` 인데 `episode` 객체 없음 → `ValueError("episode 모드는 episode 파라미터가 필요합니다")`.
3. `detection_mode == "point"` 인데 `episode` 객체 있음 → 무시하고 point 동작 (raw episode 키를 보존하되 로직에 영향 없음 — round-trip 보존).
4. `episode.peak_column` 가 raw 스키마에 없음 → 저장 시 경고 + 저장 차단 (UI), 런타임 detect 시 `ValueError`.

#### Round-trip 무회귀 보장

- `load_definition()` 은 `detection_mode` 가 없으면 dict 에 키를 추가하지 않는다 (또는 명시적으로 `"point"` 를 메모리에 주입하되 원본 파일은 변경 안 함 — **메모리 주입 방식 채택**).
- `save_definition()` 은 `detection_mode == "point"` 이고 호출자가 명시적으로 episode 파라미터를 넘기지 않으면, 기존 파일의 `detection_mode`/`episode` 필드를 **보존** (덮어쓰지 않음). 새 정의는 `detection_mode` 키를 **생략** 한다 (기본값이 point 이므로).
- 따라서 기존 33개 정의 JSON 은 본 변경 후에도 byte-for-byte 동일하게 유지된다 (사용자가 명시적으로 episode 로 전환·저장하기 전까지).

#### `_REQUIRED_FIELDS` 변화

| 필드 | 현재 | 변경 후 |
|---|---|---|
| `name`, `raw_columns`, `formula`, `output_columns`, `created_at`, `updated_at` | 필수 | 필수 (변화 없음) |
| `detection_mode` | (없음) | **선택** (없으면 point) |
| `episode` | (없음) | **조건부 선택** (`detection_mode == "episode"` 일 때만 필수, 외엔 옵션) |
| `parameters` | 선택 | 선택 (변화 없음) |

`_REQUIRED_FIELDS` frozenset 은 **변경하지 않는다** — `detection_mode` 가 누락된 기존 JSON 의 무회귀 로드 보장.

### 3.2 에피소드 검출 SQL (DuckDB gaps-and-islands)

#### 알고리즘 (의사 SQL)

```sql
WITH
  -- 1. 조건 참인 raw 행을 vehicle 별 시간순으로 정렬
  matched AS (
    SELECT
      vehicle_id,
      user_id,
      "<timestamp_col>" AS ts,
      "<peak_column>" AS peak_val,
      <output_cols...>
    FROM read_parquet(?)
    WHERE "<timestamp_col>" >= ? AND "<timestamp_col>" < ?
      AND ((<where_expr>))
      AND <vehicle_user_filter>
  ),
  -- 2. LAG 로 직전 매칭 행과의 시간 간격(초) 계산
  gapped AS (
    SELECT
      *,
      EPOCH(ts) - EPOCH(LAG(ts) OVER (PARTITION BY vehicle_id ORDER BY ts)) AS gap_sec
    FROM matched
  ),
  -- 3. gap 이 NULL (첫 행) 또는 max_gap_sec 초과면 새 island 시작
  flagged AS (
    SELECT
      *,
      CASE WHEN gap_sec IS NULL OR gap_sec > ? /* max_gap_sec */ THEN 1 ELSE 0 END AS new_island
    FROM gapped
  ),
  -- 4. 누적합으로 episode_id 부여 (vehicle 별 독립)
  numbered AS (
    SELECT
      *,
      SUM(new_island) OVER (PARTITION BY vehicle_id ORDER BY ts
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS episode_id
    FROM flagged
  ),
  -- 5. episode 단위 집계
  episodes AS (
    SELECT
      vehicle_id,
      ANY_VALUE(user_id) AS user_id,
      MIN(ts)            AS start_ts,
      MAX(ts)            AS end_ts,
      CAST(EPOCH(MAX(ts)) - EPOCH(MIN(ts)) AS BIGINT) AS duration_sec,
      <peak_agg>(peak_val) AS peak_value,
      COUNT(*)           AS sample_count,
      <peak-row 값들 — 3.3절>
    FROM numbered
    GROUP BY vehicle_id, episode_id
    HAVING duration_sec >= ? /* min_duration_sec — float 비교 시 캐스팅 */
  )
SELECT * FROM episodes
ORDER BY vehicle_id, start_ts;
```

#### 핵심 결정

1. **PARTITION BY `vehicle_id`** — vehicle 간 시간 인접 매칭이 같은 episode 로 묶이지 않게 보장 (요구사항).
2. **`EPOCH(ts)`** — DuckDB 의 `EPOCH(TIMESTAMP)` 는 초 단위 BIGINT 반환. raw `Timestamp` 가:
   - `TIMESTAMP` 타입 → `EPOCH()` 직접 호출.
   - 문자열 (`VARCHAR`) → `EPOCH(CAST(ts AS TIMESTAMP))` 로 캐스팅. 캐스팅 실패 시 `ValueError("timestamp_col 을 TIMESTAMP 로 변환할 수 없습니다")`.
   - 정수 epoch (`BIGINT` ms 또는 s) → 단순 차분 (캐스팅 불필요). **v1 범위 외** — raw 스키마는 현재 `Timestamp`/`timestamp` 컬럼이 모두 TIMESTAMP 또는 ISO 문자열로 통일되어 있음 (확인됨). epoch BIGINT 는 v2 로 보류.

   → **구현 단순화**: 모든 타입을 `CAST("<ts>" AS TIMESTAMP)` 로 통일 변환 후 `EPOCH` 호출. TIMESTAMP 입력은 캐스팅 no-op.

3. **새 island 판별**:
   - `gap_sec IS NULL` (첫 행) → 1
   - `gap_sec > max_gap_sec` → 1
   - `gap_sec == 0` (동일 timestamp) → 0 (같은 episode)
   - `gap_sec ≤ max_gap_sec` → 0 (같은 episode)

   엄격 부등호 `>` 사용 — `max_gap_sec` 와 정확히 같은 간격은 같은 episode (사용자 직관: "최대 X초 까지는 묶는다").

4. **`HAVING duration_sec >= min_duration_sec`** — `min_duration_sec = 0` 이면 단일 샘플 (`duration=0`) 도 포함.

#### 파라미터 바인딩 (보안)

`?` placeholder 로 바인딩하는 값:
- `raw_glob` (시스템 생성 — 신뢰 입력이지만 일관성 유지)
- `start`, `end_exclusive` (validate_iso_date 통과)
- `max_gap_sec` (float — 0 이상 검증 후)
- `min_duration_sec` (float — 0 이상 검증 후)
- `vehicle_ids` / `user_ids` (ADR-011 패턴 재사용)

`peak_column`, `timestamp_col`, `output_cols` 는 `validate_column_name` 통과 후 큰따옴표 quoted identifier 로 SQL 에 직접 삽입 (DuckDB 식별자 — placeholder 미지원). `peak_agg` 는 `{"max","min"}` 화이트리스트 통과 후 SQL 에 직접 삽입 (값이 이미 안전).

### 3.3 peak 방향 결정 (peak_agg)

#### 결정: `peak_agg` 명시 필드 + 자동 추론 보조

```json
"episode": {
  "peak_column": "Vehicle.Acceleration.Longitudinal",
  "peak_agg": "max"   // ← 사용자가 명시 (기본). UI 에서 자동 추론값을 제안
}
```

**대안 비교**

| 대안 | 장점 | 단점 | 채택 |
|---|---|---|---|
| (A) 항상 MAX | 단순 | 급감속(`< -3.5`) 의 peak 가 -3.5 가 아닌 -3.51 같은 더 작은 값이 되어야 함 → MIN 필요 → 동작 오류 | ❌ |
| (B) 항상 MIN | 동일 사유로 급가속에서 부적합 | | ❌ |
| (C) **명시 + 자동 추론** | 사용자 의도 명확. 자동 추론은 UX 보조 | 정의에 한 필드 추가 | ✅ |
| (D) WHERE 식 분석 (`< x` → MIN, `> x` → MAX) | 자동 | 복합 조건 (`A > 3 AND B < -2`) 에서 모호 | ❌ |

**자동 추론 규칙 (UI 보조)**

Event 페이지 에서 `peak_column` 선택 시 다음 휴리스틱으로 `peak_agg` 의 default 를 제안:
1. WHERE 식을 `_TOKEN_RE` 로 lex 하여 `peak_column` (또는 dotted 동등) 토큰 인접 비교 연산자를 찾는다.
2. `>` 또는 `>=` → `max` 제안.
3. `<` 또는 `<=` → `min` 제안.
4. 매칭 없음 / 양방향 모두 → `max` (기본).

사용자가 라디오로 최종 선택. **저장된 정의에는 사용자가 선택한 값이 들어간다 — 자동 추론은 UI default 일 뿐**.

#### output_cols 의 peak-행 값 (선택 옵션)

episode 결과 행에 "peak 가 발생한 raw 행 의 다른 컬럼 값" (예: peak 시점의 Speed) 을 포함하려면 `argmax`/`argmin` 패턴 사용:

```sql
arg_max(<other_col>, peak_val) AS <other_col>  -- peak_agg='max' 일 때
arg_min(<other_col>, peak_val) AS <other_col>  -- peak_agg='min' 일 때
```

**v1 단순화**: peak 행 값은 `output_cols` 에 명시된 컬럼 중 raw 에 실존하는 것만 `arg_max(col, peak_val)` 또는 `arg_min(col, peak_val)` 으로 포함. 누락된 컬럼은 NULL.

### 3.4 단일 샘플 에피소드 duration 처리

#### 결정: `duration_sec = 0` 그대로 둔다 (공칭 샘플간격 추정 안 함)

| 대안 | 결과 | 채택 |
|---|---|---|
| (A) **그대로 0** | 단순. `min_duration_sec > 0` 이면 자동 제거. Knowledge 시간 합산도 0 으로 정직 | ✅ |
| (B) 공칭 샘플간격 더하기 (예: 0.1초) | 의미 있는 시간 부여. 하지만 샘플레이트 추정 비용 (DESCRIBE + 통계 쿼리) + 추정 오차 | ❌ |
| (C) `min_duration_sec` 미만이면 episode 자체를 만들지 않음 | (A) 와 동일 효과 — `HAVING` 으로 처리됨. 별도 결정 없음 | (A) 에 흡수 |

**사유**: episode 모드의 **목적은 노이즈 제거** 이므로, 사용자는 `min_duration_sec = 0.5` 같은 양수값을 일반적으로 설정한다. 단일 샘플 (duration=0) 은 의도된 노이즈 → `HAVING` 으로 자연 제거. 명시적으로 `min_duration_sec = 0` 으로 설정한 사용자는 단일 샘플도 보고 싶다는 의도 → duration=0 그대로 보여주는 것이 정직하다.

**Knowledge 영향**: `{event}_시간 = SUM(duration_sec)` 에서 단일 샘플 episode 가 포함되면 0 을 더한다 (영향 없음). 이는 의도된 동작.

### 3.5 출력 parquet 스키마 (episode 모드)

#### 최소 컬럼

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `vehicle_id` | (raw 동일) | 차량 식별 — Knowledge 호환 필수 |
| `<timestamp_col>` | TIMESTAMP | episode 시작 시각 (= `start_ts`). raw 의 `timestamp_col` 이름 유지 (Knowledge events CTE 가 이 이름 기대) |
| `end_ts` | TIMESTAMP | episode 끝 시각 (참고용) |
| `duration_sec` | BIGINT | episode 지속 시간 (초). Knowledge `{event}_시간` 합산용 |
| `peak_value` | DOUBLE | episode 의 peak (peak_agg 적용 결과) |
| `sample_count` | BIGINT | episode 안의 raw 샘플 수 (디버깅·품질 평가용) |

#### 추가 컬럼 (선택)

- `user_id` (raw 에 존재할 때만) — ADR-011 user 필터 호환
- `output_cols` 에 명시된 raw 컬럼들 (peak 시점 행의 값, `arg_max`/`arg_min` 으로 산출) — UI 미리보기·다운로드 표 표시용

#### Knowledge calculator 호환

`knowledge_calculator._collect_event_parquets()` 는 `vehicle_id + timestamp_col + duration_sec` 컬럼만 있으면 동작. episode parquet 은 위 셋을 **반드시** 포함하므로 무회귀.

#### point 모드 출력 (변화 없음)

기존 그대로 — `vehicle_id, timestamp_col, output_cols, duration_sec=1`.

### 3.6 함수 인터페이스

#### 신규 모듈: `core/episode_detector.py`

기존 `formula_runner`/`event_extractor` 의 시그니처를 깨지 않기 위해 episode 전용 모듈 분리.

```python
# core/episode_detector.py

from __future__ import annotations
from pathlib import Path
import duckdb
import pandas as pd

# 검증 범위 상수
MIN_DURATION_MAX_SEC = 86400.0  # 1일
MAX_GAP_MAX_SEC = 3600.0        # 1시간
_VALID_PEAK_AGG = frozenset({"max", "min"})


def validate_episode_params(
    min_duration_sec: float | int,
    max_gap_sec: float | int,
    peak_column: str,
    peak_agg: str,
) -> None:
    """episode 파라미터 검증 — 음수·과대값·식별자 형식·peak_agg 화이트리스트.

    Raises:
        ValueError: 어느 항목이라도 검증 실패.
    """
    ...


def detect_episodes(
    parquet_glob: str | Path,
    where_expr: str,
    *,
    start: str,
    end: str,
    timestamp_col: str = "timestamp",
    peak_column: str,
    peak_agg: str = "max",
    min_duration_sec: float = 0.0,
    max_gap_sec: float = 1.0,
    output_cols: list[str] | None = None,
    allowed_root: str | Path | None = None,
    aliases: dict[str, str] | None = None,
    parameters: dict[str, object] | None = None,
    param_meta: dict[str, dict] | None = None,
    vehicle_ids: list | None = None,
    user_ids: list | None = None,
) -> pd.DataFrame:
    """gaps-and-islands episode 검출.

    Returns:
        DataFrame — vehicle_id, <timestamp_col> (start_ts), end_ts,
                    duration_sec, peak_value, sample_count, user_id?,
                    arg_max(output_cols)... 컬럼.
                    빈 결과 시 위 컬럼 schema 의 빈 DataFrame.

    Raises:
        ValueError: where_expr/식별자/파라미터/경로/날짜 검증 실패.
        duckdb.Error: SQL 실행 실패 (timestamp 캐스팅 실패 등).
    """
    ...


def count_episodes(
    parquet_glob: str | Path,
    where_expr: str,
    *,
    start: str,
    end: str,
    timestamp_col: str = "timestamp",
    peak_column: str,
    peak_agg: str = "max",
    min_duration_sec: float = 0.0,
    max_gap_sec: float = 1.0,
    allowed_root: str | Path | None = None,
    aliases: dict[str, str] | None = None,
    parameters: dict[str, object] | None = None,
    param_meta: dict[str, dict] | None = None,
    vehicle_ids: list | None = None,
    user_ids: list | None = None,
) -> dict:
    """episode 수 + 기간 + 일평균 + 평균 duration.

    Returns:
        {"total_count": int(에피소드 수),
         "days": int,
         "daily_avg": float,
         "avg_duration_sec": float,
         "total_duration_sec": float}
    """
    ...
```

#### 기존 함수의 episode 분기 (얇은 wrapper)

`run_where` / `count_matches` / `save_event_data` 의 **시그니처는 변경하지 않는다**. 대신 호출자(Event 페이지)가 정의의 `detection_mode` 를 보고 분기한다. 단, 다음 두 함수에는 **선택적 dispatch helper** 를 추가:

```python
# core/event_extractor.py — 추가 (기존 함수는 그대로 유지)

def count_matches_by_definition(
    definition: dict,                 # load_definition 결과
    parquet_glob: str | Path,
    *,
    start: str,
    end: str,
    timestamp_col: str = "timestamp",
    # ... 기존 파라미터들 (aliases, parameters, vehicle_ids, user_ids ...)
) -> dict:
    """definition['detection_mode'] 에 따라 count_matches 또는 count_episodes 로 분기.

    point 모드: 기존 count_matches 호출 (시그니처/결과 동일).
    episode 모드: count_episodes 호출 (episode 수 반환).
    """
    ...


def save_event_data_by_definition(
    definition: dict,
    parquet_glob: str | Path,
    *,
    start: str,
    end: str,
    event_root: str | Path,
    # ... 기존 파라미터들 + overwrite ...
) -> dict:
    """definition['detection_mode'] 에 따라 save_event_data 또는 episode 저장으로 분기.

    episode 모드:
      1. detect_episodes() 로 DataFrame 생성
      2. <event_root>/<name>/<start>_<end>.parquet 저장 (point 와 동일 경로 패턴)
      3. meta.json 에 detection_mode/episode 파라미터 추가 기록
    """
    ...
```

#### 시그니처 무회귀 보장

- `run_where(...)`, `count_matches(...)`, `save_event_data(...)` 의 **파라미터 목록은 추가/제거/순서 변경 없음**.
- 기존 호출부 (Event 페이지의 point 분기, knowledge_calculator 의 raw fallback 등) 100% 무회귀.

#### count_matches 가 "에피소드 수" 를 반환하는 위치

`count_matches_by_definition()` 신규 함수가 dispatch 담당. Event 페이지의 미리보기 코드는:

```python
# Event 페이지 (after 변경)
stats = count_matches_by_definition(
    definition,                     # ← detection_mode 포함된 정의
    parquet_glob, start=..., end=..., ...
)
# stats["total_count"] 는:
#   point   → 매칭 행 수
#   episode → 에피소드 수
```

기존 `count_matches()` 자체는 절대 의미를 바꾸지 않는다.

### 3.7 보안 / 검증

| 항목 | 검증 방법 | 위치 |
|---|---|---|
| `formula` (where_expr) | `validate_where_expr` (F004 화이트리스트, ADR-005) | `detect_episodes` 진입부 |
| `timestamp_col` | `validate_column_name` (`_sql_tokens` 또는 `_query_safety`) | 동일 |
| `peak_column` | `validate_column_name` + raw 스키마 존재 검사 (UI 단) | 동일 |
| `output_cols` | 각 항목 `validate_column_name` | 동일 |
| `min_duration_sec` | `isinstance(float \| int) and 0 ≤ x ≤ 86400 and not isinstance(bool)` | `validate_episode_params` |
| `max_gap_sec` | `isinstance(float \| int) and 0 ≤ x ≤ 3600 and not isinstance(bool)` | 동일 |
| `peak_agg` | `peak_agg in {"max","min"}` | 동일 |
| `vehicle_ids` / `user_ids` | ADR-011 패턴 — `?` placeholder 바인딩 | SQL 조립부 |
| `raw_glob` | `resolve_in_root(glob, allowed_root)` (옵션) | 동일 |
| `start`, `end` | `validate_iso_date` | 동일 |

상수 (`MIN_DURATION_MAX_SEC = 86400`, `MAX_GAP_MAX_SEC = 3600`) 는 `episode_detector.py` 모듈 상단에 명시.

### 3.8 UI 흐름 (Event 페이지)

#### 신규 위젯 배치

```
[기존] Event 이름 / 기간 / vehicle_id / user_id 필터
[기존] 사용할 Raw 컬럼 multiselect
[기존] 수식 textarea + 토큰 삽입 chip
[신규] 검출 모드 라디오 (point | episode) — 기본 point
[조건부] (episode 선택 시) Expander "에피소드 파라미터"
        ├─ min_duration_sec number_input  (default 0.5, step 0.1, min 0, max 86400)
        ├─ max_gap_sec number_input        (default 1.0, step 0.1, min 0, max 3600)
        ├─ peak_column selectbox           (raw_columns 에서 선택)
        └─ peak_agg radio (max | min)      (자동 추론된 값을 default)
[기존] 미리보기 (count_matches_by_definition 호출)
       point   → 행 수 + 일평균 + 상위 100건 표
       episode → 에피소드 수 + 일평균 + 상위 100 에피소드 표 (vehicle_id, start_ts, end_ts, duration_sec, peak_value, sample_count)
[기존] 정의만 저장 / 실행 및 저장 / 다운로드
```

#### session_state 키 추가

```python
_EVT_PERSIST_KEYS += (
    "evt_detection_mode",       # "point" | "episode"
    "evt_episode_min_duration", # float
    "evt_episode_max_gap",      # float
    "evt_episode_peak_column",  # str (raw_columns 에서)
    "evt_episode_peak_agg",     # "max" | "min"
)
```

정의 로드 시 — `_def["detection_mode"]` 가 있으면 위 키들에 채움. 없으면 `"point"` + episode 키들은 default.

저장 시 — `detection_mode == "episode"` 일 때만 `save_definition()` 에 `detection_mode + episode` 객체 전달. point 일 때는 전달하지 않음 (round-trip 무회귀).

#### 미리보기 표

| 모드 | 컬럼 |
|---|---|
| point (기존) | `<output_cols...>` |
| episode | `vehicle_id`, `<timestamp_col>` (start), `end_ts`, `duration_sec`, `peak_value`, `sample_count`, `<output_cols 중 raw 존재>` |

페이지네이션은 episode 결과에는 적용하지 않는다 — episode 수는 일반적으로 행 수보다 훨씬 적어 (`sample_count` 배수만큼 감소) `LIMIT 100` 만으로 충분. 100 초과 시 안내 메시지.

### 3.9 Knowledge 연동 (정상화)

`knowledge_calculator.calculate()` 는 **변경 없음**. episode parquet 이 `vehicle_id + timestamp + duration_sec` 컬럼을 가지므로 기존 events CTE 가 정상 동작.

| Knowledge 변수 | point 정의 | episode 정의 |
|---|---|---|
| `{event}_횟수 = COUNT(event_type='<name>')` | 행 수 | 에피소드 수 (정상화) |
| `{event}_시간 = SUM(duration_sec)` | 행 수 (1초씩) | 실제 지속시간 합 (초) |

#### Raw fallback (knowledge_calculator `_build_event_raw_fallback`)

event parquet 이 없을 때 정의 JSON 의 formula 를 raw 에 직접 적용하는 fallback 경로 (현재 `duration_sec = 1` 하드코딩, L262-264 와 동일 동작) 는 **v1 범위에서 변경하지 않는다**:

- 이유: fallback 은 "user 가 아직 episode 추출을 저장하지 않은 상태에서 Knowledge 를 미리 계산" 하는 비상 경로. 정확도보다 가용성 우선.
- 한계: episode 정의의 raw fallback 은 행 단위로 계수됨 (point 와 동일). 정확한 episode 계수가 필요하면 사용자는 먼저 "실행 및 저장" 으로 event parquet 을 생성해야 함.
- UI 안내: episode 정의가 fallback 경로로 실행될 때 Knowledge 페이지에 "정확한 에피소드 계수를 보려면 Event 페이지에서 먼저 추출을 저장하세요" 안내 메시지 (v2 후속).

### 3.10 테스트 전략

#### 합성 raw fixture (5종)

```python
# tests/test_episode_detector.py 에 in-memory parquet 또는 tmp_path fixture

S1. 단일 연속 20샘플 (0.1초 간격, > 임계) → 1 episode, duration≈1.9초, sample_count=20
S2. 두 episode 분리 (10샘플 + gap 3초 + 8샘플) → 2 episodes (max_gap_sec=1.0)
S3. 두 episode 병합 (10샘플 + gap 0.5초 + 8샘플) → 1 episode (max_gap_sec=1.0)
S4. 단일 스파이크 1샘플 → min_duration_sec=0.5 면 0 episodes, =0 이면 1 episode (duration=0)
S5. 2 vehicle 분리 (vehicle A 10샘플 + vehicle B 10샘플, 시간 인접) → 2 episodes
```

#### 회귀 test (point 무회귀)

```python
# tests/test_pages_event.py 등 기존 1818 test 모두 통과
# tests/test_event_definitions.py — detection_mode 누락 정의 round-trip
# 기존 33개 정의 JSON 을 한 번씩 load → save → byte 비교 (선택적, 정의별)
```

#### 정의 round-trip

```python
# tests/test_event_definitions_episode.py (신규)
# 1. detection_mode 없는 정의 load → 메모리 dict 에 detection_mode 키 없음 (또는 "point" 주입)
# 2. save_definition(name, ..., detection_mode=None) → 기존 파일과 동일 (detection_mode 키 미생성)
# 3. save_definition(..., detection_mode="episode", episode={...}) → 새 필드 추가
# 4. load 후 episode 파라미터 모두 보존
```

#### Knowledge 통합

```python
# tests/test_knowledge_calculator_episode.py (신규)
# - episode parquet 생성 후 calculate({event}_횟수=N, {event}_시간=duration합) 검증
# - point parquet 도 동시에 동작 (기존 test 무회귀)
```

#### Event 페이지 smoke (AppTest)

```python
# tests/test_pages_event.py 에 episode 모드 라디오 + 파라미터 입력 흐름 추가
```

#### 보안 회귀

```python
# tests/test_episode_detector_security.py (신규)
# - validate_episode_params: 음수, 과대값, bool, 미허용 peak_agg
# - peak_column 에 SQL 주입 시도 (";" 포함) → ValueError
# - vehicle_ids 에 SQL 주입 시도 → 파라미터 바인딩으로 ConversionException
```

---

## 4. 대안 검토

| 대안 | 장점 | 단점 | 결론 |
|---|---|---|---|
| **A. 신규 detection_mode 도입** (채택) | point 무회귀 100%. 정의별 모드 선택. 도메인 분류 명시적 | 정의 스키마 변경 (선택 필드 추가) | ✅ |
| B. 모든 정의를 episode 로 강제 전환 | 단순. 일관성 | 이산 상태 이벤트 (안전벨트미착용) 에 부적합. 기존 정의 round-trip 깨짐 | ❌ |
| C. 시간 윈도우 (resample) 방식 (`DATE_TRUNC('1s', ts)` 단위로 집계) | 구현 단순 | episode 경계가 1초 격자에 종속 — 0.5초 episode 가 1초로 반올림. max_gap_sec 개념 부재 | ❌ |
| D. Python pandas 의 `groupby` + `cumsum(diff > gap)` | DuckDB SQL 보다 디버깅 쉬움 | 메모리 로드 필요 → GB 단위 raw 에서 OOM. DuckDB 의 lazy scan 이점 상실 | ❌ |
| E. 이중 컬럼: `duration_sec` (현재 1) + `episode_duration_sec` 신규 | 기존 컬럼 보존 | 두 컬럼이 의미 분기 → Knowledge calculator 가 어느 것을 SUM 할지 분기 필요 → 복잡도 증가 | ❌ |
| F. point/episode 를 라디오가 아닌 자동 추론 (formula 만 보고) | 사용자 입력 줄임 | 의도 모호. "DrvSeatBelt = false" 이 point 인지 episode 인지 자동 판별 불가 | ❌ |

---

## 5. 결과

### 5.1 긍정적 영향

- 연속 신호 임계값 이벤트의 **횟수·시간 의미가 도메인 직관과 일치**
- 샘플링레이트 **종속성 제거** (10Hz/20Hz 가 같은 횟수)
- Knowledge `{event}_시간` 변수가 **실제 지속시간** 으로 정상화 → 분석 신뢰성 향상
- `point` 가 기본값으로 **기존 33개 정의 100% 무회귀**
- 신규 모듈 분리로 코드 격리 — 기존 1818 test 영향 없음

### 5.2 부정적 영향 / 트레이드오프

- 정의 JSON 스키마에 선택 필드 2개 추가 — `_REQUIRED_FIELDS` 미변경으로 round-trip 무회귀이나, 코드 path 가 분기됨
- DuckDB SQL 복잡도 증가 (5단 CTE) — 디버깅 시 사용자가 SQL 을 읽기 어려움. 대응: SQL 조립 함수에 단계별 주석 + 합성 fixture test 로 회귀 방지
- episode 모드 활성화 시 raw fallback 경로의 정확도 한계 (3.9절) — v2 후속 작업으로 명시

### 5.3 무회귀 보장 항목

| 항목 | 무회귀 보장 |
|---|---|
| 기존 33개 정의 JSON 파일 | byte-for-byte 동일 (사용자가 명시적으로 episode 로 전환·저장하기 전까지) |
| `core/formula_runner.run_where()` 시그니처 | 변경 없음 |
| `core/event_extractor.count_matches()` 시그니처 | 변경 없음 |
| `core/event_extractor.save_event_data()` 시그니처 | 변경 없음 |
| `core/knowledge_calculator.calculate()` 시그니처 | 변경 없음 |
| Event parquet (point 모드 저장) 스키마 | 변경 없음 (`vehicle_id + timestamp + output_cols + duration_sec=1`) |
| Knowledge `{event}_횟수`, `{event}_시간` 의 point 모드 정의 | 동일 동작 |
| `_REQUIRED_FIELDS` frozenset | 변경 없음 |
| 화이트리스트 보안 (F004, ADR-005) | 동일 적용 — `validate_where_expr`, `validate_column_name`, `?` placeholder 바인딩 |
| 기존 pytest suite (1818 passed) | 0 회귀 — episode 신규 test 만 추가 |

### 5.4 후속 조치

- [ ] Developer: `core/episode_detector.py` 신규 모듈 + 단위 테스트 (Session 1)
- [ ] Developer: `event_definitions.py` 스키마 확장 + round-trip 테스트 (Session 1)
- [ ] Developer: `event_extractor.py` dispatch helper 2개 추가 (Session 2)
- [ ] Developer: `pages/2_Event_추출_분석.py` UI 위젯 + 미리보기 표 (Session 2)
- [ ] Developer: Knowledge 통합 end-to-end test (Session 2 또는 3)
- [ ] QA: 합성 fixture 5종 + 회귀 + AppTest smoke + 보안 회귀 (Session 3)
- [ ] 하네스 동기화: ADR-012 본 파일을 `src/harness_template/claude.gstack/harness/docs/adr/` 에 미러링 (CLAUDE.md 의 동기화 정책 따름)

---

## 6. Developer 용 파일별 구현 계획

> 본 절은 Developer 에이전트가 본 ADR-012 만 보고 구현을 시작할 수 있도록 작성됨.
> 모든 변경은 **point 무회귀** 가 최우선이며, episode 신규 분기는 명시적 분기 (`detection_mode == "episode"`) 로만 트리거된다.

### 6.1 신규 파일

#### `src/data_analysis/dashboard/core/episode_detector.py` (신규)

상수 + 4 함수.

```python
# 상수
MIN_DURATION_MAX_SEC: float = 86400.0
MAX_GAP_MAX_SEC: float = 3600.0
_VALID_PEAK_AGG: frozenset[str] = frozenset({"max", "min"})

# Public 함수
def validate_episode_params(
    min_duration_sec: float | int,
    max_gap_sec: float | int,
    peak_column: str,
    peak_agg: str,
) -> None: ...

def detect_episodes(
    parquet_glob: str | Path,
    where_expr: str,
    *,
    start: str, end: str,
    timestamp_col: str = "timestamp",
    peak_column: str,
    peak_agg: str = "max",
    min_duration_sec: float = 0.0,
    max_gap_sec: float = 1.0,
    output_cols: list[str] | None = None,
    allowed_root: str | Path | None = None,
    aliases: dict[str, str] | None = None,
    parameters: dict[str, object] | None = None,
    param_meta: dict[str, dict] | None = None,
    vehicle_ids: list | None = None,
    user_ids: list | None = None,
) -> pd.DataFrame: ...

def count_episodes(
    parquet_glob: str | Path,
    where_expr: str,
    *,
    start: str, end: str,
    timestamp_col: str = "timestamp",
    peak_column: str,
    peak_agg: str = "max",
    min_duration_sec: float = 0.0,
    max_gap_sec: float = 1.0,
    allowed_root: str | Path | None = None,
    aliases: dict[str, str] | None = None,
    parameters: dict[str, object] | None = None,
    param_meta: dict[str, dict] | None = None,
    vehicle_ids: list | None = None,
    user_ids: list | None = None,
) -> dict: ...

# Private helpers (모듈 내부)
def _build_episode_sql(...) -> tuple[str, list]: ...
def _suggest_peak_agg(where_expr: str, peak_column: str) -> str: ...
```

**SQL 조립 (`_build_episode_sql`)**: 3.2절의 5단 CTE 그대로. `validate_where_expr` → `substitute_parameters` → 재검증 → `resolve_aliases` 순서는 `run_where` 와 동일 패턴 (코드 복사 가능).

**의존 모듈**: `core._query_safety`, `core._sql_tokens`, `core.formula_params`, `core.column_aliases`.

### 6.2 수정 파일

#### `src/data_analysis/dashboard/core/event_definitions.py`

- `EventDefinition` TypedDict 에 선택 필드 추가:
  ```python
  detection_mode: str  # "point" | "episode" — 선택 (없으면 point)
  episode: dict        # min_duration_sec/max_gap_sec/peak_column/peak_agg — episode 모드일 때 필수
  ```
- `_REQUIRED_FIELDS` **변경 없음**.
- `save_definition()` 시그니처 확장:
  ```python
  def save_definition(
      name, raw_columns, formula, output_columns, definitions_root,
      *,
      parameters=None,
      detection_mode: str | None = None,    # 신규 — None 이면 기존 동작 (필드 생략)
      episode: dict | None = None,          # 신규 — None 이면 기존 동작
  ) -> EventDefinition: ...
  ```
  - `detection_mode is None` → 기존 파일의 값 유지 (덮어쓰기 없음, parameters 와 동일 패턴)
  - `detection_mode == "point"` → JSON 에서 `detection_mode`/`episode` 키 **생략** (round-trip 무회귀)
  - `detection_mode == "episode"` → JSON 에 `detection_mode: "episode"` + `episode: {...}` 추가. `episode is None` 이면 `ValueError`.
- `load_definition()` 시그니처 변경 없음. 반환 dict 에 `detection_mode`/`episode` 가 있으면 그대로 포함, 없으면 키 없음 (메모리 주입 안 함 — 호출자가 `.get("detection_mode", "point")` 패턴 사용).
- `_validate_definition_schema()` — `detection_mode` 값이 있으면 `{"point","episode"}` 검증. `episode` 키 검증: episode 모드일 때 `min_duration_sec`/`max_gap_sec`/`peak_column`/`peak_agg` 모두 존재 + 타입 검증.

#### `src/data_analysis/dashboard/core/event_extractor.py`

- 기존 `count_matches()`, `save_event_data()` **시그니처 변경 없음**.
- 신규 함수 2개:
  ```python
  def count_matches_by_definition(
      definition: dict,
      parquet_glob: str | Path,
      *,
      start: str, end: str,
      timestamp_col: str = "timestamp",
      allowed_root: str | Path | None = None,
      aliases: dict[str, str] | None = None,
      parameters: dict[str, object] | None = None,
      param_meta: dict[str, dict] | None = None,
      vehicle_ids: list | None = None,
      user_ids: list | None = None,
  ) -> dict: ...

  def save_event_data_by_definition(
      definition: dict,
      parquet_glob: str | Path,
      *,
      start: str, end: str,
      event_root: str | Path,
      output_cols: list[str],
      timestamp_col: str = "timestamp",
      allowed_root: str | Path | None = None,
      overwrite: bool = False,
      aliases: dict[str, str] | None = None,
      parameters: dict[str, object] | None = None,
      param_meta: dict[str, dict] | None = None,
      vehicle_ids: list | None = None,
      user_ids: list | None = None,
  ) -> dict: ...
  ```
- dispatch 로직:
  ```python
  mode = definition.get("detection_mode", "point")
  if mode == "point":
      return count_matches(...)  # 기존 함수 그대로
  elif mode == "episode":
      ep = definition["episode"]
      return count_episodes(
          parquet_glob, where_expr=definition["formula"],
          peak_column=ep["peak_column"], peak_agg=ep.get("peak_agg", "max"),
          min_duration_sec=ep.get("min_duration_sec", 0.0),
          max_gap_sec=ep.get("max_gap_sec", 1.0),
          ...
      )
  ```
- episode 모드 저장 시 meta.json 추가 필드:
  ```python
  meta = {
      ...,  # 기존 필드
      "detection_mode": "episode",
      "episode": {min_duration_sec, max_gap_sec, peak_column, peak_agg},
      "row_count": int(에피소드 수),
  }
  ```

#### `src/data_analysis/dashboard/pages/2_Event_추출_분석.py`

- 신규 session_state 키 5개 (3.8절) — `_EVT_PERSIST_KEYS` 에 추가.
- 정의 로드 분기:
  ```python
  _det_mode = _def.get("detection_mode", "point")
  st.session_state["evt_detection_mode"] = _det_mode
  if _det_mode == "episode":
      _ep = _def.get("episode", {})
      st.session_state["evt_episode_min_duration"] = _ep.get("min_duration_sec", 0.5)
      st.session_state["evt_episode_max_gap"] = _ep.get("max_gap_sec", 1.0)
      st.session_state["evt_episode_peak_column"] = _ep.get("peak_column", "")
      st.session_state["evt_episode_peak_agg"] = _ep.get("peak_agg", "max")
  ```
- 라디오 + Expander UI (3.8절 배치도 참조).
- 미리보기 분기:
  ```python
  if st.session_state["evt_detection_mode"] == "episode":
      definition = {
          "formula": formula,
          "detection_mode": "episode",
          "episode": {...},
      }
      stats = count_matches_by_definition(definition, ...)
      # 표는 detect_episodes(...) 호출하여 상위 100 episode 렌더
  else:
      stats = count_matches(...)  # 기존 path
  ```
- 저장 분기:
  ```python
  save_definition(
      name=event_name,
      raw_columns=...,
      formula=formula,
      output_columns=selected_cols,
      definitions_root=DEFINITIONS_DIR,
      parameters=_params_to_save,
      detection_mode=st.session_state.get("evt_detection_mode") if mode == "episode" else None,
      episode={...} if mode == "episode" else None,
  )
  save_event_data_by_definition(definition, ...)
  ```

#### `src/data_analysis/dashboard/core/knowledge_calculator.py`

- **변경 없음** (3.9절). episode parquet 이 호환 스키마이므로 기존 events CTE 가 정상 동작.

### 6.3 신규 테스트 파일

| 파일 | 내용 | 케이스 수 |
|---|---|---|
| `tests/test_episode_detector.py` | 합성 fixture 5종 + 파라미터 검증 + 경계 조건 (max_gap=0, min_duration=0, 단일 vehicle, 다중 vehicle) | ~25 |
| `tests/test_episode_detector_security.py` | `validate_episode_params` + SQL 주입 차단 (peak_column 문자열) | ~10 |
| `tests/test_event_definitions_episode.py` | 스키마 round-trip (point ↔ episode), 누락 필드 처리, save 시 episode 미전달 시 기존 보존 | ~12 |
| `tests/test_event_extractor_dispatch.py` | `count_matches_by_definition` / `save_event_data_by_definition` dispatch + meta.json 필드 | ~8 |
| `tests/test_pages_event_episode.py` | AppTest smoke — 라디오 전환, 파라미터 입력, 미리보기 표 렌더 | ~5 |
| `tests/test_knowledge_calculator_episode.py` | episode parquet → Knowledge 통합 (`{event}_횟수`/`{event}_시간`) | ~6 |
| (기존) `tests/test_pages_event.py` | point 무회귀 유지 — 수정 없거나 episode 키 default 추가만 | 0 신규 |

목표 총계: 1818 + ~66 ≈ 1884 passed (회귀 0).

### 6.4 ruff / 포매팅

- 모든 신규 파일은 기존 모듈과 동일한 스타일 (docstring 한국어, `from __future__ import annotations`, 4 space indent).
- `ruff check src/data_analysis/dashboard` + `ruff format src/data_analysis/dashboard` clean 보장.

### 6.5 git 커밋 메시지 (제안)

```
feat(F030): 에피소드(윈도우) 기반 이벤트 검출 — episode 모드 추가

ADR-012 결정에 따라 정의 스키마에 detection_mode + episode 파라미터를
선택 필드로 추가. point 가 기본값이라 기존 33개 정의 100% 무회귀.

DuckDB gaps-and-islands SQL (5단 CTE) 로 조건 참인 연속 구간을
vehicle 별로 1 에피소드로 묶어 start/end/duration/peak/sample_count
산출. min_duration_sec 으로 노이즈 제거, max_gap_sec 으로 인접 구간 병합.

신규: core/episode_detector.py (detect_episodes/count_episodes/검증)
수정: core/event_definitions.py (선택 필드), core/event_extractor.py
      (dispatch helper 2개), pages/2_Event_추출_분석.py (UI)
미수정: core/formula_runner.py, core/knowledge_calculator.py
        (시그니처 무회귀 최우선)
테스트: 신규 66 케이스 — episode 동작/round-trip/dispatch/Knowledge 통합
```

---

## 7. 미해결 / v2 후속

- Raw fallback 경로의 episode 정확도 (3.9절) — Knowledge 페이지에서 episode 정의를 fallback 경로로 평가할 때 행 단위 계수로 떨어짐. 정확도가 필요한 사용자는 사전에 Event 저장 필요. UI 안내만 추가하고 v2 에서 fallback 경로도 episode SQL 사용하도록 확장.
- epoch BIGINT (ms/s 단위 timestamp) 자동 인식 — 현재는 TIMESTAMP/문자열 형식만 지원. v2 에서 raw 스키마 자동 감지 → 캐스팅 분기.
- arg_max / arg_min 의 NULL 처리 — `output_cols` 에 명시되었으나 raw 에 없는 컬럼은 v1 에서 NULL. UI 가 안내 표시할지 결정 (v2).
- 다중 raw 컬럼 peak (예: "Accel 의 절댓값 peak" — 양/음 모두 의미 있는 경우) — 현재는 max 또는 min 한 방향만. v2 에서 `peak_agg = "abs_max"` 옵션 추가 검토.

---

*작성: Architect 에이전트 | 날짜: 2026-06-08*
