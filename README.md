# assemble-publish

将 Markdown 仓库内容同步发布到博客园（MetaWeblog API）。

本仓库提供同步脚本与部署入口：可本地执行，也可在容器/定时任务中自动拉取主仓库并发布。

## 功能特性

- 单向同步：本地/主仓库 Markdown → 博客园
- 去重与更新：基于本地发布记录判断是否已发布，支持强制覆盖更新
- 增量同步：基于 Git commit 的差异（`last_synced_commit` → `HEAD`）只发布变更
- 状态持久化：可将 `.cnblogs_sync` 状态写回 `sync-state` 分支
- 自动处理：将文内本地 `.md` 链接替换为博客园站内搜索链接

## 快速开始（本地执行）

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
   SYNC_REPO_BRANCH=sync-state
   ```
   说明：
   - 仅本地执行 `sync_to_cnblogs.py` 时，`SYNC_REPO_URL` / `SYNC_REPO_BRANCH` 可留空
   - 仍兼容 `CNBLOGS_PASSWORD`，但推荐使用 `CNBLOGS_TOKEN`

2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 同步（首次运行会自动初始化发布记录）：
   ```bash
   python cnblogs_sync/sync_to_cnblogs.py
   ```

> 若脚本不在 Markdown 仓库根目录，请设置 `SYNC_REPO_ROOT` 指向目标仓库。

## 使用 `run_sync.sh`（推荐部署方式）

该脚本会拉取“主仓库”（包含 Markdown 文件），然后在其中执行同步。
首次运行会自动初始化发布记录。

```bash
# 同步（首次运行会自动初始化发布记录）
./run_sync.sh
```

必须设置：
- `CNBLOGS_RPC_URL`、`CNBLOGS_USERNAME`、`CNBLOGS_TOKEN`（或 `CNBLOGS_PASSWORD`）
- `SYNC_REPO_URL`：主仓库地址（私有仓库建议使用带 PAT 的 HTTPS）

可选：
- `SYNC_REPO_BRANCH`（默认 `main`；示例使用 `sync-state`）
- `SYNC_REPO_DEPTH`（默认 50；0 表示完整克隆）
- `WORKDIR`（默认 `/tmp/assemble-main-repo`）
- `INSTALL_DEPS`（默认 `true`，安装 `python-dotenv`）

## 整点定时同步

```bash
# 可选：启动前先立刻执行一次
RUN_IMMEDIATELY=true ./run_sync_hourly.sh
```

脚本将等待到下一个整点并循环触发同步。

## Docker 使用

```bash
docker build -t assemble-publish .

# 运行（使用环境变量或 .env 文件）
docker run --rm --env-file .env assemble-publish
```

默认入口为 `run_sync.sh`。

## 重要环境变量说明（摘录）

必填：
- `CNBLOGS_RPC_URL`、`CNBLOGS_USERNAME`、`CNBLOGS_TOKEN`（或 `CNBLOGS_PASSWORD`）
- `SYNC_REPO_URL`（仅使用 `run_sync.sh` 时需要）

常用：
- `SYNC_REPO_BRANCH`：主仓库分支（默认 `main`；示例使用 `sync-state`）
- `CNBLOGS_BLOG_ID`：未设置时脚本会尝试自动获取
- `FORCE_OVERWRITE_EXISTING`：是否覆盖已存在文章（默认 `true`）
- `INCREMENTAL_SYNC`：是否开启增量同步（默认 `true`）
- `SYNC_RECORD_PATH`：发布记录文件路径（默认 `.cnblogs_sync/.cnblogs_sync_record.json`）
- `SYNC_STATE_PATH`：增量同步状态文件（默认 `.cnblogs_sync/state.json`）
- `SYNC_RUN_LOG_PATH`：运行记录（默认 `.cnblogs_sync/run_history.jsonl`）

状态分支（默认开启）：
- `SYNC_STATE_GIT=true`：将状态写回 Git
- `SYNC_STATE_BRANCH=sync-state`
- `SYNC_STATE_REMOTE=origin`
- `SYNC_STATE_REMOTE_URL`：推送所用带 PAT 的远端 URL（部署环境常用）

完整列表见 `cnblogs_sync/sync_to_cnblogs.py` 顶部注释及 `run_sync.sh` 头部说明。

## 运行机制简述

- 首次运行会自动从博客园 API 拉取最近 300 篇文章并生成本地发布记录
- 发布时：
  - 若标题存在于发布记录中：根据 `FORCE_OVERWRITE_EXISTING` 决定更新或跳过
  - 若不存在：创建新文章并写入记录
- 增量模式会仅发布 Git diff 的 Markdown 文件

## 去重工具（历史）

`deduplicate stuff/` 中包含历史去重脚本，仅在早期已产生重复文章时使用。
当前主流程已通过发布记录与状态分支避免重复发布。

## 常见问题

- **没有发布记录会怎样？**
  脚本会自动初始化发布记录后继续同步。
- **私有仓库如何拉取？**
  使用带 PAT 的 HTTPS：`https://<PAT>@github.com/<owner>/<repo>.git`。

---

如需调整行为，请优先修改 `.env.example` 并同步到部署环境。
