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
#   OLLAMA_MODEL  기본 qwen2.5:14b-instruct-q8_0 (생성형 역할)
#   OLLAMA_JUDGE_MODEL  기본 qwen2.5:32b-instruct-q4_K_M (판정 역할 — 측정 05)
#   OLLAMA_CONTEXT  기본 32768  (전역 등재 시 limit.context)
#   OLLAMA_OUTPUT   기본 4096   (전역 등재 시 limit.output — 추론 예산, 아래 참조)
#
# **추론 예산** (ADR-021): 추론 모델(`thinking` 선언 — gemma4·nemotron·muse-glimmer 등)은
# 도구를 호출하기 **전에** 추론 토큰을 쓴다. 전역 설정에 `limit` 이 없으면 추론 중간에서
# 잘려 도구 호출이 **0건**이 된다 (`finish=length`). 그래서 등재할 때 `limit` 을 함께 넣고,
# 이미 `limit` 없이/반쪽으로 등재된 항목도 보정한다. qwen 만 쓸 때는 영향이 없다.
#
# **서버 컨텍스트 창** (측정 12, 2026-11-04): `limit` 만으로는 부족하다. `limit.context` 는
# OpenCode 내부 계산용이고 **와이어에 나가지 않는다** — 실제로 전달되는 건 `limit.output`
# → `max_tokens` 뿐이다. 창 크기는 **Ollama 서버가** 정하고, 기본값은 4096 이다.
# OpenCode 의 도구 프리앰블은 혼자 ~12.7k 토큰이라, 4096 창에서는 프롬프트가 잘려
# `prompt_tokens=4095 / completion_tokens=1 / finish=length` 로 **도구 호출이 0건**이 된다.
# 증상이 ADR-021 과 똑같아서 예산 문제로 오진하기 쉽다. 그래서 아래 [4/5] 가 서버 창을
# 직접 재고, 모자라면 `설정 완료` 를 찍지 않는다. 추론 모델만의 문제가 아니다 —
# qwen2.5:14b 도 4096 창에서는 도구 인자 스키마를 어겼고(`path` vs `filePath`),
# 창을 키우자 바로 지켜졌다.
#
# 참조: docs/poc/README.md, 학습 localllm-d2-poc-*, ADR-008 d-2 단계

set -u

OLLAMA_HOST="${OLLAMA_HOST:-http://172.16.10.217:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:14b-instruct-q8_0}"
OLLAMA_JUDGE_MODEL="${OLLAMA_JUDGE_MODEL:-qwen2.5:32b-instruct-q4_K_M}"
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
echo "[1/5] 사전 점검"
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
echo "[2/5] OpenCode 설치"
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
echo "[3/5] OpenCode ↔ Ollama provider 설정"
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

# ── 4. 서버 컨텍스트 창 점검 ───────────────────────────────
echo ""
echo "[4/5] Ollama 서버 컨텍스트 창 점검"
# 0=충분 / 1=부족 / 2=확인 불가. 셋을 구분하는 이유는 아래 배너에 있다 — 확인하지
# 못한 것을 "완료" 로 적으면, 그 배너는 서버가 꺼져 있을 때도 통과한다.
CTX_STATE=0
OLLAMA_HOST="$OLLAMA_HOST" OLLAMA_MODEL="$OLLAMA_MODEL" OLLAMA_JUDGE_MODEL="$OLLAMA_JUDGE_MODEL" \
OLLAMA_CONTEXT="$OLLAMA_CONTEXT" python3 - <<'PYCTX' || CTX_STATE=$?
"""서버가 실제로 내주는 컨텍스트 창을 재고, 모자라면 0 이 아닌 코드로 끝낸다.

`limit.context` 는 와이어에 나가지 않으므로 설정만 보고는 알 수 없다. 창을 정하는 건
서버이고, 읽는 곳은 두 군데다 — 모델에 `num_ctx` 가 박혀 있으면 `/api/show` 가 알려주고,
없으면 서버 기본값을 따르므로 한 번 적재해 `/api/ps` 의 `context_length` 를 본다.
"""
import json
import os
import re
import urllib.error
import urllib.request

HOST = os.environ["OLLAMA_HOST"].rstrip("/")
NEED = int(os.environ["OLLAMA_CONTEXT"])


