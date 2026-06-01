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
# 단, *.example / *.template / *.sample 접미사는 화이트리스트 (ADR-005 결정 6 보강)
_SECURITY_BLOCK_PATTERNS: list[str] = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "credentials.json",
    ".aws/credentials",
    ".aws/",
]

# 보안 BLOCK 화이트리스트 접미사 — 자격증명이 아닌 양식 파일 (ADR-005 결정 6 보강)
_SECURITY_WHITELIST_SUFFIXES: tuple[str, ...] = (
    ".example",
    ".template",
    ".sample",
)

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


def save_host_json(data: dict) -> bool:
    """host.json 을 원자적으로 저장한다.

    Args:
        data: 저장할 host.json 전체 딕셔너리

    Returns:
        True: 저장 성공, False: 저장 실패
    """
    try:
        _HOST_JSON.parent.mkdir(parents=True, exist_ok=True)
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
            return True
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
    except Exception as e:
        print(f"[backup] host.json 저장 실패: {e}", file=sys.stderr)
        return False


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


# ─── harness_version 마이그레이션 (ADR-005 결정 1) ───────────────────────────

def migrate_harness_version(data: dict) -> tuple[dict, bool]:
    """host.json 의 harness_version 을 1 → 2 로 마이그레이션한다.

    harness_version 이 명시되지 않은 경우 1 로 가정하여 처리한다.

    Args:
        data: host.json 전체 딕셔너리

    Returns:
        (갱신된 data, 마이그레이션 발생 여부)
    """
    current_version = data.get("harness_version", 1)
    if current_version < 2:
        data["harness_version"] = 2
        return data, True
    return data, False


# ─── 보안 검사 (ADR-005 결정 5/6) ────────────────────────────────────────────

def _is_security_whitelisted(path: str) -> bool:
    """보안 화이트리스트 접미사(.example/.template/.sample)인지 확인한다.

    ADR-005 결정 6 보강 — 이 접미사 파일은 자격증명이 아닌 양식 파일로 간주하여
    BLOCK 면제한다.

    Args:
        path: 검사할 파일 경로 (상대 경로)

    Returns:
        True: 화이트리스트 접미사 → BLOCK 면제
    """
    path_lower = path.lower()
    return any(path_lower.endswith(suffix) for suffix in _SECURITY_WHITELIST_SUFFIXES)


def scan_security_blocks(root: Path) -> list[str]:
    """보안 BLOCK 패턴에 해당하는 파일 경로 목록을 반환한다.

    rsync 실행 전 사전 검사. 발견 시 백업 중단 + exit 1.
    단, .example / .template / .sample 접미사 파일은 화이트리스트 처리하여 제외한다.
    (ADR-005 결정 6 보강)

    지원 패턴 유형:
      - 정확한 파일명: ".env", "credentials.json"
      - glob 패턴: ".env.*", "*.pem", "*.key"
      - 디렉토리 접두사: ".aws/credentials", ".aws/"
    """
    blocked: list[str] = []
    try:
        for pattern in _SECURITY_BLOCK_PATTERNS:
            pat = pattern.rstrip("/")

            if "*" in pat:
                # glob 패턴 — rglob 으로 재귀 탐색
                for p in root.rglob(pat):
                    if p.is_file():
                        rel = str(p.relative_to(root))
                        if ".git" not in rel.split("/") and not rel.startswith(".git"):
                            if not _is_security_whitelisted(rel):
                                blocked.append(rel)
            elif "/" in pat:
                # 경로 포함 패턴 (예: .aws/credentials, .aws/)
                # 루트 기준 상대 경로로 매핑
                target = root / pat
                if target.is_file():
                    rel = str(target.relative_to(root))
                    if not _is_security_whitelisted(rel):
                        blocked.append(rel)
                elif target.is_dir():
                    # 디렉토리면 하위 모든 파일 BLOCK
                    for p in target.rglob("*"):
                        if p.is_file():
                            rel = str(p.relative_to(root))
                            if not _is_security_whitelisted(rel):
                                blocked.append(rel)
            else:
                # 정확한 파일명 패턴 (예: .env, credentials.json)
                # rglob 으로 모든 하위 디렉토리에서 해당 이름의 파일 탐색
                for p in root.rglob(pat):
                    if p.is_file():
                        rel = str(p.relative_to(root))
                        # .git/ 하위 제외
                        if ".git" not in rel.split("/") and not rel.startswith(".git"):
                            if not _is_security_whitelisted(rel):
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
        save_host_json(data)
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
                "[backup] 먼저 `python3 .claude/bin/backup.py init` 을 실행하세요.",
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
                    print(f"  BLOCK {b}", file=sys.stderr)
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


