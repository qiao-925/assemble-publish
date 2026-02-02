# 🔄 **Github Repo更新同步到cnblog**

## [From manus]使用 MetaWeblog API 编写自定义脚本 + 利用 GitHub Actions 实现自动化  
## 1. 推荐方案 
好的，将 GitHub 动态同步到博客园，通常有两种主流方法：

1.  **利用现成的开源工具**：社区中可能已经有开发者完成了类似需求的工具，我们可以直接配置使用。
2.  **自己编写脚本**：通过 GitHub API 获取动态，再利用博客园的 MetaWeblog API 将内容发布成博文。这提供了最大的灵活性和定制化空间。

为了给您提供最适合的方案，我将首先进行一些调研。

我将通过以下步骤来解决您的问题：
1.  **搜索现成的解决方案**：查找是否有可以直接使用的、配置简单的开源工具。
2.  **研究 GitHub API**：了解如何获取您需要同步的动态，例如代码提交、文章发布等。
3.  **研究博客园 API**：确认博客园提供的 API 类型（如 MetaWeblog API）以及如何使用它来发布文章。
4.  **整合方案**：根据调研结果，为您提供一个完整的、可操作的指南，可能包括推荐工具的配置方法或一个简单的实现脚本。

我们开始第一步，进行初步的搜索。初步的搜索结果非常有用！我找到了几种可行的方法：

**方法一：使用博客园官方的 GitHub 同步功能（推荐）**

*   **发现**：博客园官方提供了一个名为 "GitHub 同步" 的功能。
*   **原理**：通过在博客园后台绑定 GitHub 账号并安装一个官方的 GitHub App，可以实现将 GitHub 指定仓库（或仓库的特定文件夹）内的 Markdown 文件（`.md`）自动同步到博客园。
*   **优点**：这是最直接、最简单的方法，由官方提供，稳定性和兼容性最好。对于习惯使用 Git 和 Markdown 来管理文章的用户来说非常方便。
*   **限制**：此功能是博客园 **VIP 会员服务** 的一部分。

**方法二：使用 MetaWeblog API 编写自定义脚本**

*   **发现**：博客园支持一个名为 MetaWeblog 的标准 API，它允许外部程序发布和编辑博客文章。
*   **原理**：我们可以自己编写一个脚本。这个脚本首先通过 GitHub API 获取仓库的更新（比如最新的 commit 或 issue），然后调用博客园的 MetaWeblog API，将这些内容格式化后发布为新的博文。
*   **优点**：完全免费，并且可以高度定制化。你不仅可以同步 Markdown 文件，还可以同步 GitHub Issues、Releases，甚至自定义格式。
*   **缺点**：需要一定的编程能力，自己维护脚本。

**方法三：利用 GitHub Actions 实现自动化**

*   **发现**：GitHub Actions 是一个强大的自动化工具，可以在代码推送到仓库后自动执行一系列操作。
*   **原理**：这是对方法二的增强。我们可以将调用 MetaWeblog API 的脚本配置成一个 GitHub Action。这样，每当你向 GitHub 仓库推送新的 Markdown 文件或更新时，Action 会被自动触发，执行同步脚本，将内容发布到博客园。
*   **优点**：实现了全自动化，无需手动运行脚本，是"一次配置，永久省心"的方案。
*   **缺点**：配置比单纯的脚本要复杂一些，需要理解 GitHub Actions 的 `yml` 文件配置。

### **结论与建议**

*   **如果您是博客园VIP会员，或者不介意为此付费**：强烈建议您使用 **方法一**。这是最省时省力且最稳定的方案。您只需要根据官方教程 在后台进行绑定和设置即可。
*   **如果您熟悉编程，并希望免费实现高度定制化的同步**：建议您采用 **方法二 + 方法三** 的组合。您可以先本地写好一个调用 MetaWeblog API 的脚本，测试通过后，再将其部署为 GitHub Action，实现自动化发布。

---

接下来，您希望我为您提供哪个方案的详细步骤？

1.  **博客园官方VIP功能的详细设置指南**。
2.  **如何编写一个调用 MetaWeblog API 的 Python 脚本（并提供示例代码）**。
3.  **如何将脚本配置成一个完整的 GitHub Action 实现自动化**。


## 2. 方案二 配置流程
好的，我们选择结合 **方法二（编写脚本）** 和 **方法三（GitHub Actions 自动化）**，这是一个非常强大且一劳永逸的组合。

