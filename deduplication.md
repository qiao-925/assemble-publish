# 📝 博客园文章去重工作总结

> **说明**：本文档为历史记录。当前同步默认使用 `sync-state` 分支保存状态以避免重复发布；去重脚本仅在历史上已产生重复文章时使用。

> **日期**: 2025-01-XX  
> **任务**: 博客园文章去重工具开发与 API 调研

---

## 🎯 任务背景

在同步 Markdown 文件到博客园的过程中，发现 `sync_to_cnblogs.py` 脚本存在重复创建文章的问题。每次同步都会创建新文章，导致同一篇文章出现多个副本。需要开发一个去重工具来解决这个问题。

---

## ✅ 完成的工作

### 1. 问题分析

- **问题根源**: `sync_to_cnblogs.py` 中的 `get_existing_post_id` 函数通过 `getRecentPosts(100)` 查询，但 API 返回的文章列表可能不包含所有文章，导致判断"文章不存在"而重复创建。

- **影响范围**: 博客园上存在大量重复文章，需要批量清理。

### 2. 去重工具开发

创建了 `deduplicate_cnblogs.py` 脚本，具备以下功能：

- ✅ **自动获取博客ID**: 通过 `blogger.getUsersBlogs` API 自动获取
- ✅ **批量获取文章**: 支持获取最多 300 篇文章（API 极限）
- ✅ **智能去重**: 按标题分组，识别重复文章
- ✅ **时间戳排序**: 优先保留最新的文章，删除旧的文章
- ✅ **迭代模式**: 自动循环执行，直到没有重复文章
- ✅ **安全模式**: 支持 `DRY_RUN` 模式，先预览再执行
- ✅ **详细日志**: 显示处理过程和统计信息

### 3. API 调研与发现

#### 博客园 MetaWeblog API

**RPC URL**: `https://rpc.cnblogs.com/metaweblog/xtkyxnx`

**主要使用的 API 方法**:

1. **`blogger.getUsersBlogs`**
   - 用途: 获取博客ID
   - 参数: `(appKey, username, password)`
   - 返回: 博客列表，包含 `blogid`

2. **`metaWeblog.getRecentPosts`** ⚠️
   - 用途: 获取最近的文章列表
   - 参数: `(blogid, username, password, numberOfPosts)`
   - **重要发现**: **API 极限是 300 篇**，无论请求多少，最多只返回 300 篇
   - **限制**: 不支持 offset 分页，只能获取"最近的 N 篇"

3. **`blogger.deletePost`**
   - 用途: 删除指定文章
   - 参数: `(appKey, postid, username, password, publish)`
   - 返回: `True` 表示删除成功

#### API 限制总结

| API 方法 | 限制 | 说明 |
|---------|------|------|
| `metaWeblog.getRecentPosts` | 最多返回 300 篇 | 不支持分页，无法获取超过 300 篇的文章 |
| `metaWeblog.getRecentPosts` | 不支持 offset | 无法获取"第 301-600 篇"这样的分页数据 |

**影响**: 如果博客文章总数超过 300 篇，无法一次性获取所有文章。需要通过"删除 → 重新获取"的迭代方式逐步处理。

---

## 📋 脚本功能说明

### `deduplicate_cnblogs.py`

**核心功能**:
- 自动迭代执行去重，直到没有重复文章
- 每次获取 300 篇文章（API 极限）
- 按时间戳排序，保留最新的，删除旧的
- 支持模拟模式（`DRY_RUN`）和实际删除模式

**配置选项**:
```python
KEEP_LATEST = True   # 保留最新的文章
DRY_RUN = False      # 实际执行删除（False）或仅预览（True）
DELETE_DELAY = 1     # 每次删除操作之间的延迟（秒）
```

**使用方法**:
```bash
python deduplicate_cnblogs.py
```

**工作流程**:
1. 第 1 轮: 获取 300 篇文章 → 找出重复 → 删除旧的，保留新的
2. 第 2 轮: 重新获取 300 篇文章 → 检查是否还有重复
3. 重复执行，直到没有重复文章或达到最大轮数（50 轮）

---

## 🔍 技术细节

### 时间戳处理

- **字段**: `dateCreated` 或 `pubDate`
- **解析**: 支持多种日期格式（`%Y%m%dT%H:%M:%S`, `%Y-%m-%d %H:%M:%S` 等）
- **排序策略**: 
  1. 优先按时间戳排序（最新的在前）
  2. 如果时间戳解析失败，按 `postid` 排序（通常 ID 越大越新）

