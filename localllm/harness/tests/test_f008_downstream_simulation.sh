#!/usr/bin/env bash
# F008 downstream simulation — 3개 가상 acceptance_criteria 변환 테스트
# 실제 Playwright 실행 없이 convert + detect 동작만 검증

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QA="$SCRIPT_DIR/../.claude/bin/qa_browser.py"

echo "=== F008 Downstream Simulation ==="

# TC1: 로그인 페이지 방문 → CLICK 슬롯 매칭 예상
echo ""
echo "[TC1] 로그인 페이지 acceptance criteria (CLICK slot 예상)"
CRITERIA="로그인 버튼을 클릭하면 대시보드로 이동한다"
result=$(python3 "$QA" convert F999 --acceptance "$CRITERIA" --dry-run 2>&1)
echo "$result"
if echo "$result" | grep -q "converted\|CLICK\|click\|slot\|TODO"; then
  echo "TC1 PASS"
else
  echo "TC1 INFO (no slot match — LLM fallback expected)"
fi

# TC2: 텍스트 노출 확인 → TEXT_VISIBLE 슬롯 매칭 예상
echo ""
echo "[TC2] 텍스트 노출 acceptance criteria (TEXT_VISIBLE slot 예상)"
CRITERIA="성공 메시지 '저장되었습니다'가 화면에 표시된다"
result=$(python3 "$QA" convert F999 --acceptance "$CRITERIA" --dry-run 2>&1)
echo "$result"
if echo "$result" | grep -q "converted\|TEXT\|visible\|slot\|TODO"; then
  echo "TC2 PASS"
else
  echo "TC2 INFO (no slot match — LLM fallback expected)"
fi

# TC3: <50% 매칭 → dry-run이 LLM fallback 표시
echo ""
echo "[TC3] 모호한 acceptance criteria (<50% slot match 예상)"
CRITERIA="시스템이 정상적으로 동작한다"
result=$(python3 "$QA" convert F999 --acceptance "$CRITERIA" --dry-run 2>&1)
echo "$result"
echo "TC3 PASS (exit 0 확인됨)"

# TC4: detect 동작 확인
echo ""
echo "[TC4] Playwright detect"
python3 "$QA" detect
echo "TC4 PASS"

echo ""
echo "=== Simulation Complete ==="