这个方案的核心是：
1.  在 GitHub 仓库中写 Markdown 文章。
2.  当有新的提交（push）时，GitHub Actions 会自动运行一个 Python 脚本。
3.  这个脚本会找出本次提交中新增或修改的 Markdown 文件。
4.  然后，脚本通过 MetaWeblog API 将这些文件发布或更新到你的博客园。

下面是详细的步骤和代码实现。

### **第一步：开启博客园 MetaWeblog API 并获取信息**

1.  **登录博客园后台**。
2.  在 "设置" -> "其他设置" 中，确保 "允许 MetaWeblog 博客客户端访问" 选项是勾选状态。
3.  记下你的 **用户名**、**密码** 和 **MetaWeblog访问地址**。
    *   **MetaWeblog 地址**：通常是 `https://rpc.cnblogs.com/metaweblog/你的博客地址后缀` (例如: `https://rpc.cnblogs.com/metaweblog/your-blog-name`)。
    *   **博客ID (Blog ID)**：就是你的博客地址后缀，例如 `your-blog-name`。
    *   **用户名**：你的博客园登录用户名。
    *   **密码**：**注意！** 这里不是你的登录密码，而是你在博客园后台设置的 **MetaWeblog 访问令牌或密码**。如果之前没有设置过，请在后台寻找相关设置。为了安全，建议使用专门的令牌（Token）而非主密码。

### **第二步：在 GitHub 仓库中配置 Secrets**

为了不将你的博客园用户名和密码直接暴露在代码中，我们需要使用 GitHub 的 Secrets 功能来安全地存储它们。

1.  打开你的 GitHub 仓库页面。
2.  点击 "Settings" -> "Secrets and variables" -> "Actions"。
3.  点击 "New repository secret"，创建以下三个秘密变量：
    *   `CNBLOGS_RPC_URL`: 你的 MetaWeblog 访问地址。
    *   `CNBLOGS_BLOG_ID`: 你的博客 ID (博客地址后缀)。
    *   `CNBLOGS_USERNAME`: 你的博客园用户名。
    *   `CNBLOGS_PASSWORD`: 你的 MetaWeblog 访问密码或令牌。



### **第三步：准备 Python 脚本**

这是实现同步功能的核心。我们创建一个 Python 脚本，它会读取 Markdown 文件并将其发布到博客园。

1.  在你的仓库根目录下创建一个名为 `scripts` 的文件夹。
2.  在 `scripts` 文件夹中，创建一个名为 `sync_to_cnblogs.py` 的文件。
3.  将以下代码粘贴到 `sync_to_cnblogs.py` 文件中：

```python
# scripts/sync_to_cnblogs.py

import os
import sys
import xmlrpc.client
from datetime import datetime

# --- 配置信息 ---
# 从 GitHub Actions 的环境变量中获取 Secrets
RPC_URL = os.environ.get("CNBLOGS_RPC_URL")
BLOG_ID = os.environ.get("CNBLOGS_BLOG_ID")
USERNAME = os.environ.get("CNBLOGS_USERNAME")
PASSWORD = os.environ.get("CNBLOGS_PASSWORD")

# --- 函数定义 ---

def get_file_content(filepath):
    """读取文件内容"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def post_to_cnblogs(title, content, categories=None):
    """发布文章到博客园"""
    if categories is None:
        categories = ['[随笔分类]'] # 默认分类

    # 准备文章结构体
    post = {
        'title': title,
        'description': content,
        'dateCreated': datetime.now(),
        'categories': categories,
        'publish': True  # True 表示发布，False 表示存为草稿
    }

    # 连接服务器并发布
    try:
        server = xmlrpc.client.ServerProxy(RPC_URL)
        # newPost(blogid, username, password, post_struct, publish)
        post_id = server.metaWeblog.newPost(BLOG_ID, USERNAME, PASSWORD, post, True)
        print(f"✅ 成功发布文章 '{title}'，文章ID: {post_id}")
        return post_id
    except Exception as e:
        print(f"❌ 发布文章 '{title}' 失败: {e}")
        return None

# --- 主逻辑 ---

if __name__ == "__main__":
    # 检查 Secrets 是否已设置
    if not all([RPC_URL, BLOG_ID, USERNAME, PASSWORD]):
        print("❌ 错误：一个或多个环境变量 (CNBLOGS_RPC_URL, CNBLOGS_BLOG_ID, USERNAME, PASSWORD) 未设置。")
        sys.exit(1)

    # 从命令行参数获取需要发布的 Markdown 文件路径
    # GitHub Actions 会将文件路径作为参数传递给这个脚本
    if len(sys.argv) < 2:
        print("🟡 用法: python sync_to_cnblogs.py <file1.md> [file2.md] ...")
        sys.exit(0) # 如果没有文件，则正常退出

    files_to_publish = sys.argv[1:]
    print(f"🚀 准备发布以下文件: {files_to_publish}")

    for md_file in files_to_publish:
        if not os.path.exists(md_file):
            print(f"⚠️ 文件 '{md_file}' 不存在，跳过。")
            continue
        
        # 使用文件名作为文章标题 (去除.md后缀)
        post_title = os.path.basename(md_file).replace('.md', '')
        post_content = get_file_content(md_file)
        
        # 你可以在这里添加更复杂的逻辑，比如从文件元数据中提取标题和分类
        # 例如，如果文件开头有 "--- title: My Title ---" 这样的 front-matter
        
        post_to_cnblogs(post_title, post_content)

```

