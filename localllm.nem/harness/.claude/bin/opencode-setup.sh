#!/usr/bin/env bash
# opencode-setup.sh — localllm 변형 전용: OpenCode + 로컬 LLM(Ollama) 연결 설정
#
# localllm 변형은 Claude Code 가 아니라 OpenCode(오픈소스 agent framework) + 로컬
# LLM(Ollama)으로 하네스를 구동한다. 이 스크립트는 그 환경을 설치·설정한다.
#
# autonomous 규칙 #3-B: npm 전역 설치는 외부 fetch + 시스템 변경 → 사용자 승인 필요.
# 설치 실패/거부 시 graceful degrade (안내 후 exit 0).
#
# 설정값 (환경변수로 override 가능):
#   OLLAMA_HOST   기본 http://172.16.10.217:11434  (RTX 4500 Ollama 서버)
#   OLLAMA_MODEL  기본 nemotron-3-nano:30b (전 역할 — 단일 모델 변형)
#   OLLAMA_JUDGE_MODEL  기본 nemotron-3-nano:30b (판정도 같은 모델)
#   OLLAMA_CONTEXT  기본 32768  (전역 등재 시 limit.context)
#   OLLAMA_OUTPUT   기본 4096   (전역 등재 시 limit.output — 추론 예산, 아래 참조)
#
# ⚠️ nemotron 변형의 핵심 (측정 11 결과 10): nemotron 은 **추론 모델**이라 도구를 호출하기
# 전에 추론 토큰을 먼저 쓴다. 출력 예산이 그보다 작으면 추론 중간에 잘려 도구 호출이
# 아예 생성되지 않는다 (finish=length). 따라서 전역 등재 시 `limit` 을 반드시 함께 넣는다.
# `{"name": ...}` 만 등재하면 모델은 인식되지만 도구 호출이 무산된다.
#
# 참조: docs/poc/README.md, 학습 localllm-d2-poc-*, ADR-008 d-2 단계, ADR-021

set -u

OLLAMA_HOST="${OLLAMA_HOST:-http://172.16.10.217:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-nemotron-3-nano:30b}"
OLLAMA_JUDGE_MODEL="${OLLAMA_JUDGE_MODEL:-nemotron-3-nano:30b}"
OLLAMA_CONTEXT="${OLLAMA_CONTEXT:-32768}"
OLLAMA_OUTPUT="${OLLAMA_OUTPUT:-4096}"
OC_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
OC_CONFIG="$OC_CONFIG_DIR/opencode.jsonc"

echo "=== localllm — OpenCode + Ollama 환경 설정 ==="
echo "이 변형은 Claude Code 가 아니라 OpenCode + 로컬 LLM 으로 동작합니다."
echo "  Ollama 서버 : $OLLAMA_HOST"
echo "  기본 모델   : $OLLAMA_MODEL"
echo ""

# ── 1. 사전 점검 (read-only) ────────────────────────────────
echo "[1/4] 사전 점검"
if command -v node >/dev/null 2>&1; then
  echo "  node: $(node --version)"
else
  echo "  ⚠️ node 미설치 — OpenCode 설치 불가. https://nodejs.org 설치 후 재시도."
  echo "  graceful degrade: 환경 미충족 — exit 0"
  exit 0
fi

# Ollama 서버 연결 확인
if command -v curl >/dev/null 2>&1; then
  if curl -s --max-time 5 "$OLLAMA_HOST/api/version" >/dev/null 2>&1; then
    echo "  Ollama 서버: 연결 OK ($OLLAMA_HOST)"
  else
    echo "  ⚠️ Ollama 서버($OLLAMA_HOST) 연결 실패 — 서버 구동/네트워크 확인."
    echo "  설정은 계속 진행 (서버는 나중에 켜도 됨)."
  fi
fi

# ── 2. OpenCode 설치 ───────────────────────────────────────
echo ""
echo "[2/4] OpenCode 설치"
if command -v opencode >/dev/null 2>&1; then
  echo "  이미 설치됨: opencode $(opencode --version 2>&1 | head -1) — 스킵"
else
  echo "  설치 시도: npm install -g opencode-ai"
  echo "  ⚠️ autonomous 모드: 전역 설치는 사용자 승인을 요청합니다 (규칙 #3-B)."
  if command -v npm >/dev/null 2>&1; then
    npm install -g opencode-ai \
      && echo "  ✅ OpenCode 설치 성공" \
      || echo "  ⚠️ 설치 실패 — 수동: npm install -g opencode-ai"
  else
    echo "  ⚠️ npm 미설치 — OpenCode 스킵 (Node.js 설치 필요)"
  fi
fi

# ── 3. Ollama provider 설정 (opencode.jsonc) ───────────────
echo ""
# 숫자 검증 — `OLLAMA_OUTPUT=abc` 가 그대로 JSON 에 들어가면 OpenCode 가 설정 파일을
# 파싱하지 못해 **모든 실행이 거부**된다 (fresh 경로) / 병합 경로는 traceback.
for _var in OLLAMA_CONTEXT OLLAMA_OUTPUT; do
  eval "_val=\$$_var"
  case "$_val" in
    ''|*[!0-9]*) echo "  ⚠️ $_var 은 정수여야 합니다 (받은 값: '$_val') — 중단"; exit 0 ;;
  esac
