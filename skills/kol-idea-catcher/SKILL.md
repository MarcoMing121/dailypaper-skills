---
name: kol-idea-catcher
description: |
  从小红书、Twitter 等社交平台链接提取 KOL 观点、想法、会议 talk 启发，创建 Obsidian 笔记。
  
  触发词：
  - "小红书看到的想法"
  - "这个 talk 很有启发"
  - "KOL 分享"
  - "存一下这个链接"
  - 任意社交平台链接（xhslink.com、xiaohongshu.com、twitter.com、x.com）

  不处理论文相关链接（交给 social-paper-finder）

metadata:
  {
    "openclaw": { "requires": { "bins": ["curl"], "env": [] } }
  }
---

> **开始前**: 先确认这是想法/观点类内容，不是论文

# KOL Idea Catcher - 社交平台灵感收集

从社交平台提取 KOL 观点、会议 talk 启发、行业洞察，保存到 Obsidian 笔记库。

## 缓存目录

所有下载的图片存放在：
```
/root/.openclaw/workspaces/paper-agent/.cache/social-images/
```

定期清理：cron job 每天凌晨 3 点清理超过 7 天的图片。

## 使用场景

| 场景 | 示例 |
|------|------|
| 会议 talk | "China 3DV 26 苏昊讲物理理解的错觉，很有启发" |
| KOL 观点 | "小红书博主分享的对 VLA 的看法" |
| 行业洞察 | "Twitter 上看到的机器人趋势分析" |
| 灵感记录 | "存一下这个链接，以后可能有用" |

## 笔记保存位置

```
{VAULT_PATH}/灵光一现/种子/
```

文件命名：`{主题}_{作者}_{来源}.md`

示例：`物理理解的错觉_苏昊_3DV26.md`

## 输出格式

```markdown
---
title: "物理理解的错觉"
author: "苏昊"
source: "China 3DV 26"
platform: "xiaohongshu"
link: "http://xhslink.com/o/xxx"
created: YYYY-MM-DD
tags: [3DV, 物理理解, world-model, insight]
---

# 物理理解的错觉

## 核心观点

> 机器人对物理的理解可能只是表象...

（展开 KOL 的主要论点）

## 个人启发

- 与我的研究方向（终身学习）的关联：...
- 可能的 research gap：...

## 后续行动

- [ ] 搜索苏昊的相关论文
- [ ] 思考：如何量化"物理理解的错觉"？

## 原文链接

http://xhslink.com/o/xxx

> ⚠️ 以上内容来自社交平台，观点经二次解读，请以原始来源为准
```

## Step 1: 平台识别与提取

### 小红书 (xhslink.com / xiaohongshu.com)

#### 1.1 下载页面 HTML

```bash
curl -L -s "{xhs_link}" -o /tmp/kol_xhs.html
```

#### 1.2 提取标题

```bash
grep -oP '<title>.*?</title>' /tmp/kol_xhs.html | head -1 | sed 's/<[^>]*>//g'
```

#### 1.3 提取正文描述

```bash
grep -oP '<meta name="description" content="[^"]*"' /tmp/kol_xhs.html | head -1 | sed 's/.*content="//;s/"$//'
```

#### 1.4 提取作者信息

```bash
grep -oP '"nickname":"[^"]*"' /tmp/kol_xhs.html | head -1 | sed 's/"nickname":"//;s/"$//'
```

#### 1.5 提取点赞数

```bash
grep -oP '"likedCount":"[^"]*"' /tmp/kol_xhs.html | head -1
```

#### 1.6 提取笔记 ID

```bash
grep -oP '"noteId":"[^"]*"' /tmp/kol_xhs.html | head -1 | sed 's/"noteId":"//;s/"//g'
```

#### 1.7 提取并下载图片

