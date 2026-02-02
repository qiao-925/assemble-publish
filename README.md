# assemble-publish

把 Markdown 自动同步到博客园（CNBlogs / MetaWeblog），并把同步"记录/状态"持久化到主仓库的 `sync-state` 分支，支持按 Git diff 的增量同步。

> 📁 **项目结构说明**: 查看 [docs/project-structure.md](docs/project-structure.md) 了解完整的目录结构和设计原则。

## 核心能力

- **增量同步**：用 `last_synced_commit..HEAD` 计算变更，仅处理变更的 Markdown（可关闭）
- **去重/避免重复发布**：用本地记录文件 `{title: post_id}` 判断文章是否已发布
- **状态持久化**：把记录文件 + `state.json` 写回主仓库的 `sync-state` 分支（避免依赖数据库）
- **定时运行**：适配 Zeabur Cron（每小时跑一次）

## 核心链路（推荐形态：同步仓库 + 主仓库）

1. Zeabur Cron 每小时触发一次
2. 执行 `run_sync.sh`（拉取/更新主仓库到 `WORKDIR`）
3. 运行 `cnblogs_sync/sync_to_cnblogs.py`
4. 脚本在启动时（`SYNC_STATE_GIT=true`）从主仓库 `sync-state` 分支恢复：
   - `.cnblogs_sync/.cnblogs_sync_record.json`（去重记录）
   - `.cnblogs_sync/state.json`（增量状态）
5. 通过 `git diff` 找到变更 Markdown → 发布/更新到博客园
6. 更新记录/状态并 push 回主仓库 `sync-state` 分支

## 主要脚本

- 发布/同步：`cnblogs_sync/sync_to_cnblogs.py`
- 主仓库运行入口（推荐用于 Zeabur/Cron）：`run_sync.sh`
- 去重工具（修复历史重复文章）：`cnblogs_sync/deduplicate_cnblogs.py`

## 本地快速开始

1) 安装依赖：

```bash
pip install -r requirements.txt
```

2) 配置环境变量：

- 复制 `.env.example` 为 `.env`
- 填写 `CNBLOGS_RPC_URL / CNBLOGS_USERNAME / CNBLOGS_PASSWORD`
- `CNBLOGS_PASSWORD` 可以直接填 MetaWeblog Token（也支持用 `CNBLOGS_TOKEN` 作为别名）
- `CNBLOGS_BLOG_ID` 可不填（脚本会尝试自动获取）

3) 首次初始化（必须跑一次）：

```bash
python cnblogs_sync/sync_to_cnblogs.py --init
```

4) 执行同步：

```bash
python cnblogs_sync/sync_to_cnblogs.py
```

> `run_sync.sh` 是 bash 脚本，适用于 Linux/容器环境（例如 Zeabur）。Windows 本地如需运行可使用 WSL / Git Bash；否则建议直接运行上面的 Python 命令进行验证。

## 扫描范围与排除目录

默认会递归扫描仓库内所有 `*.md`，并排除常见目录（如 `.git/.github/node_modules/__pycache__` 等）。
如需更严格的白名单/黑名单规则，可调整 `cnblogs_sync/sync_to_cnblogs.py` 里的 `EXCLUDE_DIRS`。

## 同步主仓库（推荐）

如果你希望这个仓库作为“执行仓库”，运行时拉取主仓库再同步（适合 Zeabur/Cron），用 `run_sync.sh`：

1) 配置环境变量（见 `.env.example`）：

- `SYNC_REPO_URL`：主仓库地址（建议用带 PAT 的 HTTPS；私有仓库必须）
- `SYNC_STATE_GIT=true` + `SYNC_STATE_REMOTE_URL=...`：把状态写回主仓库的 `sync-state` 分支（避免重复发布/支持增量）
- `WORKDIR`：主仓库本地缓存目录（如果指向可持久化目录，可避免每次定时任务都重新 clone）

2) 首次初始化（必须跑一次）：

```bash
./run_sync.sh --init
```

3) 正常同步（可放到 Zeabur Cron 每小时跑一次）：

```bash
./run_sync.sh
```

## 环境变量说明（最小集）

**博客园认证（必需）**

- `CNBLOGS_RPC_URL`
- `CNBLOGS_USERNAME`
- `CNBLOGS_PASSWORD`（或 `CNBLOGS_TOKEN`）
- `CNBLOGS_BLOG_ID`（可选；脚本会尝试自动获取）

**主仓库拉取（使用 `run_sync.sh` 时必需）**

