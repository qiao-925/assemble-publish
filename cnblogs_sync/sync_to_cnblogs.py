# cnblogs_sync/sync_to_cnblogs.py
#
# 博客园文章发布脚本
#
# 【功能说明】
# 将本地 Markdown 文件发布到博客园（单向：本地 → 博客园），支持基于本地 JSON 记录的去重判断。
#
# 【环境变量配置】
# 使用前需要设置以下环境变量（通过 .env 文件或系统环境变量）：
#   - CNBLOGS_RPC_URL: 博客园 RPC 地址（必需）
#   - CNBLOGS_USERNAME: 用户名（必需）
#   - CNBLOGS_TOKEN: Token（必需）
#   - SYNC_REPO_URL: 目标仓库地址（必需）
#   - SYNC_REPO_TOKEN: 推送状态分支用的 Token（必需）
#
# 【使用方法】
#
# 1. 发布文章到博客园（首次运行会自动初始化发布记录）：
#    a) 自动模式（推荐）：不指定文件，自动扫描仓库中所有 .md 文件
#       python cnblogs_sync/sync_to_cnblogs.py
#    b) 手动模式：指定要发布的文件
#       python cnblogs_sync/sync_to_cnblogs.py <file1.md> [file2.md] ...
#    说明：将 Markdown 文件发布到博客园
#          - 若发布记录不存在，会自动从 API 获取最近 300 篇文章生成记录
#          - 如果文章已在本地记录中（已发布过），默认执行更新
#          - 如果是新文章，直接发布并自动更新本地记录
#          - 自动模式会排除 .git、.github、node_modules、cnblogs_sync 等目录
#
# 【本地记录文件】
# - 位置：默认在仓库内的 `.cnblogs_sync/.cnblogs_sync_record.json`
# - 格式：{ "文章标题": "post_id", ... }
# - 作用：记录已发布到博客园的文章，避免重复发布

import os
import sys
import re
import json
import time
import subprocess
import tempfile
import shutil
import xmlrpc.client
from urllib.parse import urlparse, urlunparse, quote
from datetime import datetime
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
# from urllib.parse import quote # 不再需要这个模块，可以移除

# 加载 .env 文件中的环境变量
load_dotenv()

# --- 配置信息（仅保留必需项） ---
RPC_URL = os.getenv("CNBLOGS_RPC_URL")
USERNAME = os.getenv("CNBLOGS_USERNAME")
PASSWORD = os.getenv("CNBLOGS_TOKEN")

SYNC_REPO_URL = os.getenv("SYNC_REPO_URL")
SYNC_REPO_TOKEN = os.getenv("SYNC_REPO_TOKEN")

# 下面为固定默认值，不对外暴露配置
BLOG_ID = None  # 自动获取
KNOWLEDGE_BASE_URL = "https://assemble.gitbook.io/assemble"
CNBLOGS_SEARCH_URL = "https://zzk.cnblogs.com/my/s/blogpost-p"

# --- Git / 运行环境小优化 ---
# 避免在无交互环境（Zeabur/Cron）里 git push 触发凭据交互卡死
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

# --- 行为开关 ---
FORCE_OVERWRITE_EXISTING = True

# --- 仓库根目录（支持外部传入） ---
REPO_ROOT = Path.cwd().resolve()

# --- 记录/状态文件路径（默认相对仓库根目录） ---
SYNC_RECORD_PATH = ".cnblogs_sync/.cnblogs_sync_record.json"
SYNC_STATE_PATH = ".cnblogs_sync/state.json"
SYNC_RUN_LOG_PATH = ".cnblogs_sync/run_history.jsonl"

def resolve_repo_path(path_str):
    """将路径解析为仓库内绝对路径（支持绝对路径）"""
    p = Path(path_str)
    return p if p.is_absolute() else (REPO_ROOT / p)