```bash
# 提取图片 URL（需要反转义 \u002F → /）
img_urls=$(grep -oP 'urlDefault":"[^"]*' /tmp/kol_xhs.html | sed 's/urlDefault":"//g' | sed 's/\\u002F/\//g')

# 下载所有图片到缓存目录（以笔记 ID + 序号命名）
# 注意：图片仅存档，不在笔记中记录路径
note_id=$(grep -oP '"noteId":"[^"]*"' /tmp/kol_xhs.html | head -1 | sed 's/"noteId":"//;s/"//g')
mkdir -p /root/.openclaw/workspaces/paper-agent/.cache/social-images

i=1
for url in $img_urls; do
  curl -s "$url" -o "/root/.openclaw/workspaces/paper-agent/.cache/social-images/${note_id}_${i}.jpg"
  i=$((i+1))
done
```

#### 1.8 图片处理（⚠️ 关键：不要 read 图片！）

**❌ 不要用 `read` 工具读取图片！** 图片 base64 会占用大量上下文（每张 100-270KB），导致 context overflow。

图片的作用仅是 **供用户参考的视觉证据**，agent 不需要"看"图片来提取观点——这些信息已从 HTML 正文中提取。

**正确做法：**
- 下载图片到 `.cache/` 目录（供将来参考）
- 只在笔记中记录图片路径（不读取、不发送）
- 如果 HTML 提取失败（正文为空），使用 **OCR 或视觉模型 subagent** 单独处理，结果以文本形式返回主 session

```
✅ 正确：下载图片 → 记录路径 → 不读取
❌ 错误：下载图片 → read 图片 → base64 进入上下文
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

### Twitter/X (twitter.com / x.com)

```bash
# 使用 nitter 镜像获取（避免登录）
curl -L -s "https://nitter.net/{username}/status/{tweet_id}" -o /tmp/kol_twitter.html 2>/dev/null || \
curl -L -s "{twitter_link}" -H "User-Agent: Mozilla/5.0" -o /tmp/kol_twitter.html

# 提取推文内容
tweet_text=$(grep -oP '<div class="tweet-content[^"]*"[^>]*>.*?</div>' /tmp/kol_twitter.html | head -1 | sed 's/<[^>]*>//g')
```

## Step 2: 内容分析

分析提取的内容，识别：

1. **主题**：核心话题是什么？
2. **作者**：KOL 名字、机构
3. **来源**：会议、文章、个人经验？
4. **关键论点**：1-3 个核心观点
5. **与我研究的相关性**：关联到我的兴趣领域

## Step 3: 创建笔记

使用模板生成笔记文件：

```bash
NOTE_PATH="{VAULT_PATH}/灵光一现/种子/{主题}_{作者}_{来源}.md"
```

**必须包含的章节**：
1. 核心观点（KOL 原话 + 我的理解）
2. 个人启发（与我的研究方向的关联）
3. 后续行动（todo items）

## Step 4: Git 提交

```bash
cd {VAULT_PATH}
git add "灵光一现/种子/{filename}.md"
git commit -m "add kol idea: {主题} by {作者}"
[if GIT_PUSH_ENABLED] git push
```

## 与 social-paper-finder 的区别

| 技能 | 处理内容 | 输出 |
|------|----------|------|
| social-paper-finder | 社交平台上的**论文分享** | 提取论文信息 → 交给 paper-reader |
| kol-idea-catcher | 社交平台上的**观点/想法/insight** | 创建想法笔记 |

**判断标准**：
- 链接内容主要是**论文介绍/推荐** → social-paper-finder
- 链接内容是**个人观点/会议 talk/行业洞察** → kol-idea-catcher

## 示例

**输入**：
> 物理理解的错觉 苏昊 China 3DV 26 一天下来感触颇多... http://xhslink.com/o/xxx

**输出笔记位置**：
`灵光一现/种子/物理理解的错觉_苏昊_3DV26.md`

**笔记内容**：
- 苏昊在 3DV 上的 talk 要点
- 与终身学习/表征学习的关联思考
- 后续 todo：搜索相关论文、思考研究方向