done
echo "[3/4] OpenCode ↔ Ollama provider 설정"
mkdir -p "$OC_CONFIG_DIR"
if [ -f "$OC_CONFIG" ] && grep -q '"ollama"' "$OC_CONFIG" 2>/dev/null; then
  echo "  이미 ollama provider 설정됨: $OC_CONFIG — 필요한 모델 등재 여부 점검"
  # 중요 (측정 08): OpenCode 는 프로젝트 opencode.json 의 provider.models 를 모델 해석에
  # 반영하지 않는다. 역할별 모델(judge=32B)이 전역 설정에 없으면 --agent 실행 전체가
  # UnknownError 로 실패한다 → 누락 모델을 여기서 병합한다.
  OC_CONFIG="$OC_CONFIG" OLLAMA_MODEL="$OLLAMA_MODEL" OLLAMA_JUDGE_MODEL="$OLLAMA_JUDGE_MODEL" \
  OLLAMA_CONTEXT="$OLLAMA_CONTEXT" OLLAMA_OUTPUT="$OLLAMA_OUTPUT" \
  python3 - <<'PYMERGE'
import json, os, re, shutil
from pathlib import Path
p = Path(os.environ["OC_CONFIG"])
raw = p.read_text(encoding="utf-8")
# JSONC 관용: 행 시작 주석 + 행끝 `//` + trailing comma 를 벗긴다. 예전엔 행 시작
# 주석만 처리해, 흔한 JSONC 에 JSONDecodeError 가 나고도 "설정 완료" 를 찍었다.
stripped = re.sub(r"(^|\s)//[^\n]*", "", raw)
stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
cfg = json.loads(stripped)
models = cfg.setdefault("provider", {}).setdefault("ollama", {}).setdefault("models", {})
limit = {"context": int(os.environ["OLLAMA_CONTEXT"]), "output": int(os.environ["OLLAMA_OUTPUT"])}
added, fixed = [], []
for key in (os.environ["OLLAMA_MODEL"], os.environ["OLLAMA_JUDGE_MODEL"]):
    if not key:
        continue
    if key not in models:
        models[key] = {"name": key, "limit": dict(limit)}
        added.append(key)
        continue
    # `limit` 은 context·output 을 **모두** 요구한다. 하나만 있으면 OpenCode 가
    # `Configuration is invalid` 로 전 실행을 거부한다 — ADR-021 이 "배치 2개를
    # 폐기했다" 고 적은 바로 그 함정이다. 그런데 보정은 `limit` 키가 **통째로
    # 없을 때만** 돌아서, 반쪽 상태(`{"context": N}` 또는 `null`)는 그대로
    # "모두 등재됨" 으로 통과했다. 기존 값은 살리고 누락 필드만 채운다.
    cur = models[key].get("limit")
    have = cur if isinstance(cur, dict) else {}
    if not {"context", "output"} <= have.keys():
        merged = dict(limit)
        merged.update({k: v for k, v in have.items()
                       if k in ("context", "output") and isinstance(v, int) and v > 0})
        models[key]["limit"] = merged
        fixed.append(key)
if added or fixed:
    bak = p.with_suffix(p.suffix + ".bak-harness")
    if not bak.exists():
        shutil.copy2(p, bak)
    # 직접 덮어쓰면 중간 크래시에 전역 설정이 절단된다 — 원자적 교체.
    tmp = p.with_suffix(p.suffix + ".tmp-harness")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    if added:
        print(f"  ✅ 전역 설정에 모델 등재: {added} (limit={limit}, 백업: {bak.name})")
    if fixed:
        print(f"  ✅ limit 누락 보정: {fixed} → {limit}")
else:
    print("  ✅ 필요한 모델이 limit 과 함께 모두 등재됨")
PYMERGE
  if [ $? -ne 0 ]; then
    echo "  ⚠️ 전역 설정 병합 실패 — limit 보정이 적용되지 않았습니다."
    echo "     $OC_CONFIG 를 확인하십시오 (추론 모델은 limit 없이는 도구 호출이 0건입니다)."
  fi
else
  cat > "$OC_CONFIG" << EOFJSON
{
  "\$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local LLM)",
      "options": { "baseURL": "$OLLAMA_HOST/v1" },
      "models": {
        "$OLLAMA_MODEL": {
          "name": "$OLLAMA_MODEL (생성형 역할)",
          "limit": { "context": $OLLAMA_CONTEXT, "output": $OLLAMA_OUTPUT }
        },
        "$OLLAMA_JUDGE_MODEL": {
          "name": "$OLLAMA_JUDGE_MODEL (판정·judge 역할)",
          "limit": { "context": $OLLAMA_CONTEXT, "output": $OLLAMA_OUTPUT }
        }
      }
    }
  }
}
EOFJSON
  echo "  ✅ provider 설정 생성: $OC_CONFIG"
fi

# ── 4. 검증 ────────────────────────────────────────────────
echo ""
echo "[4/4] 검증"
if command -v opencode >/dev/null 2>&1; then
  if opencode models 2>/dev/null | grep -q "ollama/"; then
    echo "  ✅ ollama 모델 인식됨:"
    opencode models 2>/dev/null | grep "ollama/" | sed 's/^/      /'
  else
    echo "  ⚠️ ollama 모델 미인식 — opencode.jsonc / 서버 연결 확인"
  fi
fi

echo ""
echo "=== 설정 완료 ==="
echo "사용: opencode run --agent developer \"<요청>\"   # $OLLAMA_MODEL 자동"
echo "      opencode run --agent reviewer  \"<요청>\"   # $OLLAMA_JUDGE_MODEL 자동"
echo "역할별 모델 매핑: 프로젝트 opencode.json (ADR-017 결정 4 — 측정 05 근거)"
echo "모델 준비: ollama pull $OLLAMA_MODEL (서버 측 1회)"
echo "출력 예산: limit.output=$OLLAMA_OUTPUT — 추론 모델의 도구 호출 전 추론 지출을 감당한다 (ADR-021)."
echo "이 디렉토리(localllm.nem/harness)를 OpenCode 프로젝트로 열어 하네스 활용."
exit 0
