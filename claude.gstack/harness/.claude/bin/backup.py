#!/usr/bin/env python3
"""
backup.py — F010 다운스트림 백업 동기화 헬퍼

Python stdlib + git CLI + rsync만 사용. 외부 의존성 없음.
host.json 의 backup 객체를 읽어 원격 백업 리포로 산출물 동기화.

서브커맨드:
  sync       현재 프로젝트의 하네스 산출물을 backup_repo/backup_branch 로 동기화 (세션 1)
  init       host.json 의 backup 필드 초기 설정 (세션 2)
  status     마지막 sync 정보 + 변경 미리보기 (세션 2)
  config     backup 필드 조회/수정 (세션 2)
  self       셀프 dry-run — 의존성 체크 (세션 2)

옵션 (전역):
  --strict   에러 발생 시 exit 1 (CI gate) — 기본 OFF (exit 0)
  --dry-run  실제 push 안 함, 미리보기만
  --message  sync 시 커밋 메시지 override
  --format   출력 형식: human|json (기본 human)

설계 원칙:
  - 실패해도 절대 호출자를 차단하지 않음 (hook-failure-tolerance, exit 0 유지)
  - 보안 BLOCK (.env 등 자격증명 노출) 만 예외적으로 exit 1
  - force-push 절대 금지 — ff-only merge + 재시도 0회
  - SSH URL 정식 지원, HTTPS URL 도 거부하지 않되 안내만 출력
  - 메타 하네스 환경 (src/harness_template/ 보유) 은 is_meta_harness() 분기로 추가 제외
  - ADR-005 결정 1~9 모두 준수
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── 경로 상수 ────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HOST_JSON = _PROJECT_ROOT / ".claude" / "host.json"
_STATE_DIR = _PROJECT_ROOT / ".claude" / "state"
_BACKUP_CACHE = _STATE_DIR / "backup-last.json"

# ─── 제외 목록 (ADR-005 결정 6) ───────────────────────────────────────────────

# 기본 제외 패턴 — 모든 다운스트림 + 메타 하네스에 공통 적용
_EXCLUDE_PATTERNS: list[str] = [
    # 사용자 코드 — 절대 백업 대상 아님
    "src/",
    # 빌드 산출물 — 재생성 가능
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    ".venv/",
    "venv/",
    "dist/",
    "build/",
    "target/",
    ".next/",
    "out/",
    # IDE / OS 환경별
    ".vscode/",
    ".idea/",
    ".DS_Store",
    "Thumbs.db",
    "*.swp",
    "*.swo",
    # 로그
    "*.log",
    "logs/",
    "npm-debug.log*",
    # 서브 git 보호 — 백업 리포의 .git 과 충돌 방지
    ".git/",
    # 세션 로컬 상태 (CLAUDE.md 상태 파일 표 일관)
    ".claude/state/freeze-dir.txt",
    ".claude/state/lint-last.json",
    ".claude/state/backup-last.json",
    # Binary state — gitignore 일관
    ".claude/state/qa-browser/screenshots/",
    ".claude/state/qa-browser/runs/",
]

# 보안 BLOCK 패턴 — 누락 시 exit 1 (결정 5 예외, 결정 6 보안)
_SECURITY_BLOCK_PATTERNS: list[str] = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "credentials.json",
    ".aws/credentials",
    ".aws/",
]

# 메타 하네스 전용 추가 제외 — is_meta_harness() == True 일 때만 적용
_META_HARNESS_EXTRA_EXCLUDES: list[str] = [
    "src/harness_template/",  # 별도 git repo — src/ 가 이미 제외이지만 명시
]


# ─── 메타 하네스 감지 (ADR-005 결정 6) ───────────────────────────────────────

def is_meta_harness() -> bool:
    """src/harness_template/claude.gstack/ 가 있으면 메타 하네스로 판단.

    다운스트림 프로젝트에는 src/harness_template/ 자체가 없으므로 False 반환.
    """
    try:
        return (_PROJECT_ROOT / "src" / "harness_template" / "claude.gstack").is_dir()
    except Exception:
        return False


def get_effective_excludes() -> list[str]:
    """메타 하네스 여부에 따라 최종 제외 목록을 반환한다."""
    excludes = list(_EXCLUDE_PATTERNS)
    if is_meta_harness():
        excludes.extend(_META_HARNESS_EXTRA_EXCLUDES)
    return excludes


# ─── host.json 로드 / backup 설정 (ADR-005 결정 1, 2) ────────────────────────

def load_host_json() -> dict:
    """host.json 전체를 읽어 반환한다.

    harness_version: 1 (F006 시점) 와 호환 — backup 필드가 없으면 빈 dict.
    """
    try:
        if not _HOST_JSON.exists():
            return {}
        return json.loads(_HOST_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[backup] host.json 읽기 실패: {e}", file=sys.stderr)
        return {}


def load_backup_config() -> dict | None:
    """host.json 의 backup 객체를 반환한다.

    Returns:
        backup 설정 dict (repo, branch 포함) 또는 None (미설정).
    """
    data = load_host_json()
    return data.get("backup") or None


def get_backup_repo(cfg: dict) -> str | None:
    """backup 설정에서 repo URL 을 반환한다."""
    return cfg.get("repo") or cfg.get("backup_repo")  # 양쪽 키 허용


def get_backup_branch(cfg: dict) -> str:
    """backup_branch 를 반환한다. 명시 설정 없으면 auto_derive_branch_name() 결과.

    추출 우선순위 (ADR-005 결정 2):
      1. host.json backup.branch 명시 설정
      2. git remote URL basename
      3. 프로젝트 디렉토리 basename
    """
    explicit = cfg.get("branch") or cfg.get("backup_branch")
    if explicit:
        return explicit
    return _auto_derive_branch_name()


def _auto_derive_branch_name() -> str:
    """git remote URL 의 repo basename 또는 디렉토리명으로 브랜치명을 자동 추출한다."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # SSH: git@github.com:user/repo.git → repo
            # HTTPS: https://github.com/user/repo.git → repo
            m = re.search(r"[:/]([^/:]+?)(?:\.git)?$", url)
            if m:
                return m.group(1)
    except Exception:
        pass
    # 디렉토리 basename fallback
    return _PROJECT_ROOT.name


