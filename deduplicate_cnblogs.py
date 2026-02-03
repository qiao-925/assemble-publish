# deduplicate_cnblogs.py
# -*- coding: utf-8 -*-
# 修复性脚本，不在主流程中调用

import os
import sys
import time
import json
import xmlrpc.client
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

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
RPC_URL = os.getenv("CNBLOGS_RPC_URL")
USERNAME = os.getenv("CNBLOGS_USERNAME")
TOKEN = os.getenv("CNBLOGS_TOKEN")
# BLOG_ID 可以从环境变量读取，如果没有则通过 API 自动获取
BLOG_ID = None  # 自动获取

# 可选：同步脚本的发布记录文件（用于去重后修正本地记录，避免 record 指向被删的 post_id）
REPO_ROOT = Path.cwd().resolve()
SYNC_RECORD_PATH = ".cnblogs_sync/.cnblogs_sync_record.json"
SYNC_RECORD_FILE = Path(SYNC_RECORD_PATH)
if not SYNC_RECORD_FILE.is_absolute():
    SYNC_RECORD_FILE = (REPO_ROOT / SYNC_RECORD_FILE).resolve()

# 说明：本脚本会“删除”博客园上的重复文章；同时会尝试把本地发布记录（SYNC_RECORD_PATH）修正为保留的 post_id。

def load_sync_record():
    """加载同步脚本的发布记录（不存在则返回 None）"""
    if not SYNC_RECORD_FILE.exists():
        return None
    try:
        return json.loads(SYNC_RECORD_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ 加载发布记录文件失败，将跳过更新: {SYNC_RECORD_FILE} ({e})")
        return None

def save_sync_record(record):
    """保存同步脚本的发布记录"""
    try:
        SYNC_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
        SYNC_RECORD_FILE.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"✅ 已更新发布记录文件: {SYNC_RECORD_FILE}")
        return True
    except Exception as e:
        print(f"⚠️ 写入发布记录文件失败: {SYNC_RECORD_FILE} ({e})")
        return False

# --- 配置选项 ---
KEEP_LATEST = True  # True: 保留最新的，删除旧的；False: 保留最早的，删除新的
DRY_RUN = False  # True: 只显示将要删除的文章，不实际删除；False: 实际执行删除
SHOW_DETAILS = False  # True: 显示详细的处理过程；False: 只显示统计和列表
DELETE_DELAY = 0  # 删除操作之间的延迟（秒），0 表示无延迟

def get_blog_id(server):
    """通过 API 获取博客ID"""
    try:
        blogs = server.blogger.getUsersBlogs('', USERNAME, TOKEN)
        if blogs and len(blogs) > 0:
            blog_id = blogs[0].get('blogid')
            print(f"✅ 获取到博客ID: {blog_id}")
            return blog_id
        else:
            print("⚠️ 未找到博客信息")
            return None
    except Exception as e:
        print(f"⚠️ 获取博客ID时出错: {e}")
        return None

def normalize_title(title):
    """标准化标题，用于匹配（去除首尾空格）"""
    return title.strip() if title else ""

