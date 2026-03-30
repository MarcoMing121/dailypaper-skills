---
name: social-paper-finder
description: |
  从社交平台（小红书、Twitter）发现论文。当用户提供小红书或 Twitter 链接时，
  提取内容、识别论文信息、收集博主观点。

  触发词：
  - 小红书链接：xhslink.com、xiaohongshu.com
  - Twitter 链接：twitter.com、x.com
  - "这篇小红书的论文"、"Twitter 上看到的论文"

metadata:
  {
    "openclaw": { "requires": { "bins": [], "env": [] } }
  }
---

# Social Paper Finder - 社交平台论文发现

从社交平台提取论文信息，传递给 paper-reader 进行深入阅读。

## 缓存目录

所有下载的图片存放在：
```
/root/.openclaw/workspace/.cache/social-images/
```

定期清理：cron job 每天凌晨 3 点清理超过 7 天的图片。

## Step 0: 平台识别

根据 URL 判断平台：

| 平台 | URL 模式 | 处理函数 |
|------|----------|----------|
| 小红书 | `xhslink.com/*`、`xiaohongshu.com/*` | `extract_xiaohongshu()` |
| Twitter | `twitter.com/*`、`x.com/*` | `extract_twitter()` |

## Step 1: 小红书提取 (curl 方案)

### 1.1 下载页面 HTML

```bash
curl -L -s "http://xhslink.com/o/xxx" -o /tmp/xhs.html
```

### 1.2 提取标题

```bash
grep -oP '<title>.*?</title>' /tmp/xhs.html | head -1
```

### 1.3 提取正文描述

```bash
grep -oP '<meta name="description" content="[^"]*"' /tmp/xhs.html | head -1
```

### 1.4 提取作者信息

```bash
grep -oP '"nickname":"[^"]*"' /tmp/xhs.html | head -1
```

### 1.5 提取点赞数

```bash
grep -oP '"likedCount":"[^"]*"' /tmp/xhs.html | head -1
```

### 1.6 提取并下载图片

```bash
# 提取图片 URL（需要反转义 \u002F → /）
img_url=$(grep -oP 'urlDefault":"[^"]*' /tmp/xhs.html | head -1 | sed 's/urlDefault":"//g' | sed 's/\\u002F/\//g')

# 下载到缓存目录（以笔记 ID 命名）
note_id=$(grep -oP '"noteId":"[^"]*"' /tmp/xhs.html | head -1 | sed 's/"noteId":"//g' | sed 's/"//g')
curl -s "$img_url" -o "/root/.openclaw/workspace/.cache/social-images/${note_id}.jpg"
```

### 1.7 读取图片内容

使用 `read` 工具读取下载的图片，查看内容：
```bash
read /root/.openclaw/workspace/.cache/social-images/${note_id}.jpg
```

### 小红书可提取内容

| 字段 | 提取方式 | 状态 |
|------|----------|------|
| 标题 | `<title>` | ✅ |
| 正文 | `<meta name="description">` | ✅ |
| 作者 | `"nickname":"xxx"` | ✅ |
| 点赞数 | `"likedCount":"xxx"` | ✅ |
| 笔记 ID | `"noteId":"xxx"` | ✅ |
| 图片 | `urlDefault` + 反转义 | ✅ |
| 评论 | JS 动态加载 | ❌ 暂不支持 |

## Step 2: Twitter 提取 (nitter 代理)

Twitter 官方页面需要 JS 渲染，使用 nitter.net 代理：

### 2.1 转换 URL

```
原链接: https://twitter.com/user/status/123456
代理: https://nitter.net/user/status/123456
```

### 2.2 下载页面

```bash
curl -s "https://nitter.net/user/status/123456" -o /tmp/twitter.html
```

### 2.3 提取内容

```bash
# 推文正文
grep -oP '<div class="tweet-content.*?">.*?</div>' /tmp/twitter.html

# 作者
grep -oP '<a class="fullname.*?">.*?</a>' /tmp/twitter.html | head -1

# 时间
grep -oP '<span title="[^"]*"' /tmp/twitter.html | head -1
```

### Twitter 可提取内容

| 字段 | 状态 |
|------|------|
| 推文正文 | ✅ |
| 作者 | ✅ |
| 时间 | ✅ |
| 图片 | ✅ |
| 回复 | ⚠️ 需要额外请求 |

## Step 3: 识别论文信息

从正文和评论中提取：

### 3.1 arXiv ID

匹配模式：
- `arxiv.org/abs/(\d{4}\.\d{4,5})`
- `arXiv:(\d{4}\.\d{4,5})`
- `(\d{4}\.\d{4,5})` （纯数字格式）

### 3.2 论文标题

- 正文中的 "推荐论文：XXX"
- 从 arXiv 页面获取

### 3.3 其他信息

- DOI
- 会议/期刊名称
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
  "content": "正文内容",
  "paper": {
    "arxiv_id": "2403.12345",
    "title": "论文标题",
    "url": "https://arxiv.org/abs/2403.12345"
  },
  "image_path": "/root/.openclaw/workspace/.cache/social-images/xxx.jpg",
  "warning": "⚠️ 以上内容来自社交平台，博主观点不代表论文原文，请以原始论文为准"
}
```

## Step 5: 调用 paper-reader

获取论文信息后，调用 paper-reader 技能进行深入阅读：

```
传递给 paper-reader:
- 论文 URL (arXiv/DOI)
- 社交上下文（博主观点）
```

paper-reader 会在生成的 Obsidian 笔记中添加「发现来源」section。

## 错误处理

### 未找到论文信息

```
⚠️ 未能从该内容中识别出论文信息。

已提取的内容：
[显示提取的正文]

请确认：
1. 是否包含论文链接或 arXiv ID？
2. 你可以直接告诉我论文标题或 arXiv 链接
```

### curl 请求失败

```
⚠️ 无法访问该页面，可能原因：
- 网络问题
- 链接已失效
- 平台风控限制

建议：直接提供论文的 arXiv 链接或标题
```

## 使用示例

### 小红书链接

用户：`http://xhslink.com/o/xxx`

执行流程：
1. curl 下载页面
2. 正则提取标题、正文、作者、点赞数
3. 下载图片到 `.cache/social-images/`
4. read 查看图片内容
5. 识别论文 arXiv ID
6. 调用 paper-reader 阅读论文
7. 生成 Obsidian 笔记（含来源信息）

## 注意事项

1. **内容可信度**：始终提醒用户社交平台内容是二手解读
2. **图片仅供 AI 查看**：图片存放在 `.cache/` 目录，不发送给用户
3. **评论暂不支持**：小红书评论是 JS 动态加载，curl 无法获取
4. **隐私保护**：不记录用户的社交平台登录信息

## 与 paper-reader 的协作

```
┌─────────────────────────┐
│  social-paper-finder    │
│  curl 提取内容           │
│  下载图片到 .cache/      │
│  识别论文信息            │
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
