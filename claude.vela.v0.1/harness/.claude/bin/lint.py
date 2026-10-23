#!/usr/bin/env python3
"""F009 — Lint helper for harness governance.

정합성 헬스체크 도구. 거버넌스 산출물(feature_list / ADR / learnings / mirror)을
JSON·마크다운 분석으로 검사한다.

서브커맨드:
  check                  — 검사기 실행, 결과를 stdout에 표로 출력
  check --strict         — BLOCK이 1건이라도 있으면 exit 1 (기본은 항상 0)
  check --only=LINT-FL   — 특정 검사기만 실행
  check --json           — 머신용 JSON 출력
  regenerate-index       — docs/index.md 갱신
  report                 — 캐시된 마지막 실행 결과 표시

검사기:
  LINT-FL     feature_list 정합성 (status×passes, 의존성 무결성)
  LINT-STALE  stale in-progress (>30일)
  LINT-AC     acceptance_criteria 누락·모호
  LINT-ADR    ADR ↔ feature 연결성
  LINT-LEARN  learnings 모순 휴리스틱
  LINT-SSOT   main ≡ claude.loope invariant (ADR-015, BLOCK)
  LINT-MIRROR gstack 표준 변형 대조 (참고용 INFO)
  LINT-MR     변형 오버레이 정합 — **파일** 단위 (ADR-015 결정 3)
  LINT-CO     내용 오버레이 정합 — 공유 파일 **안**의 변형군별 사본 (ADR-015 결정 5, BLOCK)
  LINT-FREEZE 동결 스냅샷 불변 — baseline · openai/.codex (ADR-015 결정 6, BLOCK)
  LINT-ATL    Atlassian 쓰기 대상 제한 — 3-C 철칙 (배포본 fail-closed)

검사기·규칙 **개수를 적지 않는다** — 세 번 낡았다 (세려면 `grep -c "MR-[0-9]*:" 이 파일`).

외부 의존성: 없음 (Python stdlib only)
hook-failure-tolerance: 최상위 try/except → 예기치 못한 예외도 stderr + exit 0.
  **단 게이트 검사기는 예외다** — 아래 `_GATE_CHECKERS` 참조. 훅의 관용은 훅의 것이지
  게이트 검사기의 것이 아니다 (검사기가 죽으면 조용히 통과하는 것이 가장 나쁜 실패다).
"""

import argparse
import ast
import difflib
import json
import re
import sys
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 프로젝트 루트: bin/lint.py → .claude/bin/lint.py → 프로젝트 루트
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FEATURE_LIST = _PROJECT_ROOT / "feature_list.json"
_DOCS_ADR = _PROJECT_ROOT / "docs" / "adr"
_DOCS_DESIGN = _PROJECT_ROOT / "docs" / "design"
_DOCS_INDEX = _PROJECT_ROOT / "docs" / "index.md"
_STATE_DIR = _PROJECT_ROOT / ".claude" / "state"
_CHECKPOINTS_DIR = _STATE_DIR / "checkpoints"
_LEARNINGS_FILE = _STATE_DIR / "learnings.jsonl"
_CACHE_FILE = _STATE_DIR / "lint-last.json"
_CLAUDE_DIR = _PROJECT_ROOT / ".claude"
_GSTACK_DIR = (_PROJECT_ROOT / "src" / "harness_template"
               / "claude.gstack" / "harness" / ".claude")
_BASELINE_AGENTS_DIR = (_PROJECT_ROOT / "src" / "harness_template"
                        / "claude" / "harness" / ".claude" / "agents")
_OPENAI_SKILLS_DIR = (_PROJECT_ROOT / "src" / "harness_template"
                      / "openai" / "harness" / ".codex" / "skills")

# 라벨 (F007 design-review 일관)
BLOCK = "BLOCK"
CONCERN = "CONCERN"
INFO = "INFO"
PASS = "PASS"

# 모호 키워드 패턴 (LINT-AC)
_VAGUE_PATTERNS = re.compile(
    r"\b(잘\s*동작|적절히|일반적으로|충분히|문제없이|정상적으로|대략|적당히|보통"
    r"|works\s+correctly|properly|reasonably|appropriately)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 공통 타입
# ---------------------------------------------------------------------------

def _issue(checker_id: str, label: str, target: str, message: str) -> dict:
    """단일 검사 결과 딕셔너리를 생성한다."""
    return {
        "id": checker_id,
        "label": label,
        "target": target,
        "message": message,
    }


# ---------------------------------------------------------------------------
# LINT-FL: feature_list 정합성
# ---------------------------------------------------------------------------

def check_fl() -> list:
    """
    feature_list.json 의 정합성을 검사한다.

    검사 항목:
    - passes/status 조합 BLOCK: passes=true & status!=done, 또는 status=done & passes=false
    - 의존성 참조 무결성: dependencies 에 존재하지 않는 ID 포함 시 BLOCK
    - 의존성 순서 CONCERN: 의존 feature 가 아직 passes=false 인데 본인이 in-progress 이상
    - INFO: priority 또는 estimated_sessions 누락

    Returns:
        list[dict]: 검사 결과 목록 (각 dict는 id/label/target/message 키 보유)
    """
    results = []
    checker = "LINT-FL"

    try:
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, BLOCK, "feature_list.json", "파일이 존재하지 않음"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        all_ids = {feat.get("id") for feat in features if "id" in feat}
        status_order = ["todo", "in-progress", "review", "qa", "done"]

        for feat in features:
            fid = feat.get("id", "UNKNOWN")
            passes = feat.get("passes")
            status = feat.get("status")

            # 필수 필드 확인
            for field in ("passes", "status", "id"):
                if field not in feat:
                    results.append(_issue(checker, BLOCK, fid, f"필수 필드 누락: {field}"))

            if passes is None or status is None:
                continue

            # passes × status 정합성
            if passes is True and status != "done":
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"passes=true 인데 status={status!r} (done 이어야 함)"
                ))
            elif passes is False and status == "done":
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"status=done 인데 passes=false (passes=true 이어야 함)"
                ))
            else:
                # 정상 케이스도 명시적 PASS
                results.append(_issue(checker, PASS, fid, "passes×status 정합성 OK"))

            # 의존성 무결성
            deps = feat.get("dependencies", [])
            for dep_id in deps:
                if dep_id not in all_ids:
                    results.append(_issue(
                        checker, BLOCK, fid,
                        f"dependencies에 존재하지 않는 ID 참조: {dep_id}"
                    ))

            # 의존성 순서 CONCERN
            if status in ("in-progress", "review", "qa", "done"):
                for dep_id in deps:
                    dep_feat = next((d for d in features if d.get("id") == dep_id), None)
                    if dep_feat and not dep_feat.get("passes", True):
                        results.append(_issue(
                            checker, CONCERN, fid,
                            f"의존 feature {dep_id}가 아직 passes=false 인데 status={status!r}"
                        ))

            # INFO: priority / estimated_sessions 누락
            if not feat.get("priority"):
                results.append(_issue(checker, INFO, fid, "priority 필드 미설정"))
            if not feat.get("estimated_sessions"):
                results.append(_issue(checker, INFO, fid, "estimated_sessions 필드 미설정"))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "feature_list.json", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-STALE: 오래된 in-progress
# ---------------------------------------------------------------------------

