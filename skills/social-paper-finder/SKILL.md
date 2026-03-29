---
name: social-paper-finder
description: |
  从社交平台（小红书、Twitter）发现论文。当用户提供小红书或 Twitter 链接时，
  提取内容、识别论文信息、收集博主观点和热门评论。

  触发词：
  - 小红书链接：xhslink.com、xiaohongshu.com
  - Twitter 链接：twitter.com、x.com
  - "这篇小红书的论文"、"Twitter 上看到的论文"

metadata:
  {
    "openclaw": { "requires": { "bins": ["agent-browser"], "env": [] } }
  }
---

# Social Paper Finder - 社交平台论文发现

从社交平台提取论文信息，传递给 paper-reader 进行深入阅读。

## Step 0: 平台识别

根据 URL 判断平台：

| 平台 | URL 模式 | 处理函数 |
|------|----------|----------|
| 小红书 | `xhslink.com/*`、`xiaohongshu.com/*` | `extract_xiaohongshu()` |
| Twitter | `twitter.com/*`、`x.com/*` | `extract_twitter()` |

## Step 1: 使用 agent-browser 访问页面

### 1.1 打开链接

```bash
agent-browser open "<url>"
agent-browser wait 3000  # 等待页面加载
```

### 1.2 获取页面快照

```bash
agent-browser snapshot -i
```

### 1.3 截图（可选，用于调试）

```bash
agent-browser screenshot /tmp/social_page.png
```

## Step 2: 提取内容

### 小红书提取流程

1. **识别页面类型**：
   - 笔记详情页（有正文内容）
   - 需要登录的页面（提示用户）

2. **提取正文内容**：
   ```bash
   # 找到正文区域的文字
   agent-browser get text @content_selector
   ```

3. **提取博主信息**：
   - 博主昵称
   - 博主 ID
   - 发布时间

4. **提取评论**（前 10 条）：
   - 滚动到评论区
   - 获取热门评论内容和点赞数

### Twitter 提取流程

1. **提取推文内容**：
   - 推文正文
   - 作者信息
   - 发布时间
   - 点赞/转发数

2. **提取回复**（前 10 条）：
   - 热门回复内容
   - 回复者信息

## Step 3: 识别论文信息

从正文和评论中提取：

### 3.1 arXiv ID

匹配模式：
- `arxiv.org/abs/(\d{4}\.\d{4,5})`
- `arXiv:(\d{4}\.\d{4,5})`
- `(\d{4}\.\d{4,5})` （纯数字格式）

### 3.2 论文标题

- 引言中的 "推荐论文：XXX"
- 论文链接的标题
- 从 arXiv 页面获取

### 3.3 其他信息

- DOI
- 会议/期刊名称
- 作者
- GitHub 链接

## Step 4: 整理输出

### 输出格式

```json
{
  "platform": "xiaohongshu" | "twitter",
  "source_url": "原始链接",
  "author": {
    "name": "博主/推主昵称",
    "id": "平台ID"
  },
  "post_time": "发布时间",
  "content": "正文内容",
  "paper": {
    "arxiv_id": "2403.12345",
    "title": "论文标题",
    "url": "https://arxiv.org/abs/2403.12345",
    "doi": null,
    "venue": "arXiv",
    "github": null
  },
  "comments": [
    {
      "author": "评论者",
      "content": "评论内容",
      "likes": 10
    }
  ],
  "extracted_at": "提取时间",
  "warning": "⚠️ 以上内容来自社交平台，博主观点和评论不代表论文原文，请以原始论文为准"
}
```

## Step 5: 调用 paper-reader

获取论文信息后，调用 paper-reader 技能进行深入阅读：

```
传递给 paper-reader:
- 论文 URL (arXiv/DOI)
- 社交上下文（博主观点 + 评论）
```

paper-reader 会在生成的 Obsidian 笔记中添加「发现来源」section。

## 错误处理

### 页面需要登录

```
⚠️ 该小红书页面需要登录才能查看完整内容。

建议：
1. 你可以在小红书 App 中查看并告诉我论文标题
2. 或者提供论文的 arXiv 链接
```

### 未找到论文信息

```
⚠️ 未能从该内容中识别出论文信息。

已提取的内容：
[显示提取的正文]

请确认：
1. 是否包含论文链接或 arXiv ID？
2. 你可以直接告诉我论文标题或 arXiv 链接
```

### agent-browser 失败

```
⚠️ 无法访问该页面，可能原因：
- 网络问题
- 链接已失效
- 平台风控限制

建议：直接提供论文的 arXiv 链接或标题
```

## 使用示例

### 小红书链接

用户：`https://www.xiaohongshu.com/explore/xxx`

执行流程：
1. agent-browser 打开页面
2. 提取正文："推荐一篇 CVPR 2024 的论文，arXiv:2403.12345..."
3. 识别论文：arXiv:2403.12345
4. 提取博主观点 + 前 10 条评论
5. 调用 paper-reader 阅读论文
6. 生成 Obsidian 笔记（含来源信息）

### Twitter 链接

用户：`https://twitter.com/user/status/xxx`

执行流程：
1. agent-browser 打开页面
2. 提取推文内容
3. 识别论文信息
4. 提取前 10 条回复
5. 调用 paper-reader 阅读论文
6. 生成 Obsidian 笔记（含来源信息）

## 注意事项

1. **内容可信度**：始终提醒用户社交平台内容是二手解读
2. **截图不保存**：只用于临时分析，不存入 Obsidian
3. **评论数量**：最多提取前 10 条热门评论
4. **隐私保护**：不记录用户的社交平台登录信息

## 与 paper-reader 的协作

```
┌─────────────────────────┐
│  social-paper-finder    │
│  提取论文信息            │
│  收集社交上下文          │
└─────────────────────────┘
           │
           ▼ 传递论文 URL + 社交上下文
┌─────────────────────────┐
│  paper-reader           │
│  阅读原始论文            │
│  生成 Obsidian 笔记     │
│  添加「发现来源」section │
└─────────────────────────┘
```
