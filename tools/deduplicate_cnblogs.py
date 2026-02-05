# deduplicate_cnblogs.py
# -*- coding: utf-8 -*-

import sys
import time
import xmlrpc.client
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# 添加 src 目录到路径以导入共享模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
from assemble_publish.common import (
    logger,
    env_str,
    get_sync_record_path,
    load_sync_record,
    save_sync_record,
    get_blog_id,
)

# 加载 .env 文件中的环境变量
load_dotenv()

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# --- 配置信息 ---
RPC_URL = env_str("CNBLOGS_RPC_URL")
USERNAME = env_str("CNBLOGS_USERNAME")
TOKEN = env_str("CNBLOGS_TOKEN")
BLOG_ID = None  # 自动获取

# 同步记录文件路径
REPO_ROOT = Path.cwd().resolve()
SYNC_RECORD_FILE = get_sync_record_path(REPO_ROOT)

# --- 配置选项 ---
KEEP_LATEST = True
DRY_RUN = False
SHOW_DETAILS = False
DELETE_DELAY = 0
MAX_ROUNDS = 50


def normalize_title(title):
    """标准化标题，用于匹配（去除首尾空格）"""
    return title.strip() if title else ""


def get_all_posts(server, max_posts=300):
    """获取所有文章（getRecentPosts API 极限是 300 篇，不支持分页）"""
    all_posts = []
    all_post_ids = set()

    request_count = min(max_posts, 300)
    logger.info(f"📥 开始获取文章列表（请求 {request_count} 篇，API 极限是 300 篇）...")

    try:
        posts = server.metaWeblog.getRecentPosts(BLOG_ID, USERNAME, TOKEN, request_count)

        if posts:
            for post in posts:
                post_id = post.get('postid')
                if post_id and post_id not in all_post_ids:
                    all_posts.append(post)
                    all_post_ids.add(post_id)

            logger.info(f"  ✓ API 返回 {len(posts)} 篇文章")
            logger.info(f"  ✓ 去重后得到 {len(all_posts)} 篇不重复文章")

            if len(posts) == 300:
                logger.warning("  ⚠️ 注意：返回了 300 篇文章（API 极限），可能还有更早的文章未获取")
        else:
            logger.info("  ℹ️ 未获取到任何文章")

    except Exception as e:
        logger.error(f"获取文章时出错: {e}")
        import traceback
        traceback.print_exc()

    logger.info(f"✅ 共获取 {len(all_posts)} 篇不重复文章")
    return all_posts


def find_duplicates(posts):
    """找出重复的文章，按标题分组"""
    title_groups = defaultdict(list)

    for post in posts:
        title = normalize_title(post.get('title', ''))
        if title:
            title_groups[title].append(post)

    return {title: posts_list for title, posts_list in title_groups.items() if len(posts_list) > 1}


def parse_date(date_value):
    """解析日期值，返回 datetime 对象用于比较"""
    try:
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            for fmt in ['%Y%m%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z']:
                try:
                    return datetime.strptime(date_value, fmt)
                except:
                    continue
        return datetime.fromisoformat(str(date_value)) if hasattr(datetime, 'fromisoformat') else datetime.now()
    except:
        return datetime(1970, 1, 1)


def format_date(date_value):
    """格式化日期字符串用于显示"""
    try:
        dt = parse_date(date_value)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(date_value)


def delete_post(server, post_id, title):
    """删除指定文章（使用 blogger.deletePost）"""
    try:
        logger.debug(f"调用删除接口: blogger.deletePost, postid='{post_id}'")
        result = server.blogger.deletePost('', post_id, USERNAME, TOKEN, True)

        if result is True or result == True:
            logger.info(f"      ✅ 删除成功")
            return True
        else:
            logger.error(f"      ❌ 接口返回 False，删除失败")
            return False

    except Exception as e:
        logger.error(f"      ❌ 接口调用失败: {type(e).__name__}: {e}")
        return False


