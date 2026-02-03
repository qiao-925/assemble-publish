# assemble-publish

将 Markdown 仓库内容同步发布到博客园（MetaWeblog API）。

本仓库提供同步脚本与部署入口：可本地执行，也可在容器/定时任务中自动拉取目标 Markdown 仓库并发布。

## 功能特性

- 单向同步：目标 Markdown 仓库 → 博客园
- 去重与更新：基于本地发布记录判断是否已发布，支持强制覆盖更新
- 增量同步：基于 Git commit 的差异（`last_synced_commit` → `HEAD`）只发布变更
- 状态持久化：可将 `.cnblogs_sync` 状态写回 `sync-state` 分支
- 自动处理：将文内本地 `.md` 链接替换为博客园站内搜索链接

## 快速开始（本地执行，推荐用 run_sync.py）

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
   - `SYNC_REPO_TOKEN` 用于推送 `sync-state` 分支（也可用于私有仓库拉取/推送）
   - 其他参数均使用默认值，无需配置
2. 同步（首次运行会自动初始化发布记录）：
   ```bash
   python run_sync.py
   ```

## 整点定时同步（部署场景）

该脚本适合部署为**常驻进程/容器**：不依赖外部 Cron，等待到下一个整点后触发同步并每小时循环。
部署启动后会**立即先跑一次**，随后进入整点循环。

```bash
python run_sync_hourly.py
```

部署建议：
- 将 `run_sync_hourly.py` 作为服务启动命令（systemd / supervisor / 容器 CMD/ENTRYPOINT），保持进程常驻
- 若平台自带 Cron/定时任务，建议直接定时执行 `python run_sync.py`（例如每小时）而无需常驻
- “整点”按**部署机系统时区**计算，如需调整请在部署环境配置时区

## 运行机制简述

- 首次运行会自动从博客园 API 拉取最近 300 篇文章并生成本地发布记录
- 发布时：
  - 若标题存在于发布记录中：根据 `FORCE_OVERWRITE_EXISTING` 决定更新或跳过
  - 若不存在：创建新文章并写入记录
- 增量模式会仅发布 Git diff 的 Markdown 文件

## 去重工具（历史）

如需处理历史遗留的重复文章，可使用去重工具：

- `deduplicate_cnblogs.py`：按标题删除重复文章（保留最新）
- `deduplication.md`：原理与注意事项说明

当前主流程已通过发布记录与状态分支避免重复发布。

## 常见问题

- **没有发布记录会怎样？**
  脚本会自动初始化发布记录后继续同步。
- **私有仓库如何拉取？**
  默认示例使用公共仓库；私有仓库需提前配置 Git 凭据（HTTPS Token 或 SSH），否则无法拉取/推送。

---

如需调整行为，请优先修改 `.env.example` 并同步到部署环境。