# ─── 보안 검사 (ADR-005 결정 5/6) ────────────────────────────────────────────

def scan_security_blocks(root: Path) -> list[str]:
    """보안 BLOCK 패턴에 해당하는 파일 경로 목록을 반환한다.

    rsync 실행 전 사전 검사. 발견 시 백업 중단 + exit 1.
    """
    blocked: list[str] = []
    try:
        for pattern in _SECURITY_BLOCK_PATTERNS:
            # 단순 glob 패턴 지원 (재귀)
            pat = pattern.rstrip("/")
            if "*" in pat:
                # glob 패턴
                suffix = pat.lstrip("*.")
                for p in root.rglob(f"*.{suffix}"):
                    rel = str(p.relative_to(root))
                    # .git/ 하위 제외
                    if ".git/" not in rel and not rel.startswith(".git"):
                        blocked.append(rel)
            else:
                # 정확한 이름 또는 디렉토리
                for p in root.rglob(pat.lstrip("./").replace("/", "")):
                    rel = str(p.relative_to(root))
                    if ".git/" not in rel and not rel.startswith(".git"):
                        blocked.append(rel)
    except Exception:
        pass
    return blocked


# ─── URL 인증 모드 감지 (ADR-005 결정 4) ─────────────────────────────────────

def detect_auth_mode(repo_url: str) -> str:
    """URL 형식으로 인증 모드를 감지한다."""
    if repo_url.startswith("git@") or repo_url.startswith("ssh://"):
        return "ssh"
    elif repo_url.startswith("https://"):
        return "https"
    return "unknown"


# ─── 캐시 저장 (ADR-005 결정 7 — status 서브커맨드용) ────────────────────────

