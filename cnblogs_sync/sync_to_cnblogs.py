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
#   - CNBLOGS_BLOG_ID: 博客 ID（可选，未设置时会自动获取）
#   - CNBLOGS_USERNAME: 用户名（必需）
#   - CNBLOGS_TOKEN: Token（必需；兼容 CNBLOGS_PASSWORD）
#   - CNBLOGS_PASSWORD: 密码（可选；作为 CNBLOGS_TOKEN 的别名）
#   - KNOWLEDGE_BASE_URL: 知识库基础 URL（可选，默认：https://assemble.gitbook.io/assemble）
#   - CNBLOGS_SEARCH_URL: 博客园站内搜索 URL（可选，默认：https://zzk.cnblogs.com/my/s/blogpost-p）
#   - INCREMENTAL_SYNC: 是否启用增量同步（默认 True）
#   - SYNC_STATE_GIT: 是否将状态写回 Git 分支（默认 True）
#   - SYNC_STATE_BRANCH: 状态分支名（默认 sync-state）
#   - SYNC_STATE_REMOTE: 远端名（默认 origin）
#   - SYNC_STATE_REMOTE_URL: 远端地址（可选，用于写回 PAT URL）
#   - SYNC_REPO_ROOT: 目标仓库根目录（可选）
#   - SYNC_RECORD_PATH: 记录文件相对仓库路径（可选）
#   - SYNC_STATE_PATH: 状态文件相对仓库路径（可选）
#   - SYNC_RUN_LOG_PATH: 运行记录文件相对仓库路径（可选）
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
#          - 如果文章已在本地记录中（已发布过），根据 FORCE_OVERWRITE_EXISTING 开关决定是否更新
#          - 如果是新文章，直接发布并自动更新本地记录
#          - 自动模式会排除 .git、.github、node_modules、cnblogs_sync 等目录
#
# 【配置选项】
# - FORCE_OVERWRITE_EXISTING: 是否更新已存在的文章（默认 True）
#   设置为 True 时，已存在的文章会被更新；False 时跳过已存在的文章
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
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
# from urllib.parse import quote # 不再需要这个模块，可以移除

# 加载 .env 文件中的环境变量
load_dotenv()

# --- 配置信息 ---
RPC_URL = os.getenv("CNBLOGS_RPC_URL")
BLOG_ID = os.getenv("CNBLOGS_BLOG_ID")
USERNAME = os.getenv("CNBLOGS_USERNAME")
PASSWORD = os.getenv("CNBLOGS_TOKEN") or os.getenv("CNBLOGS_PASSWORD")
# 知识库和博客园搜索 URL 配置
KNOWLEDGE_BASE_URL = os.getenv("KNOWLEDGE_BASE_URL", "https://assemble.gitbook.io/assemble")
CNBLOGS_SEARCH_URL = os.getenv("CNBLOGS_SEARCH_URL", "https://zzk.cnblogs.com/my/s/blogpost-p")

# --- Git / 运行环境小优化 ---
# 避免在无交互环境（Zeabur/Cron）里 git push 触发凭据交互卡死
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

# --- 行为开关 ---
FORCE_OVERWRITE_EXISTING = os.getenv("FORCE_OVERWRITE_EXISTING", "true").lower() in {"1", "true", "yes", "y", "on"}

# --- 仓库根目录（支持外部传入） ---
REPO_ROOT = Path(os.getenv("SYNC_REPO_ROOT", Path(__file__).parent.parent)).resolve()

