#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_SYNC_REPO_BRANCH = "main"
DEFAULT_SYNC_REPO_DEPTH = 50
DEFAULT_WORKDIR = Path(tempfile.gettempdir()) / "assemble-main-repo"
INSTALL_DEPS = True
RUN_STEPS = [
    "准备与校验配置",
    "拉取/更新主仓库",
    "安装依赖",
    "执行同步脚本",
    "同步后去重处理",
]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                values[key] = value
    except FileNotFoundError:
        return {}
    return values


def load_env_defaults() -> None:
    env_file_candidates = [
        REPO_ROOT / ".env",
        SCRIPT_DIR / ".env",
    ]
    env_file = next((p for p in env_file_candidates if p.is_file()), None)
    if not env_file:
        return
    for key, value in parse_env_file(env_file).items():
        os.environ.setdefault(key, value)


def is_unsafe_workdir(path_str: str, path_obj: Path) -> bool:
    if not path_str or path_str in {"/", ".", ".."}:
        return True
    # Root directory check (Unix "/" or Windows drive root)
    if path_obj == path_obj.parent:
        return True
    return False


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, capture: bool = False):
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    )


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def ensure_git() -> None:
    if shutil.which("git") is None:
        print("ERROR: git not found in PATH.")
        sys.exit(1)


def build_repo_url(base_url: str, token: str) -> str:
    try:
        parsed = urlparse(base_url)
    except Exception:
        return base_url

    if parsed.scheme not in {"http", "https"}:
        return base_url

    if parsed.username or parsed.password:
        return base_url

    safe_token = quote(token, safe="")
    netloc = f"{safe_token}@{parsed.netloc}"
    return urlunparse(parsed._replace(netloc=netloc))


def sanitize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or parsed.netloc.split("@")[-1]
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=host))

def short_commit(commit: str | None) -> str:
    if not commit:
        return "unknown"
    return commit[:8]

def get_head_commit(cwd: Path, env: dict[str, str]) -> str | None:
    try:
        return run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            env=env,
            capture=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def log_plan() -> None:
    print("执行计划：")
    for i, title in enumerate(RUN_STEPS, 1):
        print(f"  {i}. {title}")


def log_step_start(step_index: int) -> None:
    print(f"\n[{step_index}/{len(RUN_STEPS)}] {RUN_STEPS[step_index - 1]}")


def log_step_ok(step_index: int, detail: str | None = None) -> None:
    title = RUN_STEPS[step_index - 1]
    if detail:
        print(f"✅ {title}：{detail}")
    else:
        print(f"✅ {title} 完成")


def log_step_fail(step_index: int, error: str) -> None:
    title = RUN_STEPS[step_index - 1] if step_index else "未知步骤"
    print(f"❌ {title} 失败：{error}")


def log_step_skip(step_index: int, detail: str | None = None) -> None:
    title = RUN_STEPS[step_index - 1]
    if detail:
        print(f"⏭️ {title}：{detail}")
    else:
        print(f"⏭️ {title} 跳过")


