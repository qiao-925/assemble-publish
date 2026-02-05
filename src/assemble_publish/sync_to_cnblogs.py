# sync_to_cnblogs.py
#
# 博客园文章发布脚本
#
# 【功能说明】
# 将本地 Markdown 文件发布到博客园（单向：本地 → 博客园）。
#
# 【环境变量配置】
# 使用前需要设置以下环境变量（通过 .env 文件或系统环境变量）：
#   - CNBLOGS_RPC_URL: 博客园 RPC 地址（必需）
#   - CNBLOGS_USERNAME: 用户名（必需）
#   - CNBLOGS_TOKEN: Token（必需）
#
# 【无状态说明】
# - 不写入任何本地记录/状态文件
# - 每次运行仅基于 API 最近 300 篇判断是否更新或新建

import os
import sys
import re
import time
import xmlrpc.client
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

# 支持直接执行和作为模块导入
try:
    from .common import logger
except ImportError:
    # 直接执行时，添加 src 目录到路径
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from assemble_publish.common import logger


class DailyLimitReached(Exception):
    """博客园当日发布数量达到上限"""

# 加载 .env 文件中的环境变量
load_dotenv()

# --- 配置信息（仅保留必需项） ---
RPC_URL = os.getenv("CNBLOGS_RPC_URL")
USERNAME = os.getenv("CNBLOGS_USERNAME")
PASSWORD = os.getenv("CNBLOGS_TOKEN")


# 下面为固定默认值，不对外暴露配置
BLOG_ID = None  # 自动获取
KNOWLEDGE_BASE_URL = "https://assemble.gitbook.io/assemble"
CNBLOGS_SEARCH_URL = "https://zzk.cnblogs.com/my/s/blogpost-p"
RECENT_POSTS_MAP: dict[str, str] = {}

# --- Git / 运行环境小优化 ---
# 避免在无交互环境（Zeabur/Cron）里 git push 触发凭据交互卡死
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

# --- 行为开关 ---
FORCE_OVERWRITE_EXISTING = True

# --- 仓库根目录（支持外部传入） ---
REPO_ROOT = Path.cwd().resolve()

SYNC_STEPS = [
    "准备",
    "获取最近文章映射",
    "生成待发布列表",
    "发布/更新文章",
]


def log_plan():
    logger.info("执行计划（同步流程）：")
    for i, title in enumerate(SYNC_STEPS, 1):
        logger.info(f"  {i}. {title}")


def log_step_start(step_index: int) -> None:
    logger.info(f"[{step_index}/{len(SYNC_STEPS)}] {SYNC_STEPS[step_index - 1]}")


def log_step_ok(step_index: int, detail: str | None = None) -> None:
    title = SYNC_STEPS[step_index - 1]
    if detail:
        logger.info(f"✅ {title}：{detail}")
    else:
        logger.info(f"✅ {title} 完成")


def log_step_skip(step_index: int, detail: str | None = None) -> None:
    title = SYNC_STEPS[step_index - 1]
    if detail:
        logger.info(f"⏭️ {title}：{detail}")
    else:
        logger.info(f"⏭️ {title} 跳过")


def log_step_fail(step_index: int, detail: str) -> None:
    title = SYNC_STEPS[step_index - 1]
    logger.error(f"❌ {title} 失败：{detail}")

# --- 需要排除的目录（不扫描这些目录下的文件） ---
EXCLUDE_DIRS = {'.git', '.github', 'node_modules', '__pycache__', '.vscode', '.idea', 'cnblogs_sync', '.cnblogs_sync'}

# --- 函数定义 ---

def find_all_markdown_files(root_dir=None):
    """递归查找仓库中所有的 Markdown 文件"""
    if root_dir is None:
        root_dir = REPO_ROOT

    root_path = Path(root_dir).resolve()
    md_files = []

    logger.info(f"🔍 开始扫描 Markdown 文件（从 {root_path} 开始）...")

    for file_path in root_path.rglob('*.md'):
        relative_path = file_path.relative_to(root_path)
        path_parts = relative_path.parts

        if any(part in EXCLUDE_DIRS for part in path_parts):
            continue

        md_files.append(str(file_path))

    md_files.sort()
    logger.info(f"✅ 找到 {len(md_files)} 个 Markdown 文件")
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

