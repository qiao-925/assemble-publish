# 项目结构说明

## 目录结构

```
assemble-publish/
├── cnblogs_sync/              # 核心代码目录
│   ├── __init__.py           # Python 包初始化文件
│   ├── sync_to_cnblogs.py    # 主同步脚本
│   └── deduplicate_cnblogs.py # 去重工具
├── docs/                      # 文档目录
│   ├── plan.md               # Zeabur 部署计划
│   ├── sync-guide.md         # 同步指南
│   ├── github-actions.md     # GitHub Actions 原理
│   ├── deduplication.md      # 去重工作总结
│   └── publish_to_cnblogs.yml.archived # 旧的 Actions 配置（存档）
├── .env.example              # 环境变量模板
├── .gitignore                # Git 忽略规则
├── .dockerignore             # Docker 忽略规则
├── Dockerfile                # Docker 镜像配置
├── README.md                 # 项目说明文档
├── requirements.txt          # Python 依赖
└── run_sync.sh               # 主仓库同步入口脚本
```

## 目录说明

### cnblogs_sync/
核心 Python 代码目录，包含所有同步相关的脚本。

- **sync_to_cnblogs.py**: 主同步脚本，负责扫描 Markdown 文件并同步到博客园
- **deduplicate_cnblogs.py**: 去重工具，用于清理历史重复发布的文章
- **__init__.py**: Python 包标识文件，使该目录成为标准 Python 包

### docs/
所有文档集中存放目录。

- **plan.md**: Zeabur 自动化部署计划和方案设计
- **sync-guide.md**: 详细的同步使用指南
- **github-actions.md**: GitHub Actions 工作原理深度解析
- **deduplication.md**: 博客园文章去重工作总结
- **publish_to_cnblogs.yml.archived**: 旧的 GitHub Actions 配置文件（已存档）

### 根目录文件

- **.env.example**: 环境变量配置模板，包含所有必需和可选的配置项
- **README.md**: 项目主文档，包含快速开始、配置说明、使用方法等
- **requirements.txt**: Python 依赖列表（目前仅需 python-dotenv）
- **run_sync.sh**: Bash 脚本，用于拉取主仓库并执行同步（适合 Zeabur Cron）
- **Dockerfile**: Docker 镜像构建配置
- **.gitignore**: Git 版本控制忽略规则
- **.dockerignore**: Docker 构建忽略规则

## 使用方式

### 本地开发/测试
```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写博客园认证信息

# 首次初始化
python cnblogs_sync/sync_to_cnblogs.py --init

# 执行同步
python cnblogs_sync/sync_to_cnblogs.py
```

### Zeabur 部署
```bash
# 配置环境变量后，定时执行
./run_sync.sh
```

### Docker 部署
```bash
docker build -t cnblogs-sync .
docker run --rm --env-file .env cnblogs-sync
```

## 设计原则

1. **代码与文档分离**: 代码在 `cnblogs_sync/`，文档在 `docs/`
2. **标准 Python 包结构**: 使用 `__init__.py` 使代码目录成为标准包
3. **清晰的命名**: 避免使用特殊字符和 emoji，使用标准的目录和文件名
4. **生产就绪**: 所有配置文件（Docker、环境变量）都在根目录，便于部署

## 迁移说明

从旧结构迁移到新结构的主要变更：

| 旧路径 | 新路径 |
|--------|--------|
| `🗀 04-cnblogs_sync (6个文件，1.3%)/sync_to_cnblogs.py` | `cnblogs_sync/sync_to_cnblogs.py` |
| `🗀 04-cnblogs_sync (6个文件，1.3%)/deduplicate_cnblogs.py` | `cnblogs_sync/deduplicate_cnblogs.py` |
| `2026-02-02-cnblogs-zeabur-plan.md` | `docs/plan.md` |
| `🗀 04-cnblogs_sync (6个文件，1.3%)/Github Repo更新同步到cnblog.md` | `docs/sync-guide.md` |
| `🗀 04-cnblogs_sync (6个文件，1.3%)/GitHub Actions工作原理深度解析.md` | `docs/github-actions.md` |
| `🗀 04-cnblogs_sync (6个文件，1.3%)/博客园文章去重工作总结.md` | `docs/deduplication.md` |
| `context` | 已删除（临时文件） |
