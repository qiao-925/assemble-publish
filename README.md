# assemble-publish

博客园发布脚本库。将 Markdown 内容同步发布到博客园（MetaWeblog API）。

> **当前定位**：本仓库是**脚本库**，主要被 `qiao-925/assemble-archive` 的 GitHub Actions workflow 引用执行。也支持本地手动运行。

## 架构位置

```
qiao-925/assemble-processing
    └─ push assemble-archive/ 变更
          ↓
qiao-925/assemble-archive
    └─ GitHub Actions workflow 触发
          ├─ checkout 本仓库到 _publish/
          └─ python _publish/src/assemble_publish/sync_to_cnblogs.py
                ↓
             博客园
```

完整架构见 `assemble-processing/ASSEMBLE_WORKFLOW.md`。

## 目录结构

```
assemble-publish/
├── src/assemble_publish/
│   ├── sync_to_cnblogs.py    # 核心发布脚本（被 workflow 直接调用）
│   └── common.py             # 通用工具
├── scripts/
│   └── run_sync.py            # 本地手动同步入口（克隆 archive 仓库 + 调用 sync）
├── tools/
│   └── deduplicate_cnblogs.py # 博客园去重工具（手动运行）
└── .env.example
```

## 本地使用（可选）

大多数情况下不需要本地运行，由 `assemble-archive` 的 workflow 自动执行。
如需本地调试或手动补发：

```bash
# 1. 准备环境变量
cp .env.example .env
# 编辑 .env，填入 CNBLOGS_RPC_URL / CNBLOGS_USERNAME / CNBLOGS_TOKEN

# 2. 运行
python scripts/run_sync.py
```

`run_sync.py` 会：
1. 克隆 `qiao-925/assemble-archive` 到本地临时目录
2. 调用 `sync_to_cnblogs.py` 扫描 `daily/<date>/*.md` 并发布

## 运行机制

`sync_to_cnblogs.py` 是**无状态**的：
- 每次运行从博客园 API 拉取最近 300 篇文章作为"已发布"快照
- 按标题匹配：
  - 已存在 → 根据 `FORCE_OVERWRITE_EXISTING` 决定覆盖或跳过（默认覆盖）
  - 不存在 → 创建新文章
- 扫描目标：仓库根目录下的 `daily/<date>/*.md`（按日期倒序）

## 环境变量

| 变量 | 说明 | 必填 |
|---|---|---|
| `CNBLOGS_RPC_URL` | 博客园 MetaWeblog RPC 地址 | ✅ |
| `CNBLOGS_USERNAME` | 博客园用户名 | ✅ |
| `CNBLOGS_TOKEN` | 博客园 Token（从博客园后台获取） | ✅ |

## 工具

- `tools/deduplicate_cnblogs.py`：按标题删除博客园上的重复文章（保留最新）
- `docs/deduplication.md`：去重原理说明
