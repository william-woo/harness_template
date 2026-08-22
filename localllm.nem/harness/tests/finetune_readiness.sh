#!/usr/bin/env bash
# finetune_readiness.sh — 파인튜닝 가능성을 원격 GPU 서버에서 점검한다 (읽기 전용).
#
# 왜 필요한가 (F031 / 측정 11 결과 14):
#   nemotron 의 판정 기록 실패는 형식·행동 문제이고, SFT 로 겨냥할 수 있는 유일한 표적이다.
#   다만 이 모델은 파인튜닝 난이도가 최상위 조합이다:
#     nemotron_h_moe — 하이브리드(Mamba-2 + Attention) × MoE(128 전문가 / 토큰당 6 활성)
#   따라서 "가능한가"를 추측하지 않고 **하드웨어·툴체인을 실제로 재고** 판정한다.
#
# 사용:
#   bash tests/finetune_readiness.sh                 # 로컬 점검
#   bash tests/finetune_readiness.sh <user>@<host>   # 원격 점검 (SSH 필요)
#
# 이 스크립트는 조회만 한다 — 설치·다운로드·학습을 실행하지 않는다.

set -u
TARGET="${1:-}"

run() {  # 로컬/원격 투명 실행
  if [ -n "$TARGET" ]; then
    timeout 25 ssh -o BatchMode=yes -o ConnectTimeout=8 "$TARGET" "$1" 2>&1
  else
    bash -c "$1" 2>&1
  fi
}

say() { printf '\n── %s\n' "$1"; }

echo "=== 파인튜닝 가능성 점검: ${TARGET:-로컬} ==="

say "1. GPU / VRAM  (가장 중요한 제약)"
run 'command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version,compute_cap --format=csv || echo "nvidia-smi 없음 — NVIDIA GPU 미탑재 또는 드라이버 미설치"'

say "2. CUDA 툴킷"
run 'command -v nvcc >/dev/null && nvcc --version | tail -2 || echo "nvcc 없음 (런타임만 있어도 학습은 가능하나 빌드가 필요한 커널은 막힌다)"'

say "3. 디스크 여유  (bf16 가중치 약 60GB + 체크포인트)"
run 'df -h /home /opt /var 2>/dev/null | awk "NR==1||/^\//{print}"'

say "4. Python / 학습 스택"
run 'python3 --version; python3 -c "import torch; print(f\"torch {torch.__version__} cuda={torch.cuda.is_available()} devices={torch.cuda.device_count()}\")" 2>/dev/null || echo "torch 미설치"'
run 'python3 -c "import transformers,peft; print(f\"transformers {transformers.__version__} / peft {peft.__version__}\")" 2>/dev/null || echo "transformers/peft 미설치 (모델카드 요구: transformers>=5.3.0)"'

say "5. 메모리 / CPU  (오프로딩 여지)"
run 'free -h | head -2; nproc | sed "s/^/cores: /"'

say "6. 판정 — 아래 기준으로 읽는다"
cat <<'EOF'
  VRAM 기준 (31.6B 하이브리드 MoE, LoRA/QLoRA 가정):
    < 24GB   → 불가. 추론 전용으로 유지
    24~40GB  → 매우 어렵다. 시퀀스 짧게 + 강한 오프로딩, 성공 보장 없음
    48~80GB  → QLoRA 현실적
    80GB+    → LoRA 여유

  툴체인 주의:
    · Q4 GGUF 로는 학습할 수 없다 — bf16 safetensors 를 따로 받아야 한다
      nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 (게이트 없음, NVIDIA Open Model License)
    · 하이브리드 Mamba + MoE 는 표준 PEFT 레시피가 그대로 듣지 않는다.
      NVIDIA 자체 스택은 Megatron-LM(사전학습) / NeMo RL·NeMo Gym(RL)
    · 학습 후 Ollama 로 되돌리려면 GGUF 재변환이 필요하고,
      nemotron_h_moe 변환 지원 여부를 먼저 확인해야 한다

  하네스 정책:
    학습 스택은 새 의존성 범주다. localllm 예외 계약은 OpenCode/Ollama 를
    *실행 환경*으로 허용한 것이므로, 파인튜닝 도입은 ADR 이 먼저 필요하다.
EOF
echo
echo "=== 점검 끝 (조회만 수행, 변경 없음) ==="