def get_all_posts(server, max_posts=300):
    """获取所有文章（getRecentPosts API 极限是 300 篇，不支持分页）"""
    all_posts = []
    all_post_ids = set()  # 用于去重
    
    # API 极限是 300，超过 300 也没用
    request_count = min(max_posts, 300)
    
    print(f"📥 开始获取文章列表（请求 {request_count} 篇，API 极限是 300 篇）...")
    
    try:
        posts = server.metaWeblog.getRecentPosts(BLOG_ID, USERNAME, TOKEN, request_count)
        
        if posts:
            # 使用 postid 去重，避免重复添加
            for post in posts:
                post_id = post.get('postid')
                if post_id and post_id not in all_post_ids:
                    all_posts.append(post)
                    all_post_ids.add(post_id)
            
            print(f"  ✓ API 返回 {len(posts)} 篇文章")
            print(f"  ✓ 去重后得到 {len(all_posts)} 篇不重复文章")
            
            # 如果返回的文章数正好是 300，提示可能还有更多文章
            if len(posts) == 300:
                print(f"  ⚠️ 注意：返回了 300 篇文章（API 极限），可能还有更早的文章未获取")
                print(f"  💡 提示：如果文章总数超过 300，需要删除部分文章后才能获取到更早的文章")
        else:
            print("  ℹ️ 未获取到任何文章")
            
    except Exception as e:
        print(f"⚠️ 获取文章时出错: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"✅ 共获取 {len(all_posts)} 篇不重复文章\n")
    return all_posts

def find_duplicates(posts):
    """找出重复的文章，按标题分组"""
    title_groups = defaultdict(list)
    
    for post in posts:
        title = normalize_title(post.get('title', ''))
        if title:
            title_groups[title].append(post)
    
    # 找出有重复的标题
    duplicates = {title: posts_list for title, posts_list in title_groups.items() if len(posts_list) > 1}
    
    return duplicates

def parse_date(date_value):
    """解析日期值，返回 datetime 对象用于比较"""
    try:
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            # 尝试解析常见格式
            for fmt in ['%Y%m%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z']:
                try:
                    return datetime.strptime(date_value, fmt)
                except:
                    continue
        # 如果是其他类型，尝试转换
        return datetime.fromisoformat(str(date_value)) if hasattr(datetime, 'fromisoformat') else datetime.now()
    except:
        # 如果解析失败，返回一个很早的日期，这样会被排到最后
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
        # 根据 API 文档：blogger.deletePost(appKey, postid, username, password, publish)
        # appKey 可以为空字符串，publish 设为 True
        print(f"      📞 调用删除接口:")
        print(f"         方法: blogger.deletePost")
        print(f"         参数: appKey='', postid='{post_id}', username='{USERNAME}', password='***', publish=True")
        print(f"         RPC URL: {RPC_URL}")
        
        result = server.blogger.deletePost('', post_id, USERNAME, TOKEN, True)
        
        print(f"      📥 接口返回: {result}")
        print(f"         返回值类型: {type(result).__name__}")
        print(f"         返回值内容: {repr(result)}")
        
        # 检查返回值
        if result is True or result == True:
            print(f"      ✅ 接口返回 True，表示删除成功")
            return True
        elif result is False or result == False:
            print(f"      ❌ 接口返回 False，表示删除失败")
            return False
        else:
            print(f"      ⚠️ 接口返回了意外的值: {result}")
            return False
            
    except Exception as e:
        print(f"      ❌ 接口调用失败:")
        print(f"         错误类型: {type(e).__name__}")
        print(f"         错误信息: {e}")
        import traceback
        print(f"      📋 错误堆栈:")
        for line in traceback.format_exc().split('\n')[:5]:
            if line.strip():
                print(f"         {line}")
        return False

def deduplicate_one_round(server):
    """执行一轮去重，返回是否还有重复文章"""
    global BLOG_ID

    sync_record = load_sync_record()
    updated_record = False
    
    # 1. 获取所有文章（API 极限是 300 篇）
    all_posts = get_all_posts(server, max_posts=300)
    
    if not all_posts:
        print("ℹ️ 没有找到任何文章。")
        return False  # 没有文章，不需要继续
    
    # 2. 找出重复的文章
    duplicates = find_duplicates(all_posts)
    
    # 统计信息
    total_posts = len(all_posts)
    duplicate_titles_count = len(duplicates)
    duplicate_posts_count = sum(len(posts) for posts in duplicates.values())
    unique_posts_count = total_posts - duplicate_posts_count + duplicate_titles_count  # 不重复的文章数（每组算1篇）
    
    print("=" * 80)
    print("📊 文章统计信息")
    print("=" * 80)
    print(f"总文章数: {total_posts} 篇")
    print(f"不重复文章: {unique_posts_count} 篇")
    print(f"重复标题数: {duplicate_titles_count} 个")
    print(f"重复文章总数: {duplicate_posts_count} 篇")
    print(f"将删除文章数: {duplicate_posts_count - duplicate_titles_count} 篇")
    print()
    
    if not duplicates:
        print("✅ 没有发现重复文章！")
        return False  # 没有重复，不需要继续
    
    # 3. 列出所有重复标题
    print("=" * 80)
    print("📋 重复标题详细列表（按重复数量排序）")
    print("=" * 80)
    
    # 按重复数量排序
    sorted_duplicates = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)
    
    for idx, (title, posts_list) in enumerate(sorted_duplicates, 1):
        print(f"{idx:3d}. [{len(posts_list)} 篇重复] {title}")
        # 显示前5篇文章的ID
        show_count = min(5, len(posts_list))
        post_ids = [str(post.get('postid', 'N/A')) for post in posts_list[:show_count]]
        print(f"     文章ID示例: {', '.join(post_ids)}")
        if len(posts_list) > 5:
            print(f"     ... 还有 {len(posts_list) - 5} 篇")
    
    print()
    
    print("=" * 80)
    print("🔍 开始处理重复文章...")
    print("=" * 80)
    print()
    
    # 4. 处理每个重复组（优先保留最新的）
    total_to_delete = 0
    total_kept = 0
    total_deleted = 0
    total_failed = 0
    
    for title, posts_list in duplicates.items():
        print(f"📄 标题: {title}")
        print(f"   重复数量: {len(posts_list)} 篇")
        
        # 按日期排序（优先保留最新的）
        try:
            # 使用 parse_date 函数正确解析和比较时间
            posts_list.sort(key=lambda p: parse_date(p.get('dateCreated', p.get('pubDate', ''))), reverse=KEEP_LATEST)
        except:
            # 如果排序失败，按 postid 排序（通常 postid 越大越新）
            try:
                posts_list.sort(key=lambda p: int(p.get('postid', 0)), reverse=KEEP_LATEST)
            except:
                pass
        
        # 保留第一篇（最新的），删除其余的（旧的）
        keep_post = posts_list[0]
        delete_posts = posts_list[1:]
        
        print(f"   ✓ 保留: Post ID {keep_post.get('postid')} (创建时间: {format_date(keep_post.get('dateCreated', keep_post.get('pubDate', 'N/A')))})")

        # 如果存在本地发布记录文件，顺手把该标题的 post_id 修正为“保留的那篇”
        if sync_record is not None and not DRY_RUN:
            keep_id = keep_post.get('postid')
            if keep_id is not None:
                sync_record[title] = keep_id
                updated_record = True
        
        for post in delete_posts:
            post_id = post.get('postid')
            post_date = format_date(post.get('dateCreated', post.get('pubDate', 'N/A')))
            
            if DRY_RUN:
                print(f"   🗑️  [模拟] 将删除: Post ID {post_id} (创建时间: {post_date})")
                total_to_delete += 1
            else:
                print(f"   🗑️  正在删除: Post ID {post_id} (创建时间: {post_date})")
                print(f"      标题: {title[:60]}{'...' if len(title) > 60 else ''}")
                success = delete_post(server, post_id, title)
                if success:
                    print(f"      ✅ 删除成功")
                    total_deleted += 1
                else:
                    print(f"      ❌ 删除失败")
                    total_failed += 1
                total_to_delete += 1
                if DELETE_DELAY > 0:
                    time.sleep(DELETE_DELAY)
                print()  # 空行分隔
        
        total_kept += 1
        print()  # 空行分隔每个标题组
    
    # 5. 总结
    print("=" * 60)
    if DRY_RUN:
        print(f"📊 [模拟模式] 统计:")
        print(f"   - 将保留: {total_kept} 篇文章（每组保留1篇最新的）")
        print(f"   - 将删除: {total_to_delete} 篇重复文章（旧的）")
        print(f"\n💡 提示: 将 DRY_RUN 设置为 False 后重新运行以实际执行删除")
    else:
        print(f"📊 统计:")
        print(f"   - 已保留: {total_kept} 篇文章（每组保留1篇最新的）")
        print(f"   - 已删除: {total_deleted} 篇重复文章（旧的）")
        if total_failed > 0:
            print(f"   - 删除失败: {total_failed} 篇")
    print("=" * 60)
    print()

    # 去重完成后，若有本地发布记录文件，则落盘一次（避免 record 指向被删的 post_id）
    if sync_record is not None:
        if DRY_RUN:
            print(f"ℹ️ DRY_RUN=true：未更新发布记录文件: {SYNC_RECORD_FILE}")
        elif updated_record:
            save_sync_record(sync_record)
    
    return True  # 有重复，已处理

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
        print("❌ 错误：以下环境变量未设置：")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n💡 请创建 .env 文件并设置这些变量，或通过环境变量直接设置。")
        print("   BLOG_ID 可以从环境变量读取，如果没有则通过 API 自动获取。")
        sys.exit(1)
    
    try:
        server = xmlrpc.client.ServerProxy(RPC_URL)
        
        # 如果 BLOG_ID 未设置，自动获取
        if not BLOG_ID:
            BLOG_ID = get_blog_id(server)
            if not BLOG_ID:
                print("❌ 无法获取博客ID，退出。")
                sys.exit(1)
            print()
        
        # 迭代模式：循环执行直到没有重复文章
        round_num = 1
        max_rounds = 50  # 防止无限循环
        
        while round_num <= max_rounds:
            print("=" * 80)
            print(f"🔄 第 {round_num} 轮去重")
            print("=" * 80)
            print()
            
            # 检查是否有重复
            has_duplicates = deduplicate_one_round(server)
            
            if not has_duplicates:
                print("=" * 80)
                print(f"✅ 完成！经过 {round_num} 轮去重，已无重复文章")
                print("=" * 80)
                break
            
            # 如果有重复，继续下一轮
            round_num += 1
            if round_num <= max_rounds:
                print(f"⏳ 等待 2 秒后开始下一轮...")
                time.sleep(2)
                print()
        
        if round_num > max_rounds:
            print("=" * 80)
            print(f"⚠️ 已达到最大轮数限制 ({max_rounds} 轮），停止迭代")
            print("=" * 80)
        
    except Exception as e:
        print(f"❌ 执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 博客园文章去重工具")
    print(f"   模式: {'模拟运行' if DRY_RUN else '实际删除'}")
    print(f"   策略: {'保留最新' if KEEP_LATEST else '保留最早'}")
    print()
    
    deduplicate_posts()