# --- 本地发布记录文件路径 ---
SYNC_RECORD_FILE = resolve_repo_path(SYNC_RECORD_PATH)
# --- 本地状态文件路径（用于增量同步） ---
SYNC_STATE_FILE = resolve_repo_path(SYNC_STATE_PATH)
# --- 本地运行记录文件路径 ---
SYNC_RUN_LOG_FILE = resolve_repo_path(SYNC_RUN_LOG_PATH)

# --- 增量同步与 Git 持久化配置 ---
INCREMENTAL_SYNC = True
SYNC_STATE_GIT = True
SYNC_STATE_BRANCH = "sync-state"
SYNC_STATE_REMOTE = "origin"

def build_state_remote_url():
    """基于 SYNC_REPO_URL + SYNC_REPO_TOKEN 自动拼接可写远端"""
    if not SYNC_REPO_URL or not SYNC_REPO_TOKEN:
        return None

    try:
        parsed = urlparse(SYNC_REPO_URL)
    except Exception:
        return None

    if parsed.scheme not in {"http", "https"}:
        print("⚠️ 仅支持 http/https 形式的 SYNC_REPO_URL 用于自动拼接 Token")
        return None

    # 若已包含凭据，直接复用原始 URL
    if parsed.username or parsed.password:
        return SYNC_REPO_URL

    token = quote(SYNC_REPO_TOKEN, safe="")
    netloc = f"{token}@{parsed.netloc}"
    return urlunparse(parsed._replace(netloc=netloc))

SYNC_STATE_REMOTE_URL = build_state_remote_url()

SYNC_STEPS = [
    "准备与恢复状态",
    "初始化发布记录",
    "检测变更并生成待发布列表",
    "发布/更新文章",
    "写回状态分支",
]


def log_plan():
    print("执行计划（同步流程）：")
    for i, title in enumerate(SYNC_STEPS, 1):
        print(f"  {i}. {title}")


def log_step_start(step_index: int) -> None:
    print(f"\n[{step_index}/{len(SYNC_STEPS)}] {SYNC_STEPS[step_index - 1]}")


def log_step_ok(step_index: int, detail: str | None = None) -> None:
    title = SYNC_STEPS[step_index - 1]
    if detail:
        print(f"✅ {title}：{detail}")
    else:
        print(f"✅ {title} 完成")


def log_step_skip(step_index: int, detail: str | None = None) -> None:
    title = SYNC_STEPS[step_index - 1]
    if detail:
        print(f"⏭️ {title}：{detail}")
    else:
        print(f"⏭️ {title} 跳过")


def log_step_fail(step_index: int, detail: str) -> None:
    title = SYNC_STEPS[step_index - 1]
    print(f"❌ {title} 失败：{detail}")

# --- 需要排除的目录（不扫描这些目录下的文件） ---
EXCLUDE_DIRS = {'.git', '.github', 'node_modules', '__pycache__', '.vscode', '.idea', 'cnblogs_sync', '.cnblogs_sync'}

# --- 函数定义 ---

def run_git(args, cwd=None, check=False):
    """运行 git 命令并返回结果"""
    cmd = ["git", "-c", "core.quotepath=false"] + args
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result