# ─── init 서브커맨드 (ADR-005 결정 3) ────────────────────────────────────────

def cmd_init(args) -> int:
    """host.json 의 backup 필드 초기 설정.

    대화형 입력(input()) 또는 --repo/--branch 플래그 병행 지원.
    이미 설정된 경우 현재 값 표시 + 변경 여부 질문 (idempotent).
    harness_version 1 → 2 마이그레이션 자동 처리.

    Args:
        args: argparse.Namespace (repo, branch, non_interactive 포함)
    """
    try:
        data = load_host_json()
        existing_backup = data.get("backup") or {}
        existing_repo = existing_backup.get("repo", "")
        existing_branch = existing_backup.get("branch", "")
        has_existing = bool(existing_repo)

        non_interactive = getattr(args, "non_interactive", False)
        repo_flag = getattr(args, "repo", "") or ""
        branch_flag = getattr(args, "branch", "") or ""

        # 이미 설정된 경우 — idempotent 처리
        if has_existing and not non_interactive and not repo_flag:
            print("[backup] 현재 backup 설정:")
            print(f"  repo  : {existing_repo}")
            print(f"  branch: {existing_branch or '(자동 추출)'}")
            last_sync = existing_backup.get("last_sync", "")
            if last_sync:
                print(f"  마지막 sync: {last_sync}")
            print()
            try:
                answer = input("[backup] 설정을 변경하시겠습니까? (y/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n[backup] 입력 중단 — 기존 설정 유지")
                return 0
            if answer not in ("y", "yes"):
                print("[backup] 기존 설정을 유지합니다.")
                return 0

        # repo URL 결정
        if repo_flag:
            new_repo = repo_flag
        elif non_interactive:
            # 비대화형 + --repo 플래그 없음 → 빈 값 (백업 미사용)
            new_repo = ""
        else:
            # 대화형 입력
            auto_branch = _auto_derive_branch_name()
            print(f"[backup] 백업 리포 URL 을 입력하세요.")
            print(f"  예: git@github.com:user/harness_backup.git")
            print(f"  빈 값 입력 시 백업 미사용.")
            try:
                new_repo = input("[backup] backup_repo URL: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[backup] 입력 중단 — 설정 취소")
                return 0

        # HTTPS URL 경고 (차단 X — ADR-005 결정 4)
        if new_repo and detect_auth_mode(new_repo) == "https":
            print("[backup] HTTPS URL 이 입력되었습니다.")
            print("  SSH URL 권장: git@github.com:user/repo.git")
            print("  HTTPS 사용 시 인증 방법:")
            print("    1) ~/.netrc 파일에 credential 등록")
            print("    2) GH_TOKEN 환경변수 (또는 git credential helper)")
            print("  자동 모드에서 자격증명 노출에 주의하세요.")

        # 빈 repo — 백업 미사용
        if not new_repo:
            print("[backup] backup_repo 가 설정되지 않았습니다. 백업을 사용하지 않습니다.")
            # backup 객체 제거 (또는 유지)
            if has_existing:
                try:
                    if not non_interactive:
                        answer = input("[backup] 기존 backup 설정을 제거하시겠습니까? (y/N): ").strip().lower()
                    else:
                        answer = "n"
                except (EOFError, KeyboardInterrupt):
                    answer = "n"
                if answer in ("y", "yes"):
                    data.pop("backup", None)
                    save_host_json(data)
                    print("[backup] backup 설정을 제거했습니다.")
            return 0

        # branch 결정
        auto_branch = _auto_derive_branch_name()
        if branch_flag:
            new_branch = branch_flag
        elif non_interactive:
            # 비대화형 + --branch 없음 → 자동 추출
            new_branch = auto_branch
        else:
            print(f"[backup] 백업 브랜치명을 입력하세요.")
            print(f"  Enter 입력 시 자동 추출값 사용: {auto_branch}")
            try:
                branch_input = input("[backup] backup_branch (Enter = 자동): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[backup] 입력 중단 — 설정 취소")
                return 0
            new_branch = branch_input if branch_input else auto_branch

        # host.json 갱신 + harness_version 마이그레이션
        if "backup" not in data or not isinstance(data.get("backup"), dict):
            data["backup"] = {}

        data["backup"]["repo"] = new_repo
        data["backup"]["branch"] = new_branch

        # harness_version 1 → 2 마이그레이션
        data, migrated = migrate_harness_version(data)
        if migrated:
            print("[backup] host.json schema 1 → 2 마이그레이션 됨")

        if save_host_json(data):
            print("[backup] host.json 의 backup 필드를 업데이트했습니다.")
            print(f"  repo  : {new_repo}")
            print(f"  branch: {new_branch}")
            print()
            print("[backup] 다음: `python3 .claude/bin/backup.py sync` 로 첫 백업을 실행하세요.")
        else:
            print("[backup] host.json 저장 실패 — 수동으로 편집하세요.", file=sys.stderr)
            return 0

        return 0

    except Exception as e:
        print(f"[backup] init 오류: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0  # hook-failure-tolerance


# ─── status 서브커맨드 (ADR-005 결정 7) ──────────────────────────────────────

def cmd_status(args) -> int:
    """마지막 sync 정보 + host.json backup 설정 표시.

    캐시(.claude/state/backup-last.json) 가 없으면 "아직 sync 실행 안 됨" 안내.
    --preview 플래그 시 rsync dry-run 으로 변경 예정 파일 미리보기.
    """
    try:
        # host.json backup 설정 표시
        cfg = load_backup_config()
        data = load_host_json()

        print("[backup] ── backup 설정 ──────────────────────────────")
        if cfg:
            repo_url = get_backup_repo(cfg) or "(미설정)"
            branch = cfg.get("branch") or f"(자동 추출: {_auto_derive_branch_name()})"
            print(f"  backup_repo  : {repo_url}")
            print(f"  backup_branch: {branch}")
            last_sync = cfg.get("last_sync", "")
            last_commit = cfg.get("last_sync_commit", "")
            if last_sync:
                print(f"  last_sync    : {last_sync}")
            if last_commit:
                print(f"  last_commit  : {last_commit}")
        else:
            print("  (backup 미설정 — `python3 .claude/bin/backup.py init` 을 먼저 실행하세요)")

        harness_version = data.get("harness_version", 1)
        print(f"  harness_version: {harness_version}")

        print()
        print("[backup] ── 마지막 sync 이력 ──────────────────────────")
        if _BACKUP_CACHE.exists():
            try:
                cache = json.loads(_BACKUP_CACHE.read_text(encoding="utf-8"))
                ts = cache.get("ts", "없음")
                status = cache.get("status", "?")
                commit = cache.get("commit", "")
                branch_cache = cache.get("branch", "?")
                repo_cache = cache.get("repo", "?")

                status_icon = {
                    "success": "PASS",
                    "no-changes": "SKIP",
                    "clone-failed": "FAIL",
                    "push-failed": "FAIL",
                    "rsync-failed": "FAIL",
                    "branch-failed": "FAIL",
                    "commit-failed": "FAIL",
                }.get(status, status.upper())

                print(f"  시각  : {ts}")
                print(f"  상태  : {status_icon} ({status})")
                print(f"  repo  : {repo_cache}")
                print(f"  branch: {branch_cache}")
                if commit:
                    print(f"  commit: {commit}")
            except Exception as e:
                print(f"  (캐시 파일 읽기 실패: {e})")
        else:
            print("  아직 sync 를 실행한 적이 없습니다.")
            print("  `python3 .claude/bin/backup.py sync` 로 첫 백업을 실행하세요.")

        # --preview: rsync dry-run 으로 변경 예정 파일 미리보기
        preview = getattr(args, "preview", False)
        if preview and cfg:
            repo_url = get_backup_repo(cfg)
            if repo_url:
                print()
                print("[backup] ── 변경 예정 파일 미리보기 (--preview) ────────")
                print("  (임시 clone 없이 로컬 기준 파일 목록만 표시)")
                excludes = get_effective_excludes()
                # 간단히 find 로 예정 파일 목록 (rsync 는 clone 필요해서 skip)
                try:
                    r = subprocess.run(
                        ["git", "status", "--short"],
                        cwd=_PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if r.stdout.strip():
                        print("  로컬 git 변경 파일:")
                        for line in r.stdout.strip().splitlines()[:20]:
                            print(f"    {line}")
                    else:
                        print("  git 변경 파일 없음 (clean working tree)")
                except Exception as e:
                    print(f"  git status 실패: {e}")
            else:
                print()
                print("[backup] --preview: backup_repo 미설정 — 미리보기 불가")

        return 0

    except Exception as e:
        print(f"[backup] status 오류: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0


# ─── config 서브커맨드 (ADR-005 결정 7) ──────────────────────────────────────

def cmd_config(args) -> int:
    """backup 필드 조회/수정.

    서브 액션:
      show              현재 backup_repo / backup_branch / harness_version 표시
      get <key>         특정 키 값만 출력 (스크립트 파싱용)
      set <key> <value> backup_repo / backup_branch 갱신. host.json atomic write.
      unset <key>       필드 제거 (백업 비활성화)
    """
    try:
        action = getattr(args, "config_action", None) or "show"

        if action == "show":
            return _config_show()
        elif action == "get":
            key = getattr(args, "config_key", "") or ""
            return _config_get(key)
        elif action == "set":
            key = getattr(args, "config_key", "") or ""
            value = getattr(args, "config_value", "") or ""
            return _config_set(key, value)
        elif action == "unset":
            key = getattr(args, "config_key", "") or ""
            return _config_unset(key)
        else:
            print(f"[backup] config: 알 수 없는 액션 '{action}'", file=sys.stderr)
            print("[backup] 사용법: config show | get <key> | set <key> <value> | unset <key>")
            return 0

    except Exception as e:
        print(f"[backup] config 오류: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0


def _config_show() -> int:
    """현재 backup 설정 전체를 표시한다."""
    data = load_host_json()
    cfg = data.get("backup") or {}
    harness_version = data.get("harness_version", 1)

    print("[backup] ── config show ─────────────────────────────")
    print(f"  harness_version: {harness_version}")

    if cfg:
        repo = cfg.get("repo", "(미설정)")
        branch = cfg.get("branch", "(자동 추출)")
        last_sync = cfg.get("last_sync", "(없음)")
        last_commit = cfg.get("last_sync_commit", "(없음)")
        print(f"  backup.repo         : {repo}")
        print(f"  backup.branch       : {branch}")
        print(f"  backup.last_sync    : {last_sync}")
        print(f"  backup.last_sync_commit: {last_commit}")
    else:
        print("  backup: (미설정)")
        print("  `python3 .claude/bin/backup.py init` 으로 설정하세요.")

    return 0


def _config_get(key: str) -> int:
    """특정 키 값만 출력한다 (스크립트 파싱용).

    Args:
        key: 조회할 키 이름 (backup_repo, backup_branch, harness_version 등)
    """
    if not key:
        print("[backup] config get: 키를 지정하세요.", file=sys.stderr)
        print("  사용법: config get <backup_repo|backup_branch|harness_version>")
        return 0

    data = load_host_json()
    cfg = data.get("backup") or {}

    # 키 별칭 정규화
    key_map = {
        "backup_repo": "repo",
        "backup_branch": "branch",
        "repo": "repo",
        "branch": "branch",
        "last_sync": "last_sync",
        "last_sync_commit": "last_sync_commit",
    }

    if key == "harness_version":
        print(data.get("harness_version", 1))
    elif key in key_map:
        normalized = key_map[key]
        value = cfg.get(normalized, "")
        if value:
            print(value)
        else:
            # 빈 값도 출력 (스크립트에서 비어있으면 미설정으로 처리)
            print("")
    else:
        print(f"[backup] config get: 알 수 없는 키 '{key}'", file=sys.stderr)
        print("  지원 키: backup_repo, backup_branch, harness_version, last_sync, last_sync_commit")

    return 0


def _config_set(key: str, value: str) -> int:
    """backup_repo 또는 backup_branch 를 갱신한다.

    Args:
        key: 설정할 키 (backup_repo 또는 backup_branch)
        value: 설정할 값
    """
    if not key:
        print("[backup] config set: 키를 지정하세요.", file=sys.stderr)
        print("  사용법: config set <backup_repo|backup_branch> <값>")
        return 0

    if value is None:
        value = ""

    data = load_host_json()
    if "backup" not in data or not isinstance(data.get("backup"), dict):
        data["backup"] = {}

    key_map = {
        "backup_repo": "repo",
        "backup_branch": "branch",
        "repo": "repo",
        "branch": "branch",
    }

    if key not in key_map:
        print(f"[backup] config set: 설정 불가 키 '{key}'", file=sys.stderr)
        print("  설정 가능 키: backup_repo (또는 repo), backup_branch (또는 branch)")
        return 0

    normalized = key_map[key]
    data["backup"][normalized] = value

    # HTTPS URL 경고
    if normalized == "repo" and value and detect_auth_mode(value) == "https":
        print("[backup] HTTPS URL 감지 — SSH URL 권장: git@github.com:user/repo.git")

    # harness_version 마이그레이션
    data, migrated = migrate_harness_version(data)
    if migrated:
        print("[backup] host.json schema 1 → 2 마이그레이션 됨")

    if save_host_json(data):
        display_key = "backup.repo" if normalized == "repo" else "backup.branch"
        print(f"[backup] {display_key} = {value!r}")
    else:
        print("[backup] host.json 저장 실패", file=sys.stderr)

    return 0


def _config_unset(key: str) -> int:
    """backup 필드에서 특정 키를 제거한다.

    Args:
        key: 제거할 키 이름
    """
    if not key:
        print("[backup] config unset: 키를 지정하세요.", file=sys.stderr)
        print("  사용법: config unset <backup_repo|backup_branch>")
        return 0

    data = load_host_json()
    cfg = data.get("backup") or {}

    key_map = {
        "backup_repo": "repo",
        "backup_branch": "branch",
        "repo": "repo",
        "branch": "branch",
    }

    if key not in key_map:
        print(f"[backup] config unset: 알 수 없는 키 '{key}'", file=sys.stderr)
        return 0

    normalized = key_map[key]
    if normalized in cfg:
        del cfg[normalized]
        data["backup"] = cfg
        if save_host_json(data):
            display_key = "backup.repo" if normalized == "repo" else "backup.branch"
            print(f"[backup] {display_key} 제거됨")
        else:
            print("[backup] host.json 저장 실패", file=sys.stderr)
    else:
        print(f"[backup] backup.{normalized} 이미 설정되지 않은 상태입니다.")

    return 0


# ─── self 서브커맨드 (ADR-005 결정 7, F007/F009 라벨 일관) ───────────────────

def cmd_self(args) -> int:
    """셀프 dry-run — 의존성 체크 및 환경 점검.

    점검 항목:
      - git CLI 존재 + 버전
      - rsync CLI 존재 + 버전
      - ssh-agent / ~/.ssh/ 키 등록 여부
      - backup_repo 가 SSH URL 이면 ssh -T <host> 연결 가능 여부
      - is_meta_harness() 결과 + effective_excludes 카운트
      - .claude/state/backup-last.json 캐시 존재 여부

    출력 양식: F009 lint.py self 와 일관된 마크다운 표.
    """
    results: list[tuple[str, str, str]] = []  # (항목, 상태, 내용)

    # 1. git CLI 확인
    try:
        r = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            version = r.stdout.strip()
            results.append(("git CLI", "PASS", version))
        else:
            results.append(("git CLI", "BLOCK", "git 명령어를 찾을 수 없습니다"))
    except FileNotFoundError:
        results.append(("git CLI", "BLOCK", "git 미설치 — sudo apt install git"))
    except Exception as e:
        results.append(("git CLI", "CONCERN", f"확인 실패: {e}"))

    # 2. rsync CLI 확인
    try:
        r = subprocess.run(
            ["rsync", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            first_line = r.stdout.splitlines()[0] if r.stdout else "?"
            results.append(("rsync CLI", "PASS", first_line))
        else:
            results.append(("rsync CLI", "BLOCK", "rsync 명령어를 찾을 수 없습니다"))
    except FileNotFoundError:
        results.append(("rsync CLI", "BLOCK", "rsync 미설치 — sudo apt install rsync"))
    except Exception as e:
        results.append(("rsync CLI", "CONCERN", f"확인 실패: {e}"))

    # 3. ssh-agent + 키 등록 확인
    try:
        r = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            key_count = len(r.stdout.strip().splitlines()) if r.stdout.strip() else 0
            results.append(("ssh-agent + 키", "PASS", f"{key_count}개 키 등록됨"))
        elif r.returncode == 1:
            # ssh-agent 실행 중이나 키 없음
            results.append(("ssh-agent + 키", "CONCERN", "ssh-agent 실행 중이나 키 미등록 — ssh-add ~/.ssh/id_ed25519"))
        else:
            # ssh-agent 미실행
            results.append(("ssh-agent + 키", "CONCERN", "ssh-agent 미실행 — eval $(ssh-agent) && ssh-add"))
    except FileNotFoundError:
        results.append(("ssh-agent + 키", "CONCERN", "ssh-add 없음 — SSH 클라이언트 미설치"))
    except Exception as e:
        results.append(("ssh-agent + 키", "CONCERN", f"확인 실패: {e}"))

    # 4. backup_repo SSH 연결 테스트
    cfg = load_backup_config()
    if cfg:
        repo_url = get_backup_repo(cfg) or ""
        if repo_url and detect_auth_mode(repo_url) == "ssh":
            # git@github.com:user/repo.git → github.com
            m = re.match(r"git@([^:]+):", repo_url)
            if m:
                ssh_host = m.group(1)
                try:
                    r = subprocess.run(
                        ["ssh", "-T", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
                         f"git@{ssh_host}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    # GitHub 등은 exit 1 이지만 stderr 에 "successfully authenticated" 포함
                    output = (r.stdout + r.stderr).lower()
                    if "successfully authenticated" in output or "welcome" in output:
                        results.append((f"SSH {ssh_host}", "PASS", "연결 및 인증 성공"))
                    elif r.returncode == 255:
                        results.append((f"SSH {ssh_host}", "CONCERN", "연결 실패 — SSH 키 등록 확인 필요"))
                    else:
                        results.append((f"SSH {ssh_host}", "CONCERN", f"응답 있음 (exit {r.returncode}) — 수동 확인 권장"))
                except subprocess.TimeoutExpired:
                    results.append((f"SSH {ssh_host}", "CONCERN", "연결 타임아웃 — 네트워크 확인"))
                except Exception as e:
                    results.append((f"SSH {ssh_host}", "CONCERN", f"테스트 실패: {e}"))
            else:
                results.append(("SSH 연결 테스트", "CONCERN", f"호스트 파싱 실패: {repo_url}"))
        elif repo_url and detect_auth_mode(repo_url) == "https":
            results.append(("SSH 연결 테스트", "CONCERN", "HTTPS URL — SSH 연결 테스트 불가. SSH URL 권장."))
        else:
            results.append(("SSH 연결 테스트", "CONCERN", "backup_repo 미설정 — 연결 테스트 스킵"))
    else:
        results.append(("SSH 연결 테스트", "CONCERN", "backup 미설정 — init 먼저 실행하세요"))

    # 5. is_meta_harness + effective_excludes
    meta = is_meta_harness()
    excludes = get_effective_excludes()
    meta_label = "메타 하네스" if meta else "다운스트림"
    results.append(("환경 감지", "PASS", f"{meta_label} — 제외 패턴 {len(excludes)}개"))

    # 6. 캐시 파일 존재 확인
    if _BACKUP_CACHE.exists():
        try:
            cache = json.loads(_BACKUP_CACHE.read_text(encoding="utf-8"))
            ts = cache.get("ts", "?")
            status = cache.get("status", "?")
            results.append(("sync 캐시", "PASS", f"존재 — 마지막: {ts} ({status})"))
        except Exception:
            results.append(("sync 캐시", "CONCERN", "캐시 파일 파싱 실패"))
    else:
        results.append(("sync 캐시", "CONCERN", "캐시 없음 — 아직 sync 실행 전"))

    # 출력 — F009 lint.py self 와 일관된 마크다운 표
    print("[backup] ── self check ──────────────────────────────")
    print()
    print("| 항목 | 상태 | 내용 |")
    print("|------|------|------|")
    for item, status, detail in results:
        status_marker = {"PASS": "PASS", "CONCERN": "WARN", "BLOCK": "BLOCK"}.get(status, status)
        print(f"| {item} | {status_marker} | {detail} |")

    print()

    # 요약
    blocks = [r for r in results if r[1] == "BLOCK"]
    concerns = [r for r in results if r[1] == "CONCERN"]
    passes = [r for r in results if r[1] == "PASS"]

    print(f"[backup] PASS {len(passes)}  /  CONCERN {len(concerns)}  /  BLOCK {len(blocks)}")

    if blocks:
        print()
        print("[backup] BLOCK 항목이 있습니다 — 아래 내용을 해결 후 sync 를 실행하세요:")
        for item, _, detail in blocks:
            print(f"  BLOCK {item}: {detail}")
    elif concerns:
        print()
        print("[backup] CONCERN 항목이 있습니다 (sync 는 가능하나 점검 권장):")
        for item, _, detail in concerns:
            print(f"  WARN {item}: {detail}")
    else:
        print("[backup] 모든 항목 PASS — sync 준비 완료.")

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

    # sync 서브커맨드
    sub.add_parser("sync", help="백업 리포에 현재 산출물 동기화")

    # init 서브커맨드
    init_p = sub.add_parser("init", help="backup 설정 초기화 (host.json 의 backup 필드)")
    init_p.add_argument(
        "--repo",
        default="",
        help="백업 리포 URL (비대화형 모드용)",
    )
    init_p.add_argument(
        "--branch",
        default="",
        help="백업 브랜치명 (비대화형 모드용, 기본 자동 추출)",
    )
    init_p.add_argument(
        "--non-interactive",
        dest="non_interactive",
        action="store_true",
        default=False,
        help="대화형 입력 없이 플래그만으로 설정",
    )

    # status 서브커맨드
    status_p = sub.add_parser("status", help="마지막 sync 정보 + 설정 표시")
    status_p.add_argument(
        "--preview",
        action="store_true",
        default=False,
        help="다음 sync 시 변경될 파일 미리보기 (git status 기반)",
    )

    # config 서브커맨드
    config_p = sub.add_parser("config", help="backup 설정 조회/수정")
    config_sub = config_p.add_subparsers(dest="config_action", metavar="<액션>")

    config_sub.add_parser("show", help="현재 backup 설정 전체 표시")

    config_get_p = config_sub.add_parser("get", help="특정 키 값 출력")
    config_get_p.add_argument("config_key", nargs="?", default="", help="키 이름")

    config_set_p = config_sub.add_parser("set", help="backup_repo 또는 backup_branch 갱신")
    config_set_p.add_argument("config_key", nargs="?", default="", help="키 이름")
    config_set_p.add_argument("config_value", nargs="?", default="", help="설정할 값")

    config_unset_p = config_sub.add_parser("unset", help="필드 제거 (백업 비활성화)")
    config_unset_p.add_argument("config_key", nargs="?", default="", help="키 이름")

    # self 서브커맨드
    sub.add_parser("self", help="셀프 dry-run — 의존성 체크 (git/rsync/ssh/host.json)")

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
            return 0
    except Exception as e:
        print(f"[backup] 최상위 예외: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 0  # hook-failure-tolerance


if __name__ == "__main__":
    sys.exit(main())