def api(path, payload=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def declared_num_ctx(show):
    """모델에 박힌 `num_ctx` (Modelfile PARAMETER). 없으면 None — 서버 기본값을 따른다."""
    m = re.search(r"^num_ctx\s+(\d+)", show.get("parameters") or "", re.M)
    return int(m.group(1)) if m else None


def loaded_context(model):
    """적재된 모델의 실제 창. 적재돼 있지 않으면 1 토큰만 생성해 적재한다."""
    for attempt in (0, 1):
        for m in api("/api/ps", timeout=30).get("models", []):
            if m.get("name") == model and m.get("context_length"):
                return int(m["context_length"])
        if attempt == 0:
            print(f"      ({model} 적재 중 — 창 크기 측정)")
            api("/api/generate", {"model": model, "prompt": "hi", "stream": False,
                                  "options": {"num_predict": 1}})
    return None


short, unknown = [], []
for model in dict.fromkeys(filter(None, (os.environ["OLLAMA_MODEL"],
                                         os.environ["OLLAMA_JUDGE_MODEL"]))):
    try:
        show = api("/api/show", {"model": model}, timeout=60)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  ⚠️ {model}: 조회 실패 ({exc}) — 창 크기를 확인하지 못했습니다")
        unknown.append(model)
        continue
    caps = show.get("capabilities") or []
    ctx = declared_num_ctx(show)
    origin = "모델 num_ctx"
    if ctx is None:
        try:
            ctx = loaded_context(model)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"  ⚠️ {model}: 측정 실패 ({exc})")
            unknown.append(model)
            continue
        origin = "서버 기본값"
    if ctx is None:
        print(f"  ⚠️ {model}: 창 크기를 읽지 못했습니다")
        unknown.append(model)
        continue
    mark = "✅" if ctx >= NEED else "❌"
    note = " (추론 모델)" if "thinking" in caps else ""
    print(f"  {mark} {model}{note}: 컨텍스트 {ctx} ({origin}, 필요 {NEED})")
    if ctx < NEED:
        short.append((model, ctx))

if short:
    print("")
    print("  도구 프리앰블만으로 ~12.7k 토큰이라, 이 창에서는 프롬프트가 잘려")
    print("  도구 호출이 0건이 됩니다 (finish=length). 서버에서 창을 키우십시오:")
    for model, _ in short:
        tag = f"{model.split(':')[0]}:ctx{NEED // 1024}k"
        print(f"    curl {HOST}/api/create -d '{json.dumps({'model': tag, 'from': model, 'parameters': {'num_ctx': NEED}, 'stream': False})}'")
    print("  (기존 태그는 그대로 두고 파생 태그를 만듭니다 — 가중치를 공유하므로")
    print("   디스크 추가 사용은 없고, 다른 측정의 대조군도 바뀌지 않습니다.)")
    raise SystemExit(1)
if unknown:
    raise SystemExit(2)
PYCTX

# ── 5. 검증 ────────────────────────────────────────────────
echo ""
echo "[5/5] 검증"
if command -v opencode >/dev/null 2>&1; then
  if opencode models 2>/dev/null | grep -q "ollama/"; then
    echo "  ✅ ollama 모델 인식됨:"
    opencode models 2>/dev/null | grep "ollama/" | sed 's/^/      /'
  else
    echo "  ⚠️ ollama 모델 미인식 — opencode.jsonc / 서버 연결 확인"
  fi
fi

echo ""
# 창이 모자라면 설정 파일은 멀쩡해도 하네스는 **동작하지 않는다**. 그 상태에서
# "설정 완료" 를 찍으면, 다음 사람은 도구 호출 0건의 원인을 모델 탓으로 돌린다.
# 확인하지 **못한** 경우도 완료로 적지 않는다 — 서버가 꺼져 있을 때 통과하는 점검은
# 점검이 아니다.
if [ "$CTX_STATE" -eq 1 ]; then
  echo "=== 설정 미완료 — 서버 컨텍스트 부족 ==="
  echo "위 [4/5] 의 안내대로 서버 창을 키운 뒤 OLLAMA_MODEL 을 파생 태그로 지정해 재실행하십시오."
  exit 0
elif [ "$CTX_STATE" -ne 0 ]; then
  echo "=== 설정 완료 (서버 컨텍스트 미확인) ==="
  echo "서버에 닿지 못해 창 크기를 재지 못했습니다. 서버를 켠 뒤 이 스크립트를 다시 실행하십시오 —"
  echo "창이 4096 이면 설정이 멀쩡해도 도구 호출은 0건입니다."
  exit 0
fi
echo "=== 설정 완료 ==="
echo "사용: opencode run --agent developer \"<요청>\"   # 생성형 — $OLLAMA_MODEL 자동"
echo "      opencode run --agent reviewer  \"<요청>\"   # 판정  — $OLLAMA_JUDGE_MODEL 자동"
echo "역할별 모델 매핑: 프로젝트 opencode.json (ADR-017 결정 4 — 측정 05 근거)"
echo "판정(judge) 역할은 32B 권장 — ollama pull $OLLAMA_JUDGE_MODEL (서버 측 1회)"
echo "추론 예산: limit.context=$OLLAMA_CONTEXT / limit.output=$OLLAMA_OUTPUT — "\
     "추론 모델(gemma4·nemotron·glimmer)은 이것 없이는 도구 호출이 0건이다 (ADR-021)."
echo "이 디렉토리(localllm/harness)를 OpenCode 프로젝트로 열어 하네스 활용."
exit 0