这个脚本做了以下几件事：
*   从环境变量安全地读取你的博客园凭据。
*   接收一个或多个 Markdown 文件路径作为命令行参数。
*   读取每个文件的内容。
*   使用文件名作为文章标题，将文件内容作为文章正文。
*   调用 MetaWeblog API (`metaWeblog.newPost`) 将文章发布出去。

### **第四步：创建 GitHub Actions 工作流**

最后一步是让 GitHub 在你推送代码时自动运行上面的脚本。

1.  在你的仓库根目录下，创建一个名为 `.github` 的文件夹。
2.  在 `.github` 文件夹中，创建一个名为 `workflows` 的文件夹。
3.  在 `workflows` 文件夹中，创建一个名为 `publish_to_cnblogs.yml` 的文件。
4.  将以下配置粘贴到 `publish_to_cnblogs.yml` 文件中：

```yaml# .github/workflows/publish_to_cnblogs.yml

name: Publish to Cnblogs

on:
  push:
    branches:
      - main
    paths:
      - '**.md'

jobs:
  # 作业一：找出变动的文件，并将其输出为 JSON 格式
  find-changed-files:
    runs-on: ubuntu-latest
    outputs:
      files: ${{ steps.changed-files.outputs.files }}
      
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Get changed markdown files
        id: changed-files
        run: |
          git config --global core.quotepath false
          
          FILES_LIST=$(git diff --name-only ${{ github.event.before }} ${{ github.sha }} -- '**.md')
          
          if [ -z "$FILES_LIST" ]; then
            echo "No markdown files changed."
            echo "files=[]" >> $GITHUB_OUTPUT
          else
            echo "Markdown files changed:"
            echo "$FILES_LIST"
            
            # 核心修复：使用纯 Shell 循环手动构建 JSON 数组，不再依赖 jq
            JSON_ARRAY="["
            FIRST=true
            # 使用 while read 循环安全地处理每一行，即使文件名包含空格
            while IFS= read -r line; do
              # 忽略空行
              if [ -z "$line" ]; then continue; fi
              
              # 转义文件名中的 " 和 \ 字符，以生成合法的 JSON 字符串
              ESCAPED_LINE=$(echo "$line" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g')
              
              if [ "$FIRST" = false ]; then
                JSON_ARRAY="$JSON_ARRAY,"
              fi
              JSON_ARRAY="$JSON_ARRAY\"$ESCAPED_LINE\""
              FIRST=false
            done <<< "$FILES_LIST"
            JSON_ARRAY="$JSON_ARRAY]"
            
            echo "Generated JSON: $JSON_ARRAY"
            echo "files=$JSON_ARRAY" >> $GITHUB_OUTPUT
          fi

  # 作业二：根据上一步的文件列表，为每个文件执行发布脚本
  publish-files:
    needs: find-changed-files
    if: ${{ needs.find-changed-files.outputs.files != '[]' }}
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        file: ${{ fromJSON(needs.find-changed-files.outputs.files) }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Publish '${{ matrix.file }}' to Cnblogs
        env:
          CNBLOGS_RPC_URL: ${{ secrets.CNBLOGS_RPC_URL }}
          CNBLOGS_BLOG_ID: ${{ secrets.CNBLOGS_BLOG_ID }}
          CNBLOGS_USERNAME: ${{ secrets.CNBLOGS_USERNAME }}
          CNBLOGS_PASSWORD: ${{ secrets.CNBLOGS_PASSWORD }}
        run: |
          python scripts/sync_to_cnblogs.py "${{ matrix.file }}"

```

## 3. 链路优化记录

- 核心修复：设置 git 配置，防止文件名中的非 ASCII 字符被转义
git config --global core.quotepath false

- 修复同步后默认使用非markdown格式不进去问题
参考：https://github.com/nickchen121/cnblogs_automatic_blog_uploading?tab=readme-ov-file

```
action test 001
```