def save_cache(
    repo: str,
    branch: str,
    status: str,
    commit: str = "",
) -> None:
    """마지막 sync 결과를 .claude/state/backup-last.json 에 원자적으로 저장한다."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        cache = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "repo": repo,
            "branch": branch,
            "status": status,
            "commit": commit,
        }
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(_STATE_DIR),
            prefix=".backup-cache-",
            suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, _BACKUP_CACHE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
    except Exception:
        pass  # 캐시 저장 실패는 무시 (hook-failure-tolerance)


def update_host_json_last_sync(commit_sha: str) -> None:
    """host.json 의 backup.last_sync + backup.last_sync_commit 를 갱신한다."""
    try:
        data = load_host_json()
        if "backup" not in data or not isinstance(data["backup"], dict):
            return
        now_str = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        data["backup"]["last_sync"] = now_str
        data["backup"]["last_sync_commit"] = commit_sha
        # harness_version 2 로 업그레이드
        data["harness_version"] = 2
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(_HOST_JSON.parent),
            prefix=".host-json-",
            suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_path, _HOST_JSON)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    except Exception as e:
        print(f"[backup] host.json 갱신 실패 (무시): {e}", file=sys.stderr)


# ─── 커밋 메시지 생성 ─────────────────────────────────────────────────────────

def build_commit_message(override: str = "") -> str:
    """sync 커밋 메시지를 자동 생성한다. override 가 있으면 그대로 사용."""
    if override:
        return override
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    project_name = _PROJECT_ROOT.name
    feature_summary = ""
    try:
        fl_path = _PROJECT_ROOT / "feature_list.json"
        if fl_path.exists():
            fl = json.loads(fl_path.read_text(encoding="utf-8"))
            done = sum(1 for f in fl if f.get("passes"))
            total = len(fl)
            feature_summary = f" — {done}/{total} done"
    except Exception:
        pass
    return (
        f"backup({project_name}): 자동 동기화 {ts}{feature_summary}\n"
        "\n"
        "F010 /project:backup-sync — 하네스 엔지니어링 산출물 백업.\n"
        "src/, node_modules, secrets, build artifacts 제외.\n"
        "\n"
        "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n"
    )


# ─── sync 서브커맨드 (ADR-005 결정 7, Step 1.3~1.5) ─────────────────────────

def cmd_sync(args) -> int:
    """현재 프로젝트의 하네스 산출물을 backup_repo/backup_branch 로 동기화한다.

    동작 순서:
      1. host.json 의 backup 객체 로드 및 검증
      2. 보안 BLOCK 패턴 사전 검사
      3. 임시 디렉토리에 백업 리포 clone
      4. backup_branch checkout (없으면 orphan branch 신규 생성)
      5. rsync — 제외 목록 적용
      6. git add / commit / push (ff-only)
      7. host.json 의 last_sync + last_sync_commit 갱신
    """
    try:
        # 1. backup 설정 로드
        cfg = load_backup_config()
        if not cfg:
            print("[backup] backup 설정이 없습니다.", file=sys.stderr)
            print(
                "[backup] 먼저 host.json 에 backup 객체를 추가하거나 "
                "`python3 .claude/bin/backup.py init` 을 실행하세요 (세션 2 예정).",
                file=sys.stderr,
            )
            print(
                "[backup] 직접 host.json 편집 예:\n"
                '  "backup": {\n'
                '    "repo": "git@github.com:USER/REPO.git",\n'
                '    "branch": "PROJECT-SLUG"\n'
                "  }",
                file=sys.stderr,
            )
            return 0

        repo_url = get_backup_repo(cfg)
        if not repo_url:
            print("[backup] backup.repo 가 설정되지 않았습니다.", file=sys.stderr)
            print(
                "[backup] host.json 의 backup.repo 에 SSH URL 을 추가하세요:\n"
                '  "repo": "git@github.com:USER/REPO.git"',
                file=sys.stderr,
            )
            return 0

        # 2. URL 인증 모드 확인 (ADR-005 결정 4)
        auth_mode = detect_auth_mode(repo_url)
        if auth_mode == "https":
            print(f"[backup] HTTPS URL 감지: {repo_url}", file=sys.stderr)
            print("[backup] SSH URL 권장: git@github.com:user/repo.git", file=sys.stderr)
            print(
                "[backup] HTTPS 사용 시 인증 방법:\n"
                "  1) ~/.netrc 파일에 credential 등록\n"
                "  2) GH_TOKEN 환경변수 (또는 git credential helper)\n"
                "  3) 자동 모드에서 자격증명 노출에 주의하세요.",
                file=sys.stderr,
            )
            # 진행은 허용 (안내만 — 결정 4)
        elif auth_mode == "unknown":
            print(f"[backup] 알 수 없는 URL 형식: {repo_url}", file=sys.stderr)
            print("[backup] SSH 형식 권장: git@github.com:user/repo.git", file=sys.stderr)

        backup_branch = get_backup_branch(cfg)
        if not backup_branch:
            print("[backup] backup_branch 추출 실패.", file=sys.stderr)
            print(
                "[backup] host.json 의 backup.branch 에 브랜치명을 명시하거나 "
                "git remote 를 설정하세요.",
                file=sys.stderr,
            )
            return 0

        # 3. 보안 BLOCK 검사 (ADR-005 결정 5/6 — 보안만 exit 1)
        if not getattr(args, "dry_run", False):
            blocked = scan_security_blocks(_PROJECT_ROOT)
            if blocked:
                print(
                    "[backup] BLOCK — 자격증명 파일이 백업 대상에 포함되었습니다.",
                    file=sys.stderr,
                )
                for b in blocked[:10]:
                    print(f"  ❌ {b}", file=sys.stderr)
                print(
                    "[backup] 동작: 백업 중단 (자격증명 노출 위험).\n"
                    "[backup] 해결: 해당 파일을 .gitignore 에 추가하거나 다른 위치로 이동하세요.",
                    file=sys.stderr,
                )
                return 1  # 보안 예외 — exit 1

        print(f"[backup] 시작 — repo: {repo_url}, branch: {backup_branch}")
        if is_meta_harness():
            print("[backup] 메타 하네스 감지 — src/harness_template/ 추가 제외")

        # 4. 임시 디렉토리에 clone
        with tempfile.TemporaryDirectory(prefix="backup-sync-") as tmp_str:
            clone_dir = Path(tmp_str) / "backup-clone"

            print(f"[backup] clone 중: {repo_url}")
            r = subprocess.run(
                ["git", "clone", "--quiet", repo_url, str(clone_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                print(f"[backup] clone 실패:", file=sys.stderr)
                print(f"  {r.stderr.strip()}", file=sys.stderr)
                if auth_mode == "ssh":
                    print(
                        "[backup] SSH 인증 확인:\n"
                        "  1) ssh-agent 실행 중인지: ssh-add -l\n"
                        "  2) SSH 키 등록 확인: ssh -T git@github.com\n"
                        "  3) 리포 접근 권한 확인: GitHub Settings → SSH keys",
                        file=sys.stderr,
                    )
                save_cache(repo_url, backup_branch, status="clone-failed")
                return 0  # hook-failure-tolerance

            # 5. 브랜치 checkout (없으면 orphan branch)
            r = subprocess.run(
                ["git", "checkout", backup_branch],
                cwd=clone_dir,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                print(f"[backup] 브랜치 '{backup_branch}' 미존재 — orphan branch 신규 생성")
                r = subprocess.run(
                    ["git", "checkout", "--orphan", backup_branch],
                    cwd=clone_dir,
                    capture_output=True,
                    text=True,
                )
                if r.returncode != 0:
                    print(
                        f"[backup] orphan branch 생성 실패: {r.stderr.strip()}",
                        file=sys.stderr,
                    )
                    save_cache(repo_url, backup_branch, status="branch-failed")
                    return 0
                # orphan branch 는 기존 파일이 staged — 모두 제거
                subprocess.run(
                    ["git", "rm", "-rf", "."],
                    cwd=clone_dir,
                    capture_output=True,
                )

            # 6. rsync — 제외 목록 적용 (ADR-005 결정 6)
            excludes = get_effective_excludes()
            rsync_args = ["rsync", "-a", "--delete"]
            for pat in excludes:
                rsync_args.extend(["--exclude", pat])
            rsync_args.extend([
                str(_PROJECT_ROOT) + "/",
                str(clone_dir) + "/",
            ])

            if getattr(args, "dry_run", False):
                # dry-run: rsync --dry-run 으로 변경 파일 미리보기
                dry_rsync = ["rsync", "-a", "--delete", "--dry-run", "--itemize-changes"]
                for pat in excludes:
                    dry_rsync.extend(["--exclude", pat])
                dry_rsync.extend([
                    str(_PROJECT_ROOT) + "/",
                    str(clone_dir) + "/",
                ])
                r_dry = subprocess.run(dry_rsync, capture_output=True, text=True, timeout=60)
                print("[backup] --dry-run 미리보기:")
                print(r_dry.stdout[:2000] or "  (변경 없음)")
                print("[backup] dry-run 완료 — 실제 push 는 수행하지 않습니다.")
                return 0

            r = subprocess.run(rsync_args, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                print(f"[backup] rsync 실패: {r.stderr.strip()}", file=sys.stderr)
                save_cache(repo_url, backup_branch, status="rsync-failed")
                return 0

            # qa-browser .gitkeep 디렉토리 보존
            for subdir in [
                ".claude/state/qa-browser/screenshots",
                ".claude/state/qa-browser/runs",
            ]:
                target_dir = clone_dir / subdir
                target_dir.mkdir(parents=True, exist_ok=True)
                gitkeep = target_dir / ".gitkeep"
                if not gitkeep.exists():
                    gitkeep.touch()

            # 7. git add + commit
            subprocess.run(["git", "add", "-A"], cwd=clone_dir, capture_output=True)

            # 변경 없으면 일찍 종료
            r = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=clone_dir,
                capture_output=True,
            )
            if r.returncode == 0:
                print("[backup] 변경 사항 없음 — sync 스킵")
                save_cache(repo_url, backup_branch, status="no-changes")
                return 0

            # 변경 통계 출력
            r_stat = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                cwd=clone_dir,
                capture_output=True,
                text=True,
            )
            if r_stat.stdout:
                print(r_stat.stdout.rstrip())

            commit_msg = build_commit_message(getattr(args, "message", "") or "")
            r = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=clone_dir,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                print(f"[backup] commit 실패: {r.stderr.strip()}", file=sys.stderr)
                save_cache(repo_url, backup_branch, status="commit-failed")
                return 0

            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=clone_dir,
                capture_output=True,
                text=True,
            ).stdout.strip()[:7]

            # 8. push (ff-only — force push 절대 없음, ADR-005 결정 5)
            print(f"[backup] push origin {backup_branch} ...")
            r = subprocess.run(
                ["git", "push", "origin", backup_branch],
                cwd=clone_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                stderr_msg = r.stderr.strip()
                print(f"[backup] push 실패:", file=sys.stderr)
                print(f"  {stderr_msg}", file=sys.stderr)
                if "non-fast-forward" in stderr_msg or "rejected" in stderr_msg:
                    print(
                        "[backup] 원격 브랜치가 앞서 있습니다 (ff-only 정책).\n"
                        "[backup] force push 는 절대 수행하지 않습니다 (ADR-005 결정 5).\n"
                        "[backup] 수동 확인 후 재시도하거나 백업 리포에서 직접 해결하세요.",
                        file=sys.stderr,
                    )
                save_cache(repo_url, backup_branch, status="push-failed", commit=commit_sha)
                strict = getattr(args, "strict", False)
                return 1 if strict else 0

            # 9. 성공 처리
            print(f"[backup] PASS — {commit_sha} → origin/{backup_branch}")
            save_cache(repo_url, backup_branch, status="success", commit=commit_sha)
            update_host_json_last_sync(commit_sha)
            return 0

    except Exception as e:
        print(f"[backup] 예기치 못한 오류: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0  # hook-failure-tolerance


# ─── 미구현 서브커맨드 (세션 2 예정) ─────────────────────────────────────────

def cmd_init(args) -> int:
    """host.json 의 backup 필드 초기 설정. (세션 2 구현 예정)"""
    print("[backup] `init` 서브커맨드는 세션 2 에서 구현됩니다.")
    print("[backup] 지금은 host.json 을 직접 편집하세요:")
    print(
        '  "backup": {\n'
        '    "repo": "git@github.com:USER/REPO.git",\n'
        '    "branch": "PROJECT-SLUG"\n'
        "  }"
    )
    return 0


def cmd_status(args) -> int:
    """마지막 sync 정보 + 변경 미리보기. (세션 2 구현 예정)"""
    print("[backup] `status` 서브커맨드는 세션 2 에서 구현됩니다.")
    if _BACKUP_CACHE.exists():
        try:
            cache = json.loads(_BACKUP_CACHE.read_text(encoding="utf-8"))
            print(f"[backup] 마지막 sync: {cache.get('ts', '없음')}")
            print(f"[backup] 상태: {cache.get('status', '?')}")
            print(f"[backup] commit: {cache.get('commit', '?')}")
            print(f"[backup] branch: {cache.get('branch', '?')}")
        except Exception:
            print("[backup] 캐시 파일을 읽을 수 없습니다.")
    else:
        print("[backup] 아직 sync 이력이 없습니다.")
    return 0


def cmd_config(args) -> int:
    """backup 필드 조회/수정. (세션 2 구현 예정)"""
    print("[backup] `config` 서브커맨드는 세션 2 에서 구현됩니다.")
    cfg = load_backup_config()
    if cfg:
        print("[backup] 현재 backup 설정:")
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    else:
        print("[backup] backup 설정이 없습니다. `init` 을 먼저 실행하세요 (세션 2 예정).")
    return 0


def cmd_self(args) -> int:
    """셀프 dry-run — 의존성 체크. (세션 2 구현 예정)"""
    print("[backup] `self` 서브커맨드는 세션 2 에서 구현됩니다.")
    print("[backup] 기본 의존성 확인:")
    # git 존재 확인
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        print(f"  git: {'OK — ' + r.stdout.strip() if r.returncode == 0 else 'MISSING'}")
    except Exception:
        print("  git: ERROR")
    # rsync 존재 확인
    try:
        r = subprocess.run(["rsync", "--version"], capture_output=True, text=True, timeout=5)
        first_line = r.stdout.splitlines()[0] if r.stdout else "?"
        print(f"  rsync: {'OK — ' + first_line if r.returncode == 0 else 'MISSING'}")
    except Exception:
        print("  rsync: ERROR")
    # host.json 확인
    cfg = load_backup_config()
    print(f"  backup config: {'설정됨' if cfg else '미설정 (init 필요)'}")
    print(f"  meta_harness: {is_meta_harness()}")
    return 0


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    """backup.py 진입점 — argparse 서브커맨드 라우팅."""
    parser = argparse.ArgumentParser(
        prog="backup.py",
        description="F010 — 하네스 다운스트림 백업 동기화 헬퍼",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="에러 발생 시 exit 1 (CI gate). 기본 OFF.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="실제 push 없이 미리보기만 (sync 서브커맨드)",
    )
    parser.add_argument(
        "--message",
        default="",
        help="sync 시 커밋 메시지 override",
    )
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help="출력 형식 (기본 human)",
    )

    sub = parser.add_subparsers(dest="cmd", metavar="<서브커맨드>")
    sub.add_parser("sync", help="백업 리포에 현재 산출물 동기화 (세션 1 구현)")
    sub.add_parser("init", help="backup 설정 초기화 (세션 2 예정)")
    sub.add_parser("status", help="마지막 sync 정보 표시 (세션 2 예정)")
    sub.add_parser("config", help="backup 설정 조회/수정 (세션 2 예정)")
    sub.add_parser("self", help="셀프 dry-run 의존성 체크 (세션 2 예정)")

    args = parser.parse_args()

    try:
        if args.cmd == "sync":
            return cmd_sync(args)
        elif args.cmd == "init":
            return cmd_init(args)
        elif args.cmd == "status":
            return cmd_status(args)
        elif args.cmd == "config":
            return cmd_config(args)
        elif args.cmd == "self":
            return cmd_self(args)
        else:
            parser.print_help()
            print()
            print("[backup] 사용법: python3 .claude/bin/backup.py <sync|init|status|config|self>")
            print("[backup] 세션 1: sync 구현 완료. init/status/config/self 는 세션 2 예정.")
            return 0
    except Exception as e:
        print(f"[backup] 최상위 예외: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0  # hook-failure-tolerance


if __name__ == "__main__":
    sys.exit(main())
