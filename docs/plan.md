
> 日期：2026-02-02
> 状态：草案（关键项已定）
> 目标：用 Zeabur 实现“自动同步到博客园”，减少手动命令执行

---

## 1) 背景与目标

- **背景**：当前同步依赖本地手动执行脚本（`sync_to_cnblogs.py`），操作成本高、容易忘。
- **核心目标**：在不改变现有脚本核心逻辑的前提下，实现可持续、可观测、可恢复的自动化同步。
- **约束**：
  - 需要博客园 MetaWeblog 认证信息（环境变量）
  - API 有 300 篇获取上限（去重依赖本地记录文件）
  - 记录文件必须持久化，否则会出现重复发布风险

---

## 2) 现状资产梳理（已存在）

- 脚本：`cnblogs_sync/sync_to_cnblogs.py`
  - 支持 `--init` 初始化本地记录
  - 自动扫描全仓 Markdown（排除 `.git/.github/node_modules/cnblogs_sync` 等）
  - 依赖本地记录文件：`.cnblogs_sync_record.json`
- 去重脚本：`cnblogs_sync/deduplicate_cnblogs.py`
- 旧的 GitHub Actions 工作流（存档）：`docs/publish_to_cnblogs.yml.archived`

---

## 3) 关键决策点（已定与待定）

1. **同步范围**：全仓 Markdown（已定）
2. **触发方式**：定时（每小时）（已定）
3. **记录文件存放**：Git 专用分支 `sync-state`（已定）
4. **发布策略**：
   - `FORCE_OVERWRITE_EXISTING` 是否保持为 True？（待定）
   - 增量同步（只同步变更文件）（已定）

---

## 4) 方案候选（Zeabur 方向）

### 方案 A：Zeabur 定时任务（Cron） + 仓库拉取 + 脚本执行
- **流程**：Zeabur 定时拉取仓库 → 执行 `sync_to_cnblogs.py` → 使用持久化卷保存 `.cnblogs_sync_record.json`。
- **优点**：简单稳定、无需额外 API。
- **缺点**：每次全仓扫描；若频率高会增加 API 调用与耗时。

### 方案 B：Zeabur Webhook 服务 + 后台任务
- **流程**：GitHub Webhook → Zeabur 接收事件 → 触发同步（可传递变更文件列表）。
- **优点**：可做到“增量同步”，更精准。
- **缺点**：需要额外服务端逻辑和事件鉴权。

### 方案 C：保留 GitHub Actions，但把执行环境迁到 Zeabur
- **流程**：Actions 触发 → 调 Zeabur API 或执行远程命令 → 脚本运行。
- **优点**：迁移成本低。
- **缺点**：依旧依赖 GitHub Actions 配置与运行时。

---

## 5) 推荐的最小可行路径（可快速落地）

> 采用 **方案 A** + **Git 专用分支持久化**，快速验证自动化闭环，后续再考虑升级为方案 B。

### 阶段 1（MVP）
1. 确定同步范围为全仓（已定）。
2. Zeabur 直接拉取当前仓库（`assemble-publish`）。
3. 配置 Zeabur 环境变量（含 Git PAT），启用 `sync-state` 分支持久化。
4. 首次运行前，先手动执行一次 `--init`，确保发布记录可用。
5. 建立定时任务（每小时执行一次）。

### 阶段 2（优化）
1. 支持“增量同步”——只同步变更文件（减少 API 调用）。
2. 增加运行日志和失败通知（邮件/飞书/钉钉/Slack）。
3. 失败回滚/重试机制。

---

## 6) 待确认信息（请你拍板）

- 是否允许覆盖已存在文章（`FORCE_OVERWRITE_EXISTING`）？
- 是否需要额外的失败通知（邮件/飞书/钉钉/Slack）？

---

## 9) 落地运行方式（当前主线：不再使用 worker）

### 运行流程（Zeabur Cron）
1. Zeabur 拉取当前仓库 `assemble-publish`
2. 定时执行：`python cnblogs_sync/sync_to_cnblogs.py`
3. 脚本在启动时（`SYNC_STATE_GIT=true`）：从 `sync-state` 分支恢复 `.cnblogs_sync_record.json` + `state.json`
4. 同步完成后：更新状态文件并 push 回 `sync-state` 分支（需要 `SYNC_STATE_REMOTE_URL` 提供 PAT 权限）

### 首次初始化（必须手动跑一次）

```bash
python cnblogs_sync/sync_to_cnblogs.py --init
```

> 初始化会从 API 获取最近 300 篇文章标题与 post_id，写入 `.cnblogs_sync_record.json`，用于后续去重与避免重复发布。

---

## 7) 风险与注意事项

- **API 限制**：`getRecentPosts` 仅返回最近 300 篇，必须依赖本地记录。
- **记录丢失风险**：若记录文件未持久化，将触发重复发布。
- **全仓扫描耗时**：仓库较大时，建议做目录白名单。

---

## 8) 预期输出

- Zeabur 自动化同步可用
- 同步日志可追踪
- 无需手动执行命令

---

> 下一步：你确定“同步范围 + 触发方式 + 频率 + 是否增量”后，我就开始细化方案并落地。