def get_blog_id(server):
    """自动获取 BLOG_ID"""
    try:
        blogs = server.blogger.getUsersBlogs('', USERNAME, PASSWORD)
        if blogs and len(blogs) > 0:
            blog = blogs[0] or {}
            blog_id = blog.get('blogid') or blog.get('blogId') or blog.get('id')
            return str(blog_id) if blog_id is not None else None
    except Exception as e:
        logger.warning(f"自动获取 BLOG_ID 失败: {e}")
    return None

def fetch_recent_posts_map(server, limit=300):
    """获取最近文章映射（标题 -> post_id），仅用于本次运行。失败时抛出异常。"""
    recent_posts = server.metaWeblog.getRecentPosts(BLOG_ID, USERNAME, PASSWORD, limit)

    mapping = {}
    for post in (recent_posts or []):
        title = post.get('title', '').strip()
        post_id = post.get('postid')
        if title and post_id:
            mapping[title] = post_id
    return mapping

PostResult = Literal["created", "updated", "skipped", "failed"]


def post_to_cnblogs(title, content, categories=None) -> PostResult:
    """发布文章到博客园，基于最近文章映射判断是否已存在"""
    knowledge_base_url = f"{KNOWLEDGE_BASE_URL}?q={title}"
    prepend_content = f"> 关联知识库：<a href=\"{knowledge_base_url}\">{title}</a>\r\n\r\n"

    processed_body = replace_internal_md_links(content)
    final_content = prepend_content + processed_body

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

    try:
        server = xmlrpc.client.ServerProxy(RPC_URL)
        existing_post_id = RECENT_POSTS_MAP.get(title)

        if existing_post_id:
            if FORCE_OVERWRITE_EXISTING:
                logger.info(f"ℹ️ 最近文章中已存在 '{title}'（Post ID: {existing_post_id}），强制覆盖...")
                success = server.metaWeblog.editPost(existing_post_id, USERNAME, PASSWORD, post_data, post_data['publish'])
                if success:
                    logger.info(f"✅ 成功更新文章 '{title}'，Post ID: {existing_post_id}")
                    RECENT_POSTS_MAP[title] = existing_post_id
                    return "updated"
                else:
                    logger.error(f"❌ 更新文章 '{title}' 失败")
                    return "failed"
            else:
                logger.info(f"ℹ️ 最近文章中已存在 '{title}'（Post ID: {existing_post_id}），跳过发布")
                return "skipped"
        else:
            logger.info(f"📄 文章 '{title}' 不在最近文章中，将创建新文章")
            new_post_id = server.metaWeblog.newPost(BLOG_ID, USERNAME, PASSWORD, post_data, post_data['publish'])
            logger.info(f"✅ 成功发布新文章 '{title}'，文章ID: {new_post_id}")
            RECENT_POSTS_MAP[title] = new_post_id
            return "created"

    except xmlrpc.client.Fault as e:
        msg = str(e)
        if "当日博文发布数量" in msg or "超出当日博文发布数量" in msg:
            raise DailyLimitReached(msg)
        logger.error(f"❌ 发布或更新文章 '{title}' 时发生错误: {e}")
        return "failed"
    except Exception as e:
        logger.error(f"❌ 发布或更新文章 '{title}' 时发生错误: {e}")
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

    if missing_vars:
        logger.error("❌ 环境变量缺失，无法继续：")
        for var in missing_vars:
            logger.error(f"  - {var}")
        logger.error("请检查 .env 或系统环境变量后再运行。")
        sys.exit(1)

    log_plan()
    step_status = ["未开始"] * len(SYNC_STEPS)

    def set_status(step_index: int, status: str, detail: str | None = None) -> None:
        if detail:
            step_status[step_index - 1] = f"{status}：{detail}"
        else:
            step_status[step_index - 1] = status

    def print_summary() -> None:
        logger.info("执行结果：")
        for i, title in enumerate(SYNC_STEPS, 1):
            logger.info(f"  {i}. {title} -> {step_status[i - 1]}")

    # Step 1: prepare
    step = 1
    log_step_start(step)
    server = xmlrpc.client.ServerProxy(RPC_URL)
    if not BLOG_ID:
        try:
            BLOG_ID = get_blog_id(server)
            if BLOG_ID:
                logger.info(f"✅ 自动获取到 BLOG_ID: {BLOG_ID}")
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
    step1_detail = f"BLOG_ID={BLOG_ID}"
    log_step_ok(step, step1_detail)
    set_status(step, "成功", step1_detail)

    # Step 2: fetch recent posts map
    step = 2
    log_step_start(step)
    RECENT_POSTS_MAP.clear()
    try:
        RECENT_POSTS_MAP.update(fetch_recent_posts_map(server, limit=300))
    except Exception as e:
        log_step_fail(step, f"获取最近文章失败: {e}")
        set_status(step, "失败", "API 调用失败")
        print_summary()
        sys.exit(1)
    record_count = len(RECENT_POSTS_MAP)
    record_detail = f"已获取最近 {record_count} 篇文章"
    log_step_ok(step, record_detail)
    set_status(step, "成功", record_detail)

    # Step 3: build publish list
    step = 3
    log_step_start(step)
    run_mode = "full"
    if len(sys.argv) > 1:
        files_to_publish = sys.argv[1:]
        logger.info(f"  - 手动模式：指定 {len(files_to_publish)} 个文件")
        run_mode = "manual"
    else:
        files_to_publish = find_all_markdown_files()
        if not files_to_publish:
            log_step_ok(step, "未找到 Markdown 文件")
            set_status(step, "跳过", "未找到 Markdown 文件")
            print_summary()
            sys.exit(0)
        logger.info(f"  - 全量扫描：共 {len(files_to_publish)} 个 Markdown 文件")

    list_detail = f"模式={run_mode}，候选={len(files_to_publish)}"
    log_step_ok(step, list_detail)
    set_status(step, "成功", list_detail)

    # Step 4: publish
    step = 4
    log_step_start(step)
    SUCCESS_BATCH_SIZE_SMALL = 5
    SUCCESS_REST_SECONDS_SMALL = 3
    SUCCESS_BATCH_SIZE_LARGE = 20
    SUCCESS_REST_SECONDS_LARGE = 10

    success_count = 0
    skipped_count = 0
    failed_count = 0
    missing_count = 0

    daily_limit_reached = False
    processed = 0

    for idx, md_file in enumerate(files_to_publish, 1):
        if not os.path.exists(md_file):
            logger.warning(f"⚠️ 文件不存在，跳过: '{md_file}'")
            failed_count += 1
            missing_count += 1
            continue

        logger.info(f"[{idx}/{len(files_to_publish)}] 处理文件: {md_file}")
        post_title = os.path.basename(md_file).replace('.md', '')
        post_content = get_file_content(md_file)

        try:
            result = post_to_cnblogs(post_title, post_content)
        except DailyLimitReached as e:
            logger.error(f"❌ 检测到博客园当日发布额度已用尽，停止本次同步：{e}")
            processed = idx - 1
            daily_limit_reached = True
            break

        if result in {"created", "updated"}:
            success_count += 1
            if success_count % SUCCESS_BATCH_SIZE_SMALL == 0:
                logger.info(f"⏳ 已处理 {success_count} 篇，休息 {SUCCESS_REST_SECONDS_SMALL}s...")
                time.sleep(SUCCESS_REST_SECONDS_SMALL)
                logger.info("✅ 继续同步...")

            if success_count % SUCCESS_BATCH_SIZE_LARGE == 0:
                logger.info(f"⏳ 已处理 {success_count} 篇，休息 {SUCCESS_REST_SECONDS_LARGE}s...")
                time.sleep(SUCCESS_REST_SECONDS_LARGE)
                logger.info("✅ 继续同步...")
        elif result == "skipped":
            skipped_count += 1
        else:
            failed_count += 1
        processed = idx

    total = len(files_to_publish)
    if daily_limit_reached:
        step4_detail = (
            f"因当日发布额度用尽已停止；成功={success_count}，跳过={skipped_count}，失败={failed_count}，已处理={processed}/{total}"
        )
    else:
        step4_detail = (
            f"成功={success_count}，跳过={skipped_count}，失败={failed_count}，总计={total}"
        )
    if missing_count:
        step4_detail += f"，缺失={missing_count}"
    log_step_ok(step, step4_detail)
    step4_status = "成功" if (failed_count == 0 and not daily_limit_reached) else "部分失败"
    set_status(step, step4_status, step4_detail)

    print_summary()