- `SYNC_REPO_URL`
- `SYNC_REPO_BRANCH`（默认 `main`）
- `SYNC_REPO_DEPTH`（默认 `50`；`0` 表示完整克隆）
- `WORKDIR`（默认 `/tmp/assemble-main-repo`；建议指向可持久化目录）

**状态写回主仓库（强烈建议开启）**

- `SYNC_STATE_GIT=true`
- `SYNC_STATE_BRANCH=sync-state`
- `SYNC_STATE_REMOTE=origin`
- `SYNC_STATE_REMOTE_URL`（带 PAT 的 HTTPS URL，用于 push `sync-state`）

**行为开关（可选）**

- `INCREMENTAL_SYNC=true`：启用增量同步（默认 `true`）
- `FORCE_OVERWRITE_EXISTING=true`：已发布文章是否强制更新（默认 `true`；设为 `false` 则跳过已存在文章）

**路径配置（可选）**

- `SYNC_RECORD_PATH`（默认 `.cnblogs_sync/.cnblogs_sync_record.json`）
- `SYNC_STATE_PATH`（默认 `.cnblogs_sync/state.json`）

## 增量同步与状态持久化

脚本支持两类状态文件：

- `.cnblogs_sync/.cnblogs_sync_record.json`：`{ 标题: post_id }`，用于去重/更新
- `.cnblogs_sync/state.json`：保存 `last_synced_commit` 等信息，用于增量同步

推荐开启 `SYNC_STATE_GIT=true`，把这两个文件持久化到专用分支 `sync-state`（避免依赖外部数据库，也避免污染 main 分支）。

需要的环境变量：

- `SYNC_STATE_GIT=true`
- `SYNC_STATE_BRANCH=sync-state`
- `SYNC_STATE_REMOTE=origin`
- `SYNC_STATE_REMOTE_URL=...`（建议用带 PAT 的 HTTPS URL，用于 push）

可选：如果运行环境没有配置 git identity，可设置：

- `GIT_USER_NAME`
- `GIT_USER_EMAIL`

## 发布策略（重要）

- 默认 `FORCE_OVERWRITE_EXISTING=true`：标题命中记录时会走 `editPost` 更新文章内容（适合“仓库即真相”的同步模式）。
- 如果你不想改动历史文章，把它设为 `false`：命中记录就跳过，只发布新文章。

## 去重工具（处理历史重复文章）

当你历史上已经产生了重复文章，可以运行：

```bash
python cnblogs_sync/deduplicate_cnblogs.py
```

说明：

- 受限于 `getRecentPosts` 的 API 上限（最多 300 篇），脚本采用“迭代轮询”的方式清理最近范围内的重复。
- 去重脚本会在实际删除后，尝试同步更新本地发布记录（`SYNC_RECORD_PATH`）为“保留的那篇 post_id”，避免后续 `editPost` 指向已删除的文章。

## Zeabur（Cron）落地思路

1. 在 Zeabur 部署此仓库（确保运行环境具备 `python` + `git`）
2. 配置 `.env.example` 里的环境变量（至少 CNBlogs 认证 + `SYNC_REPO_URL` + SYNC_STATE_*）
3. 创建定时任务（例如每小时）执行（推荐）：

```bash
./run_sync.sh
```

## 常见问题（排错）

- **担心重复发布？**  
  脚本会依赖 `.cnblogs_sync/.cnblogs_sync_record.json` 做去重；如果记录文件不存在，脚本会直接中止以避免“全量当新文章”导致重复发布。
- **为什么 `--init` 只能看到最近 300 篇？**  
  这是博客园 MetaWeblog `getRecentPosts` 的限制；脚本的策略是把“曾经发布过的标题→post_id”长期存到 `sync-state` 分支里，避免每次都依赖 API 列表判断。
- **`sync-state` push 失败？**  
  通常是 PAT 权限或 remote URL 配置问题：检查 `SYNC_STATE_REMOTE_URL` 是否是带 PAT 的 HTTPS 地址，并且有 push 权限。

## 安全建议

- 不要把 `.env` 提交到仓库（已在 `.gitignore` 忽略）。
- `SYNC_REPO_URL / SYNC_STATE_REMOTE_URL` 如果携带 PAT，务必当作密钥管理（仅在平台环境变量中配置）。

## Docker（可选）

如果你用 Docker 部署（Zeabur 常见），镜像默认执行 `run_sync.sh`：

```bash
docker build -t cnblogs-sync .
docker run --rm --env-file .env cnblogs-sync
```