def is_git_repo():
    """检查当前目录是否为 Git 仓库"""
    result = run_git(["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"

def ensure_remote(remote, remote_url=None):
    """确保 remote 存在并可用（可选：设置 PAT URL）"""
    if not remote_url:
        return
    result = run_git(["remote", "get-url", remote])
    if result.returncode != 0:
        run_git(["remote", "add", remote, remote_url], check=True)
        return
    current_url = result.stdout.strip()
    if current_url != remote_url:
        run_git(["remote", "set-url", remote, remote_url], check=True)

def has_remote(remote):
    """检查 remote 是否存在"""
    result = run_git(["remote", "get-url", remote])
    return result.returncode == 0

def remote_branch_exists(remote, branch):
    """检查远端分支是否存在"""
    result = run_git(["ls-remote", "--heads", remote, branch])
    return result.returncode == 0 and bool(result.stdout.strip())

def ensure_git_identity(cwd):
    """确保 git commit 的 user.name/user.email 已配置（CI/容器环境常缺省）"""
    result_name = run_git(["config", "--get", "user.name"], cwd=cwd)
    result_email = run_git(["config", "--get", "user.email"], cwd=cwd)

    user_name = (result_name.stdout or "").strip() if result_name.returncode == 0 else ""
    user_email = (result_email.stdout or "").strip() if result_email.returncode == 0 else ""

    if not user_name:
        default_name = os.getenv("GIT_USER_NAME", "cnblogs-sync-bot")
        run_git(["config", "user.name", default_name], cwd=cwd, check=True)
    if not user_email:
        default_email = os.getenv("GIT_USER_EMAIL", "cnblogs-sync-bot@users.noreply.github.com")
        run_git(["config", "user.email", default_email], cwd=cwd, check=True)

def restore_state_from_git() -> str:
    """从专用分支恢复状态文件（记录 + 增量状态）"""
    if not SYNC_STATE_GIT:
        return "未启用"
    if not is_git_repo():
        print("⚠️ 当前目录不是 Git 仓库，无法从分支恢复状态")
        return "跳过（非 Git 仓库）"

    try:
        ensure_remote(SYNC_STATE_REMOTE, SYNC_STATE_REMOTE_URL)
        if not has_remote(SYNC_STATE_REMOTE):
            print(f"⚠️ 未找到 remote '{SYNC_STATE_REMOTE}'，请设置 SYNC_REPO_TOKEN")
            return "跳过（remote 缺失）"
        run_git(["fetch", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], check=True)
    except Exception as e:
        print(f"⚠️ 拉取分支失败，跳过状态恢复：{e}")
        return "跳过（拉取失败）"

    restored = 0
    missing = 0
    skipped = 0
    for path in [SYNC_RECORD_FILE, SYNC_STATE_FILE, SYNC_RUN_LOG_FILE]:
        try:
            rel_path = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            print(f"⚠️ 状态文件不在仓库内，跳过恢复: {path}")
            skipped += 1
            continue
        result = run_git(["show", f"{SYNC_STATE_REMOTE}/{SYNC_STATE_BRANCH}:{rel_path}"])
        if result.returncode == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(result.stdout, encoding="utf-8")
            print(f"✅ 已从分支恢复状态文件: {rel_path}")
            restored += 1
        else:
            print(f"ℹ️ 分支未包含状态文件: {rel_path}")
            missing += 1

    if restored == 0 and missing == 0 and skipped == 0:
        return "无状态文件"

    parts = []
    if restored:
        parts.append(f"恢复={restored}")
    if missing:
        parts.append(f"缺失={missing}")
    if skipped:
        parts.append(f"跳过={skipped}")
    return "，".join(parts)

def persist_state_to_git():
    """将状态文件提交到专用分支并推送"""
    if not SYNC_STATE_GIT:
        return True, "未启用"
    if not is_git_repo():
        print("⚠️ 当前目录不是 Git 仓库，无法持久化状态")
        return False, "非 Git 仓库"

    temp_dir = None
    try:
        ensure_remote(SYNC_STATE_REMOTE, SYNC_STATE_REMOTE_URL)
        if not has_remote(SYNC_STATE_REMOTE):
            print(f"⚠️ 未找到 remote '{SYNC_STATE_REMOTE}'，请设置 SYNC_REPO_TOKEN")
            return False, f"缺少 remote: {SYNC_STATE_REMOTE}"
        branch_exists = remote_branch_exists(SYNC_STATE_REMOTE, SYNC_STATE_BRANCH)
        base_ref = "HEAD"
        if branch_exists:
            try:
                run_git(["fetch", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], check=True)
                fetch_head = run_git(["rev-parse", "FETCH_HEAD"])
                if fetch_head.returncode == 0 and fetch_head.stdout.strip():
                    base_ref = fetch_head.stdout.strip()
                else:
                    remote_ref = f"{SYNC_STATE_REMOTE}/{SYNC_STATE_BRANCH}"
                    ref_check = run_git(["rev-parse", "--verify", remote_ref])
                    if ref_check.returncode == 0:
                        base_ref = remote_ref
                    else:
                        print(f"⚠️ 未找到远端引用 {remote_ref}，将改为创建新分支")
            except Exception as e:
                print(f"⚠️ 拉取状态分支失败，将改为创建新分支：{e}")
                base_ref = "HEAD"

        temp_dir = tempfile.mkdtemp(prefix="cnblogs-sync-state-")
        run_git(["worktree", "add", "-B", SYNC_STATE_BRANCH, temp_dir, base_ref], check=True)

        rel_paths = []
        for path in [SYNC_RECORD_FILE, SYNC_STATE_FILE, SYNC_RUN_LOG_FILE]:
            if not path.exists():
                continue
            try:
                rel_path = path.relative_to(REPO_ROOT)
            except ValueError:
                print(f"⚠️ 状态文件不在仓库内，无法持久化: {path}")
                continue
            dest_path = Path(temp_dir) / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest_path)
            rel_paths.append(rel_path.as_posix())

        if not rel_paths:
            print("ℹ️ 未找到可持久化的状态文件")
            return True, "无状态文件"

        status = run_git(["status", "--porcelain"], cwd=temp_dir)
        if not status.stdout.strip():
            print("ℹ️ 状态文件无变化，无需提交")
            return True, "无变化"

        run_git(["add"] + rel_paths, cwd=temp_dir, check=True)
        ensure_git_identity(temp_dir)
        commit_msg = f"chore: update cnblogs sync state ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        run_git(["commit", "-m", commit_msg], cwd=temp_dir, check=True)
        try:
            run_git(["push", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], cwd=temp_dir, check=True)
        except Exception as e:
            msg = str(e)
            if "non-fast-forward" in msg or "fetch first" in msg or "rejected" in msg:
                print("⚠️ 推送被拒绝（non-fast-forward），改用 --force-with-lease 重试")
                run_git(["push", "--force-with-lease", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], cwd=temp_dir, check=True)
            else:
                raise
        print(f"✅ 状态已推送到分支: {SYNC_STATE_BRANCH}")
        return True, f"已推送到分支: {SYNC_STATE_BRANCH}"
    except Exception as e:
        print(f"❌ 持久化状态失败: {e}")
        return False, "持久化失败"
    finally:
        if temp_dir:
            try:
                run_git(["worktree", "remove", temp_dir, "--force"])
            except Exception:
                pass
            try:
                if Path(temp_dir).exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

def load_sync_state():
    """加载增量同步状态"""
    if SYNC_STATE_FILE.exists():
        try:
            with open(SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载状态文件时出错: {e}，将使用空状态")
            return {}
    return {}

def save_sync_state(state):
    """保存增量同步状态"""
    try:
        SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存状态文件时出错: {e}")

def append_run_log(entry):
    """追加一行运行记录（JSONL）"""
    try:
        SYNC_RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_RUN_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ 写入运行记录失败: {e}")

def get_head_commit():
    """获取当前 HEAD commit"""
    result = run_git(["rev-parse", "HEAD"])
    if result.returncode == 0:
        return result.stdout.strip()
    return None

def short_commit(commit: str | None) -> str:
    if not commit:
        return "无"
    return commit[:8]

def get_changed_markdown_files(last_commit, head_commit):
    """获取两次提交之间变更的 Markdown 文件"""
    if not last_commit or not head_commit:
        return None
    result = run_git(["diff", "--name-only", f"{last_commit}..{head_commit}", "--", "*.md"])
    if result.returncode != 0:
        print(f"⚠️ 获取增量文件失败: {result.stderr.strip()}")
        return None

    changed_files = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        rel_path = Path(rel)
        if any(part in EXCLUDE_DIRS for part in rel_path.parts):
            continue
        abs_path = REPO_ROOT / rel_path
        if abs_path.exists():
            changed_files.append(str(abs_path))
    return changed_files

def find_all_markdown_files(root_dir=None):
    """递归查找仓库中所有的 Markdown 文件"""
    if root_dir is None:
        # 默认从脚本所在目录的父目录（项目根目录）开始扫描
        root_dir = REPO_ROOT
    
    root_path = Path(root_dir).resolve()
    md_files = []
    
    print(f"🔍 开始扫描 Markdown 文件（从 {root_path} 开始）...")
    
    for file_path in root_path.rglob('*.md'):
        # 检查文件路径中是否包含需要排除的目录
        relative_path = file_path.relative_to(root_path)
        path_parts = relative_path.parts
        
        # 如果路径的任何部分在排除列表中，跳过
        if any(part in EXCLUDE_DIRS for part in path_parts):
            continue
        
        md_files.append(str(file_path))
    
    md_files.sort()  # 按路径排序
    print(f"✅ 找到 {len(md_files)} 个 Markdown 文件")
    return md_files

def get_file_content(filepath):
    """读取文件内容"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def replace_internal_md_links(content):
    """查找内容中所有指向本地 .md 文件的链接，并将其替换为博客园站内搜索链接。"""
    md_link_pattern = re.compile(r'(\[.*?\])\((.*?\.md)\)')
    def replacer(match):
        link_text = match.group(1)
        md_path = match.group(2)
        keyword = os.path.basename(md_path).replace('.md', '')

        # 核心修改：不再对关键词进行 URL 编码
        # encoded_keyword = quote(keyword) # 移除此行

        # 直接使用原始关键词构建 URL
        new_url = f"{CNBLOGS_SEARCH_URL}?Keywords={keyword}"
        return f"{link_text}({new_url} )"
    return md_link_pattern.sub(replacer, content)

def load_sync_record():
    """加载本地发布记录"""
    if SYNC_RECORD_FILE.exists():
        try:
            with open(SYNC_RECORD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载发布记录文件时出错: {e}，将使用空记录")
            return {}
    return {}

def save_sync_record(record):
    """保存本地发布记录"""
    try:
        SYNC_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_RECORD_FILE, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存发布记录文件时出错: {e}")

def get_blog_id(server):
    """自动获取 BLOG_ID"""
    try:
        blogs = server.blogger.getUsersBlogs('', USERNAME, PASSWORD)
        if blogs and len(blogs) > 0:
            blog = blogs[0] or {}
            blog_id = blog.get('blogid') or blog.get('blogId') or blog.get('id')
            return str(blog_id) if blog_id is not None else None
    except Exception as e:
        print(f"⚠️ 自动获取 BLOG_ID 失败: {e}")
    return None

def init_sync_record():
    """初始化发布记录：从 API 获取最近 300 篇文章的标题和 post_id"""
    global BLOG_ID
    if not all([RPC_URL, USERNAME, PASSWORD]):
        print("❌ 错误：一个或多个环境变量未设置，无法初始化发布记录")
        return False
    
    print("🔄 开始初始化发布记录（从 API 获取最近 300 篇文章）...")
    
    try:
        server = xmlrpc.client.ServerProxy(RPC_URL)
        if not BLOG_ID:
            BLOG_ID = get_blog_id(server)
            if not BLOG_ID:
                print("❌ 错误：无法自动获取 BLOG_ID，请检查账号权限与 RPC 配置")
                return False
            print(f"✅ 自动获取到 BLOG_ID: {BLOG_ID}")

        # API 极限是 300 篇
        recent_posts = server.metaWeblog.getRecentPosts(BLOG_ID, USERNAME, PASSWORD, 300)
        
        if not recent_posts:
            record = load_sync_record() or {}
            save_sync_record(record)
            print("ℹ️ 未获取到任何文章，已初始化空发布记录")
            print(f"📁 记录文件保存在: {SYNC_RECORD_FILE}")
            return True
        
        # 合并模式：保留旧记录 + 用最近 300 篇刷新 post_id（避免因 API 限制丢失旧映射）
        record = load_sync_record() or {}
        for post in recent_posts:
            title = post.get('title', '').strip()
            post_id = post.get('postid')
            if title and post_id:
                record[title] = post_id
        
        # 保存记录
        save_sync_record(record)
        print(f"✅ 成功初始化发布记录：共 {len(record)} 篇文章")
        print(f"📁 记录文件保存在: {SYNC_RECORD_FILE}")
        return True
        
    except Exception as e:
        print(f"❌ 初始化发布记录时出错: {e}")
        return False

PostResult = Literal["created", "updated", "skipped", "failed"]


def post_to_cnblogs(title, content, categories=None) -> PostResult:
    """发布文章到博客园，基于本地记录判断是否已存在"""
    # --- 步骤1: 准备最终内容 ---

    # 核心修改：不再对标题进行 URL 编码
    # encoded_title = quote(title) # 移除此行

    # 直接使用原始标题构建 URL
    knowledge_base_url = f"{KNOWLEDGE_BASE_URL}?q={title}"
    prepend_content = f"> 关联知识库：<a href=\"{knowledge_base_url}\">{title}</a>\r\n\r\n"

    processed_body = replace_internal_md_links(content)
    final_content = prepend_content + processed_body

    # --- 步骤2: 准备 post 数据结构 ---
    final_categories = ['[Markdown]']
    if categories and isinstance(categories, list):
        final_categories.extend(categories)
    else:
        final_categories.append('[随笔分类]')

    post_data = {
        'title': title,
        'description': final_content,
        'categories': final_categories,
        'publish': True
    }

    # --- 步骤3: 基于本地记录的核心发布/更新/跳过逻辑 ---
    try:
        server = xmlrpc.client.ServerProxy(RPC_URL)
        
        # 加载本地记录
        sync_record = load_sync_record()
        existing_post_id = sync_record.get(title)

        if existing_post_id:
            if FORCE_OVERWRITE_EXISTING:
                print(f"ℹ️ 本地记录显示文章 '{title}' 已存在（Post ID: {existing_post_id}），强制覆盖模式已开启...")
                success = server.metaWeblog.editPost(existing_post_id, USERNAME, PASSWORD, post_data, post_data['publish'])
                if success:
                    print(f"✅ 成功更新文章 '{title}'，Post ID: {existing_post_id}")
                    # 确保记录中的 post_id 是最新的（虽然通常不会变）
                    sync_record[title] = existing_post_id
                    save_sync_record(sync_record)
                    return "updated"
                else:
                    print(f"❌ 更新文章 '{title}' 失败")
                    return "failed"
            else:
                print(f"ℹ️ 本地记录显示文章 '{title}' 已存在（Post ID: {existing_post_id}），跳过发布")
                return "skipped"
        else:
            print(f"📄 文章 '{title}' 不在本地记录中，将创建新文章")
            new_post_id = server.metaWeblog.newPost(BLOG_ID, USERNAME, PASSWORD, post_data, post_data['publish'])
            print(f"✅ 成功发布新文章 '{title}'，文章ID: {new_post_id}")
            
            # 更新本地记录（始终更新）
            sync_record[title] = new_post_id
            save_sync_record(sync_record)
            return "created"

    except Exception as e:
        print(f"❌ 发布或更新文章 '{title}' 时发生严重错误: {e}")
        return "failed"

# --- 主流程 ---
if __name__ == "__main__":
    run_started_ts = time.time()
    missing_vars = []
    if not RPC_URL:
        missing_vars.append("CNBLOGS_RPC_URL")
    if not USERNAME:
        missing_vars.append("CNBLOGS_USERNAME")
    if not PASSWORD:
        missing_vars.append("CNBLOGS_TOKEN")
    if not SYNC_REPO_URL:
        missing_vars.append("SYNC_REPO_URL")
    if not SYNC_REPO_TOKEN:
        missing_vars.append("SYNC_REPO_TOKEN")

    if missing_vars:
        print("❌ 环境变量缺失，无法继续：")
        for var in missing_vars:
            print(f"  - {var}")
        print("请检查 .env 或系统环境变量后再运行。")
        sys.exit(1)

    log_plan()
    step_status = ["未开始"] * len(SYNC_STEPS)

    def set_status(step_index: int, status: str, detail: str | None = None) -> None:
        if detail:
            step_status[step_index - 1] = f"{status}：{detail}"
        else:
            step_status[step_index - 1] = status

    def print_summary() -> None:
        print("\n执行结果：")
        for i, title in enumerate(SYNC_STEPS, 1):
            print(f"  {i}. {title} -> {step_status[i - 1]}")

    # Step 1: prepare & restore
    step = 1
    log_step_start(step)
    restore_detail = restore_state_from_git()
    if not BLOG_ID:
        try:
            server = xmlrpc.client.ServerProxy(RPC_URL)
            BLOG_ID = get_blog_id(server)
            if BLOG_ID:
                print(f"✅ 自动获取到 BLOG_ID: {BLOG_ID}")
            else:
                log_step_fail(step, "无法自动获取 BLOG_ID")
                set_status(step, "失败", "BLOG_ID 获取失败")
                print_summary()
                sys.exit(1)
        except Exception as e:
            log_step_fail(step, f"获取 BLOG_ID 失败: {e}")
            set_status(step, "失败", "BLOG_ID 获取异常")
            print_summary()
            sys.exit(1)
    step1_detail = f"状态恢复={restore_detail}，BLOG_ID={BLOG_ID}"
    log_step_ok(step, step1_detail)
    set_status(step, "成功", step1_detail)

    # Step 2: init record
    step = 2
    log_step_start(step)
    if not SYNC_RECORD_FILE.exists():
        print("  - 发布记录不存在，开始初始化")
        ok = init_sync_record()
        if not ok:
            log_step_fail(step, "初始化发布记录失败")
            set_status(step, "失败", "初始化失败")
            print_summary()
            sys.exit(1)
        record_count = len(load_sync_record() or {})
        record_detail = f"记录数={record_count}"
        log_step_ok(step, record_detail)
        set_status(step, "成功", record_detail)
    else:
        log_step_skip(step, "发布记录已存在")
        set_status(step, "跳过", "发布记录已存在")

    # Step 3: build publish list
    step = 3
    log_step_start(step)
    sync_state = load_sync_state()
    head_commit = get_head_commit()
    last_synced_commit = sync_state.get("last_synced_commit")
    head_short = short_commit(head_commit)
    last_short = short_commit(last_synced_commit)

    run_mode = "full"
    if len(sys.argv) > 1:
        files_to_publish = sys.argv[1:]
        print(f"  - 手动模式：指定 {len(files_to_publish)} 个文件")
        run_mode = "manual"
    else:
        files_to_publish = None
        if INCREMENTAL_SYNC:
            changed_files = get_changed_markdown_files(last_synced_commit, head_commit)
            if changed_files is not None:
                files_to_publish = changed_files
                run_mode = "incremental"
                print(f"  - 增量对比：{last_short}..{head_short}，变更 {len(files_to_publish)} 个 Markdown 文件")
            else:
                print("  - 增量差异获取失败，改为全量扫描")

        if files_to_publish is None:
            files_to_publish = find_all_markdown_files()
            if not files_to_publish:
                log_step_ok(step, "未找到 Markdown 文件")
                set_status(step, "跳过", "未找到 Markdown 文件")
                print_summary()
                sys.exit(0)
            print(f"  - 全量扫描：共 {len(files_to_publish)} 个 Markdown 文件")

    list_detail = f"模式={run_mode}，候选={len(files_to_publish)}"
    if run_mode != "manual":
        list_detail += f"，last={last_short}，head={head_short}"
    log_step_ok(step, list_detail)
    set_status(step, "成功", list_detail)

    # Step 4: publish
    step = 4
    log_step_start(step)
    if run_mode == "incremental" and not files_to_publish:
        step4_detail = "无变更"
        log_step_skip(step, step4_detail)
        set_status(step, "跳过", step4_detail)

        if head_commit:
            sync_state["last_synced_commit"] = head_commit
        sync_state["last_run_at"] = datetime.now().isoformat(timespec="seconds")
        sync_state["last_run_mode"] = run_mode
        sync_state["last_total_candidates"] = 0
        sync_state["last_published_count"] = 0
        sync_state["last_skipped_count"] = 0
        sync_state["last_failed_count"] = 0
        save_sync_state(sync_state)
        log_entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "mode": run_mode,
            "candidates": 0,
            "published": 0,
            "skipped": 0,
            "failed": 0,
            "status": "no_change",
            "duration_s": int(time.time() - run_started_ts)
        }
        if head_commit:
            log_entry["head_commit"] = head_commit
        append_run_log(log_entry)

        step = 5
        log_step_start(step)
        persist_ok, persist_detail = persist_state_to_git()
        if not persist_ok:
            log_step_fail(step, persist_detail)
            set_status(step, "失败", persist_detail)
            print_summary()
            sys.exit(2)
        log_step_ok(step, persist_detail)
        set_status(step, "成功", persist_detail)
        print_summary()
        sys.exit(0)

    SUCCESS_BATCH_SIZE_SMALL = 5
    SUCCESS_REST_SECONDS_SMALL = 3
    SUCCESS_BATCH_SIZE_LARGE = 20
    SUCCESS_REST_SECONDS_LARGE = 10

    success_count = 0
    skipped_count = 0
    failed_count = 0
    missing_count = 0

    for idx, md_file in enumerate(files_to_publish, 1):
        if not os.path.exists(md_file):
            print(f"⚠️ 文件不存在，跳过: '{md_file}'")
            failed_count += 1
            missing_count += 1
            continue

        print(f"\n[{idx}/{len(files_to_publish)}] 处理文件: {md_file}")
        post_title = os.path.basename(md_file).replace('.md', '')
        post_content = get_file_content(md_file)

        result = post_to_cnblogs(post_title, post_content)

        if result in {"created", "updated"}:
            success_count += 1
            if success_count % SUCCESS_BATCH_SIZE_SMALL == 0:
                print(f"\n⏳ 已处理 {success_count} 篇，休息 {SUCCESS_REST_SECONDS_SMALL}s...")
                time.sleep(SUCCESS_REST_SECONDS_SMALL)
                print("✅ 继续同步...\n")

            if success_count % SUCCESS_BATCH_SIZE_LARGE == 0:
                print(f"\n⏳ 已处理 {success_count} 篇，休息 {SUCCESS_REST_SECONDS_LARGE}s...")
                time.sleep(SUCCESS_REST_SECONDS_LARGE)
                print("✅ 继续同步...\n")
        elif result == "skipped":
            skipped_count += 1
        else:
            failed_count += 1

    step4_detail = (
        f"成功={success_count}，跳过={skipped_count}，失败={failed_count}，总计={len(files_to_publish)}"
    )
    if missing_count:
        step4_detail += f"，缺失={missing_count}"
    log_step_ok(step, step4_detail)
    step4_status = "成功" if failed_count == 0 else "部分失败"
    set_status(step, step4_status, step4_detail)

    if run_mode != "manual" and head_commit:
        sync_state["last_synced_commit"] = head_commit
    sync_state["last_run_at"] = datetime.now().isoformat(timespec="seconds")
    sync_state["last_run_mode"] = run_mode
    sync_state["last_total_candidates"] = len(files_to_publish)
    sync_state["last_published_count"] = success_count
    sync_state["last_skipped_count"] = skipped_count
    sync_state["last_failed_count"] = failed_count
    save_sync_state(sync_state)
    log_entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mode": run_mode,
        "candidates": len(files_to_publish),
        "published": success_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "status": "completed",
        "duration_s": int(time.time() - run_started_ts)
    }
    if head_commit:
        log_entry["head_commit"] = head_commit
    append_run_log(log_entry)

    step = 5
    log_step_start(step)
    persist_ok, persist_detail = persist_state_to_git()
    if not persist_ok:
        log_step_fail(step, persist_detail)
        set_status(step, "失败", persist_detail)
        print_summary()
        sys.exit(2)
    log_step_ok(step, persist_detail)
    set_status(step, "成功", persist_detail)

    print_summary()