def main() -> int:
    load_env_defaults()
    log_plan()

    step_status: list[str] = ["未开始"] * len(RUN_STEPS)
    def set_status(step_index: int, status: str, detail: str | None = None) -> None:
        if detail:
            step_status[step_index - 1] = f"{status}：{detail}"
        else:
            step_status[step_index - 1] = status

    def print_summary() -> None:
        print("\n执行结果：")
        for i, title in enumerate(RUN_STEPS, 1):
            print(f"  {i}. {title} -> {step_status[i - 1]}")

    step_index = 0
    try:
        # Step 1: prepare
        step_index = 1
        log_step_start(step_index)
        sync_repo_url = os.getenv("SYNC_REPO_URL")
        sync_repo_token = os.getenv("SYNC_REPO_TOKEN")
        if not sync_repo_url:
            log_step_fail(step_index, "缺少 SYNC_REPO_URL")
            set_status(step_index, "失败", "缺少 SYNC_REPO_URL")
            print_summary()
            return 1
        if not sync_repo_token:
            log_step_fail(step_index, "缺少 SYNC_REPO_TOKEN")
            set_status(step_index, "失败", "缺少 SYNC_REPO_TOKEN")
            print_summary()
            return 1

        sync_repo_branch = DEFAULT_SYNC_REPO_BRANCH
        sync_repo_depth = DEFAULT_SYNC_REPO_DEPTH
        workdir = str(DEFAULT_WORKDIR)

        workdir_path = Path(workdir).expanduser().absolute()
        if is_unsafe_workdir(workdir, workdir_path):
            log_step_fail(step_index, f"WORKDIR 非法：{workdir}")
            set_status(step_index, "失败", "WORKDIR 非法")
            print_summary()
            return 1

        ensure_git()

        env = os.environ.copy()
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("SYNC_REPO_URL", sync_repo_url)
        env.setdefault("SYNC_REPO_TOKEN", sync_repo_token)

        remote_url = build_repo_url(sync_repo_url, sync_repo_token)
        safe_url = sanitize_url(sync_repo_url)
        depth_label = "全量" if sync_repo_depth == 0 else f"深度={sync_repo_depth}"
        prepare_detail = f"仓库={safe_url} 分支={sync_repo_branch} {depth_label} 工作区={workdir_path}"
        log_step_ok(step_index, prepare_detail)
        set_status(step_index, "成功", prepare_detail)

        # Step 2: clone/update
        step_index = 2
        log_step_start(step_index)
        if (workdir_path / ".git").is_dir():
            print(f"  - 已存在工作区，执行更新：{workdir_path}")
            try:
                run(["git", "remote", "get-url", "origin"], cwd=workdir_path, env=env, capture=True)
                run(["git", "remote", "set-url", "origin", remote_url], cwd=workdir_path, env=env)
            except subprocess.CalledProcessError:
                run(["git", "remote", "add", "origin", remote_url], cwd=workdir_path, env=env)

            if sync_repo_depth != 0:
                run(
                    ["git", "fetch", "--prune", "--depth", str(sync_repo_depth), "origin", sync_repo_branch],
                    cwd=workdir_path,
                    env=env,
                )
            else:
                run(["git", "fetch", "--prune", "origin", sync_repo_branch], cwd=workdir_path, env=env)
                try:
                    shallow = run(
                        ["git", "rev-parse", "--is-shallow-repository"],
                        cwd=workdir_path,
                        env=env,
                        capture=True,
                    ).stdout.strip()
                    if shallow == "true":
                        run(["git", "fetch", "--prune", "--unshallow", "origin"], cwd=workdir_path, env=env)
                except subprocess.CalledProcessError:
                    pass

            run(["git", "checkout", "-B", sync_repo_branch, f"origin/{sync_repo_branch}"], cwd=workdir_path, env=env)
            run(["git", "reset", "--hard", f"origin/{sync_repo_branch}"], cwd=workdir_path, env=env)
            head_commit = short_commit(get_head_commit(workdir_path, env))
            update_detail = f"方式=更新 HEAD={head_commit}"
            log_step_ok(step_index, update_detail)
            set_status(step_index, "成功", update_detail)
        else:
            print(f"  - 工作区不存在，执行克隆：{workdir_path}")
            if workdir_path.exists():
                shutil.rmtree(workdir_path)

            clone_args = ["git", "clone", "--branch", sync_repo_branch]
            if sync_repo_depth != 0:
                clone_args += ["--depth", str(sync_repo_depth)]
            clone_args += [remote_url, str(workdir_path)]
            run(clone_args, env=env)
            head_commit = short_commit(get_head_commit(workdir_path, env))
            clone_detail = f"方式=克隆 HEAD={head_commit}"
            log_step_ok(step_index, clone_detail)
            set_status(step_index, "成功", clone_detail)

        # Step 3: deps
        step_index = 3
        log_step_start(step_index)
        if INSTALL_DEPS:
            req_file_candidates = [
                REPO_ROOT / "requirements.txt",
                SCRIPT_DIR / "requirements.txt",
            ]
            req_file = next((p for p in req_file_candidates if p.is_file()), None)
            if not req_file:
                raise FileNotFoundError("requirements.txt not found")
            run(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req_file)],
                env=env,
            )
            log_step_ok(step_index, "依赖已安装")
            set_status(step_index, "成功", "依赖已安装")
        else:
            log_step_ok(step_index, "跳过安装依赖")
            set_status(step_index, "跳过", "跳过安装依赖")

        # Step 4: run sync
        step_index = 4
        log_step_start(step_index)
        args = []
        for arg in sys.argv[1:]:
            if arg == "--init":
                print("  - 忽略 --init（内部自动初始化）")
                continue
            args.append(arg)

        sync_script_candidates = [
            REPO_ROOT / "src" / "assemble_publish" / "sync_to_cnblogs.py",
            REPO_ROOT / "sync_to_cnblogs.py",
            SCRIPT_DIR / "sync_to_cnblogs.py",
            SCRIPT_DIR / "cnblogs_sync" / "sync_to_cnblogs.py",
        ]
        sync_script = next((p for p in sync_script_candidates if p.is_file()), None)
        if not sync_script:
            raise FileNotFoundError("未找到同步脚本：sync_to_cnblogs.py")
        run([sys.executable, str(sync_script), *args], cwd=workdir_path, env=env)
        args_display = " ".join(args) if args else "(无)"
        sync_detail = f"参数={args_display}"
        log_step_ok(step_index, sync_detail)
        set_status(step_index, "成功", sync_detail)

        # Step 5: post-sync dedup
        step_index = 5
        log_step_start(step_index)
        if not env_flag("POST_DEDUP", False):
            log_step_skip(step_index, "未启用 POST_DEDUP")
            set_status(step_index, "跳过", "未启用 POST_DEDUP")
        else:
            dedup_script = REPO_ROOT / "tools" / "deduplicate_cnblogs.py"
            if not dedup_script.is_file():
                raise FileNotFoundError("未找到去重脚本：tools/deduplicate_cnblogs.py")

            dedup_env = env.copy()
            post_to_dedup = {
                "POST_DEDUP_DRY_RUN": "DEDUP_DRY_RUN",
                "POST_DEDUP_KEEP_LATEST": "DEDUP_KEEP_LATEST",
                "POST_DEDUP_DELETE_DELAY": "DEDUP_DELETE_DELAY",
                "POST_DEDUP_SHOW_DETAILS": "DEDUP_SHOW_DETAILS",
                "POST_DEDUP_MAX_ROUNDS": "DEDUP_MAX_ROUNDS",
            }
            for src_key, dest_key in post_to_dedup.items():
                if src_key in dedup_env:
                    dedup_env.setdefault(dest_key, dedup_env[src_key])

            run([sys.executable, str(dedup_script)], cwd=workdir_path, env=dedup_env)
            log_step_ok(step_index, "去重完成")
            set_status(step_index, "成功", "去重完成")

        print("\n✅ 全部步骤执行完成")
        print_summary()
        return 0
    except subprocess.CalledProcessError as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        log_step_fail(step_index, detail.strip())
        set_status(step_index, "失败", "命令执行失败")
        print_summary()
        return 1
    except Exception as exc:
        log_step_fail(step_index, str(exc))
        set_status(step_index, "失败")
        print_summary()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
