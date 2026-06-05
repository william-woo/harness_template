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
  LINT-MIRROR 미러링 diff (4변형)
  LINT-MR     변형 오버레이 정합 (7변형 — F011 신설, F012 확장: MR-6/MR-7, F013 추가: MR-8)

외부 의존성: 없음 (Python stdlib only)
hook-failure-tolerance: 최상위 try/except → 예기치 못한 예외도 stderr + exit 0
"""

import argparse
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

        # BLOCK: .py 파일 diff
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
                    checker, BLOCK, rel,
                    f".claude/ ↔ claude.gstack/ .py 파일 diff 존재 ({diff_summary}) — 미러링 누락 의심"
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
    """LINT-MR: 7 변형 미러 정합 점검 (F011 신설, F012 확장, F013 MR-8 추가).

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

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "LINT-MR", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# 검사기 레지스트리
# ---------------------------------------------------------------------------

_CHECKERS = {
    "LINT-FL": ("feature_list 정합성", check_fl),
    "LINT-STALE": ("오래된 in-progress", check_stale),
    "LINT-AC": ("acceptance_criteria 누락·모호", check_ac),
    "LINT-ADR": ("ADR ↔ feature 연결성", check_adr),
    "LINT-LEARN": ("learnings 모순", check_learn),
    "LINT-MIRROR": ("미러링 diff (4변형)", check_mirror),
    "LINT-MR": ("변형 오버레이 정합 (7변형 — F013 MR-8 추가)", check_mirror_regression),
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
            all_results[checker_id] = [
                _issue(checker_id, INFO, checker_id, f"검사기 실행 실패 — {exc}")
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