def _parse_checkpoint_date(filename: str):
    """
    체크포인트 파일명에서 날짜를 파싱한다.

    파일명 형식: YYYYMMDD-HHMMSS-*.md 또는 YYYYMMDD-*.md

    Returns:
        datetime | None
    """
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", filename)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def check_stale() -> list:
    """
    in-progress 상태인 feature 의 stale 여부를 검사한다.

    비교 방법:
    - .claude/state/checkpoints/ 파일명 YYYYMMDD prefix 파싱 → 가장 최근 일자 추출
    - in-progress feature 와 마지막 checkpoint 날짜 차이 계산

    라벨:
    - BLOCK: 60일 이상 경과
    - CONCERN: 30~60일 경과
    - INFO: 0~30일 또는 checkpoint 없음

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-STALE"

    try:
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, INFO, "feature_list.json", "파일 없음 — 검사 스킵"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        in_progress = [f for f in features if f.get("status") == "in-progress"]

        if not in_progress:
            results.append(_issue(checker, INFO, "feature_list.json", "in-progress feature 없음 — 검사 대상 0건"))
            return results

        # 가장 최근 checkpoint 날짜 추출
        latest_checkpoint_dt = None
        if _CHECKPOINTS_DIR.exists():
            checkpoint_dates = []
            for cp_file in _CHECKPOINTS_DIR.glob("*.md"):
                dt = _parse_checkpoint_date(cp_file.name)
                if dt:
                    checkpoint_dates.append(dt)
            if checkpoint_dates:
                latest_checkpoint_dt = max(checkpoint_dates)

        now = datetime.now(tz=timezone.utc)

        for feat in in_progress:
            fid = feat.get("id", "UNKNOWN")

            if latest_checkpoint_dt is None:
                results.append(_issue(checker, INFO, fid, "checkpoint 파일 없음 — 경과일 추정 불가"))
                continue

            elapsed_days = (now - latest_checkpoint_dt).days

            if elapsed_days >= 60:
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"in-progress 상태이며 최근 checkpoint로부터 {elapsed_days}일 경과 (60일 이상 — stale)"
                ))
            elif elapsed_days >= 30:
                results.append(_issue(
                    checker, CONCERN, fid,
                    f"in-progress 상태이며 최근 checkpoint로부터 {elapsed_days}일 경과 (30~60일)"
                ))
            else:
                results.append(_issue(
                    checker, INFO, fid,
                    f"in-progress 상태이며 최근 checkpoint로부터 {elapsed_days}일 경과 (30일 미만)"
                ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "feature_list.json", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-AC: acceptance_criteria 누락·모호
# ---------------------------------------------------------------------------

def check_ac() -> list:
    """
    feature_list.json 각 feature 의 acceptance_criteria 를 검사한다.

    검사 항목:
    - BLOCK: acceptance_criteria 배열 자체 없거나 비어있음
    - CONCERN: 모호 키워드 포함 항목 존재 (정규식: _VAGUE_PATTERNS)
    - INFO: 단일 항목 (분해 부족 가능성)

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-AC"

    try:
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, INFO, "feature_list.json", "파일 없음 — 검사 스킵"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        for feat in features:
            fid = feat.get("id", "UNKNOWN")
            ac = feat.get("acceptance_criteria")

            if ac is None or (isinstance(ac, list) and len(ac) == 0):
                results.append(_issue(
                    checker, BLOCK, fid,
                    "acceptance_criteria 배열이 없거나 비어있음"
                ))
                continue

            if not isinstance(ac, list):
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"acceptance_criteria 타입 오류: {type(ac).__name__} (list 이어야 함)"
                ))
                continue

            # 모호 키워드 검사
            vague_found = []
            for item in ac:
                if isinstance(item, str) and _VAGUE_PATTERNS.search(item):
                    vague_found.append(item[:60] + ("..." if len(item) > 60 else ""))

            if vague_found:
                for vague in vague_found:
                    results.append(_issue(
                        checker, CONCERN, fid,
                        f"모호 키워드 포함: {vague!r}"
                    ))
            else:
                results.append(_issue(checker, PASS, fid, f"acceptance_criteria {len(ac)}건 — 모호 키워드 없음"))

            # 단일 항목 INFO
            if len(ac) == 1:
                results.append(_issue(
                    checker, INFO, fid,
                    "acceptance_criteria가 1건 — 분해 부족 가능성 (INFO)"
                ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "feature_list.json", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-ADR: ADR ↔ feature 연결성
# ---------------------------------------------------------------------------

def _parse_adr_frontmatter(content: str) -> dict:
    """
    ADR 마크다운에서 frontmatter와 status를 파싱한다.

    ADR은 YAML --- 블록이 아닌 헤딩과 섹션으로 구성되므로
    '## 상태' 섹션과 Feature 참조(Fxxx 패턴)를 추출한다.

    헤더의 `> Feature: Fxxx` 줄을 주 feature로 추출하고,
    본문 전체에서 F000 패턴을 보조 참조로 추출한다.

    Args:
        content: ADR 파일 전체 내용

    Returns:
        dict: {"status": str, "feature_refs": list[str], "primary_features": list[str]}
    """
    status = "unknown"
    # 상태 추출: `status:` 라인 또는 `## 상태` 섹션 첫 줄의 backtick 값
    status_match = re.search(r"`([A-Za-z][A-Za-z\s]+)`", content[:500])
    if status_match:
        raw = status_match.group(1).strip().lower()
        if any(kw in raw for kw in ("accepted", "proposed", "deprecated", "superseded")):
            status = raw.split()[0]  # 첫 단어만 (예: "accepted" 추출)

    # 주 feature 추출: 헤더의 "> Feature: Fxxx" 또는 "> Feature: Fxxx, Fyyy" 패턴
    primary_features = []
    header_feature_match = re.search(r">\s*Feature\s*:\s*((?:F\d{3}[,\s]*)+)", content[:300])
    if header_feature_match:
        primary_features = sorted(set(
            f"F{n}" for n in re.findall(r"F(\d{3})", header_feature_match.group(1))
        ))

    # 본문 전체 feature 참조 추출 (주 feature + 본문 내 참조)
    feature_refs = re.findall(r"\bF(\d{3})\b", content)
    feature_refs = sorted(set(f"F{n}" for n in feature_refs))

    return {
        "status": status,
        "feature_refs": feature_refs,
        "primary_features": primary_features,
    }


def check_adr() -> list:
    """
    ADR ↔ feature 연결성을 검사한다.

    검사 항목:
    - BLOCK: ADR에서 참조하는 feature ID가 feature_list.json에 존재하지 않음
    - CONCERN: feature가 category=infra + dependencies 3개 이상인데 ADR 0개 (설계 누락 가능성)
    - INFO: ADR status가 proposed이지만 관련 feature는 이미 done
    - PASS: 정합성 OK

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-ADR"

    try:
        # feature_list 로드
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, INFO, "feature_list.json", "파일 없음 — 검사 스킵"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        all_feature_ids = {feat.get("id") for feat in features if "id" in feat}
        feature_by_id = {feat["id"]: feat for feat in features if "id" in feat}

        # ADR 파일 목록
        if not _DOCS_ADR.exists():
            results.append(_issue(checker, INFO, "docs/adr/", "ADR 디렉토리 없음 — 검사 스킵"))
            return results

        # ADR-000-template.md 제외 (_load_adrs와 일관성 유지)
        adr_files = [f for f in sorted(_DOCS_ADR.glob("ADR-*.md"))
                     if "template" not in f.name.lower()]
        if not adr_files:
            results.append(_issue(checker, INFO, "docs/adr/", "ADR 파일 없음 — 검사 스킵"))
            return results

        # 각 feature에 연결된 ADR 추적
        feature_to_adrs: dict = {fid: [] for fid in all_feature_ids}

        for adr_path in adr_files:
            adr_name = adr_path.name
            try:
                content = adr_path.read_text(encoding="utf-8")
            except Exception as exc:
                results.append(_issue(checker, INFO, adr_name, f"파일 읽기 실패 — {exc}"))
                continue

            parsed = _parse_adr_frontmatter(content)
            adr_status = parsed["status"]
            feature_refs = parsed["feature_refs"]
            primary_features = parsed["primary_features"]

            if not feature_refs:
                results.append(_issue(checker, INFO, adr_name, "feature 참조 없음 (F000 패턴 미발견)"))
                continue

            # 참조하는 feature ID 유효성 검사
            # 주 feature(헤더의 > Feature: Fxxx)만 BLOCK, 본문 예시 참조는 INFO
            valid_refs = []
            for fid in feature_refs:
                if fid not in all_feature_ids:
                    # 주 feature인 경우만 BLOCK, 본문 참조는 INFO
                    if fid in primary_features:
                        results.append(_issue(
                            checker, BLOCK, adr_name,
                            f"헤더에 선언된 주 feature ID가 feature_list.json에 없음: {fid}"
                        ))
                    else:
                        results.append(_issue(
                            checker, INFO, adr_name,
                            f"본문 참조 feature ID가 feature_list.json에 없음 (예시/미래계획일 수 있음): {fid}"
                        ))
                else:
                    valid_refs.append(fid)
                    feature_to_adrs[fid].append(adr_name)

            # INFO: ADR proposed이지만 feature는 done
            adr_reported = set()
            for fid in valid_refs:
                feat = feature_by_id.get(fid)
                if feat and adr_status == "proposed" and feat.get("status") == "done":
                    results.append(_issue(
                        checker, INFO, adr_name,
                        f"ADR status=proposed이지만 관련 feature {fid}는 done — ADR 상태 갱신 고려"
                    ))
                    adr_reported.add(adr_name)

            if valid_refs and adr_name not in adr_reported:
                results.append(_issue(checker, PASS, adr_name, f"feature 참조 정합 OK: {', '.join(sorted(set(valid_refs)))}"))

        # CONCERN: infra category + dependencies 3개 이상인데 ADR 없음
        for feat in features:
            fid = feat.get("id", "UNKNOWN")
            if (feat.get("category") == "infra"
                    and len(feat.get("dependencies", [])) >= 3
                    and not feature_to_adrs.get(fid)):
                results.append(_issue(
                    checker, CONCERN, fid,
                    "category=infra + dependencies 3개 이상인데 연결된 ADR 없음 — 설계 누락 가능성"
                ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "LINT-ADR", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-LEARN: learnings 모순 휴리스틱
# ---------------------------------------------------------------------------

# 부정 키워드: 사용 금지 의미
_NEGATIVE_KEYWORDS = [
    "금지", "사용 금지", "must not", "should not", "절대", "하지 마", "하면 안",
    "피해야", "avoid", "never", "do not", "don't",
]
# 긍정 키워드: 사용 권장 의미
_POSITIVE_KEYWORDS = [
    "사용", "권장", "should", "must use", "use ", "recommended", "prefer",
    "써야", "사용해야", "활용",
]


def _extract_topic_words(text: str) -> set:
    """
    학습 텍스트에서 주제 단어(명사/식별자)를 추출한다.

    코드 식별자(snake_case, camelCase), 기술 용어를 추출한다.
    단순 휴리스틱이라 정밀도보다 재현율 우선.

    Args:
        text: insight 또는 key 문자열

    Returns:
        set[str]: 추출된 주제 단어 집합
    """
    # 영문 식별자, 기술 용어 추출 (snake_case, camelCase, hyphenated)
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-\.]{2,}", text)
    # 한글 명사성 단어 (3글자 이상으로 제한 — 조사/어미 false positive 방지)
    korean = re.findall(r"[가-힣]{3,}", text)
    result = set(w.lower() for w in words) | set(korean)
    # 너무 일반적인 영문 단어 제거
    stopwords_en = {
        "the", "this", "that", "with", "from", "have", "will", "for",
        "are", "not", "and", "but", "can", "use", "when", "then",
        "should", "must", "also", "about", "into", "only", "each",
        "all", "any", "one", "two", "new", "old", "its", "our",
        "which", "their", "them", "was", "has", "been", "had",
        "via", "per", "etc", "same", "how", "out", "off",
    }
    # 한글 일반 동사/조사성 표현 불용어 (2~3글자 어미·조사)
    stopwords_ko = {
        "한다", "하다", "이다", "있다", "없다", "된다", "된다",
        "으로", "에서", "이나", "하면", "이면", "하여", "하고",
        "것이", "경우", "수도", "있는", "없는", "되는", "하는",
        "것을", "들이", "에서", "에게", "에서", "것과",
    }
    return result - stopwords_en - stopwords_ko


def check_learn() -> list:
    """
    learnings.jsonl의 모순을 휴리스틱으로 검사한다.

    검사 항목:
    - CONCERN: 동일 주제 키워드가 한 entry에서 부정, 다른 entry에서 긍정으로 등장
    - INFO: confidence <= 5인 entry
    - INFO: type별 카운트가 1건 이하인 경우 (소규모 학습)
    - PASS: 명백한 모순 없음

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-LEARN"

    try:
        if not _LEARNINGS_FILE.exists():
            results.append(_issue(checker, INFO, "learnings.jsonl", "파일 없음 — 검사 스킵"))
            return results

        entries = []
        with open(_LEARNINGS_FILE, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry["_lineno"] = lineno
                    entries.append(entry)
                except json.JSONDecodeError as exc:
                    results.append(_issue(checker, INFO, f"learnings.jsonl:{lineno}", f"JSON 파싱 실패 — {exc}"))

        if not entries:
            results.append(_issue(checker, INFO, "learnings.jsonl", "유효한 entry 없음"))
            return results

        # confidence <= 5 INFO
        for entry in entries:
            confidence = entry.get("confidence")
            if isinstance(confidence, (int, float)) and confidence <= 5:
                key = entry.get("key", f"line{entry['_lineno']}")
                results.append(_issue(
                    checker, INFO, f"learnings:{key}",
                    f"confidence={confidence} (5 이하 — 신뢰도 낮음)"
                ))

        # type별 카운트
        type_counts: dict = {}
        for entry in entries:
            t = entry.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        for t, cnt in type_counts.items():
            if cnt <= 1:
                results.append(_issue(
                    checker, INFO, f"learnings:type={t}",
                    f"type={t!r} 카운트 {cnt}건 — 소규모 학습 (INFO)"
                ))

        # 모순 탐지: 동일 주제 키워드에 부정+긍정 동시 등장
        # topic → [(key, sentiment)] 매핑 구성
        topic_sentiments: dict = {}  # topic_word → {"neg": [key...], "pos": [key...]}

        for entry in entries:
            # insight만 사용 (key는 식별자라 false positive 유발)
            text = entry.get("insight", "").lower()
            key = entry.get("key", f"line{entry['_lineno']}")

            is_neg = any(kw in text for kw in _NEGATIVE_KEYWORDS)
            # 부정 맥락이면 긍정 매칭 제외 — false positive 감소
            is_pos = (any(kw in text for kw in _POSITIVE_KEYWORDS) and not is_neg)

            if not (is_neg or is_pos):
                continue

            topics = _extract_topic_words(text)
            for topic in topics:
                if topic not in topic_sentiments:
                    topic_sentiments[topic] = {"neg": [], "pos": []}
                if is_neg:
                    topic_sentiments[topic]["neg"].append(key)
                if is_pos:
                    topic_sentiments[topic]["pos"].append(key)

        # 모순: 동일 topic에 neg와 pos 모두 등장
        contradiction_reported = set()
        for topic, sentiments in topic_sentiments.items():
            negs = sentiments["neg"]
            poss = sentiments["pos"]
            if not negs or not poss:
                continue
            # neg와 pos가 다른 entry에서 나온 경우만 모순으로 간주
            neg_set = set(negs)
            pos_set = set(poss)
            if neg_set & pos_set:
                # 같은 entry에서 둘 다 나온 경우 — 문맥적 부정일 수 있음 (스킵)
                # 하지만 다른 entry에도 있으면 보고
                exclusive_neg = neg_set - pos_set
                exclusive_pos = pos_set - neg_set
                if not exclusive_neg or not exclusive_pos:
                    continue
                negs = list(exclusive_neg)
                poss = list(exclusive_pos)

            pair_key = tuple(sorted([negs[0], poss[0]]))
            if pair_key in contradiction_reported:
                continue
            contradiction_reported.add(pair_key)

            results.append(_issue(
                checker, CONCERN,
                f"learnings:topic={topic}",
                f"모순 가능성 — 부정: {negs[0]!r}, 긍정: {poss[0]!r} (동일 주제 {topic!r})"
            ))

        concern_count = sum(1 for r in results if r["label"] == CONCERN)
        if concern_count == 0:
            results.append(_issue(checker, PASS, "learnings.jsonl",
                                  f"명백한 모순 없음 ({len(entries)}건 검사)"))
        else:
            # 검사 완료 표시 (CONCERN 있어도 검사 자체는 성공)
            results.append(_issue(checker, INFO, "learnings.jsonl",
                                  f"총 {len(entries)}건 검사 완료 — CONCERN {concern_count}건 (단순 키워드 휴리스틱)"))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "learnings.jsonl", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-MIRROR: 4변형 정합
# ---------------------------------------------------------------------------

_MIRROR_EXCLUDE_PATTERNS = re.compile(
    r"(__pycache__|\.pyc|\.pyo|/state/|settings\.local\.json|lint-last\.json)"
)


def _collect_files(base_dir: Path, rel_base: Path = None) -> dict:
    """
    디렉토리 아래의 모든 파일을 수집한다.

    Args:
        base_dir: 탐색할 루트 디렉토리
        rel_base: 상대경로 계산 기준 (None이면 base_dir 사용)

    Returns:
        dict: {상대경로 str: Path 절대경로}
    """
    if rel_base is None:
        rel_base = base_dir
    result = {}
    if not base_dir.exists():
        return result
    for path in base_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(rel_base))
        if _MIRROR_EXCLUDE_PATTERNS.search(rel):
            continue
        result[rel] = path
    return result


def check_mirror() -> list:
    """
    4변형(main .claude/ / claude.gstack/ / baseline / openai) 정합성을 검사한다.

    검사 항목:
    - BLOCK: .claude/ ↔ claude.gstack/ 간 .py 파일 내용 diff 존재
    - CONCERN: rules, skills 파일의 줄 수 차이가 baseline ↔ openai 간 10% 이상
    - INFO: 한쪽에만 존재하는 파일 (claude.gstack 기준)
    - PASS: 정합

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-MIRROR"

    try:
        # .claude/ ↔ claude.gstack/.claude/ 비교
        main_claude = _CLAUDE_DIR
        gstack_claude = _GSTACK_DIR

        if not main_claude.exists():
            results.append(_issue(checker, INFO, ".claude/", "디렉토리 없음"))
            return results
        if not gstack_claude.exists():
            results.append(_issue(checker, INFO, "claude.gstack/harness/.claude/", "디렉토리 없음"))
            return results

        main_files = _collect_files(main_claude, main_claude)
        gstack_files = _collect_files(gstack_claude, gstack_claude)

        main_keys = set(main_files.keys())
        gstack_keys = set(gstack_files.keys())

        # `.py` diff 는 **BLOCK 이 아니다** — F021 로 SSOT 가 `claude.loope` 로
        # 옮겨졌고(ADR-015), `claude.gstack` 은 autonomous 오버레이를 제외한 **표준**
        # 변형이라 main 과 다른 것이 정상이다. main ≡ loope 는 `LINT-SSOT` 가 본다.
        # 구 기준으로 BLOCK 을 내면 게이트가 늘 빨간 상태가 되어 아무도 안 보게 된다.
        common_py = {k for k in (main_keys & gstack_keys) if k.endswith(".py")}
        py_diff_found = False
        for rel in sorted(common_py):
            main_text = main_files[rel].read_text(encoding="utf-8", errors="replace")
            gstack_text = gstack_files[rel].read_text(encoding="utf-8", errors="replace")
            if main_text != gstack_text:
                diff_lines = list(difflib.unified_diff(
                    main_text.splitlines(), gstack_text.splitlines(),
                    fromfile=f".claude/{rel}", tofile=f"claude.gstack/.claude/{rel}",
                    lineterm="",
                ))
                diff_summary = f"{len(diff_lines)}줄 diff"
                results.append(_issue(
                    checker, INFO, rel,
                    f".claude/ ↔ claude.gstack/ .py diff ({diff_summary}) — gstack 은 표준 변형이라 정상일 수 있다"
                ))
                py_diff_found = True

        if not py_diff_found and common_py:
            results.append(_issue(checker, PASS, "*.py", f".py 파일 {len(common_py)}개 diff 없음"))

        # INFO: 한쪽에만 존재하는 파일 (state/ 제외)
        only_in_main = main_keys - gstack_keys
        only_in_gstack = gstack_keys - main_keys

        for rel in sorted(only_in_main):
            # state/ 는 의도적으로 미러 제외
            if rel.startswith("state/") or "state/" in rel:
                continue
            results.append(_issue(
                checker, INFO, rel,
                f".claude/에만 존재 — claude.gstack/ 미러링 누락 가능성"
            ))

        for rel in sorted(only_in_gstack):
            results.append(_issue(
                checker, INFO, rel,
                f"claude.gstack/에만 존재 — .claude/ 기준 파일 삭제됐을 가능성"
            ))

        # CONCERN: baseline ↔ openai skills/rules 줄 수 차이 10% 이상
        if _BASELINE_AGENTS_DIR.exists() and _OPENAI_SKILLS_DIR.exists():
            baseline_skills = _PROJECT_ROOT / "src" / "harness_template" / "claude" / "harness" / ".claude" / "skills"
            openai_skills = _OPENAI_SKILLS_DIR

            if baseline_skills.exists():
                for baseline_skill_dir in baseline_skills.iterdir():
                    if not baseline_skill_dir.is_dir():
                        continue
                    skill_name = baseline_skill_dir.name
                    # baseline skill.md
                    baseline_skill_md = baseline_skill_dir / "SKILL.md"
                    openai_skill_md = openai_skills / skill_name / "SKILL.md"

                    if not baseline_skill_md.exists() or not openai_skill_md.exists():
                        continue

                    b_lines = len(baseline_skill_md.read_text(encoding="utf-8").splitlines())
                    o_lines = len(openai_skill_md.read_text(encoding="utf-8").splitlines())

                    if b_lines == 0:
                        continue
                    diff_pct = abs(b_lines - o_lines) / b_lines * 100
                    if diff_pct >= 10:
                        results.append(_issue(
                            checker, CONCERN, f"skills/{skill_name}/SKILL.md",
                            f"baseline({b_lines}줄) ↔ openai({o_lines}줄) 줄 수 차이 {diff_pct:.0f}% (10% 이상)"
                        ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "LINT-MIRROR", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-MR: 변형 오버레이 정합 (F011 신설)
# ---------------------------------------------------------------------------

_HT = _PROJECT_ROOT / "src" / "harness_template"

# 자율 오버레이 파일 (claude.gstack 에서 제외되어야 함)
_AUTO_OVERLAY_FILES = [
    "harness/.claude/agents/gatekeeper.md",
    "harness/.claude/hooks/pre-bash-auto-boundary-check.sh",
]

# 디자인 오버레이 파일 (claude.gstack.auto.design 에만 존재해야 함)
_DESIGN_OVERLAY_FILES = [
    "harness/.claude/agents/designer.md",
    "harness/.claude/commands/design-pick.md",
    "harness/.claude/bin/design_pick.py",
]

# 디자인 오버레이 디렉토리 (존재 여부만 확인)
# ADR-006 결정 1: 변형 내 경로는 docs/design-references/ (메인의 .claude/design/references/ 와 다름)
_DESIGN_OVERLAY_DIRS = [
    "harness/docs/design-references",
]

# 디자인 오버레이가 없어야 하는 변형 (MR-4: wiki/orch 변형은 design의 1:1 복사이므로 제외)
_VARIANTS_NO_DESIGN = ["claude", "claude.gstack", "claude.gstack.auto"]

# 디자인 오버레이를 보유해야 하는 변형 (MR-5: design + wiki + orch 셋 다)
_VARIANTS_WITH_DESIGN = [
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",  # F013: orch 변형도 wiki 복사라 디자인 보유
]

# wiki 오버레이 파일 (ⓑ‴ wiki 변형 + ⓑ⁗ orch 변형에만 존재해야 함 — MR-6)
_WIKI_OVERLAY_FILES = [
    "harness/.claude/bin/wiki.py",
    "harness/.claude/commands/wiki.md",
    "harness/.claude/bin/wiki-setup.sh",
]

# wiki vault 디렉토리 (MR-6)
_WIKI_OVERLAY_DIRS = [
    "harness/wiki",
]

# wiki 오버레이가 없어야 하는 변형 (MR-6: ⓐ/ⓑ/ⓑ′/ⓑ″ 4 변형 — orch 변형은 wiki 복사라 제외)
_VARIANTS_NO_WIKI = ["claude", "claude.gstack", "claude.gstack.auto", "claude.gstack.auto.design"]

# wiki 오버레이를 보유해야 하는 변형 (MR-6 확장: wiki + orch 둘 다)
_VARIANTS_WITH_WIKI = [
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",  # F013: orch 변형도 wiki 오버레이 보유 (wiki 상속)
]

# orch 오버레이 파일 (ⓑ⁗ orch 변형에만 존재해야 함 — MR-8)
_ORCH_OVERLAY_FILES = [
    "harness/.claude/agents/researcher.md",
    "harness/.claude/commands/orchestrate.md",
]

# orch 상태 디렉토리 (MR-8: .gitkeep 존재 여부로 확인)
_ORCH_OVERLAY_DIRS = [
    "harness/.claude/state/orch",
    "harness/docs/orch-examples",   # ADR-008 결정 7 + CLAUDE.md orch 오버레이 4항목
]

# orch 오버레이가 없어야 하는 변형 (MR-8: ⓐ/ⓑ/ⓑ′/ⓑ″/ⓑ‴ 5 변형)
_VARIANTS_NO_ORCH = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
]

# orch 오버레이를 보유해야 하는 변형 (MR-8: orch 변형만)
_VARIANTS_WITH_ORCH = ["claude.gstack.auto.design.wiki.orch"]

# d-2 오버레이 파일 (ⓑ⁵ localllm 변형에만 존재해야 함 — MR-9, F015 정식 등재)
# 주의: opencode.py 는 d-2 오버레이가 아님 — gstack 등 6변형이 호스트 어댑터로 정당 보유.
#       MR-9 는 OpenCode "런타임 산출물"(.opencode/) + 설치 스크립트 + PoC 문서만 격리 검사한다.
_D2_OVERLAY_FILES = [
    "harness/.opencode/AGENTS.md",
    "harness/.claude/bin/opencode-setup.sh",
    "harness/.claude/bin/cycle_driver.py",   # 결정론 supervisor 드라이버 (F025 — ADR-018)
    "harness/.claude/bin/autoresearch.py",   # 자가 실험 루프 (F027 — ADR-019)
    "harness/.claude/bin/schema_check.py",   # 도구 지시 ↔ 스키마 정합 (F031 — ADR-022)
    "harness/.claude/schema/opencode-tools.json",   # 도구 스키마 스냅샷 (F031)
]

# d-2 상태/산출 디렉토리 (MR-9)
_D2_OVERLAY_DIRS = [
    "harness/.opencode/agent",
    "harness/.opencode/commands",   # render-commands 산출물 (F023 — ADR-017)
    "harness/docs/poc",
    "harness/.claude/policy",       # autoresearch 승격 대상 (F027 — 사람 승인분만)
]

# d-2 오버레이가 없어야 하는 변형 (MR-9: localllm 외 6 변형 — openai 는 별도 처리)
_VARIANTS_NO_D2 = [
    "claude.aif",
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
    "claude.hermes",
    "claude.productmgr",
    "claude.productnw",
    "claude.loope", "claude.vela.v0.1",
]

# d-2 오버레이를 보유해야 하는 변형 (MR-9: localllm 만)
_VARIANTS_WITH_D2 = ["localllm", "localllm.nem", "localllm.aif"]

# hermes 오버레이 파일 (ⓑ⁶ claude.hermes 변형에만 존재해야 함 — MR-10, F016 신설)
# Hermes Agent 패턴 이식: FTS5 세션검색 + 스킬 자동생성/self-improve (ADR-010)
_HERMES_OVERLAY_FILES = [
    "harness/.claude/bin/session_search.py",
    "harness/.claude/bin/skill_forge.py",
    "harness/.claude/commands/session-search.md",
    "harness/.claude/commands/skill-forge.md",
]

# hermes 오버레이가 없어야 하는 변형 (MR-10: claude.hermes 외 6 변형 — openai 별도)
_VARIANTS_NO_HERMES = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
]

# hermes 오버레이를 보유해야 하는 변형 (MR-10: claude.hermes + 상속받은 productmgr/productnw/loope
# + localllm — F023 loope 계보 승격, ADR-017)
_VARIANTS_WITH_HERMES = ["claude.hermes", "claude.productmgr", "claude.productnw", "claude.loope", "claude.vela.v0.1",
                         "localllm", "localllm.nem", "claude.aif", "localllm.aif"]

# pm 오버레이 파일 (ⓑ⁷ claude.productmgr 변형에만 존재해야 함 — MR-11, F018 신설)
# Product Manager 주도 통합 SDLC (ADR-011)
_PM_OVERLAY_FILES = [
    "harness/.claude/agents/product-manager.md",
    "harness/.claude/commands/product-cycle.md",
]

# pm 오버레이가 없어야 하는 변형 (MR-11: claude.productmgr 외 8 변형 — openai 별도)
_VARIANTS_NO_PM = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
    "claude.hermes",
]

# pm 오버레이를 보유해야 하는 변형 (MR-11: claude.productmgr + 상속받은 productnw/loope
# + localllm — F023 loope 계보 승격, ADR-017)
_VARIANTS_WITH_PM = ["claude.productmgr", "claude.productnw", "claude.loope", "claude.vela.v0.1", "localllm", "localllm.nem",
                     "claude.aif", "localllm.aif"]

# nw(컨소시엄) 오버레이 파일 (ⓑ⁸ claude.productnw 변형에만 존재해야 함 — MR-12, F019 신설)
# 분산 멀티팀 에이전트 컨소시엄: 메시지 계약 + 로스터 + 로컬 큐 + Slack 게이트웨이
# (ADR-012, d-3). "전송은 stub" 은 2026-09-19 에 폐기된 서술이다 — Slack 은 발신·수신
# 모두 stdlib 폴링으로 실구현이고, Teams·Telegram 은 2026-09-23 에 제거했다 (ADR-013 5-bis).
_NW_OVERLAY_FILES = [
    "harness/.claude/bin/consortium.py",
    "harness/.claude/commands/consortium.md",
]

# nw 오버레이가 없어야 하는 변형 (MR-12: claude.productnw 외 10 변형 — openai 별도)
_VARIANTS_NO_NW = [
    "claude.aif",
    "localllm.aif",
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
    "localllm", "localllm.nem",
    "claude.hermes",
    "claude.productmgr",
    "claude.loope", "claude.vela.v0.1",
]

# nw 오버레이를 보유해야 하는 변형 (MR-12: claude.productnw 만)
_VARIANTS_WITH_NW = ["claude.productnw"]

# loop 오버레이 파일 (ⓑ⁹ claude.loope 변형에만 존재해야 함 — MR-13, F020 신설)
# LangChain loop engineering: Loop 2(검증 루프) + Loop 4(hill-climbing) 정형화 (ADR-014)
_LOOP_OVERLAY_FILES = [
    "harness/.claude/bin/verify_loop.py",
    "harness/.claude/commands/verify-loop.md",
    "harness/.claude/rubrics/code-review.md",
    "harness/.claude/rubrics/qa-acceptance.md",
    "harness/.claude/bin/hill_climb.py",
    "harness/.claude/commands/hill-climb.md",
]

# loop 오버레이가 없어야 하는 변형 (MR-13: claude.loope 외 10 변형 — openai 별도)
_VARIANTS_NO_LOOP = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
    "claude.hermes",
    "claude.productmgr",
    "claude.productnw",
]

# loop 오버레이를 보유해야 하는 변형 (MR-13: claude.loope + localllm — F023 loope 계보 승격, ADR-017)
_VARIANTS_WITH_LOOP = ["claude.loope", "claude.vela.v0.1", "localllm", "localllm.nem", "claude.aif", "localllm.aif"]

# AIF 오버레이 파일 (ⓑ¹⁰ claude.aif + ⓑ¹¹ localllm.aif 에만 존재해야 함 — MR-14, F028 신설)
# RLAIF/CAI 판정 설계 규율 이식: 항목형 rubric + 증거 강제 + 앙상블 + UNCERTAIN (ADR-020)
_AIF_OVERLAY_FILES = [
    "harness/.claude/bin/aif_judge.py",
    "harness/.claude/commands/aif-judge.md",
    "harness/.claude/rubrics/_items-schema.md",
    "harness/.claude/rubrics/code-review.items.md",
    "harness/.claude/rubrics/qa-acceptance.items.md",
]

# AIF 판정 기록 디렉토리 (MR-14)
_AIF_OVERLAY_DIRS = [
    "harness/.claude/state/aif",
]

# AIF 오버레이가 없어야 하는 변형 (MR-14: aif 계열 2 변형 외 전부 — openai 별도)
_VARIANTS_NO_AIF = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
    "claude.hermes",
    "claude.productmgr",
    "claude.productnw",
    "claude.loope", "claude.vela.v0.1",
    "localllm", "localllm.nem",
]

# AIF 오버레이를 보유해야 하는 변형 (MR-14)
_VARIANTS_WITH_AIF = ["claude.aif", "localllm.aif"]

# Atlassian 오버레이 파일 (ⓑ¹³ claude.vela.* 계열에만 존재해야 함 — MR-15, F032 신설)
# Jira·Confluence 연동 (ADR-023): 공식 MCP 가 도구를 주므로 API 래퍼는 만들지 않고,
# 매핑·멱등성(중복 발행 방지)만 결정론 코드로 둔다.
_ATLASSIAN_OVERLAY_FILES = [
    "harness/.claude/bin/atlassian_map.py",
    "harness/.claude/commands/atlassian.md",
    "harness/.claude/skills/atlassian/SKILL.md",
    # 3-C 철칙 (2026-09-28) — 쓰기 대상 제한. 목록과 그것을 강제하는 훅은 한 쌍이다.
    "harness/.claude/atlassian-targets.json",
    "harness/.claude/hooks/pre-atlassian-write-check.sh",
]

# Atlassian 매핑 상태 디렉토리 (MR-15)
_ATLASSIAN_OVERLAY_DIRS = [
    "harness/.claude/state/atlassian",
]

# Atlassian 오버레이가 없어야 하는 변형 (MR-15: vela 계열 외 전부 — openai 별도)
_VARIANTS_NO_ATLASSIAN = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
    "claude.hermes",
    "claude.productmgr",
    "claude.productnw",
    "claude.loope",
    "claude.aif",
    "localllm", "localllm.nem", "localllm.aif",
]

# Atlassian 오버레이를 보유해야 하는 변형 (MR-15: vela 계열)
_VARIANTS_WITH_ATLASSIAN = ["claude.vela.v0.1"]

# ── 내용 오버레이 (LINT-CO — F021 에스컬레이션 / ADR-015 결정 5) ──────────────
#
# 오버레이는 **파일로도, 내용으로도** 존재한다. 위 `_*_OVERLAY_FILES` 는 전자만 본다.
# 2026-10-19 에 `reviewer.md` 를 전 변형에 일괄 복사했을 때 ① loop 서술이 비-loop
# 5곳에 누수되고 ② 동결 baseline 이 덮이고 ③ aif 의 의도된 차이가 지워졌는데
# `lint --strict` 는 **0 BLOCK** 이었다. 파일 단위 격리만 실재했기 때문이다.
#
# 여기서 **새 표를 만들지 않는다.** 갈래는 임의가 아니라 오버레이 멤버십의 함수이고,
# 그 멤버십은 위 `_VARIANTS_WITH_*` 가 이미 유지한다. 그래서 파일당 선언은 **축 이름
# 한 줄**이다 — 값이 아니라 **모양**의 선언이라 정당한 문구 수정에 **불변**이다.
# (기대 해시 표로 두면 `reviewer.md` 를 한 줄 고칠 때마다 갈래 수만큼 갱신해야 하고,
#  그 번거로움이 `regenerate` 를 부르며, 그 순간 검사기는 공회전한다.)

#: 모델 축 — `localllm.nem` (F030 / ADR-021). **부모와 같은 오버레이 프로필을 가지면서
#: 내용이 갈리는 첫 변형**이라, 파일 기반 정책만으로는 그 차이를 원리적으로 볼 수 없다.
#: ("자기 파일이 하나도 없다" 고 적었던 것은 **거짓**이다 — `.claude/policy/qa.md`·
#:  `.claude/policy/reviewer.md`·`tests/finetune_readiness.sh` 가 nem 에만 있고, 셋 다
#:  어느 `_*_OVERLAY_FILES` 에도 없어 **존재 축**(F038)이 닫는다.)
#: 갈리는 파일 수는 적지 않는다 — 선언에서 센다. "4 파일" 은 선언이 늘어난 날 낡았다.
_VARIANTS_WITH_MODEL_NEM = ["localllm.nem"]

#: 축 이름 → 그 축을 가진 변형 목록. **기존 상수를 참조한다 — 재나열하지 않는다.**
#: 재나열하면 두 목록이 갈라지고, 그것이 지금 고치는 결함 그 자체다.
_CO_AXES = {
    "design": _VARIANTS_WITH_DESIGN, "wiki": _VARIANTS_WITH_WIKI,
    "orch": _VARIANTS_WITH_ORCH, "d2": _VARIANTS_WITH_D2,
    "hermes": _VARIANTS_WITH_HERMES, "pm": _VARIANTS_WITH_PM,
    "nw": _VARIANTS_WITH_NW, "loop": _VARIANTS_WITH_LOOP,
    "aif": _VARIANTS_WITH_AIF, "atl": _VARIANTS_WITH_ATLASSIAN,
    "model_nem": _VARIANTS_WITH_MODEL_NEM,
}

#: 이 파일의 내용은 이 축들에 대해서**만** 갈라진다.
#: 없는 파일은 **축 ∅** — 존재하는 모든 곳에서 바이트 동일해야 한다(fail-closed 기본값).
#: 이 목록은 **도출**한 것이다 — 관측 분할을 재현하는 최소 축 집합을 탐색해, 갈린 파일
#: 전부가 기존 `_VARIANTS_WITH_*` 조합으로 재구성되는 것을 확인했다. **개수는 적지
#: 않는다**: 선언이 하나 늘 때마다 낡는다 (`len(_CONTENT_OVERLAY_AXES)` 로 센다).
_CONTENT_OVERLAY_AXES = {
    ".claude/agents/reviewer.md": {"loop", "aif"},
    ".claude/agents/qa.md": {"loop", "aif"},
    ".claude/commands/retro.md": {"loop"},
    ".claude/commands/product-cycle.md": {"loop"},
    ".claude/commands/verify-loop.md": {"aif"},
    ".claude/commands/init-project.md": {"d2", "model_nem"},
    ".claude/rules/coding-standards.md": {"loop", "d2", "aif"},
    ".claude/skills/coding/SKILL.md": {"d2"},
    ".claude/skills/coding/SKILL.md.template": {"d2"},
    ".claude/skills/design-review/SKILL.md": {"d2"},
    ".claude/skills/qa-browser/SKILL.md": {"d2"},
    ".claude/bin/cycle_driver.py": {"aif", "model_nem"},
    ".claude/bin/autoresearch.py": {"model_nem"},
    ".claude/bin/opencode-setup.sh": {"model_nem"},
    # `.opencode/` 는 `.claude/` 의 **렌더 산출물**이다 (host.py render-agents/commands).
    # 원본만 가드하면 산출물이 조용히 어긋난다 — 리뷰 MUST-2 가 실측으로 짚었다.
    ".opencode/agent/reviewer.md": {"aif"},
    ".opencode/agent/qa.md": {"aif"},
    ".opencode/commands/verify-loop.md": {"aif"},
    ".opencode/commands/init-project.md": {"model_nem"},
    ".opencode/AGENTS.md": {"model_nem"},
    "opencode.json": {"model_nem"},
    "docs/poc/MODEL-GRADES.md": {"model_nem"},
    "tests/suite/run_suite.py": {"model_nem"},
}

# ── 제외 규칙 표 (ADR-015 결정 2 개정 — 2026-10-23) ─────────────────────────
#
# **제외는 목록이 아니라 규칙이다.** 세 라운드 연속으로 같은 모양의 결함이 났는데,
# 원인은 테스트를 덜 써서가 아니라 **규칙이 흩어진 상수·조건문으로만 존재해서** 테스트가
# 언제나 "직전에 고친 그 규칙 하나" 만 겨냥할 수 있었던 것이다. 다음 규칙이 추가되는
# 순간 또 구멍이 난다 (실측: mC·mD·mH·mT2 가 전부 그 모양).
#
# 그래서 규칙을 **증인 포함 데이터**로 적고 테스트가 표를 순회한다. 행을 추가하면
# 테스트가 **자동으로 따라온다** — 증인 없는 행은 그 자체로 BLOCK 이다.
#
#   kind     exact(정확 일치) / prefix(루트 상대 접두) / anydir(경로 성분 — 캐시·VCS 만)
#   scope    이 행이 적용되는 검사기 — {"ssot", "co", "freeze"} 의 부분집합
#            **이 열이 '파생' 이 지웠던 사실이다.** SSOT 의 제외는 "main→loope 로
#            미러하지 않는다", CO 의 제외는 "어느 변형끼리도 비교하지 않는다" —
#            둘은 같은 사실이 아니다. 파생이 그 차이를 지워 `.claude/state/*/README.md`
#            같은 전 변형 공유 문서가 무가드로 떨어졌다 (실측: LINT-CO 보유 0).
#   guard    제외하는 대신 **무엇이 보는가** (ADR-015 "가드 없는 제외 금지" 의 기계 강제)
#   inside   이 행이 **반드시 제외해야 하는** 경로 (≥1)
#   outside  이 행이 **제외하면 안 되는 이웃** 경로 (≥1) — 통로를 한 칸 넓히는 변이를 잡는다
_SCOPE_RULES = (
    # ── 캐시·VCS·외부 설치물: 트리 어디에 있든 건너뛴다 ────────────────────
    dict(kind="anydir", pattern="__pycache__", scope={"ssot", "co", "freeze"},
         guard="없음 — 생성물이고 git 추적 대상도 아니다",
         reason="Python 바이트코드 캐시 — 소스에서 생성되고 환경마다 다르다",
         inside=[".claude/bin/__pycache__/lint.cpython-310.pyc"],
         outside=[".claude/bin/lint.py"]),
    dict(kind="anydir", pattern=".git", scope={"ssot", "co", "freeze"},
         guard="없음 — VCS 내부", reason="git 내부 메타데이터 — 미러 대상이 아니다",
         inside=[".git/config"], outside=[".claude/bin/git-sync.sh"]),
    dict(kind="anydir", pattern="node_modules", scope={"ssot", "co"},
         guard="없음 — 외부 설치물, git 미추적", reason="npm 설치물 — 외부 의존성이고 git 추적 대상이 아니다",
         inside=[".opencode/node_modules/x/index.js"], outside=[".opencode/AGENTS.md"]),
    dict(kind="anydir", pattern=".pytest_cache", scope={"ssot", "co"},
         guard="없음 — 생성물", reason="pytest 실행 캐시 — 생성물이고 환경마다 다르다",
         inside=["tests/.pytest_cache/v/cache/nodeids"], outside=["tests/test_lint_overlay.py"]),
    dict(kind="anydir", pattern=".venv", scope={"ssot", "co"},
         guard="없음 — 외부 설치물", reason="Python 가상환경 — 외부 설치물이라 미러 대상이 아니다",
         inside=[".venv/lib/python3.10/site-packages/x.py"], outside=[".claude/bin/lint.py"]),
    dict(kind="anydir", pattern=".mypy_cache", scope={"ssot", "co"},
         guard="없음 — 생성물", reason="mypy 타입 캐시 — 생성물이고 환경마다 다르다",
         inside=[".mypy_cache/3.10/x.json"], outside=[".claude/bin/host.py"]),

    # ── 머신 로컬: 변형마다 정당하게 다르다 ────────────────────────────────
    dict(kind="exact", pattern=".claude/settings.json", scope={"ssot", "co"},
         guard="없음 — 머신별 권한 구성이라 비교 대상이 아니다",
         reason="머신 로컬 권한·훅 배선",
         inside=[".claude/settings.json"], outside=[".claude/settings-example.json"]),
    dict(kind="exact", pattern=".claude/settings.local.json", scope={"ssot", "co"},
         guard="없음 — 머신 로컬", reason="로컬 권한 누적 — 머신마다 다르게 쌓인다",
         inside=[".claude/settings.local.json"], outside=[".claude/settings-local-notes.md"]),
    dict(kind="exact", pattern=".claude/host.json", scope={"ssot", "co"},
         guard="`host.py check`", reason="프로젝트 로컬 agent_type·백업 설정",
         inside=[".claude/host.json"], outside=[".claude/hosts.json"]),
    dict(kind="exact", pattern=".claude/bin/live_status.sh", scope={"ssot", "co"},
         guard="없음 — 머신 로컬 관측 도구(tmux·파일 기반)",
         reason="머신 로컬 관측 도구",
         inside=[".claude/bin/live_status.sh"], outside=[".claude/bin/lint.py"]),
    dict(kind="exact", pattern=".claude/atlassian-targets.json", scope={"ssot", "co"},
         guard="`LINT-ATL` — 배포본이 빈 목록인지 본다 (3-C 철칙)",
         reason="쓰기 허용 대상 — settings.json 과 같은 층위의 로컬 값",
         inside=[".claude/atlassian-targets.json"], outside=[".claude/atlassian-map.json"]),
    dict(kind="exact", pattern=".claude/hooks/pre-atlassian-write-check.sh", scope={"ssot", "co"},
         guard="`LINT-ATL` — 로컬 훅과 vela 사본의 **바이트 동일**을 본다",
         reason="허용 목록을 강제하는 훅 — 목록과 한 쌍",
         inside=[".claude/hooks/pre-atlassian-write-check.sh"],
         outside=[".claude/hooks/pre-bash-check.sh"]),

    # ── MAIN 전용 커밋 상태: loope 로 미러하지 않지만 **비교는 한다** ───────
    #    scope 에서 "co" 를 뺀 것이 핵심이다. 전엔 `state/` 접두 하나로 둘 다 빠져
    #    `.claude/state/*/README.md`(전 변형 공유 문서)가 무가드로 떨어졌다.
    dict(kind="prefix", pattern=".claude/state/checkpoints/", scope={"ssot"},
         guard="`LINT-CO` — 변형에 나타나면 보유 분할로 드러난다",
         reason="MAIN 전용 세션 인계 기록 — loope 로 미러하지 않는다",
         inside=[".claude/state/checkpoints/20261020-x.md"],
         outside=[".claude/state/orch/README.md"]),
    dict(kind="exact", pattern=".claude/state/learnings.jsonl", scope={"ssot"},
         guard="`LINT-CO`", reason="MAIN 전용 학습 누적 로그",
         inside=[".claude/state/learnings.jsonl"],
         outside=[".claude/state/verify-loop/README.md"]),
    dict(kind="exact", pattern=".claude/state/analytics.jsonl", scope={"ssot"},
         guard="`LINT-CO`", reason="MAIN 전용 이벤트 로그",
         inside=[".claude/state/analytics.jsonl"],
         outside=[".claude/state/product-cycle/README.md"]),
    dict(kind="prefix", pattern=".claude/design/", scope={"ssot"},
         guard="`LINT-CO` — 변형 트리 보유 0 이라 CO 에서는 애초에 아무것도 막지 않았다",
         reason="`design_pick.py apply` 의 프로젝트 로컬 산출물",
         inside=[".claude/design/tokens.json"],
         outside=["docs/design/F007-design-review-checklist.md"]),

    # ── (C) 변형 로컬·생성물: 미러 대상이 아니다 ───────────────────────────
    dict(kind="exact", pattern="CLAUDE.md", scope={"co"},
         guard="`check_ssot` 의 **섹션 단위** main↔loope 비교",
         reason="변형별 헤더가 다르다",
         inside=["CLAUDE.md"], outside=["docs/claude-md-notes.md"]),
    dict(kind="exact", pattern="README.md", scope={"co"},
         guard="없음 — 변형 소개문이라 다른 것이 정상",
         reason="변형 소개문 — 변형마다 다른 것이 정상이다",
         inside=["README.md"], outside=["docs/readme-template.md"]),
    dict(kind="exact", pattern=".gitignore", scope={"co"},
         guard="없음 — 변형마다 런타임 산출물 경로가 다르다",
         reason="변형마다 런타임 산출물 경로가 다르다",
         inside=[".gitignore"], outside=[".claude/bin/gitignore-check.sh"]),
    dict(kind="exact", pattern="feature_list.json", scope={"co"},
         guard="`LINT-FL` 이 각 트리에서 따로 본다",
         reason="템플릿엔 데모 샘플을 유지한다",
         inside=["feature_list.json"], outside=["docs/feature-list-schema.md"]),
    dict(kind="exact", pattern="claude-progress.txt", scope={"co"},
         guard="없음 — 세션 인계용", reason="세션 인계용 로그 — 변형별로 다른 것이 정상",
         inside=["claude-progress.txt"], outside=["docs/claude-progress-notes.md"]),
    dict(kind="exact", pattern="docs/progress-archive.txt", scope={"co"},
         guard="없음 — 위의 아카이브", reason="진행 로그의 아카이브 — 위와 같은 이유로 변형별",
         inside=["docs/progress-archive.txt"], outside=["docs/progress-notes.md"]),
    dict(kind="exact", pattern="docs/index.md", scope={"co"},
         guard="`lint.py regenerate-index` 가 생성한다", reason="생성 산출물 — `lint.py regenerate-index` 가 만든다",
         inside=["docs/index.md"], outside=["docs/index-notes.md"]),
    dict(kind="exact", pattern="docs/UPSTREAM.md", scope={"co"},
         guard="없음 — 어느 변형에서 파생됐는지 적는 메타",
         reason="변형 메타 — 어느 변형에서 파생됐는지 적는다",
         inside=["docs/UPSTREAM.md"], outside=["docs/UPSTREAM-notes.md"]),
    dict(kind="prefix", pattern="wiki/", scope={"co"},
         guard="`wiki.py lint` — vault 정합성은 거기서 본다",
         reason="생성 vault — 변형 로컬 입력(feature_list·ADR 집합)에서 생성되므로 "
                "노드 내용 자체가 다르다 (`related:` 링크·인덱스 노드 수)",
         inside=["wiki/index.md"], outside=["docs/adr/ADR-007-llm-wiki-knowledge-graph.md"]),
    dict(kind="prefix", pattern="src/", scope={"co"},
         guard="변형으로 **따로** 센다 — 메인의 `src/harness_template/` 은 루트 목록에 "
               "올라가고, 그 밖의 `src/` 는 하네스가 아니라 사용자 소스다",
         reason="메인의 템플릿 트리 자신 — 변형 루트로 중복 집계되면 안 된다",
         inside=["src/harness_template/claude.loope/harness/CLAUDE.md", "src/gstack/app.py"],
         outside=["docs/design/F007-design-review-checklist.md", "tests/test_lint_overlay.py"]),
    dict(kind="prefix", pattern="tests/suite/results/", scope={"co"},
         guard="없음 — 변형·모델마다 다른 것이 **결과**다",
         reason="무인 스위트 실측 로그",
         inside=["tests/suite/results/round1.jsonl"], outside=["tests/suite/run_suite.py"]),
)

#: **양의 목록** — 각 경로류는 공유 파일을 1건 이상 내놓아야 한다. 0 이면 BLOCK.
#: 증인은 "제외를 **더하는**" 방향을 막는다. 이것은 **범위가 무신호로 줄어드는** 반대
#: 방향을 막는다 — 실측(mH): ssot 제외에 `hooks/` 를 더하면 파생으로
#: LINT-CO 범위가 조용히 줄었는데 37 테스트와 `lint --strict` 가 **전부 통과**했다.
_SCOPE_REQUIRED = {
    ".claude/agents/": "에이전트 정의",
    ".claude/bin/": "헬퍼 스크립트",
    ".claude/commands/": "슬래시 커맨드",
    ".claude/hooks/": "훅 스크립트",
    ".claude/rules/": "팀 규칙",
    ".claude/skills/": "스킬",
    "docs/adr/": "아키텍처 결정 기록",
    "tests/": "테스트",
}


def _scope_rules(scope: str) -> tuple:
    """이 검사기에 적용되는 규칙만."""
    return tuple(r for r in _SCOPE_RULES if scope in r["scope"])


def _scope_match(rel: str, scope: str):
    """`rel` 을 제외하는 규칙을 돌려준다 (없으면 None).

    **부울이 아니라 규칙 자체**를 돌려준다 — 증인 테스트가 "어느 행이 잡았는가" 를
    단언해야 다른 행에 흡수된 죽은 행이 조용히 통과하지 않는다.
    """
    parts = tuple(Path(rel).parts)
    for rule in _SCOPE_RULES:
        if scope not in rule["scope"]:
            continue
        kind, pat = rule["kind"], rule["pattern"]
        if kind == "anydir" and pat in parts:
            return rule
        if kind == "exact" and rel == pat:
            return rule
        if kind == "prefix" and rel.startswith(pat):
            return rule
    return None


#: 동결 변형 — `LINT-CO` 에 참여시키지 않는다. "baseline 은 늘 달라야 한다" 로 모델링하면
#: Karpathy 동기화가 영구 금지된다. 동결은 `LINT-FREEZE` 가 해시로 본다.
_CO_FROZEN = ("claude", "openai")


# 외부 의존성 매니페스트 (wiki 변형 외에 있으면 BLOCK — MR-7)
_EXTERNAL_DEP_FILES = [
    "harness/.claude/bin/wiki-setup.sh",
    "harness/requirements.txt",
    "harness/package.json",
]

# openai 변형 포함한 외부 의존성 검사 대상 (MR-7: 5 변형)
_VARIANTS_NO_EXTERNAL_DEPS = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
]
# openai 변형 경로 (구조가 달라 별도 처리)
_OPENAI_VARIANT_HARNESS = "openai/harness"


def check_mirror_regression() -> list:
    """LINT-MR: 12 변형 미러 정합 점검 (F011~F013, F015 MR-9, F016 MR-10, F018 MR-11, F019 MR-12, F020 MR-13).

    F010 미러 회귀 2 회 학습 반영 — 자동 가드.
    F012: MR-6 (wiki 오버레이 격리) + MR-7 (외부 의존성 격리) 추가.
    F013: MR-5/_VARIANTS_WITH_DESIGN 갱신 + MR-6/_VARIANTS_WITH_WIKI 신설 + MR-8 (orch 오버레이 격리) 추가.

    검사 항목:
    - MR-1: claude.gstack 에 자율 오버레이 파일 부재
    - MR-2: claude.gstack/settings.json 에 Bash(*) 미사용
    - MR-3: claude.gstack/CLAUDE.md 에 Autonomous Mode 섹션 부재
    - MR-4: claude.gstack.auto.design 외 변형 (ⓐ/ⓑ/ⓑ′) 에 디자인 오버레이 부재
    - MR-5: claude.gstack.auto.design + wiki + orch 변형에 디자인 오버레이 존재
    - MR-6: ⓐ/ⓑ/ⓑ′/ⓑ″ 4 변형에 wiki 오버레이 부재 + wiki/orch 변형에 wiki 오버레이 존재
    - MR-7: 5 변형 (ⓐ/ⓑ/ⓑ′/ⓑ″/ⓒ) 에 외부 의존성 매니페스트 부재 (wiki/orch 변형만 wiki-setup.sh 허용)
    - MR-8: ⓐ/ⓑ/ⓑ′/ⓑ″/ⓑ‴ 5 변형에 orch 오버레이 부재 + orch 변형에 orch 오버레이 존재

    Returns:
        list[dict]: 검사 결과 목록 (각 dict는 id/label/target/message 키 보유)
    """
    results = []
    checker = "LINT-MR"

    try:
        # MR-1: claude.gstack 에 자율 오버레이 파일 없어야 함
        gstack = _HT / "claude.gstack"
        if gstack.exists():
            for rel_path in _AUTO_OVERLAY_FILES:
                target_path = gstack / rel_path
                if target_path.exists():
                    results.append(_issue(
                        checker, BLOCK,
                        f"claude.gstack/{rel_path}",
                        "표준 변형에 자율 오버레이 파일 잘못 미러됨 — 제거 필요",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        f"claude.gstack/{rel_path}",
                        "표준 변형에 자율 오버레이 부재 OK",
                    ))
        else:
            results.append(_issue(
                checker, INFO,
                "claude.gstack",
                "claude.gstack 변형 디렉토리 부재 — 건너뜀",
            ))

        # MR-2: claude.gstack/settings.json 에 Bash(*) 없어야 함
        gstack_settings = gstack / "harness" / ".claude" / "settings.json"
        if gstack_settings.exists():
            try:
                content = gstack_settings.read_text(encoding="utf-8")
                # 다양한 이스케이프 변종 모두 감지 (Reviewer SHOULD-3):
                #   Bash(*)          — 표준
                #   Bash("*")        — 큰따옴표 변종
                #   Bash(\"*\")      — json.dumps 이스케이프 경로
                bash_wildcard_patterns = ['Bash(*)', 'Bash("*")', 'Bash(\\"*\\")', "Bash('*')"]
                if any(pat in content for pat in bash_wildcard_patterns):
                    results.append(_issue(
                        checker, BLOCK,
                        "claude.gstack/.claude/settings.json",
                        "표준 변형에 자율 모드 Bash(*) 권한 잘못 적용됨",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        "claude.gstack/.claude/settings.json",
                        "Bash(*) 부재 OK",
                    ))
            except Exception as exc:
                results.append(_issue(
                    checker, INFO,
                    "claude.gstack/.claude/settings.json",
                    f"파일 읽기 실패 — {exc}",
                ))
        else:
            results.append(_issue(
                checker, INFO,
                "claude.gstack/.claude/settings.json",
                "파일 부재 — 건너뜀",
            ))

        # MR-3: claude.gstack/CLAUDE.md 에 Autonomous Mode 헤딩 없어야 함
        # (표 등에서 "Autonomous Mode" 텍스트 참조는 허용 — 섹션 헤딩 `## *Autonomous Mode` 만 금지)
        gstack_claude_md = gstack / "harness" / "CLAUDE.md"
        if gstack_claude_md.exists():
            try:
                content = gstack_claude_md.read_text(encoding="utf-8")
                # 헤딩 형식만 검사: ^## ... Autonomous Mode (라인 시작)
                auto_mode_heading = re.search(
                    r"^#{1,6}\s+.*Autonomous Mode", content, re.MULTILINE
                )
                if auto_mode_heading:
                    results.append(_issue(
                        checker, BLOCK,
                        "claude.gstack/harness/CLAUDE.md",
                        "표준 변형에 Autonomous Mode 헤딩 섹션 잘못 미러됨",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        "claude.gstack/harness/CLAUDE.md",
                        "Autonomous Mode 헤딩 섹션 부재 OK",
                    ))
            except Exception as exc:
                results.append(_issue(
                    checker, INFO,
                    "claude.gstack/harness/CLAUDE.md",
                    f"파일 읽기 실패 — {exc}",
                ))
        else:
            results.append(_issue(
                checker, INFO,
                "claude.gstack/harness/CLAUDE.md",
                "파일 부재 — 건너뜀",
            ))

        # MR-4: claude.gstack.auto.design 외 변형에 디자인 오버레이 없어야 함
        all_overlay = _DESIGN_OVERLAY_FILES + _DESIGN_OVERLAY_DIRS
        for variant in _VARIANTS_NO_DESIGN:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO,
                    variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_overlay = []
            for rel in all_overlay:
                if (variant_dir / rel).exists():
                    found_overlay.append(rel)
            if found_overlay:
                results.append(_issue(
                    checker, BLOCK,
                    variant,
                    f"디자인 오버레이가 {variant} 에 잘못 미러됨: {found_overlay}",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    variant,
                    f"{variant} 변형에 디자인 오버레이 부재 OK",
                ))

        # MR-5: claude.gstack.auto.design + wiki 변형에 디자인 오버레이 모두 존재해야 함
        # (wiki 변형은 design 변형의 1:1 복사이므로 디자인 오버레이 보유 정상)
        for design_variant_name in _VARIANTS_WITH_DESIGN:
            design_variant = _HT / design_variant_name
            if design_variant.exists():
                missing = []
                for rel in _DESIGN_OVERLAY_FILES:
                    if not (design_variant / rel).exists():
                        missing.append(rel)
                for rel in _DESIGN_OVERLAY_DIRS:
                    if not (design_variant / rel).exists():
                        missing.append(rel)
                if missing:
                    results.append(_issue(
                        checker, CONCERN,
                        design_variant_name,
                        f"디자인 변형에 일부 오버레이 부재: {missing}",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        design_variant_name,
                        "디자인 오버레이 모두 존재 OK",
                    ))
            else:
                results.append(_issue(
                    checker, INFO,
                    design_variant_name,
                    f"{design_variant_name} 변형 부재 (F011/F012 미적용 가능)",
                ))

        # MR-6: ⓐ/ⓑ/ⓑ′/ⓑ″ 4 변형에 wiki 오버레이 파일/디렉토리 없어야 함
        # (wiki 오버레이는 ⓑ‴ claude.gstack.auto.design.wiki 에만 존재)
        all_wiki_overlay = _WIKI_OVERLAY_FILES + _WIKI_OVERLAY_DIRS
        for variant in _VARIANTS_NO_WIKI:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO,
                    variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_wiki = []
            for rel in all_wiki_overlay:
                if (variant_dir / rel).exists():
                    found_wiki.append(rel)
            if found_wiki:
                results.append(_issue(
                    checker, BLOCK,
                    variant,
                    f"wiki 오버레이가 {variant} 에 잘못 미러됨 (wiki 변형 전용): {found_wiki}",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    variant,
                    f"{variant} 변형에 wiki 오버레이 부재 OK",
                ))

        # MR-6 (계속): wiki/orch 변형에 wiki 오버레이 모두 존재해야 함
        # F013: _VARIANTS_WITH_WIKI = [wiki, orch] — orch 변형도 wiki 상속
        for wiki_variant_name in _VARIANTS_WITH_WIKI:
            wiki_variant = _HT / wiki_variant_name
            if wiki_variant.exists():
                missing_wiki = []
                for rel in _WIKI_OVERLAY_FILES:
                    if not (wiki_variant / rel).exists():
                        missing_wiki.append(rel)
                for rel in _WIKI_OVERLAY_DIRS:
                    if not (wiki_variant / rel).exists():
                        missing_wiki.append(rel)
                if missing_wiki:
                    results.append(_issue(
                        checker, CONCERN,
                        wiki_variant_name,
                        f"{wiki_variant_name} 변형에 일부 wiki 오버레이 부재: {missing_wiki}",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        wiki_variant_name,
                        f"{wiki_variant_name} wiki 오버레이 모두 존재 OK",
                    ))
            else:
                results.append(_issue(
                    checker, INFO,
                    wiki_variant_name,
                    f"{wiki_variant_name} 변형 부재 (F012/F013 미적용 가능)",
                ))

        # MR-7: 5 변형 (ⓐ/ⓑ/ⓑ′/ⓑ″/ⓒ) 에 외부 의존성 매니페스트 없어야 함
        # (wiki-setup.sh 는 wiki 변형에만 허용, requirements.txt / package.json 도 불가)
        for variant in _VARIANTS_NO_EXTERNAL_DEPS:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                continue
            found_ext = []
            for rel in _EXTERNAL_DEP_FILES:
                if (variant_dir / rel).exists():
                    found_ext.append(rel)
            if found_ext:
                results.append(_issue(
                    checker, BLOCK,
                    variant,
                    f"외부 의존성 매니페스트가 {variant} 에 잘못 포함 (wiki 변형만 허용): {found_ext}",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    variant,
                    f"{variant} 변형에 외부 의존성 매니페스트 부재 OK",
                ))

        # MR-7 (계속): openai 변형도 wiki-setup.sh 없어야 함 (경로가 다름)
        openai_dir = _HT / "openai"
        if openai_dir.exists():
            openai_setup = openai_dir / "harness" / ".codex" / "bin" / "wiki-setup.sh"
            openai_setup2 = openai_dir / "harness" / "wiki-setup.sh"
            if openai_setup.exists() or openai_setup2.exists():
                results.append(_issue(
                    checker, BLOCK,
                    "openai/.codex",
                    "openai 변형에 wiki-setup.sh 잘못 포함 (wiki 변형만 허용)",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    "openai/.codex",
                    "openai 변형에 외부 의존성 매니페스트 부재 OK",
                ))

        # MR-7 (계속): wiki/orch 변형에 wiki-setup.sh 존재해야 함 (graceful degrade 매뉴얼)
        # F013: orch 변형도 wiki 복사라 wiki-setup.sh 보유 (외부 의존성 상속)
        for wiki_variant_name in _VARIANTS_WITH_WIKI:
            wiki_variant = _HT / wiki_variant_name
            if wiki_variant.exists():
                wiki_setup = wiki_variant / "harness" / ".claude" / "bin" / "wiki-setup.sh"
                if not wiki_setup.exists():
                    results.append(_issue(
                        checker, CONCERN,
                        wiki_variant_name,
                        f"{wiki_variant_name} 변형에 wiki-setup.sh 부재 — graceful degrade 매뉴얼 누락",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        wiki_variant_name,
                        f"{wiki_variant_name} wiki-setup.sh 존재 OK (외부 의존성 허용 변형)",
                    ))

        # MR-8: ⓐ/ⓑ/ⓑ′/ⓑ″/ⓑ‴ 5 변형에 orch 오버레이 없어야 함
        # (orch 오버레이는 ⓑ⁗ claude.gstack.auto.design.wiki.orch 에만 존재 — ADR-008 결정 7)
        all_orch_overlay = _ORCH_OVERLAY_FILES + _ORCH_OVERLAY_DIRS
        for variant in _VARIANTS_NO_ORCH:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO,
                    variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_orch = []
            for rel in all_orch_overlay:
                if (variant_dir / rel).exists():
                    found_orch.append(rel)
            if found_orch:
                results.append(_issue(
                    checker, BLOCK,
                    variant,
                    f"orch 오버레이가 {variant} 에 잘못 미러됨 (orch 변형 전용): {found_orch}",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    variant,
                    f"{variant} 변형에 orch 오버레이 부재 OK",
                ))

        # MR-8 (계속): orch 변형에 orch 오버레이 모두 존재해야 함
        for orch_variant_name in _VARIANTS_WITH_ORCH:
            orch_variant = _HT / orch_variant_name
            if orch_variant.exists():
                missing_orch = []
                for rel in _ORCH_OVERLAY_FILES:
                    if not (orch_variant / rel).exists():
                        missing_orch.append(rel)
                for rel in _ORCH_OVERLAY_DIRS:
                    if not (orch_variant / rel).exists():
                        missing_orch.append(rel)
                if missing_orch:
                    results.append(_issue(
                        checker, CONCERN,
                        orch_variant_name,
                        f"{orch_variant_name} 변형에 일부 orch 오버레이 부재: {missing_orch}",
                    ))
                else:
                    results.append(_issue(
                        checker, PASS,
                        orch_variant_name,
                        f"{orch_variant_name} orch 오버레이 모두 존재 OK",
                    ))
            else:
                results.append(_issue(
                    checker, INFO,
                    orch_variant_name,
                    f"{orch_variant_name} 변형 부재 (F013 미적용 가능)",
                ))

        # MR-9: localllm 외 6 변형에 d-2 오버레이(.opencode/ 런타임 + opencode-setup + docs/poc) 없어야 함
        # (d-2 오버레이는 ⓑ⁵ localllm 에만 존재 — F015 정식 등재 / ADR-009 결정 6 개정)
        all_d2_overlay = _D2_OVERLAY_FILES + _D2_OVERLAY_DIRS
        for variant in _VARIANTS_NO_D2:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO,
                    variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_d2 = []
            for rel in all_d2_overlay:
                if (variant_dir / rel).exists():
                    found_d2.append(rel)
            if found_d2:
                results.append(_issue(
                    checker, BLOCK,
                    variant,
                    f"d-2 오버레이가 {variant} 에 잘못 미러됨 (localllm 전용): {found_d2}",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    variant,
                    f"{variant} 변형에 d-2 오버레이 부재 OK",
                ))

        # MR-9 (계속): localllm 변형에 d-2 오버레이 + opencode 어댑터 구조 불변식 존재해야 함
        # (구조만 검사 — 스킬·문서 본문은 검사하지 않아 PoC churn 마찰 없음)
        for d2_variant_name in _VARIANTS_WITH_D2:
            d2_variant = _HT / d2_variant_name
            if not d2_variant.exists():
                results.append(_issue(
                    checker, INFO,
                    d2_variant_name,
                    f"{d2_variant_name} 변형 부재 (F015 미적용 가능)",
                ))
                continue
            missing_d2 = []
            for rel in _D2_OVERLAY_FILES + _D2_OVERLAY_DIRS:
                if not (d2_variant / rel).exists():
                    missing_d2.append(rel)
            # opencode 어댑터 구조 불변식: render_agents 보유 + host.json agent_type=opencode
            adapter = d2_variant / "harness" / ".claude" / "bin" / "host_adapters" / "opencode.py"
            if not (adapter.exists() and "def render_agents" in adapter.read_text(encoding="utf-8")):
                missing_d2.append("opencode.py:render_agents")
            host_json = d2_variant / "harness" / ".claude" / "host.json"
            if not (host_json.exists() and '"agent_type": "opencode"' in host_json.read_text(encoding="utf-8")):
                missing_d2.append("host.json:agent_type=opencode")
            if missing_d2:
                results.append(_issue(
                    checker, CONCERN,
                    d2_variant_name,
                    f"{d2_variant_name} 변형에 일부 d-2 구조 부재: {missing_d2}",
                ))
            else:
                results.append(_issue(
                    checker, PASS,
                    d2_variant_name,
                    f"{d2_variant_name} d-2 오버레이 + opencode 어댑터 구조 모두 존재 OK",
                ))

        # MR-10: claude.hermes 외 6 변형에 hermes 오버레이 없어야 함
        # (hermes 오버레이는 ⓑ⁶ claude.hermes 에만 존재 — F016 / ADR-010)
        for variant in _VARIANTS_NO_HERMES:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO, variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_hermes = [rel for rel in _HERMES_OVERLAY_FILES
                            if (variant_dir / rel).exists()]
            if found_hermes:
                results.append(_issue(
                    checker, BLOCK, variant,
                    f"hermes 오버레이가 {variant} 에 잘못 미러됨 (claude.hermes 전용): {found_hermes}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, variant,
                    f"{variant} 변형에 hermes 오버레이 부재 OK",
                ))

        # MR-10 (계속): claude.hermes 변형에 hermes 오버레이 모두 존재해야 함
        for hermes_variant_name in _VARIANTS_WITH_HERMES:
            hv = _HT / hermes_variant_name
            if not hv.exists():
                results.append(_issue(
                    checker, INFO, hermes_variant_name,
                    f"{hermes_variant_name} 변형 부재 (F016 미적용 가능)",
                ))
                continue
            missing = [rel for rel in _HERMES_OVERLAY_FILES if not (hv / rel).exists()]
            if missing:
                results.append(_issue(
                    checker, CONCERN, hermes_variant_name,
                    f"{hermes_variant_name} 변형에 일부 hermes 오버레이 부재: {missing}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, hermes_variant_name,
                    f"{hermes_variant_name} hermes 오버레이 모두 존재 OK",
                ))

        # MR-11: claude.productmgr 외 8 변형에 pm 오버레이 없어야 함
        # (pm 오버레이는 ⓑ⁷ claude.productmgr 에만 존재 — F018 / ADR-011)
        for variant in _VARIANTS_NO_PM:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO, variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_pm = [rel for rel in _PM_OVERLAY_FILES if (variant_dir / rel).exists()]
            if found_pm:
                results.append(_issue(
                    checker, BLOCK, variant,
                    f"pm 오버레이가 {variant} 에 잘못 미러됨 (claude.productmgr 전용): {found_pm}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, variant,
                    f"{variant} 변형에 pm 오버레이 부재 OK",
                ))

        # MR-11 (계속): claude.productmgr 변형에 pm 오버레이 모두 존재해야 함
        for pm_variant_name in _VARIANTS_WITH_PM:
            pv = _HT / pm_variant_name
            if not pv.exists():
                results.append(_issue(
                    checker, INFO, pm_variant_name,
                    f"{pm_variant_name} 변형 부재 (F018 미적용 가능)",
                ))
                continue
            missing = [rel for rel in _PM_OVERLAY_FILES if not (pv / rel).exists()]
            if missing:
                results.append(_issue(
                    checker, CONCERN, pm_variant_name,
                    f"{pm_variant_name} 변형에 일부 pm 오버레이 부재: {missing}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, pm_variant_name,
                    f"{pm_variant_name} pm 오버레이 모두 존재 OK",
                ))

        # MR-12: claude.productnw 외 9 변형에 nw(컨소시엄) 오버레이 없어야 함
        # (nw 오버레이는 ⓑ⁸ claude.productnw 에만 존재 — F019 / ADR-012)
        for variant in _VARIANTS_NO_NW:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO, variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_nw = [rel for rel in _NW_OVERLAY_FILES if (variant_dir / rel).exists()]
            if found_nw:
                results.append(_issue(
                    checker, BLOCK, variant,
                    f"nw 오버레이가 {variant} 에 잘못 미러됨 (claude.productnw 전용): {found_nw}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, variant,
                    f"{variant} 변형에 nw 오버레이 부재 OK",
                ))

        # MR-12 (계속): claude.productnw 변형에 nw 오버레이 모두 존재해야 함
        for nw_variant_name in _VARIANTS_WITH_NW:
            nv = _HT / nw_variant_name
            if not nv.exists():
                results.append(_issue(
                    checker, INFO, nw_variant_name,
                    f"{nw_variant_name} 변형 부재 (F019 미적용 가능)",
                ))
                continue
            missing = [rel for rel in _NW_OVERLAY_FILES if not (nv / rel).exists()]
            if missing:
                results.append(_issue(
                    checker, CONCERN, nw_variant_name,
                    f"{nw_variant_name} 변형에 일부 nw 오버레이 부재: {missing}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, nw_variant_name,
                    f"{nw_variant_name} nw 오버레이 모두 존재 OK",
                ))

        # MR-13: claude.loope 외 10 변형에 loop(검증 루프) 오버레이 없어야 함
        # (loop 오버레이는 ⓑ⁹ claude.loope 에만 존재 — F020 / ADR-014)
        for variant in _VARIANTS_NO_LOOP:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(
                    checker, INFO, variant,
                    f"{variant} 변형 디렉토리 부재 — 건너뜀",
                ))
                continue
            found_loop = [rel for rel in _LOOP_OVERLAY_FILES if (variant_dir / rel).exists()]
            if found_loop:
                results.append(_issue(
                    checker, BLOCK, variant,
                    f"loop 오버레이가 {variant} 에 잘못 미러됨 (claude.loope 전용): {found_loop}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, variant,
                    f"{variant} 변형에 loop 오버레이 부재 OK",
                ))

        # MR-13 (계속): claude.loope 변형에 loop 오버레이 모두 존재해야 함
        for loop_variant_name in _VARIANTS_WITH_LOOP:
            lv = _HT / loop_variant_name
            if not lv.exists():
                results.append(_issue(
                    checker, INFO, loop_variant_name,
                    f"{loop_variant_name} 변형 부재 (F020 미적용 가능)",
                ))
                continue
            missing = [rel for rel in _LOOP_OVERLAY_FILES if not (lv / rel).exists()]
            if missing:
                results.append(_issue(
                    checker, CONCERN, loop_variant_name,
                    f"{loop_variant_name} 변형에 일부 loop 오버레이 부재: {missing}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, loop_variant_name,
                    f"{loop_variant_name} loop 오버레이 모두 존재 OK",
                ))

        # MR-14: aif 계열 외 변형에 AIF 오버레이 없어야 함 (F028 — ADR-020)
        all_aif = _AIF_OVERLAY_FILES + _AIF_OVERLAY_DIRS
        for variant in _VARIANTS_NO_AIF:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(checker, INFO, variant, f"{variant} 변형 디렉토리 부재 — 건너뜀"))
                continue
            found_aif = [rel for rel in all_aif if (variant_dir / rel).exists()]
            if found_aif:
                results.append(_issue(
                    checker, BLOCK, variant,
                    f"AIF 오버레이가 {variant} 에 잘못 미러됨 (aif 계열 전용): {found_aif}",
                ))
            else:
                results.append(_issue(checker, PASS, variant, f"{variant} 변형에 AIF 오버레이 부재 OK"))

        # MR-14 (계속): aif 계열 변형에 AIF 오버레이 모두 존재해야 함
        for aif_variant_name in _VARIANTS_WITH_AIF:
            av = _HT / aif_variant_name
            if not av.exists():
                results.append(_issue(
                    checker, INFO, aif_variant_name,
                    f"{aif_variant_name} 변형 부재 (F028 미적용 가능)",
                ))
                continue
            missing = [rel for rel in all_aif if not (av / rel).exists()]
            if missing:
                results.append(_issue(
                    checker, CONCERN, aif_variant_name,
                    f"{aif_variant_name} 변형에 일부 AIF 오버레이 부재: {missing}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, aif_variant_name,
                    f"{aif_variant_name} AIF 오버레이 모두 존재 OK",
                ))

        # MR-15: vela 계열 외 변형에 Atlassian 오버레이 없어야 함 (F032 — ADR-023)
        all_atl = _ATLASSIAN_OVERLAY_FILES + _ATLASSIAN_OVERLAY_DIRS
        for variant in _VARIANTS_NO_ATLASSIAN:
            variant_dir = _HT / variant
            if not variant_dir.exists():
                results.append(_issue(checker, INFO, variant, f"{variant} 변형 디렉토리 부재 — 건너뜀"))
                continue
            found_atl = [rel for rel in all_atl if (variant_dir / rel).exists()]
            if found_atl:
                results.append(_issue(
                    checker, BLOCK, variant,
                    f"Atlassian 오버레이가 {variant} 에 잘못 미러됨 (vela 계열 전용): {found_atl}",
                ))
            else:
                results.append(_issue(checker, PASS, variant, f"{variant} 변형에 Atlassian 오버레이 부재 OK"))

        # MR-15 (계속): vela 계열 변형에 Atlassian 오버레이 모두 존재해야 함
        for vela_variant_name in _VARIANTS_WITH_ATLASSIAN:
            vv = _HT / vela_variant_name
            if not vv.exists():
                results.append(_issue(
                    checker, INFO, vela_variant_name,
                    f"{vela_variant_name} 변형 부재 (F032 미적용 가능)",
                ))
                continue
            missing = [rel for rel in all_atl if not (vv / rel).exists()]
            if missing:
                results.append(_issue(
                    checker, CONCERN, vela_variant_name,
                    f"{vela_variant_name} 변형에 일부 Atlassian 오버레이 부재: {missing}",
                ))
            else:
                results.append(_issue(
                    checker, PASS, vela_variant_name,
                    f"{vela_variant_name} Atlassian 오버레이 모두 존재 OK",
                ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "LINT-MR", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# 검사기 레지스트리

# ---------------------------------------------------------------------------
# LINT-SSOT: main ≡ claude.loope (ADR-015 invariant)
# ---------------------------------------------------------------------------

# ADR-015 결정 2 의 제외 목록은 **`_SCOPE_RULES` 한 표**다 (위). 전엔 여기에
# `_SSOT_EXCLUDE_PREFIXES`/`_SSOT_EXCLUDE_EXACT` 가 따로 있었고, `scope` 열을 도입하면서
# `_ssot_excluded` 를 표의 뷰로 바꾼 뒤에도 **정의만 남아** 있었다. 죽은 상수는 그 자체가
# 함정이다 — 거기에 행을 더하면 아무 일도 일어나지 않는데 더한 사람은 더했다고 믿는다
# (실측 mH: `hooks/` 를 더해도 51 테스트·`lint --strict` 전부 통과). 그래서 지웠다.

def _ssot_excluded(rel: str, scoped: bool) -> bool:
    """이 상대경로가 main↔loope 비교에서 빠지는가 — **표의 `ssot` 뷰**다.

    전엔 `_SSOT_EXCLUDE_*` 를 직접 읽었고, 그래서 `_SCOPE_RULES` 의 `scope` 열이
    **선언일 뿐 배선이 아니었다**. 표는 `.claude/state/*/README.md` 를 ssot 의
    `outside` 증인(=제외하면 안 됨)으로 들고 있는데 실제 함수는 True 를 냈다 —
    증인이 **아무도 호출하지 않는 뷰**에 대해 증언하고 있었다. 그래서 3차에서 잡은
    mH 가 방향만 바꿔(CO→SSOT) 그대로 생존했다 (4차 MUST-1).

    `scoped` 는 경로가 `.claude/` 기준(True)인지 루트 기준(False)인지다 — 표는 루트
    기준이므로 `.claude/` 를 붙여 맞춘다.
    """
    full = f".claude/{rel}" if scoped else rel
    return _scope_match(full, "ssot") is not None




def _ssot_rel_files(root: Path, scoped: bool = True) -> dict:
    """미러 비교 대상 파일을 상대경로 → 내용 해시로 모은다.

    **git 추적 경계**는 `LINT-CO` 와 같다 — 미러는 추적되는 내용에 대한 계약이다.
    전엔 디스크를 그대로 걷어서, `_ssot_excluded` 를 표의 뷰로 배선하자마자
    gitignored 런타임 31건(`state/*.lock`·`sessions.db`·`backup-last.json` …)이
    "main 에만 존재" 로 쏟아졌다. 같은 위험에 검사기마다 경계가 다르면 한쪽을
    고칠 때 다른 쪽이 터진다 (4차 MUST-1 배선 주의).
    """
    import hashlib
    out = {}
    if not root.exists():
        return out
    tracked = _co_tracked(root)
    for path in root.rglob("*"):
        # symlink 는 따라가지 않는다 — loope 쪽에 main 을 가리키는 링크를 두면
        # 해시가 같아 drift 가 가려진다 (재리뷰 NICE-1).
        if path.is_symlink():
            out[str(path.relative_to(root))] = "<symlink — 미러에 심볼릭 링크 금지>"
            continue
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        if tracked is not None and rel not in tracked:
            continue        # 로컬 산출물 — 미러 계약 밖이다
        if _ssot_excluded(rel, scoped):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except OSError:
            continue
        out[rel] = digest
    return out


def _co_profile(variant: str, axes) -> frozenset:
    """이 변형이 선언된 축들 중 **어디에 속하는가** — 기대 분할의 좌표.

    `MAIN` 은 `claude.loope` 의 프로필로 환산한다 (ADR-015: main ≡ loope).
    """
    src = "claude.loope" if variant == "MAIN" else variant
    return frozenset(a for a in axes if src in _CO_AXES[a])


def _co_tracked(root: Path) -> set | None:
    """`root` 아래 **git 추적** 파일의 상대경로. git 을 못 쓰면 None.

    미러는 **추적되는 내용**에 대한 계약이다. 디스크를 그대로 훑으면 로컬 산출물이
    섞인다 — 실측: 메인의 `.opencode/` 는 gitignore 된 render 결과물인데 디스크
    스캔에서는 d-2 변형들과 "갈린" 것으로 읽혔다(7 BLOCK). `package-lock.json` 도 같다.
    반대로 `docs/poc/measurements/06-harness-e2e.md` 는 3곳 모두 추적이고 **진짜 drift** 다.
    """
    import subprocess
    try:
        res = subprocess.run(["git", "ls-files", "-z"], cwd=str(root),
                             capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return {x.decode("utf-8", "replace") for x in res.stdout.split(b"\0") if x}


def _co_walk(root: Path, scope: str = "co"):
    """트리를 훑는다. 건너뛸 디렉토리는 **표의 `anydir` 행**이 정한다.

    symlink 은 **조용히 건너뛰지 않고 돌려준다** — 호출자가 BLOCK 한다. 전에는
    `continue` 였고, 그래서 변형 사본을 전부 main 으로 링크하면 부분 미러가
    BLOCK 1 → **0** 으로 사라졌다 (실측 mS3). `LINT-SSOT` 는 같은 위험을 sentinel
    digest 로 이미 막는다 — 같은 위험에 검사기마다 정책이 다르면 약한 쪽으로 샌다.
    """
    skip = {r["pattern"] for r in _scope_rules(scope) if r["kind"] == "anydir"}
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for q in entries:
            if q.is_symlink():
                yield q         # 호출자가 BLOCK — 조용히 빠지면 범위가 줄어든다
            elif q.is_dir():
                if q.name not in skip:
                    stack.append(q)
            elif q.is_file() and q.suffix != ".pyc":
                yield q


def _co_collect() -> tuple:
    """{상대경로: {변형: 해시}}, 스캔한 트리 수, **읽지 못한 파일** 목록.

    **트리 전체**를 훑는다. 전에는 `.claude/`·`docs/adr/` 만 봤고, 그 바깥에 실제 drift
    (`docs/poc/measurements/06-harness-e2e.md` — F024 수정이 3 사본 중 1곳에만)와 미가드
    내용 오버레이(`.opencode/` 렌더 산출물 등 9종)가 있었다. 범위를 좁히면 AC3 의
    "미분류 0건" 이 **범위 축소로 통과**해 버린다 (리뷰 MUST-2).
    """
    import hashlib
    roots = {"MAIN": _PROJECT_ROOT}
    for d in sorted(_HT.iterdir()):
        if d.is_dir() and (d / "harness").is_dir() and d.name not in _CO_FROZEN:
            roots[d.name] = d / "harness"
    files: dict = {}
    unread: list = []
    untracked_roots: list = []
    links: list = []
    for name, root in roots.items():
        tracked = _co_tracked(root)
        if tracked is None:
            # 조용히 디스크로 내려가지 않는다 — 어떤 경계로 쟀는지 보고한다.
            untracked_roots.append(name)
        for q in _co_walk(root, "co"):
            rel = str(q.relative_to(root))
            if tracked is not None and rel not in tracked:
                continue        # 로컬 산출물 — 미러 계약 밖이다
            if _scope_match(rel, "co") is not None:
                continue        # 표가 제외한다 (머신 로컬 · 변형 로컬 · 캐시)
            # symlink 판정은 **제외 필터 뒤**다. 앞에 두면 범위 밖(`src/` 하위 소스
            # 트리 등)의 정당한 링크까지 잡는다 — 실제로 `src/gstack/` 의 상대 링크
            # 2건을 거짓 BLOCK 했다.
            if q.is_symlink():
                links.append(f"{name}:{rel}")
                continue
            try:
                digest = hashlib.sha256(q.read_bytes()).hexdigest()[:12]
            except OSError as exc:
                # **조용히 넘기지 않는다.** 읽지 못한 파일은 그 트리에서 사라져 보유 수가
                # 줄고, 분할이 틀린 채 통과한다 (F020 8차가 같은 모양을 실측했다).
                unread.append(f"{name}:{rel} ({type(exc).__name__})")
                continue
            files.setdefault(rel, {})[name] = digest
    return files, len(roots), unread, untracked_roots, links


def check_content_overlay() -> list:
    """공유 파일 **안의** 오버레이가 선언된 축대로만 갈라지는지 본다 (ADR-015 결정 5).

    `LINT-MR` 은 오버레이 **파일**이 남의 변형에 있는지를 본다. 이 검사기는 모든 변형이
    **공유하는 파일의 내용**이 선언된 축이 만드는 분할과 **정확히** 일치하는지 본다.
    양방향이라 조용한 실패 모드가 없다:

      - 같은 프로필인데 바이트가 다르다  → **선언 안 된 분기** (부분 미러·미선언 축)
      - 다른 프로필인데 바이트가 같다    → **오버레이 소실** (일괄 복사 사고)

    정당한 편집(모든 비동결 사본에 같은 수정)은 분할을 바꾸지 않으므로 **0 BLOCK** 이다 —
    그것이 기대 해시 표 대신 파생 분할을 고른 이유다.
    """
    results = []
    checker = "LINT-CO"
    if not _HT.exists():
        return [_issue(checker, INFO, "src/harness_template/", "템플릿 트리 없음 — 검사 생략")]

    unknown = {a for ax in _CONTENT_OVERLAY_AXES.values() for a in ax} - set(_CO_AXES)
    if unknown:
        results.append(_issue(checker, BLOCK, "_CONTENT_OVERLAY_AXES",
                              f"_CO_AXES 에 없는 축을 선언했다: {sorted(unknown)}"))
        return results

    files, n_roots, unread, untracked_roots, links = _co_collect()
    if links:
        results.append(_issue(
            checker, BLOCK, "symlink",
            f"{len(links)}건 — 미러에 심볼릭 링크를 두지 않는다. 링크하면 사본이 늘 "
            f"같아 보여 부분 미러가 **사라진다**(실측 BLOCK 1→0): {links[:5]}"))
    if untracked_roots:
        results.append(_issue(
            checker, CONCERN, "git 추적 목록 없음",
            f"{untracked_roots} 에서 `git ls-files` 를 쓰지 못해 디스크를 그대로 훑었다 — "
            "로컬 산출물이 섞여 거짓 BLOCK 이 날 수 있다"))
    if unread:
        results.append(_issue(checker, BLOCK, "읽지 못한 파일",
                              f"{len(unread)}건이 스캔에서 빠졌다 — 그 트리에서 사라져 "
                              f"분할이 틀린 채 통과한다: {unread[:5]}"))
    shared = {rel: m for rel, m in files.items() if len(m) >= 2}
    if not shared:
        return [_issue(checker, BLOCK, "src/harness_template/",
                       "공유 파일을 하나도 못 찾았다 — 검사기가 공회전한다")]

    bad = 0

    # **양의 목록** — 각 경로류가 공유 파일을 1건 이상 내놓는가. 제외를 더해 어떤
    # 경로류가 통째로 비면 여기서 막힌다. 증인(`outside`)은 "제외를 더하는" 방향을
    # 막고 이것은 "범위가 무신호로 줄어드는" 반대 방향을 막는다 — 실측(mH): 파생으로
    # `hooks/` 가 빠졌을 때 37 테스트와 `lint --strict` 가 **전부 통과**했다.
    for prefix, label in sorted(_SCOPE_REQUIRED.items()):
        if not any(r.startswith(prefix) for r in shared):
            bad += 1
            results.append(_issue(checker, BLOCK, prefix,
                                  f"{label} 경로류의 공유 파일이 0건이다 — 제외가 "
                                  "너무 넓거나 스캔 범위가 줄었다"))

    # **선언을 순회**한다 (`shared` 가 아니라). 보유 1 은 전에 `shared`(≥2)와
    # `missing`(0) 어디에도 들지 않아, 테스트는 실패하는데 `lint --strict` 는
    # **exit 0** 이었다 (실측: 단일 보유 파일을 선언하면 `PASS`).
    for rel in sorted(set(shared) | set(_CONTENT_OVERLAY_AXES)):
        obs = files.get(rel, {})
        if rel in _CONTENT_OVERLAY_AXES and not obs:
            bad += 1
            results.append(_issue(checker, BLOCK, rel,
                                  "축을 선언했는데 스캔에 없다 — 범위가 좁아졌거나 "
                                  "파일이 사라졌다"))
            continue
        if rel in _CONTENT_OVERLAY_AXES and len(obs) == 1:
            bad += 1
            results.append(_issue(
                checker, BLOCK, rel,
                f"사본이 하나뿐이다({list(obs)}) — 내용 오버레이는 사본이 둘 이상일 때만 "
                "성립하는 개념이다. 이것은 **파일** 오버레이이므로 `_*_OVERLAY_FILES` 로 "
                "옮겨라"))
            continue
        if len(obs) < 2:
            continue
        axes = _CONTENT_OVERLAY_AXES.get(rel, set())
        groups: dict = {}
        for variant, digest in obs.items():
            groups.setdefault(_co_profile(variant, axes), {}) \
                  .setdefault(digest, []).append(variant)

        def _name(prof):
            return ",".join(sorted(prof)) or "(base)"

        # ⓪ 선언한 축이 이 파일에서 **실제로 분할을 만들 수 있는가**.
        #    축 안·밖 중 한쪽만 이 파일을 보유하면 그 선언은 아무것도 제약하지 않는다 —
        #    붙여 놔도 조용히 통과한다(실측: `nw` 를 4 파일에 붙여도 생존). 죽은 선언은
        #    다음 사람에게 "여기는 갈려도 된다" 는 거짓 신호를 준다.
        holders = set(obs)
        for axis in sorted(axes):
            members = {("claude.loope" if v == "MAIN" else v) for v in holders}
            inside = members & set(_CO_AXES[axis])
            if not inside or inside == members:
                bad += 1
                side = "안" if not inside else "밖"
                results.append(_issue(
                    checker, BLOCK, rel,
                    f"죽은 축 선언 — 이 파일을 가진 변형 중 축 '{axis}' {side}이 비었다. "
                    "선언이 아무것도 제약하지 않는다 (붙여 놔도 조용히 통과)"))

        # ① 같은 프로필인데 갈렸다
        for prof, by_digest in sorted(groups.items(), key=lambda kv: _name(kv[0])):
            if len(by_digest) > 1:
                bad += 1
                detail = " | ".join(f"{d}:{sorted(vs)}" for d, vs in sorted(by_digest.items()))
                results.append(_issue(
                    checker, BLOCK, rel,
                    f"선언 안 된 분기 — 프로필 '{_name(prof)}' 안에서 내용이 갈렸다: {detail}. "
                    "부분 미러이거나 선언되지 않은 축이다"))

        # ② 다른 프로필인데 같아졌다
        seen: dict = {}
        for prof, by_digest in groups.items():
            for digest in by_digest:
                seen.setdefault(digest, []).append(prof)
        for digest, profs in sorted(seen.items()):
            if len(profs) < 2:
                continue
            bad += 1
            names = sorted(_name(x) for x in profs)
            # `set().intersection(*profs)` 는 **항상 ∅** 이라 diff 가 합집합이 됐다 —
            # 힌트가 "분할을 만들지 않는 축" 으로 엉뚱한 축까지 지목했다 (리뷰 SHOULD-3).
            diff = frozenset.union(*profs) - frozenset.intersection(*profs)
            hint = (f" 선언된 축 {sorted(diff)} 가 실제로는 분할을 만들지 않는다 — "
                    "죽은 축 선언이거나 오버레이가 지워졌다." if diff else "")
            results.append(_issue(
                checker, BLOCK, rel,
                f"오버레이 소실 — 서로 다른 프로필 {names} 이 같은 내용이 됐다.{hint}"))

    if not bad:
        results.append(_issue(checker, PASS, f"{len(shared)} 공유 파일",
                              f"내용 오버레이 정합 OK ({n_roots} 트리 · "
                              f"선언 {len(_CONTENT_OVERLAY_AXES)} 파일 · 축 {len(_CO_AXES)})"))
    return results


#: 동결 매니페스트 — 경로 → {sha256, reason}. ADR-015 결정 6.
_FREEZE_MANIFEST = _CLAUDE_DIR / "freeze-manifest.json"

#: `reason` 의 허용값. 다른 값은 사유 날조로 보고 BLOCK 한다.
_FREEZE_REASONS = ("phase0", "karpathy")

#: Karpathy 4원칙 제목. `reason: "karpathy"` 인 파일은 하나 이상 포함해야 한다 —
#: 사유가 참인지 보는 `must_contain` 앵커다. 리워딩되면 **시끄럽게** 실패한다
#: (`must_not_contain` 이었다면 조용히 vacuous 가 된다).
_KARPATHY_TITLES = ("Think Before Coding", "Simplicity First",
                    "Surgical Changes", "Goal-Driven Execution")


def check_freeze() -> list:
    """동결 스냅샷(`claude/` baseline · `openai/.codex/`)이 바뀌지 않았는지 본다.

    `LINT-CO` 는 이것을 **못 잡는다**(실측 — baseline 만 덮어쓰면 0 BLOCK). 동결을 축으로
    모델링하면 "baseline 은 늘 달라야 한다" 가 되어 Karpathy 동기화를 영구 금지하게 된다.

    해시 표가 여기서는 옳다 — 해시 표의 결함("자주 바뀌는 파일에 쓰면 갱신이 번거로워
    `regenerate` 를 부르고 그 순간 공회전")은 자주 바뀌는 대상에서만 생기는데, 동결
    대상은 정의상 안 바뀐다. **그래서 `regenerate` 서브커맨드를 만들지 않는다.**
    Karpathy 동기화는 매니페스트를 거쳐 간다 — 같은 커밋에서 해시와 사유를 갱신하고,
    그 한 줄이 diff 에 남아 리뷰에서 보인다. 일괄 `cp` 는 매니페스트를 갱신하지 않는다.
    """
    import hashlib
    results = []
    checker = "LINT-FREEZE"
    if not _HT.exists():
        return [_issue(checker, INFO, "src/harness_template/", "템플릿 트리 없음 — 검사 생략")]
    if not _FREEZE_MANIFEST.is_file():
        return [_issue(checker, BLOCK, ".claude/freeze-manifest.json",
                       "동결 매니페스트가 없다 — 동결이 강제되지 않는다 (ADR-015 결정 6)")]
    try:
        raw = json.loads(_FREEZE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [_issue(checker, BLOCK, ".claude/freeze-manifest.json",
                       f"매니페스트를 읽지 못했다 ({type(exc).__name__}) — 손상이면 전면 거부다")]
    # `[]` 처럼 **문법은 맞는데 모양이 틀린** 손상이 있다. `.get` 이 AttributeError 를 내고
    # 그것이 러너에서 INFO 로 강등되면 게이트가 조용히 열린다 (실측). 형태도 본다.
    if not isinstance(raw, dict) or not isinstance(raw.get("files"), dict):
        return [_issue(checker, BLOCK, ".claude/freeze-manifest.json",
                       f"매니페스트 모양이 틀렸다 ({type(raw).__name__}) — "
                       "`{\"files\": {경로: {sha256, reason}}}` 여야 한다")]
    manifest = raw["files"]
    if not manifest:
        return [_issue(checker, BLOCK, ".claude/freeze-manifest.json",
                       "매니페스트가 비었다 — 검사기가 공회전한다")]

    bad = 0
    for rel, entry in sorted(manifest.items()):
        path = _PROJECT_ROOT / rel
        reason = (entry or {}).get("reason")
        if reason not in _FREEZE_REASONS:
            bad += 1
            results.append(_issue(checker, BLOCK, rel,
                                  f"사유가 허용값이 아니다: {reason!r} — "
                                  f"{list(_FREEZE_REASONS)} 중 하나여야 한다"))
            continue
        if not path.is_file():
            bad += 1
            results.append(_issue(checker, BLOCK, rel, "동결 파일이 사라졌다"))
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != (entry or {}).get("sha256"):
            bad += 1
            results.append(_issue(checker, BLOCK, rel,
                                  "동결 파일이 바뀌었다 — 의도적 Karpathy 동기화라면 "
                                  "같은 커밋에서 매니페스트의 sha256·reason 을 갱신하라"))
            continue
        if reason == "karpathy":
            text = data.decode("utf-8", errors="replace")
            if not any(t in text for t in _KARPATHY_TITLES):
                bad += 1
                results.append(_issue(checker, BLOCK, rel,
                                      "사유가 'karpathy' 인데 4원칙 제목이 하나도 없다 — "
                                      "사유가 거짓이거나 동기화가 되돌려졌다"))

    # 매니페스트에 없는 동결 파일 — 새로 들어온 것은 동결 밖이라 가드가 0이 된다
    tracked = set(manifest)
    for base in (_HT / "claude" / "harness", _HT / "openai" / "harness"):
        if not base.is_dir():
            continue
        for q in sorted(base.rglob("*")):
            if q.is_symlink():
                # 조용히 건너뛰지 않는다. SSOT·CO 를 통일한 근거("같은 위험에 검사기마다
                # 정책이 다르면 약한 쪽으로 샌다")가 FREEZE 에도 적용된다 — 실측: 일반
                # 파일 `slipped.md` 는 BLOCK 인데 같은 자리에 링크를 두면 0 BLOCK 이었다.
                bad += 1
                results.append(_issue(checker, BLOCK, str(q.relative_to(_PROJECT_ROOT)),
                                      "동결 트리에 심볼릭 링크가 있다 — 해시 대조를 "
                                      "우회한다"))
                continue
            if not q.is_file():
                continue
            if q.suffix == ".pyc":
                continue
            # 건너뛰기는 **표의 `freeze` scope** 가 정한다. 손으로 적은
            # `any(x in q.parts for x in ("state", …))` 는 `LINT-SSOT`·`LINT-CO` 가
            # 각각 한 번씩 고친 bare-name 밀반입 통로와 같은 모양이었다 — 실측:
            # `claude/harness/.claude/agents/evil.md` 는 BLOCK 인데 그 아래 `state/`·
            # `node_modules/`·`.pytest_cache/` 를 한 겹 끼우면 전부 **0 BLOCK**.
            # 같은 결함이 세 검사기에 각각 생긴 이유가 각자 손으로 적은 것이다.
            if _scope_match(str(q.relative_to(_PROJECT_ROOT)), "freeze") is not None:
                continue
            if str(q.relative_to(_PROJECT_ROOT)) not in tracked:
                bad += 1
                results.append(_issue(checker, BLOCK, str(q.relative_to(_PROJECT_ROOT)),
                                      "동결 트리에 매니페스트에 없는 파일이 있다 — "
                                      "동결 밖이라 아무 가드도 보지 않는다"))

    if not bad:
        n_k = sum(1 for e in manifest.values() if (e or {}).get("reason") == "karpathy")
        results.append(_issue(checker, PASS, f"{len(manifest)} 동결 파일",
                              f"해시 일치 OK (karpathy {n_k} / phase0 {len(manifest) - n_k})"))
    return results


#: 문서가 인용해도 되는 비-코드 심볼 (환경변수·외부 규약 — 우리 코드에 없는 것이 정상).
_DOC_SYMBOL_ALLOW = frozenset({
    "CLAUDE_PROJECT_DIR", "HARNESS_AGENT_TYPE", "PYTHONPYCACHEPREFIX",
    "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME", "LC_ALL",
})


def check_doc_symbols() -> list:
    """문서가 **코드를 인용하되 복제하지 않는지** 본다 (ADR-015 결정 8).

    이 리포에서 숫자·심볼 인용이 낡은 것은 **네 번째**다 — 제외 "5종"→7, 통로
    "둘"→"넷"→9, `model_nem` "4 파일"→9, 그리고 `_CO_SKIP_DIRS` 는 개명 뒤
    **존재하지 않는 심볼**이 됐다. "숫자를 적지 말고 세는 명령을 적는다" 는 규율은
    옳지만 **사람의 기억에 의존해서 네 번 다 실패했다.**

    기계가 볼 수 있는 만큼만 기계에 맡긴다:

      1. 문서가 백틱으로 인용한 `_UPPER_SNAKE` 식별자는 `.claude/bin/*.py` 에 실재해야
         한다 → 개명 리팩터가 문서를 끌고 간다.
      2. 숫자를 적으려면 출처를 단다 —
         `<!-- lint:len _CONTENT_OVERLAY_AXES -->22<!-- /lint -->`.
         실제 길이와 다르면 BLOCK. (표현식 평가는 하지 않는다 — **심볼 길이**만.)

    **검사할 수 없는 서술 주장**("자기 파일이 하나도 없는")은 이 검사기가 못 본다.
    답은 "검사기를 더 똑똑하게" 가 아니라 그런 문장을 쓰지 않는 규율 + 리뷰다 —
    그 경계를 정직하게 긋는 것이 "전부 자동화했다" 보다 낫다.
    """
    import re as _re
    results = []
    checker = "LINT-DOC"

    # 코드에 실재하는 모듈 수준 심볼 수집
    symbols: dict = {}
    bindir = _CLAUDE_DIR / "bin"
    if not bindir.is_dir():
        return [_issue(checker, INFO, ".claude/bin/", "코드 디렉토리 없음 — 검사 생략")]
    # **메인 bin 만** 본다 (하위 패키지 포함). 처음엔 "문서가 오버레이 전용 심볼도
    # 인용한다" 며 변형 bin 까지 합집합으로 봤는데, 그 근거로 든 예(ADR-016 의
    # opencode 어댑터 상수)가 **메인에도 있어** 틀렸다. 실측: 문서가 인용하는 23개
    # 전부 메인에서 해결되고, 변형에만 있는 인용은 **0개**다. 합집합으로 두면
    # 변형 전용 심볼 52개가 메인 문서에서 조용히 통과하는 통로가 된다.
    # 변형 전용 심볼을 정말 인용해야 할 날이 오면 그때 **그 변형의 문서**로 좁힌다.
    for q in sorted(bindir.rglob("*.py")):   # host_adapters/ 같은 하위 패키지도
        try:
            tree = ast.parse(q.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                targets = [node.name]
            for name in targets:
                symbols.setdefault(name, q.name)

    docs = [_PROJECT_ROOT / "CLAUDE.md"]
    adr = _PROJECT_ROOT / "docs" / "adr"
    if adr.is_dir():
        docs += sorted(adr.glob("*.md"))

    cited = _re.compile(r"`(_[A-Z][A-Z0-9_]{3,})`")
    provenance = _re.compile(r"<!--\s*lint:len\s+([A-Za-z_][A-Za-z0-9_]*)\s*-->"
                             r"\s*(\d+)\s*<!--\s*/lint\s*-->")
    bad = 0
    for doc in docs:
        if not doc.is_file():
            continue
        try:
            text = doc.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(doc.relative_to(_PROJECT_ROOT))
        for line_no, line in enumerate(text.splitlines(), 1):
            for name in cited.findall(line):
                if name in symbols or name in _DOC_SYMBOL_ALLOW:
                    continue
                bad += 1
                results.append(_issue(
                    checker, BLOCK, f"{rel}:{line_no}",
                    f"`{name}` 을 인용하는데 `.claude/bin/*.py` 에 없다 — 개명됐거나 "
                    "오타다. 문서가 코드보다 앞서가면 다음 사람이 그 이름을 찾는다"))
        for name, written in provenance.findall(text):
            if name not in symbols:
                bad += 1
                results.append(_issue(checker, BLOCK, rel,
                                      f"`lint:len {name}` 의 심볼이 코드에 없다"))
                continue
            actual = _doc_symbol_len(name)
            if actual is None:
                bad += 1
                # 길이는 **이 모듈**의 심볼만 잴 수 있다 (존재 검사는 bin 전체).
                # 그 비대칭을 사유에 적는다 — 전엔 "컨테이너가 아니다" 라고만 해서
                # 다른 모듈 심볼에 달았을 때 엉뚱한 곳을 고치게 했다.
                results.append(_issue(
                    checker, BLOCK, rel,
                    f"`{name}` 의 길이를 잴 수 없다 — `lint.py` 자신의 컨테이너 심볼만 "
                    f"잴 수 있다 (존재 검사는 `.claude/bin/**` 전체, 길이는 이 모듈)"))
            elif int(written) != actual:
                bad += 1
                results.append(_issue(
                    checker, BLOCK, rel,
                    f"`{name}` 길이가 문서는 {written}, 실제는 {actual} — 출처를 달았으면 "
                    "값은 기계가 맞춘다"))

    if not bad:
        results.append(_issue(checker, PASS, f"{len(docs)} 문서",
                              f"인용 심볼 실재 OK (코드 심볼 {len(symbols)}개)"))
    return results


def _doc_symbol_len(name: str):
    """이 모듈의 심볼 길이 — `lint:len` 출처 검사용. 잴 수 없으면 None."""
    obj = globals().get(name)
    try:
        return len(obj)
    except TypeError:
        return None


def check_atlassian_targets() -> list:
    """배포되는 허용 목록이 **비어 있는지** 본다 (3-C 철칙).

    vela 를 가져가는 다운스트림이 우리 스페이스 키를 물려받으면, 그 하네스는
    처음부터 **남의 Confluence 에 쓸 수 있는 상태**로 시작한다. 목록은 각자
    채우는 것이지 배포에 실려 나가는 것이 아니다.

    로컬 작업 트리(메인 `.claude/`)는 검사하지 않는다 — 거기 채우는 것이 정상이다.
    """
    checker = "LINT-ATL"
    results = []
    tpl = _PROJECT_ROOT / "src" / "harness_template"
    variants = sorted(tpl.glob("claude.vela.*")) if tpl.exists() else []
    if not variants:
        results.append(_issue(checker, INFO, "claude.vela.*", "vela 변형 없음 — 검사 생략"))
        return results
    for var in variants:
        rel = f"{var.name}/harness/.claude/atlassian-targets.json"
        path = var / "harness" / ".claude" / "atlassian-targets.json"
        hook = var / "harness" / ".claude" / "hooks" / "pre-atlassian-write-check.sh"
        if not path.is_file():
            results.append(_issue(checker, BLOCK, rel, "허용 목록 파일 없음 — 훅이 전면 거부한다"))
            continue
        if not hook.is_file():
            results.append(_issue(checker, BLOCK, f"{var.name}/…/pre-atlassian-write-check.sh",
                                  "허용 목록만 있고 **강제하는 훅이 없다** — 목록은 장식이 된다"))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            results.append(_issue(checker, BLOCK, rel, f"JSON 파싱 실패: {exc}"))
            continue
        leaked = [k for k in ("confluence_spaces", "jira_projects") if data.get(k)]
        if leaked:
            results.append(_issue(checker, BLOCK, rel,
                                  f"배포본에 허용 대상이 들어 있다 {leaked} — "
                                  f"다운스트림이 남의 스페이스에 쓸 수 있게 된다"))
        else:
            results.append(_issue(checker, PASS, rel, "허용 목록 비어 있음 OK (fail-closed 기본값)"))
        # 훅이 settings.json 에 배선돼 있는가 — 스크립트만 있으면 아무것도 막지 않는다
        st = var / "harness" / ".claude" / "settings.json"
        if st.is_file():
            try:
                pre = json.loads(st.read_text(encoding="utf-8")).get("hooks", {}).get("PreToolUse", [])
            except ValueError:
                pre = []
            wired = any("atlassian" in json.dumps(m, ensure_ascii=False).lower() for m in pre)
            results.append(_issue(checker, PASS if wired else BLOCK,
                                  f"{var.name}/…/settings.json",
                                  "PreToolUse 에 Atlassian 훅 배선 OK" if wired
                                  else "훅이 PreToolUse 에 배선되지 않았다 — 선언만 있고 강제가 없다"))
    results.extend(_check_local_atlassian_guard(checker, variants))
    return results


def _check_local_atlassian_guard(checker: str, variants: list) -> list:
    """로컬 작업 트리의 가드를 본다 — **목록의 내용이 아니라 가드의 무결성**을.

    로컬 허용 목록은 채우는 것이 정상이라 내용은 검사하지 않는다. 그러나 그 파일과
    훅을 LINT-SSOT 제외 목록에 넣은 순간, 훅은 **어느 미러 검사도 보지 않는 파일**이
    된다 — F021 이 고친 밀반입 통로가 같은 모양으로 다시 열린다. 그래서 훅만은
    배포 사본과 바이트 동일을 요구한다. 목록은 로컬 값이라 비교하지 않고, 대신
    **읽을 수 있는지**만 본다 (깨진 목록은 훅이 전면 거부하는데, 그 사실을 발행
    시점이 아니라 lint 에서 알아야 한다).
    """
    results = []
    local_hook = _PROJECT_ROOT / ".claude" / "hooks" / "pre-atlassian-write-check.sh"
    local_list = _PROJECT_ROOT / ".claude" / "atlassian-targets.json"
    if not local_hook.is_file() and not local_list.is_file():
        results.append(_issue(checker, INFO, ".claude/atlassian-targets.json",
                              "로컬 가드 없음 — 이 작업 트리는 Atlassian 에 쓰지 않는다"))
        return results
    # 한쪽만 있으면 반쪽이다. 목록만 있으면 아무것도 막지 않고, 훅만 있으면 전면 거부다.
    if local_hook.is_file() != local_list.is_file():
        missing = "훅" if local_list.is_file() else "허용 목록"
        results.append(_issue(checker, BLOCK, ".claude/ (로컬)",
                              f"가드가 반쪽이다 — {missing} 이 없다. 둘은 한 쌍이어야 한다"))
        return results
    ref = next((v / "harness" / ".claude" / "hooks" / "pre-atlassian-write-check.sh"
                for v in variants), None)
    if ref is not None and ref.is_file():
        same = ref.read_bytes() == local_hook.read_bytes()
        results.append(_issue(checker, PASS if same else BLOCK,
                              ".claude/hooks/pre-atlassian-write-check.sh",
                              "배포 사본과 바이트 동일 OK" if same
                              else "배포 사본과 다르다 — 로컬 훅은 SSOT 비교에서 빠지므로 "
                                   "여기서 갈라지면 아무도 못 잡는다"))
    try:
        data = json.loads(local_list.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        results.append(_issue(checker, BLOCK, ".claude/atlassian-targets.json",
                              f"읽을 수 없다 ({type(exc).__name__}) — 훅이 전면 거부한다"))
        return results
    if not isinstance(data, dict):
        results.append(_issue(checker, BLOCK, ".claude/atlassian-targets.json",
                              "최상위가 객체가 아니다 — 훅이 전면 거부한다"))
        return results
    targets = [t for k in ("confluence_spaces", "jira_projects")
               for t in (data.get(k) or []) if isinstance(data.get(k), list)]
    results.append(_issue(checker, INFO, ".claude/atlassian-targets.json",
                          f"로컬 허용 대상 {len(targets)}건: {targets}" if targets
                          else "로컬 허용 목록 비어 있음 — 모든 쓰기가 거부된다"))
    return results


def check_ssot() -> list:
    """`main .claude/` ≡ `claude.loope/harness/.claude/` 를 **내용으로** 강제한다.

    왜 새 검사기인가 (F021 리뷰 MUST-6):
      `LINT-MIRROR` 는 구 SSOT(`claude.gstack`)를 보고 `.py` 만 비교한다. 그래서
      ADR-015 가 invariant 로 선언한 `main ≡ loope` 를 **원리적으로 못 잡는다** —
      실제로 `coding-standards.md` 내용 drift, `CLAUDE.md` 본문 drift, 한쪽에만
      있는 파일이 전부 0 BLOCK 으로 통과했다.

      F010 의 "미러 회귀 2회" 교훈이 겨냥한 결함 클래스가 정확히 이것이다:
      규칙을 문서에 적어 두고 강제는 파일 존재만 보는 것.
    """
    results = []
    checker = "LINT-SSOT"
    loope = (_PROJECT_ROOT / "src" / "harness_template" / "claude.loope" / "harness")
    if not loope.exists():
        results.append(_issue(checker, INFO, "claude.loope/", "변형 없음 — 검사 생략"))
        return results

    # 제외 목록(`state/`·`design/`·`settings.json`…)은 `.claude/` 기준으로 쓰였다.
    # 다른 쌍에 그대로 적용하면 같은 이름의 하위 디렉토리가 통째로 사각이 된다.
    pairs = [(".claude/", _CLAUDE_DIR, loope / ".claude", True),
             ("docs/adr/", _PROJECT_ROOT / "docs" / "adr", loope / "docs" / "adr", False)]
    for label, main_root, var_root, scoped in pairs:
        main_files = _ssot_rel_files(main_root, scoped)
        var_files = _ssot_rel_files(var_root, scoped)
        only_main = sorted(set(main_files) - set(var_files))
        only_var = sorted(set(var_files) - set(main_files))
        differing = sorted(k for k in (set(main_files) & set(var_files))
                           if main_files[k] != var_files[k])
        for rel in only_main:
            results.append(_issue(checker, BLOCK, f"{label}{rel}",
                                  "main 에만 존재 — loope 로 미러하거나 ADR-015 제외 목록에 등재"))
        for rel in only_var:
            results.append(_issue(checker, BLOCK, f"{label}{rel}",
                                  "loope 에만 존재 — main 에서 삭제된 파일이 남았을 수 있다"))
        for rel in differing:
            results.append(_issue(checker, BLOCK, f"{label}{rel}",
                                  "내용 drift — ADR-015 의 main ≡ loope invariant 위반"))
        if not (only_main or only_var or differing):
            results.append(_issue(checker, PASS, label,
                                  f"main ≡ loope OK ({len(main_files)} 파일)"))

    # CLAUDE.md 는 변형별 헤더가 다를 수 있으므로 **본문 섹션** 단위로 비교한다.
    main_md = _PROJECT_ROOT / "CLAUDE.md"
    var_md = loope / "CLAUDE.md"
    if main_md.exists() and var_md.exists():
        import re as _re

        def _sections(path: Path) -> dict:
            text = path.read_text(encoding="utf-8", errors="replace")
            out, cur, buf = {}, None, []
            for line in text.splitlines():
                if line.startswith("## "):
                    if cur:
                        out[cur] = "\n".join(buf).strip()
                    cur, buf = line[3:].strip(), []
                else:
                    buf.append(line)
            if cur:
                out[cur] = "\n".join(buf).strip()
            return out

        a, b = _sections(main_md), _sections(var_md)
        # 헤더 인용부("이 작업 환경은…")는 변형별 맞춤이 허용된다 — 섹션 이름으로 제외.
        skip = {"📋 프로젝트 개요", "🗂️ 디렉토리 구조", "🔨 주요 명령어"}
        drift = [k for k in (set(a) & set(b)) if k not in skip and a[k] != b[k]]
        missing = sorted((set(a) - set(b)) - skip)
        # 파일 수준 비교는 양방향인데 섹션 수준은 main-only 만 봤다 — loope 에만
        # 섹션을 더하면 0 BLOCK 이었다 (재리뷰 MUST-2). 정책이 층마다 달랐다.
        extra = sorted((set(b) - set(a)) - skip)
        for name in missing:
            results.append(_issue(checker, BLOCK, f"CLAUDE.md §{name}",
                                  "main 에만 있는 섹션 — loope 로 미러"))
        for name in extra:
            results.append(_issue(checker, BLOCK, f"CLAUDE.md §{name}",
                                  "loope 에만 있는 섹션 — main 에서 삭제됐거나 변형에 몰래 추가됐다"))
        for name in sorted(drift):
            results.append(_issue(checker, BLOCK, f"CLAUDE.md §{name}",
                                  "본문 drift — 일괄 편집이 일부 변형에만 도달했을 수 있다"))
        if not (drift or missing or extra):
            results.append(_issue(checker, PASS, "CLAUDE.md", "본문 섹션 정합 OK"))
    return results


# ---------------------------------------------------------------------------

#: 이 검사기들이 **죽으면 BLOCK** 이다. 나머지(참고용·휴리스틱)는 INFO 로 둔다.
#: 판정 기준: 그 검사기가 없으면 **통과하면 안 되는 것이 통과하는가**.
_GATE_CHECKERS = frozenset({"LINT-SSOT", "LINT-MR", "LINT-CO", "LINT-FREEZE",
                            "LINT-ATL", "LINT-DOC"})

_CHECKERS = {
    "LINT-FL": ("feature_list 정합성", check_fl),
    "LINT-STALE": ("오래된 in-progress", check_stale),
    "LINT-AC": ("acceptance_criteria 누락·모호", check_ac),
    "LINT-ADR": ("ADR ↔ feature 연결성", check_adr),
    "LINT-LEARN": ("learnings 모순", check_learn),
    "LINT-MIRROR": ("gstack 표준 변형 대조 (참고용 INFO)", check_mirror),
    "LINT-SSOT": ("main ≡ claude.loope invariant (ADR-015)", check_ssot),
    "LINT-ATL": ("Atlassian 쓰기 대상 제한 — 3-C 철칙 (배포본 fail-closed)", check_atlassian_targets),
    "LINT-MR": ("변형 오버레이 정합 — 파일 단위", check_mirror_regression),
    "LINT-CO": ("내용 오버레이 정합 — 공유 파일 안의 변형군별 사본 (ADR-015 결정 5)", check_content_overlay),
    "LINT-FREEZE": ("동결 스냅샷 불변 — baseline · openai/.codex (ADR-015 결정 6)", check_freeze),
    "LINT-DOC": ("문서가 인용한 심볼·숫자가 코드와 맞는가 (ADR-015 결정 8)", check_doc_symbols),
}


# ---------------------------------------------------------------------------
# 출력 포매터
# ---------------------------------------------------------------------------

def _format_human(ts: str, all_results: dict, summary: dict) -> str:
    """
    검사 결과를 사람이 읽기 좋은 마크다운 표 형식으로 포매팅한다.

    Args:
        ts: 실행 시각 문자열
        all_results: {checker_id: [issue, ...]} 딕셔너리
        summary: {"BLOCK": n, "CONCERN": n, "INFO": n, "PASS": n}

    Returns:
        str: 포매팅된 출력 문자열
    """
    lines = []
    lines.append(f"=== F009 Lint Report — {ts} ===")
    lines.append("")

    for checker_id, (checker_desc, _) in _CHECKERS.items():
        if checker_id not in all_results:
            continue
        issues = all_results[checker_id]
        lines.append(f"{checker_id} ({checker_desc})")
        lines.append("| # | 라벨 | 항목 | 메시지 |")
        lines.append("|---|---|---|---|")
        for i, issue in enumerate(issues, 1):
            label = issue["label"]
            target = issue["target"]
            message = issue["message"]
            lines.append(f"| {i} | {label} | {target} | {message} |")
        lines.append("")

    block_n = summary["BLOCK"]
    concern_n = summary["CONCERN"]
    info_n = summary["INFO"]
    pass_n = summary["PASS"]
    lines.append(f"요약: {block_n} BLOCK, {concern_n} CONCERN, {info_n} INFO, {pass_n} PASS")

    if block_n > 0:
        lines.append("")
        lines.append("BLOCK 항목이 있습니다. 즉시 수정이 필요합니다.")
        lines.append("--strict 플래그를 사용하면 BLOCK 발견 시 exit 1 (CI gate 용도)")

    return "\n".join(lines)


def _format_json(ts: str, all_results: dict, summary: dict) -> str:
    """
    검사 결과를 머신 파싱용 JSON 형식으로 포매팅한다.

    Args:
        ts: ISO 8601 타임스탬프 문자열
        all_results: {checker_id: [issue, ...]} 딕셔너리
        summary: {"BLOCK": n, "CONCERN": n, "INFO": n, "PASS": n}

    Returns:
        str: JSON 문자열
    """
    flat_results = []
    for checker_id, issues in all_results.items():
        for issue in issues:
            flat_results.append(issue)

    output = {
        "ts": ts,
        "results": flat_results,
        "summary": summary,
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 캐시 저장 (atomic write)
# ---------------------------------------------------------------------------

def _save_cache(ts: str, all_results: dict, summary: dict) -> None:
    """
    검사 결과를 .claude/state/lint-last.json 에 원자적으로 저장한다.

    atomic write: tempfile + os.rename 패턴으로 부분 쓰기 방지.

    Args:
        ts: ISO 8601 타임스탬프
        all_results: 검사 결과 딕셔너리
        summary: 요약 딕셔너리
    """
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        flat_results = []
        for issues in all_results.values():
            flat_results.extend(issues)
        payload = {"ts": ts, "results": flat_results, "summary": summary}
        # tempfile을 같은 디렉토리에 생성해야 atomic rename 가능
        fd, tmp_path = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.rename(tmp_path, _CACHE_FILE)
        except Exception:
            # 임시 파일 정리
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        print(f"[lint] 캐시 저장 실패 (무시): {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# regenerate-index: docs/index.md 생성
# ---------------------------------------------------------------------------

def _load_features() -> list:
    """feature_list.json 로드. 실패 시 빈 리스트 반환."""
    if not _FEATURE_LIST.exists():
        return []
    try:
        with open(_FEATURE_LIST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _load_adrs(known_feature_ids: set = None) -> list:
    """
    docs/adr/*.md를 파싱하여 ADR 목록을 반환한다.

    Args:
        known_feature_ids: feature_list에 등록된 ID 집합. 제공 시 index.md에서
                           미등록 ID를 필터링한다.

    Returns:
        list[dict]: [{"filename", "number", "title", "status", "feature_refs"}, ...]
    """
    if not _DOCS_ADR.exists():
        return []
    adrs = []
    for adr_path in sorted(_DOCS_ADR.glob("ADR-*.md")):
        # ADR-000-template.md는 제외
        if "template" in adr_path.name.lower():
            continue
        try:
            content = adr_path.read_text(encoding="utf-8")
        except Exception:
            continue
        parsed = _parse_adr_frontmatter(content)

        # 번호 추출: ADR-001-...md → 001
        num_match = re.match(r"ADR-(\d+)", adr_path.name)
        num = num_match.group(1) if num_match else "???"

        # 제목 추출: 첫 번째 # 헤딩 — "ADR-NNN: " 접두사 제거
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else adr_path.stem
        # "ADR-001: " 같은 접두사 제거
        title = re.sub(r"^ADR-\d+\s*:\s*", "", title)

        # index.md 출력용: feature_list에 없는 ID는 필터링
        feature_refs = parsed["feature_refs"]
        if known_feature_ids is not None:
            feature_refs = [fid for fid in feature_refs if fid in known_feature_ids]

        adrs.append({
            "filename": adr_path.name,
            "number": f"ADR-{num}",
            "title": title,
            "status": parsed["status"],
            "feature_refs": feature_refs,
        })
    return adrs


def _load_design_docs(known_feature_ids: set = None) -> list:
    """
    docs/design/*.md를 파싱하여 설계 문서 목록을 반환한다.

    Args:
        known_feature_ids: feature_list에 등록된 ID 집합. 제공 시 미등록 ID 필터링.

    Returns:
        list[dict]: [{"filename", "feature_refs"}, ...]
    """
    if not _DOCS_DESIGN.exists():
        return []
    docs = []
    for doc_path in sorted(_DOCS_DESIGN.glob("*.md")):
        try:
            content = doc_path.read_text(encoding="utf-8")
        except Exception:
            continue
        # 파일명에서 FNNNs 추출 (가장 신뢰도 높음)
        feature_refs = sorted(set(f"F{n}" for n in re.findall(r"\bF(\d{3})\b", doc_path.name)))
        if known_feature_ids is not None:
            feature_refs = [fid for fid in feature_refs if fid in known_feature_ids]
        docs.append({
            "filename": doc_path.name,
            "feature_refs": feature_refs,
        })
    return docs


def _load_commands() -> list:
    """
    .claude/commands/*.md 목록을 반환한다.

    Returns:
        list[str]: 커맨드 이름 목록 (파일명 .md 제외)
    """
    cmd_dir = _CLAUDE_DIR / "commands"
    if not cmd_dir.exists():
        return []
    return sorted(p.stem for p in cmd_dir.glob("*.md"))


def _load_agents() -> list:
    """
    .claude/agents/*.md 목록을 반환한다.

    Returns:
        list[str]: 에이전트 이름 목록
    """
    agent_dir = _CLAUDE_DIR / "agents"
    if not agent_dir.exists():
        return []
    return sorted(p.stem for p in agent_dir.glob("*.md"))


def _load_skills() -> list:
    """
    .claude/skills/*/SKILL.md 목록을 반환한다.

    각 SKILL.md 의 YAML frontmatter에서 description 필드를 추출한다.
    frontmatter가 없거나 파싱 실패 시 빈 문자열로 대체한다.

    Returns:
        list[dict]: [{"name", "description"}, ...]
    """
    skills_dir = _CLAUDE_DIR / "skills"
    if not skills_dir.exists():
        return []
    skills = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        desc = ""
        if skill_md.is_file():
            try:
                content = skill_md.read_text(encoding="utf-8")
                # frontmatter description 추출 (YAML block scalar '|' 또는 단일 라인)
                m = re.search(
                    r'^description:\s*(?:\|\s*\n)?\s*(.+?)(?=\n[a-z]|\n---|\n\n)',
                    content,
                    re.MULTILINE | re.DOTALL,
                )
                if m:
                    desc = m.group(1).strip().split('\n')[0]
            except Exception:
                desc = ""
        skills.append({"name": skill_name, "description": desc})
    return skills


def _load_learnings_stats() -> dict:
    """
    learnings.jsonl에서 통계를 계산한다.

    Returns:
        dict: {"total": int, "by_type": {type: count}, "recent": [최근 5건 insight]}
    """
    if not _LEARNINGS_FILE.exists():
        return {"total": 0, "by_type": {}, "recent": []}

    entries = []
    try:
        with open(_LEARNINGS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return {"total": 0, "by_type": {}, "recent": []}

    by_type: dict = {}
    for e in entries:
        t = e.get("type", "other")
        by_type[t] = by_type.get(t, 0) + 1

    # 최근 5건: ts 기준 역순
    sorted_entries = sorted(entries, key=lambda e: e.get("ts", ""), reverse=True)
    recent = []
    for e in sorted_entries[:5]:
        insight = e.get("insight", "")
        if len(insight) > 80:
            insight = insight[:77] + "..."
        feature_id = e.get("feature_id", "")
        key = e.get("key", "")
        recent.append(f"[{e.get('type', '?')}] {key}: {insight}" + (f" ({feature_id})" if feature_id else ""))

    return {"total": len(entries), "by_type": by_type, "recent": recent}


def _categorize_commands(commands: list) -> dict:
    """
    커맨드 목록을 카테고리별로 분류한다.

    Args:
        commands: 커맨드 이름 목록

    Returns:
        dict: {카테고리: [커맨드명, ...]}
    """
    categories = {
        "세션": ["init-project", "start-session", "handoff", "status"],
        "안전": ["freeze", "unfreeze", "guard"],
        "학습": ["learn", "context-save", "context-restore"],
        "자동화": ["plan-full", "ship", "retro", "lint"],
        "영구지식": ["brain-sync", "brain-search", "brain-stats", "brain-list"],
        "호스트": ["host"],
        "감사": ["design-review", "qa-browser"],
    }
    cmd_set = set(commands)
    result = {}
    categorized = set()
    for cat, cmds in categories.items():
        found = [c for c in cmds if c in cmd_set]
        if found:
            result[cat] = found
            categorized.update(found)

    # 카테고리 미분류 커맨드
    uncategorized = sorted(cmd_set - categorized)
    if uncategorized:
        result["기타"] = uncategorized

    return result


def generate_index() -> str:
    """
    docs/index.md 내용을 생성하여 반환한다.

    Returns:
        str: index.md 전체 마크다운 내용
    """
    now = datetime.now(tz=timezone(timedelta(hours=9)))
    ts_str = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    features = _load_features()
    known_ids = {f.get("id") for f in features if "id" in f}
    adrs = _load_adrs(known_feature_ids=known_ids)
    design_docs = _load_design_docs(known_feature_ids=known_ids)
    agents = _load_agents()
    skills = _load_skills()
    commands = _load_commands()
    learnings_stats = _load_learnings_stats()
    cmd_categories = _categorize_commands(commands)

    lines = []

    # 헤더
    lines.append("<!-- AUTO-GENERATED — 손으로 수정하지 말 것 -->")
    lines.append("<!-- python3 .claude/bin/lint.py regenerate-index 로 재생성 -->")
    lines.append("")
    lines.append("# 프로젝트 산출물 인덱스")
    lines.append("")
    lines.append(f"자동 생성됨. 손으로 수정하지 말 것 — `python3 .claude/bin/lint.py regenerate-index` 로 재생성.")
    lines.append(f"마지막 갱신: {ts_str}")
    lines.append("")

    # Features 섹션
    lines.append("## Features")
    lines.append("")
    lines.append("| ID | 상태 | 우선순위 | 제목 |")
    lines.append("|---|---|---|---|")
    for feat in features:
        fid = feat.get("id", "?")
        status = feat.get("status", "?")
        priority = feat.get("priority", "?")
        title = feat.get("title", "?")
        lines.append(f"| {fid} | {status} | {priority} | {title} |")
    lines.append("")

    # ADR 섹션
    lines.append("## ADR (Architecture Decision Records)")
    lines.append("")
    if adrs:
        lines.append("| 번호 | 상태 | 제목 | 관련 feature |")
        lines.append("|---|---|---|---|")
        for adr in adrs:
            refs = ", ".join(adr["feature_refs"]) if adr["feature_refs"] else "—"
            lines.append(f"| {adr['number']} | {adr['status']} | {adr['title']} | {refs} |")
    else:
        lines.append("ADR 없음.")
    lines.append("")

    # Design Documents 섹션
    lines.append("## Design Documents")
    lines.append("")
    if design_docs:
        lines.append("| 파일 | 관련 feature |")
        lines.append("|---|---|")
        for doc in design_docs:
            refs = ", ".join(doc["feature_refs"]) if doc["feature_refs"] else "—"
            lines.append(f"| {doc['filename']} | {refs} |")
    else:
        lines.append("설계 문서 없음.")
    lines.append("")

    # Agents 섹션
    lines.append("## Agents")
    lines.append("")
    if agents:
        agent_list = " / ".join(agents)
        lines.append(f"{agent_list} ({len(agents)}종)")
        lines.append(f"각각 [.claude/agents/](.claude/agents/)에 정의.")
    else:
        lines.append("에이전트 없음.")
    lines.append("")

    # Skills 섹션
    lines.append("## Skills")
    lines.append("")
    if skills:
        lines.append("| 이름 | 설명 |")
        lines.append("|---|---|")
        for skill in skills:
            lines.append(f"| {skill['name']} | {skill['description']} |")
    else:
        lines.append("스킬 없음.")
    lines.append("")

    # Commands 섹션
    lines.append("## Commands")
    lines.append("")
    lines.append(f"{len(commands)}종의 슬래시 커맨드 — [.claude/commands/](.claude/commands/)")
    lines.append("")
    if cmd_categories:
        lines.append("| 카테고리 | 커맨드 |")
        lines.append("|---|---|")
        for cat, cmds in cmd_categories.items():
            lines.append(f"| {cat} | {', '.join(cmds)} |")
    lines.append("")

    # Learnings 통계 섹션
    lines.append("## Learnings 통계")
    lines.append("")
    total = learnings_stats["total"]
    by_type = learnings_stats["by_type"]
    recent = learnings_stats["recent"]

    if total == 0:
        lines.append("learnings.jsonl 없음 또는 비어있음.")
    else:
        type_parts = []
        for t in ["pattern", "pitfall", "architecture", "preference", "decision"]:
            cnt = by_type.get(t, 0)
            if cnt:
                type_parts.append(f"{t}: {cnt}")
        other_cnt = sum(v for k, v in by_type.items()
                        if k not in {"pattern", "pitfall", "architecture", "preference", "decision"})
        if other_cnt:
            type_parts.append(f"other: {other_cnt}")

        lines.append(f"총 {total}건 — " + " / ".join(type_parts))
        lines.append("")
        lines.append("최근 5건:")
        for item in recent:
            lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 서브커맨드 핸들러
# ---------------------------------------------------------------------------

def cmd_check(args) -> int:
    """
    'check' 서브커맨드 핸들러 — 검사기 실행 후 결과 출력.

    Args:
        args: argparse Namespace (strict, only, json 필드 포함)

    Returns:
        int: exit code (--strict 시 BLOCK 존재하면 1, 그 외 0)
    """
    now = datetime.now(tz=timezone(timedelta(hours=9)))  # KST
    ts_display = now.strftime("%Y-%m-%d %H:%M")
    ts_iso = now.isoformat()

    # 실행할 검사기 결정
    only = getattr(args, "only", None)
    if only:
        # --only=LINT-FL,LINT-AC 형태 지원
        only_ids = [x.strip() for x in only.split(",")]
        checkers_to_run = {k: v for k, v in _CHECKERS.items() if k in only_ids}
        unknown = [x for x in only_ids if x not in _CHECKERS]
        if unknown:
            print(f"[lint] 알 수 없는 검사기 ID: {unknown}", file=sys.stderr)
            print(f"[lint] 사용 가능: {list(_CHECKERS.keys())}", file=sys.stderr)
    else:
        checkers_to_run = _CHECKERS

    # 검사기 실행
    all_results = {}
    for checker_id, (_, fn) in checkers_to_run.items():
        try:
            all_results[checker_id] = fn()
        except Exception as exc:  # noqa: BLE001
            # **게이트 검사기가 죽으면 BLOCK 이다.** 전에는 전부 INFO 로 강등했고
            # `--strict` 는 INFO 를 세지 않으므로, 검사기를 죽이는 입력 하나가 게이트를
            # 통째로 여는 통로였다 (실측: `freeze-manifest.json` 을 `[]` 로 바꾸면
            # AttributeError → INFO → exit 0). ADR-015 결정 6 의 "손상이면 전면 거부" 가
            # 그 모양의 손상에서 거짓이었다.
            #
            # hook-failure-tolerance 는 **훅**의 정책이다 — 훅은 작업을 막지 않는 것이
            # 목적이고, 게이트 검사기는 막는 것이 목적이다. 둘에 같은 관용을 적용하면
            # "조용히 통과" 가 되고, 그것이 이 리포가 가장 비싸게 배운 실패 형태다.
            label = BLOCK if checker_id in _GATE_CHECKERS else INFO
            all_results[checker_id] = [
                _issue(checker_id, label, checker_id,
                       f"검사기 실행 실패 — {type(exc).__name__}: {exc}")
            ]

    # 요약 계산
    summary = {BLOCK: 0, CONCERN: 0, INFO: 0, PASS: 0}
    for issues in all_results.values():
        for issue in issues:
            label = issue.get("label", INFO)
            if label in summary:
                summary[label] += 1

    # 캐시 저장
    _save_cache(ts_iso, all_results, summary)

    # 출력
    use_json = getattr(args, "json", False)
    if use_json:
        print(_format_json(ts_iso, all_results, summary))
    else:
        print(_format_human(ts_display, all_results, summary))

    # exit code
    strict = getattr(args, "strict", False)
    if strict and summary[BLOCK] > 0:
        return 1
    return 0


def cmd_regenerate_index(args) -> int:  # noqa: ARG001
    """
    'regenerate-index' 서브커맨드 핸들러 — docs/index.md 생성.

    Args:
        args: argparse Namespace (미사용)

    Returns:
        int: exit code (항상 0)
    """
    try:
        content = generate_index()
        _DOCS_INDEX.parent.mkdir(parents=True, exist_ok=True)

        # atomic write
        fd, tmp_path = tempfile.mkstemp(dir=_DOCS_INDEX.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.rename(tmp_path, _DOCS_INDEX)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # 통계 출력
        features = _load_features()
        known_ids = {f.get("id") for f in features if "id" in f}
        adrs = _load_adrs(known_feature_ids=known_ids)
        commands = _load_commands()
        learnings_stats = _load_learnings_stats()

        print(f"[lint] docs/index.md 생성 완료")
        print(f"[lint]   features: {len(features)}건")
        print(f"[lint]   ADRs: {len(adrs)}건")
        print(f"[lint]   commands: {len(commands)}건")
        print(f"[lint]   learnings: {learnings_stats['total']}건")
        print(f"[lint]   경로: {_DOCS_INDEX}")

    except Exception as exc:  # noqa: BLE001
        print(f"[lint] regenerate-index 실패 (무시): {exc}", file=sys.stderr)

    return 0


def cmd_report(args) -> int:  # noqa: ARG001
    """
    'report' 서브커맨드 핸들러 — 캐시된 마지막 실행 결과 표시.

    캐시 부재 시 친절한 안내 출력. 캐시 존재 시 check와 동일한 포맷으로 재출력.

    Args:
        args: argparse Namespace (미사용)

    Returns:
        int: exit code (항상 0)
    """
    if not _CACHE_FILE.exists():
        print("[lint] 캐시 파일이 없습니다.")
        print("[lint] 먼저 다음 명령을 실행하세요:")
        print("[lint]   python3 .claude/bin/lint.py check")
        print(f"[lint] 예상 캐시 경로: {_CACHE_FILE}")
        return 0

    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            cached = json.load(f)

        ts = cached.get("ts", "unknown")
        summary = cached.get("summary", {})
        results_list = cached.get("results", [])

        # checker_id별로 재구성
        all_results: dict = {}
        for issue in results_list:
            cid = issue.get("id", "UNKNOWN")
            if cid not in all_results:
                all_results[cid] = []
            all_results[cid].append(issue)

        # check와 동일한 포맷으로 출력
        # ts 포맷: ISO → 표시용
        try:
            dt = datetime.fromisoformat(ts)
            ts_display = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            ts_display = ts

        print(f"[lint] 캐시에서 재출력 (마지막 실행: {ts})")
        print(_format_human(ts_display, all_results, summary))

    except Exception as exc:  # noqa: BLE001
        print(f"[lint] 캐시 읽기 실패: {exc}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> int:
    """
    lint.py 메인 진입점.

    서브커맨드를 파싱하고 적절한 핸들러를 호출한다.
    최상위 try/except로 예기치 못한 예외도 stderr 로그 + exit 0 보장.

    Returns:
        int: exit code
    """
    parser = argparse.ArgumentParser(
        description="F009 — Lint helper for harness governance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # check
    check_parser = subparsers.add_parser("check", help="검사기 실행")
    check_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="BLOCK이 1건이라도 있으면 exit 1 (CI gate용)",
    )
    check_parser.add_argument(
        "--only",
        metavar="CHECKER_ID",
        default=None,
        help="특정 검사기만 실행 (예: LINT-FL, 콤마 구분 복수 지정 가능)",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="머신용 JSON 출력",
    )

    # regenerate-index
    subparsers.add_parser("regenerate-index", help="docs/index.md 갱신")

    # report
    subparsers.add_parser("report", help="캐시된 마지막 실행 결과 표시")

    args = parser.parse_args()

    if args.command == "check":
        return cmd_check(args)
    elif args.command == "regenerate-index":
        return cmd_regenerate_index(args)
    elif args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # hook-failure-tolerance: 예기치 못한 예외도 exit 0
        print(f"[lint] 예기치 못한 오류 (무시): {exc}", file=sys.stderr)
        sys.exit(0)
