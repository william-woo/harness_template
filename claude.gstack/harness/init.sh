#!/usr/bin/env bash
# init.sh — 개발 환경 시작 및 기본 동작 확인
# 에이전트가 세션 시작 시 실행하여 환경 상태를 점검한다
# 프로젝트에 맞게 수정하세요

set -eo pipefail

echo "🚀 개발 환경 초기화 중..."

# ── 1. 의존성 확인 ──────────────────────────────────
echo "📦 의존성 확인..."
if [ ! -d "node_modules" ]; then
  echo "  node_modules 없음, 설치 중..."
  npm install --silent
fi

# ── 2. 환경변수 확인 ────────────────────────────────
echo "🔑 환경변수 확인..."
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "  ⚠️  .env.example을 복사했습니다. 실제 값을 설정하세요."
  else
    echo "  ⚠️  .env 파일이 없습니다."
  fi
fi

# ── 3. 빌드 확인 ────────────────────────────────────
echo "🔨 빌드 확인..."
BUILD_OUTPUT=$(npm run build 2>&1) || {
  BUILD_EXIT=$?
  echo "$BUILD_OUTPUT" | tail -10
  echo "  ❌ 빌드 실패! 이전 세션의 코드를 확인하세요."
  echo "  힌트: git log --oneline -5"
  exit $BUILD_EXIT
}
echo "$BUILD_OUTPUT" | tail -3

# ── 4. 단위 테스트 실행 ─────────────────────────────
echo "🧪 단위 테스트 실행..."
TEST_OUTPUT=$(npm test 2>&1) || {
  TEST_EXIT=$?
  echo "$TEST_OUTPUT" | tail -15
  echo "  ❌ 테스트 실패! 회귀가 발생했습니다."
  echo "  힌트: git diff HEAD~1 로 변경사항 확인"
  exit $TEST_EXIT
}
echo "$TEST_OUTPUT" | tail -3

# ── 5. 개발 서버 시작 (백그라운드) ──────────────────
echo "🌐 개발 서버 시작..."
# TODO: 프로젝트에 맞게 아래 주석을 해제하고 수정하세요
# npm run dev &
# DEV_PID=$!
# sleep 3
#
# if curl -sf http://localhost:3000/health > /dev/null; then
#   echo "  ✅ 서버 정상 실행 중 (PID: $DEV_PID)"
# else
#   echo "  ❌ 서버 응답 없음 — 로그를 확인하세요"
#   kill $DEV_PID 2>/dev/null || true
#   exit 1
# fi

# ── 완료 ─────────────────────────────────────────────
echo ""
echo "✅ 환경 준비 완료!"
echo "   다음 단계: cat claude-progress.txt 로 이전 작업 파악"
echo ""