### 去重逻辑

1. **标题标准化**: 去除首尾空格后比较
2. **分组**: 按标准化后的标题分组
3. **保留策略**: 每组保留 1 篇（最新的），删除其余（旧的）

---

## ⚠️ 已知问题与限制

### 1. API 限制

- **300 篇极限**: `getRecentPosts` 最多返回 300 篇，无法一次性获取所有文章
- **无分页支持**: 不支持 offset 参数，无法获取"下一页"数据

### 2. 处理策略

- **迭代删除**: 通过"删除 → 重新获取"的方式逐步处理
- **可能遗漏**: 如果文章总数超过 300 篇，且前 300 篇中没有重复，更早的文章可能无法被处理

### 3. 性能考虑

- **删除延迟**: 每次删除操作后延迟 1 秒，避免请求过于频繁
- **轮次限制**: 最多执行 50 轮，防止无限循环

---

## 🚀 后续改进方向

### 短期优化

1. **增加统计信息**: 记录每轮处理的文章数量和删除数量
2. **错误处理**: 增强异常处理，记录删除失败的文章
3. **日志输出**: 支持将处理日志保存到文件

### 长期优化

1. **分页支持**: 如果博客园 API 未来支持分页，可以一次性获取所有文章
2. **增量处理**: 记录已处理的文章 ID，避免重复处理
3. **内容对比**: 不仅按标题去重，还可以对比文章内容，识别内容相同的文章
4. **批量操作**: 如果 API 支持批量删除，可以提高处理效率

### 根本解决方案

**修复 `sync_to_cnblogs.py`**:
- 改进 `get_existing_post_id` 函数，确保能正确识别已存在的文章
- 考虑使用 `metaWeblog.getPost` 通过标题精确查询
- 或者使用文章的唯一标识（如文件路径的哈希值）来避免重复

---

## 📚 相关文件

- `sync_to_cnblogs.py` - 同步脚本（需要修复重复创建问题）
- `deduplicate_cnblogs.py` - 去重工具
- `.github/workflows/publish_to_cnblogs.yml` - GitHub Actions 工作流

---

## 🔗 API 参考

### MetaWeblog API 文档

- **RPC URL**: `https://rpc.cnblogs.com/metaweblog/xtkyxnx`
- **认证方式**: 用户名 + Token（MetaWeblog API Token）
- **主要方法**:
  - `blogger.getUsersBlogs` - 获取博客列表
  - `metaWeblog.getRecentPosts` - 获取最近文章（⚠️ 极限 300 篇）
  - `metaWeblog.getPost` - 获取单篇文章
  - `metaWeblog.newPost` - 创建新文章
  - `metaWeblog.editPost` - 编辑文章
  - `blogger.deletePost` - 删除文章

### curl 测试命令

**获取博客ID**:
```bash
curl -X POST "https://rpc.cnblogs.com/metaweblog/xtkyxnx" \
  -H "Content-Type: text/xml" \
  -d "<?xml version=\"1.0\"?><methodCall><methodName>blogger.getUsersBlogs</methodName><params><param><value><string></string></value></param><param><value><string>用户名</string></value></param><param><value><string>TOKEN</string></value></param></params></methodCall>"
```

**获取最近 300 篇文章**:
```bash
curl -X POST "https://rpc.cnblogs.com/metaweblog/xtkyxnx" \
  -H "Content-Type: text/xml" \
  -d "<?xml version=\"1.0\"?><methodCall><methodName>metaWeblog.getRecentPosts</methodName><params><param><value><string>BLOG_ID</string></value></param><param><value><string>用户名</string></value></param><param><value><string>TOKEN</string></value></param><param><value><int>300</int></value></param></params></methodCall>"
```

---

## 📝 总结

本次任务成功开发了博客园文章去重工具，并深入调研了博客园 MetaWeblog API 的特性。发现并记录了 `getRecentPosts` API 的 300 篇极限限制，为后续优化提供了重要参考。

**关键成果**:
- ✅ 完成去重工具开发
- ✅ 发现并记录 API 限制（300 篇极限）
- ✅ 实现迭代处理机制
- ✅ 建立时间戳排序和保留策略

**待解决问题**:
- ⚠️ `sync_to_cnblogs.py` 的重复创建问题需要修复
- ⚠️ API 300 篇限制导致无法一次性处理所有文章

---

*文档生成时间: 2025-01-XX*
