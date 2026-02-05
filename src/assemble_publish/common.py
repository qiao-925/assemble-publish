# common.py
# 公共模块：日志、配置、API 辅助函数

import json
import logging
import os
import sys
from pathlib import Path

# --- 日志配置 ---
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """配置并返回 logger"""
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("assemble_publish")
    logger.setLevel(level)
    return logger


logger = setup_logging()


# --- 环境变量辅助函数 ---
def env_bool(name: str, default: bool = False) -> bool:
    """读取布尔类型环境变量"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    """读取整数类型环境变量"""
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_str(name: str, default: str = "") -> str:
    """读取字符串类型环境变量"""
    return os.getenv(name, default).strip()


# --- 同步记录文件操作 ---
def get_sync_record_path(repo_root: Path | None = None) -> Path:
    """获取同步记录文件路径"""
    if repo_root is None:
        repo_root = Path.cwd().resolve()
    return (repo_root / ".cnblogs_sync" / ".cnblogs_sync_record.json").resolve()


def load_sync_record(record_file: Path) -> dict[str, str] | None:
    """加载同步记录（不存在则返回 None）"""
    if not record_file.exists():
        return None
    try:
        return json.loads(record_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"加载发布记录文件失败: {record_file} ({e})")
        return None


def save_sync_record(record_file: Path, record: dict[str, str]) -> bool:
    """保存同步记录"""
    try:
        record_file.parent.mkdir(parents=True, exist_ok=True)
        record_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"已更新发布记录文件: {record_file}")
        return True
    except Exception as e:
        logger.warning(f"写入发布记录文件失败: {record_file} ({e})")
        return False


# --- 博客园 API 辅助函数 ---
def get_blog_id(server, username: str, password: str) -> str | None:
    """通过 API 获取博客 ID"""
    try:
        blogs = server.blogger.getUsersBlogs("", username, password)
        if blogs and len(blogs) > 0:
            blog = blogs[0] or {}
            blog_id = blog.get("blogid") or blog.get("blogId") or blog.get("id")
            if blog_id is not None:
                logger.info(f"获取到博客 ID: {blog_id}")
                return str(blog_id)
        logger.warning("未找到博客信息")
        return None
    except Exception as e:
        logger.warning(f"获取博客 ID 时出错: {e}")
        return None


def fetch_recent_posts_map(
    server, blog_id: str, username: str, password: str, limit: int = 300
) -> dict[str, str]:
    """获取最近文章映射（标题 -> post_id）"""
    try:
        recent_posts = server.metaWeblog.getRecentPosts(blog_id, username, password, limit)
    except Exception as e:
        logger.warning(f"获取最近文章失败: {e}")
        return {}

    mapping = {}
    for post in recent_posts or []:
        title = post.get("title", "").strip()
        post_id = post.get("postid")
        if title and post_id:
            mapping[title] = post_id
    return mapping