# --- 记录/状态文件路径（默认相对仓库根目录） ---
SYNC_RECORD_PATH = os.getenv(
    "SYNC_RECORD_PATH",
    ".cnblogs_sync/.cnblogs_sync_record.json"
)
SYNC_STATE_PATH = os.getenv(
    "SYNC_STATE_PATH",
    ".cnblogs_sync/state.json"
)
SYNC_RUN_LOG_PATH = os.getenv(
    "SYNC_RUN_LOG_PATH",
    ".cnblogs_sync/run_history.jsonl"
)

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
INCREMENTAL_SYNC = os.getenv("INCREMENTAL_SYNC", "true").lower() in {"1", "true", "yes", "y"}
SYNC_STATE_GIT = os.getenv("SYNC_STATE_GIT", "true").lower() in {"1", "true", "yes", "y"}
SYNC_STATE_BRANCH = os.getenv("SYNC_STATE_BRANCH", "sync-state")
SYNC_STATE_REMOTE = os.getenv("SYNC_STATE_REMOTE", "origin")
SYNC_STATE_REMOTE_URL = os.getenv("SYNC_STATE_REMOTE_URL")

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

def restore_state_from_git():
    """从专用分支恢复状态文件（记录 + 增量状态）"""
    if not SYNC_STATE_GIT:
        return
    if not is_git_repo():
        print("⚠️ 当前目录不是 Git 仓库，无法从分支恢复状态")
        return

    try:
        ensure_remote(SYNC_STATE_REMOTE, SYNC_STATE_REMOTE_URL)
        if not has_remote(SYNC_STATE_REMOTE):
            print(f"⚠️ 未找到 remote '{SYNC_STATE_REMOTE}'，请设置 SYNC_STATE_REMOTE_URL（带 PAT）或仅本地测试时设置 SYNC_STATE_GIT=false")
            return
        run_git(["fetch", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], check=True)
    except Exception as e:
        print(f"⚠️ 拉取分支失败，跳过状态恢复：{e}")
        return

    for path in [SYNC_RECORD_FILE, SYNC_STATE_FILE, SYNC_RUN_LOG_FILE]:
        try:
            rel_path = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            print(f"⚠️ 状态文件不在仓库内，跳过恢复: {path}")
            continue
        result = run_git(["show", f"{SYNC_STATE_REMOTE}/{SYNC_STATE_BRANCH}:{rel_path}"])
        if result.returncode == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(result.stdout, encoding="utf-8")
            print(f"✅ 已从分支恢复状态文件: {rel_path}")
        else:
            print(f"ℹ️ 分支未包含状态文件: {rel_path}")

