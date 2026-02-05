# assemble-publish

## 命令清单

```bash
# 初始化环境变量文件
cp .env.example .env

# 本地执行同步（推荐入口）
python scripts/run_sync.py

# 常驻定时同步（每日 00:00 / 12:00）
python scripts/run_sync_hourly.py

# 去重工具（历史/手动运行）
python tools/deduplicate_cnblogs.py
```

将 Markdown 仓库内容同步发布到博客园（MetaWeblog API）。

本仓库提供同步脚本与部署入口：可本地执行，也可在容器/定时任务中自动拉取目标 Markdown 仓库并发布。

## 功能特性

- 单向同步：目标 Markdown 仓库 → 博客园
- 去重与更新：基于本地发布记录判断是否已发布，支持强制覆盖更新
- 自动处理：将文内本地 `.md` 链接替换为博客园站内搜索链接

## 快速开始（本地执行，推荐用 scripts/run_sync.py）

1. 准备环境变量（复制并修改）：
   ```bash
   cp .env.example .env
   ```
   最小可用配置（与 `.env.example` 一致）：
   ```bash
   CNBLOGS_RPC_URL=
   CNBLOGS_USERNAME=
   CNBLOGS_TOKEN=
   SYNC_REPO_URL=
   SYNC_REPO_TOKEN=
   ```
   说明：
   - 本仓库是“同步脚本仓库”，`SYNC_REPO_URL` 指向待发布的 Markdown 仓库（HTTPS URL）
   - `SYNC_REPO_TOKEN` 用于私有仓库拉取/推送（HTTPS Token 或同等凭据）
   - 若系统 pip 提示 externally-managed-environment（PEP 668），脚本会自动创建 `.venv` 安装依赖；也可设置 `USE_VENV=true` 或 `VENV_DIR` 自定义路径
   - 其他参数均使用默认值，无需配置
2. 同步（首次运行会自动初始化发布记录）：
   ```bash
   python scripts/run_sync.py
   ```

## 定时同步（每日两次，部署场景）

该脚本适合部署为**常驻进程/容器**：不依赖外部 Cron，等待到下一个定点触发同步并循环。
部署启动后会**立即先跑一次**，随后在**每天 00:00 与 12:00**触发。

```bash
python scripts/run_sync_hourly.py
```

部署建议：
- 将 `scripts/run_sync_hourly.py` 作为服务启动命令（systemd / supervisor / 容器 CMD/ENTRYPOINT），保持进程常驻
- 若平台自带 Cron/定时任务，建议直接定时执行 `python scripts/run_sync.py`（例如每天 00:00/12:00）而无需常驻
- 触发时间按**部署机系统时区**计算，如需调整请在部署环境配置时区

## 运行机制简述

- 首次运行会自动从博客园 API 拉取最近 300 篇文章并生成本地发布记录
- 发布时：
  - 若标题存在于发布记录中：根据 `FORCE_OVERWRITE_EXISTING` 决定更新或跳过
  - 若不存在：创建新文章并写入记录
- 默认全量扫描并发布 Markdown 文件

## 同步后自动去重（可选）

若你的历史文章超过 300 篇，为避免重复，可在每次同步完成后自动执行去重脚本：

- 在 `.env` 中设置 `POST_DEDUP=true`
- 可选参数：`DEDUP_DRY_RUN`、`DEDUP_KEEP_LATEST`、`DEDUP_DELETE_DELAY`、`DEDUP_SHOW_DETAILS`、`DEDUP_MAX_ROUNDS`

注意：去重会删除博客园上的重复文章，建议先设置 `DEDUP_DRY_RUN=true` 观察输出。

## 去重工具（历史）

如需处理历史遗留的重复文章，可使用去重工具：

- `tools/deduplicate_cnblogs.py`：按标题删除重复文章（保留最新）
- `docs/deduplication.md`：原理与注意事项说明

当前主流程已通过发布记录避免重复发布。

## 常见问题

- **没有发布记录会怎样？**
  脚本会自动初始化发布记录后继续同步。
- **私有仓库如何拉取？**
  默认示例使用公共仓库；私有仓库需提前配置 Git 凭据（HTTPS Token 或 SSH），否则无法拉取/推送。

---

如需调整行为，请优先修改 `.env.example` 并同步到部署环境。
