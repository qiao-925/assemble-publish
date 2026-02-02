# cnblogs sync worker（小仓库）

这个目录用于生成一个独立的 `sync-worker` 小仓库，运行时浅克隆主仓库并执行同步脚本。

## 文件说明

- `run_sync_worker.sh`：Zeabur 定时任务执行入口
- `requirements.txt`：Python 依赖（仅 `python-dotenv`）

## 运行流程

1. Zeabur 环境里提供 Python + git
2. 执行 `run_sync_worker.sh`（会按需安装 `requirements.txt`）
3. 脚本浅克隆主仓库并调用主仓库内的同步脚本
4. 同步状态回写到主仓库的 `sync-state` 分支

## 必要环境变量（Zeabur 配置）

**博客园认证**
- `CNBLOGS_RPC_URL`
- `CNBLOGS_BLOG_ID`
- `CNBLOGS_USERNAME`
- `CNBLOGS_PASSWORD`

**同步配置**
- `SYNC_REPO_URL`：主仓库地址（建议用带 PAT 的 HTTPS）
- `SYNC_REPO_BRANCH`：默认 `main`
- `SYNC_STATE_GIT=true`
- `SYNC_STATE_BRANCH=sync-state`
- `SYNC_STATE_REMOTE=origin`
- `SYNC_STATE_REMOTE_URL`：带 PAT 的 origin 地址（用于 push 状态）
- `INCREMENTAL_SYNC=true`

**可选**
- `SYNC_REPO_ROOT`：主仓库本地路径（默认脚本运行目录）
- `SYNC_RECORD_PATH`：记录文件相对主仓库路径
- `SYNC_STATE_PATH`：状态文件相对主仓库路径
- `PYTHON_BIN`：Python 可执行文件（默认优先 `python3`）
- `INSTALL_DEPS`：是否在运行时 `pip install`（默认 `true`）

## 首次初始化

需要先运行一次：

```bash
python "🗀 04-cnblogs_sync (6个文件，1.3%)/sync_to_cnblogs.py" --init
```