def persist_state_to_git():
    """将状态文件提交到专用分支并推送"""
    if not SYNC_STATE_GIT:
        return True
    if not is_git_repo():
        print("⚠️ 当前目录不是 Git 仓库，无法持久化状态")
        return False

    temp_dir = None
    try:
        ensure_remote(SYNC_STATE_REMOTE, SYNC_STATE_REMOTE_URL)
        if not has_remote(SYNC_STATE_REMOTE):
            print(f"⚠️ 未找到 remote '{SYNC_STATE_REMOTE}'，请设置 SYNC_STATE_REMOTE_URL（带 PAT）或仅本地测试时设置 SYNC_STATE_GIT=false")
            return False
        branch_exists = remote_branch_exists(SYNC_STATE_REMOTE, SYNC_STATE_BRANCH)
        if branch_exists:
            run_git(["fetch", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], check=True)

        temp_dir = tempfile.mkdtemp(prefix="cnblogs-sync-state-")
        if branch_exists:
            run_git(
                ["worktree", "add", "-B", SYNC_STATE_BRANCH, temp_dir, f"{SYNC_STATE_REMOTE}/{SYNC_STATE_BRANCH}"],
                check=True
            )
        else:
            run_git(["worktree", "add", "-B", SYNC_STATE_BRANCH, temp_dir, "HEAD"], check=True)

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
            return True

        status = run_git(["status", "--porcelain"], cwd=temp_dir)
        if not status.stdout.strip():
            print("ℹ️ 状态文件无变化，无需提交")
            return True

        run_git(["add"] + rel_paths, cwd=temp_dir, check=True)
        ensure_git_identity(temp_dir)
        commit_msg = f"chore: update cnblogs sync state ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        run_git(["commit", "-m", commit_msg], cwd=temp_dir, check=True)
        run_git(["push", SYNC_STATE_REMOTE, SYNC_STATE_BRANCH], cwd=temp_dir, check=True)
        print(f"✅ 状态已推送到分支: {SYNC_STATE_BRANCH}")
        return True
    except Exception as e:
        print(f"❌ 持久化状态失败: {e}")
        return False
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
        with open(SYNC_RECORD_FILE, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存发布记录文件时出错: {e}")

def get_blog_id(server):
    """自动获取 BLOG_ID（CNBLOGS_BLOG_ID）"""
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
                print("❌ 错误：CNBLOGS_BLOG_ID 未设置且无法自动获取，请手动设置 CNBLOGS_BLOG_ID")
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

def post_to_cnblogs(title, content, categories=None):
    """发布文章到博客园，基于本地记录判断是否已存在
    返回 True 表示成功发布/更新，False 表示跳过或失败"""
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
                    return True  # 成功更新
                else:
                    print(f"❌ 更新文章 '{title}' 失败")
                    return False  # 更新失败
            else:
                print(f"ℹ️ 本地记录显示文章 '{title}' 已存在（Post ID: {existing_post_id}），跳过发布")
                return False  # 跳过，不算成功发布
        else:
            print(f"📄 文章 '{title}' 不在本地记录中，将创建新文章")
            new_post_id = server.metaWeblog.newPost(BLOG_ID, USERNAME, PASSWORD, post_data, post_data['publish'])
            print(f"✅ 成功发布新文章 '{title}'，文章ID: {new_post_id}")
            
            # 更新本地记录（始终更新）
            sync_record[title] = new_post_id
            save_sync_record(sync_record)
            return True  # 成功发布

    except Exception as e:
        print(f"❌ 发布或更新文章 '{title}' 时发生严重错误: {e}")
        return False  # 发布失败

# --- 主逻辑 ---
if __name__ == "__main__":
    run_started_ts = time.time()
    missing_vars = []
    if not RPC_URL:
        missing_vars.append("CNBLOGS_RPC_URL")
    if not USERNAME:
        missing_vars.append("CNBLOGS_USERNAME")
    if not PASSWORD:
        missing_vars.append("CNBLOGS_TOKEN / CNBLOGS_PASSWORD")
    
    if missing_vars:
        print("❌ 错误：以下环境变量未设置：")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n💡 请创建 .env 文件并设置这些变量，或通过环境变量直接设置。")
        sys.exit(1)

    # 如果开启 Git 状态持久化，先尝试恢复状态文件
    restore_state_from_git()

    # BLOG_ID 可选：未设置则尝试自动获取
    if not BLOG_ID:
        try:
            server = xmlrpc.client.ServerProxy(RPC_URL)
            BLOG_ID = get_blog_id(server)
            if BLOG_ID:
                print(f"✅ 自动获取到 BLOG_ID: {BLOG_ID}")
            else:
                print("❌ 错误：CNBLOGS_BLOG_ID 未设置且无法自动获取，请手动设置 CNBLOGS_BLOG_ID")
                sys.exit(1)
        except Exception as e:
            print(f"❌ 自动获取 BLOG_ID 失败: {e}")
            sys.exit(1)

    # 自动初始化：没有发布记录时先生成（避免重复创建文章）
    if not SYNC_RECORD_FILE.exists():
        print("ℹ️ 未发现发布记录，开始自动初始化...")
        ok = init_sync_record()
        if not ok:
            sys.exit(1)
        if not persist_state_to_git():
            sys.exit(2)

    # 读取增量同步状态
    sync_state = load_sync_state()
    head_commit = get_head_commit()
    last_synced_commit = sync_state.get("last_synced_commit")

    # 确定要发布的文件列表
    run_mode = "full"
    manual_mode = len(sys.argv) > 1

    if len(sys.argv) > 1:
        # 手动模式：使用命令行参数指定的文件
        files_to_publish = sys.argv[1:]
        print(f"📝 手动模式：准备发布 {len(files_to_publish)} 个指定文件")
        run_mode = "manual"
    else:
        files_to_publish = None
        if INCREMENTAL_SYNC:
            changed_files = get_changed_markdown_files(last_synced_commit, head_commit)
            if changed_files is not None:
                files_to_publish = changed_files
                run_mode = "incremental"
                print(f"🧩 增量模式：找到 {len(files_to_publish)} 个变更 Markdown 文件")

        if files_to_publish is None:
            # 自动模式：扫描仓库中所有 Markdown 文件
            files_to_publish = find_all_markdown_files()
            if not files_to_publish:
                print("⚠️ 未找到任何 Markdown 文件")
                sys.exit(0)
            print(f"🤖 全量模式：找到 {len(files_to_publish)} 个 Markdown 文件，准备发布")

    print()

    # 增量模式且没有变更时，直接更新状态并退出
    if run_mode == "incremental" and not files_to_publish:
        print("ℹ️ 未检测到 Markdown 变更，跳过发布")
        if head_commit:
            sync_state["last_synced_commit"] = head_commit
        sync_state["last_run_at"] = datetime.now().isoformat(timespec="seconds")
        sync_state["last_run_mode"] = run_mode
        sync_state["last_total_candidates"] = 0
        sync_state["last_published_count"] = 0
        save_sync_state(sync_state)
        log_entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "mode": run_mode,
            "candidates": 0,
            "published": 0,
            "status": "no_change",
            "duration_s": int(time.time() - run_started_ts)
        }
        if head_commit:
            log_entry["head_commit"] = head_commit
        append_run_log(log_entry)
        if not persist_state_to_git():
            sys.exit(2)
        sys.exit(0)

    # 限流配置：基于成功发布的文章数
    SUCCESS_BATCH_SIZE_SMALL = 5  # 每成功发布5篇休息
    SUCCESS_REST_SECONDS_SMALL = 3  # 休息3秒
    
    SUCCESS_BATCH_SIZE_LARGE = 20  # 每成功发布20篇休息
    SUCCESS_REST_SECONDS_LARGE = 10  # 休息10秒
    
    success_count = 0  # 成功发布的计数器
    
    for idx, md_file in enumerate(files_to_publish, 1):
        if not os.path.exists(md_file):
            print(f"⚠️ 文件 '{md_file}' 不存在，跳过。")
            continue

        print(f"\n[{idx}/{len(files_to_publish)}] 处理文件: {md_file}")
        post_title = os.path.basename(md_file).replace('.md', '')
        post_content = get_file_content(md_file)

        success = post_to_cnblogs(post_title, post_content)
        
        # 如果成功发布，增加成功计数器
        if success:
            success_count += 1
            
            # 每成功发布 5 篇后休息 3 秒
            if success_count % SUCCESS_BATCH_SIZE_SMALL == 0:
                print(f"\n⏸️  已成功发布 {success_count} 篇文章，休息 {SUCCESS_REST_SECONDS_SMALL} 秒...")
                time.sleep(SUCCESS_REST_SECONDS_SMALL)
                print("▶️  继续发布...\n")
            
            # 每成功发布 20 篇后休息 10 秒
            if success_count % SUCCESS_BATCH_SIZE_LARGE == 0:
                print(f"\n⏸️  已成功发布 {success_count} 篇文章，休息 {SUCCESS_REST_SECONDS_LARGE} 秒...")
                time.sleep(SUCCESS_REST_SECONDS_LARGE)
                print("▶️  继续发布...\n")

    # 运行结束后更新状态（手动模式不更新 last_synced_commit）
    if run_mode != "manual" and head_commit:
        sync_state["last_synced_commit"] = head_commit
    sync_state["last_run_at"] = datetime.now().isoformat(timespec="seconds")
    sync_state["last_run_mode"] = run_mode
    sync_state["last_total_candidates"] = len(files_to_publish)
    sync_state["last_published_count"] = success_count
    save_sync_state(sync_state)
    log_entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mode": run_mode,
        "candidates": len(files_to_publish),
        "published": success_count,
        "status": "completed",
        "duration_s": int(time.time() - run_started_ts)
    }
    if head_commit:
        log_entry["head_commit"] = head_commit
    append_run_log(log_entry)

    if not persist_state_to_git():
        sys.exit(2)