def deduplicate_one_round(server):
    """执行一轮去重，返回是否还有重复文章"""
    global BLOG_ID

    sync_record = load_sync_record(SYNC_RECORD_FILE)
    updated_record = False

    all_posts = get_all_posts(server, max_posts=300)

    if not all_posts:
        logger.info("ℹ️ 没有找到任何文章。")
        return False

    duplicates = find_duplicates(all_posts)

    total_posts = len(all_posts)
    duplicate_titles_count = len(duplicates)
    duplicate_posts_count = sum(len(posts) for posts in duplicates.values())
    unique_posts_count = total_posts - duplicate_posts_count + duplicate_titles_count

    logger.info("=" * 80)
    logger.info("📊 文章统计信息")
    logger.info("=" * 80)
    logger.info(f"总文章数: {total_posts} 篇")
    logger.info(f"不重复文章: {unique_posts_count} 篇")
    logger.info(f"重复标题数: {duplicate_titles_count} 个")
    logger.info(f"重复文章总数: {duplicate_posts_count} 篇")
    logger.info(f"将删除文章数: {duplicate_posts_count - duplicate_titles_count} 篇")

    if not duplicates:
        logger.info("✅ 没有发现重复文章！")
        return False

    logger.info("=" * 80)
    logger.info("📋 重复标题详细列表（按重复数量排序）")
    logger.info("=" * 80)

    sorted_duplicates = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)

    for idx, (title, posts_list) in enumerate(sorted_duplicates, 1):
        logger.info(f"{idx:3d}. [{len(posts_list)} 篇重复] {title}")
        show_count = min(5, len(posts_list))
        post_ids = [str(post.get('postid', 'N/A')) for post in posts_list[:show_count]]
        logger.info(f"     文章ID示例: {', '.join(post_ids)}")

    logger.info("=" * 80)
    logger.info("🔍 开始处理重复文章...")
    logger.info("=" * 80)

    total_to_delete = 0
    total_kept = 0
    total_deleted = 0
    total_failed = 0

    for title, posts_list in duplicates.items():
        logger.info(f"📄 标题: {title}")
        logger.info(f"   重复数量: {len(posts_list)} 篇")

        try:
            posts_list.sort(key=lambda p: parse_date(p.get('dateCreated', p.get('pubDate', ''))), reverse=KEEP_LATEST)
        except:
            try:
                posts_list.sort(key=lambda p: int(p.get('postid', 0)), reverse=KEEP_LATEST)
            except:
                pass

        keep_post = posts_list[0]
        delete_posts = posts_list[1:]

        logger.info(f"   ✓ 保留: Post ID {keep_post.get('postid')} (创建时间: {format_date(keep_post.get('dateCreated', keep_post.get('pubDate', 'N/A')))})")

        if sync_record is not None and not DRY_RUN:
            keep_id = keep_post.get('postid')
            if keep_id is not None:
                sync_record[title] = keep_id
                updated_record = True

        for post in delete_posts:
            post_id = post.get('postid')
            post_date = format_date(post.get('dateCreated', post.get('pubDate', 'N/A')))

            if DRY_RUN:
                logger.info(f"   🗑️  [模拟] 将删除: Post ID {post_id} (创建时间: {post_date})")
                total_to_delete += 1
            else:
                logger.info(f"   🗑️  正在删除: Post ID {post_id} (创建时间: {post_date})")
                success = delete_post(server, post_id, title)
                if success:
                    total_deleted += 1
                else:
                    total_failed += 1
                total_to_delete += 1
                if DELETE_DELAY > 0:
                    time.sleep(DELETE_DELAY)

        total_kept += 1

    logger.info("=" * 60)
    if DRY_RUN:
        logger.info(f"📊 [模拟模式] 统计:")
        logger.info(f"   - 将保留: {total_kept} 篇文章（每组保留1篇最新的）")
        logger.info(f"   - 将删除: {total_to_delete} 篇重复文章（旧的）")
        logger.info("💡 提示: 将 DRY_RUN 设置为 False 后重新运行以实际执行删除")
    else:
        logger.info(f"📊 统计:")
        logger.info(f"   - 已保留: {total_kept} 篇文章（每组保留1篇最新的）")
        logger.info(f"   - 已删除: {total_deleted} 篇重复文章（旧的）")
        if total_failed > 0:
            logger.warning(f"   - 删除失败: {total_failed} 篇")
    logger.info("=" * 60)

    if sync_record is not None:
        if DRY_RUN:
            logger.info(f"ℹ️ DRY_RUN=true：未更新发布记录文件: {SYNC_RECORD_FILE}")
        elif updated_record:
            save_sync_record(SYNC_RECORD_FILE, sync_record)

    return True


def deduplicate_posts():
    """主去重逻辑（迭代模式：直到没有重复文章）"""
    global BLOG_ID

    missing_vars = []
    if not RPC_URL:
        missing_vars.append("CNBLOGS_RPC_URL")
    if not USERNAME:
        missing_vars.append("CNBLOGS_USERNAME")
    if not TOKEN:
        missing_vars.append("CNBLOGS_TOKEN")

    if missing_vars:
        logger.error("❌ 错误：以下环境变量未设置：")
        for var in missing_vars:
            logger.error(f"   - {var}")
        logger.error("💡 请创建 .env 文件并设置这些变量，或通过环境变量直接设置。")
        sys.exit(1)

    try:
        server = xmlrpc.client.ServerProxy(RPC_URL)

        if not BLOG_ID:
            BLOG_ID = get_blog_id(server, USERNAME, TOKEN)
            if not BLOG_ID:
                logger.error("❌ 无法获取博客ID，退出。")
                sys.exit(1)

        round_num = 1
        max_rounds = MAX_ROUNDS

        while round_num <= max_rounds:
            logger.info("=" * 80)
            logger.info(f"🔄 第 {round_num} 轮去重")
            logger.info("=" * 80)

            has_duplicates = deduplicate_one_round(server)

            if not has_duplicates:
                logger.info("=" * 80)
                logger.info(f"✅ 完成！经过 {round_num} 轮去重，已无重复文章")
                logger.info("=" * 80)
                break

            round_num += 1
            if round_num <= max_rounds:
                logger.info("⏳ 等待 2 秒后开始下一轮...")
                time.sleep(2)

        if round_num > max_rounds:
            logger.warning("=" * 80)
            logger.warning(f"⚠️ 已达到最大轮数限制 ({max_rounds} 轮），停止迭代")
            logger.warning("=" * 80)

    except Exception as e:
        logger.error(f"❌ 执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("🚀 博客园文章去重工具")
    logger.info(f"   模式: {'模拟运行' if DRY_RUN else '实际删除'}")
    logger.info(f"   策略: {'保留最新' if KEEP_LATEST else '保留最早'}")
    deduplicate_posts()
