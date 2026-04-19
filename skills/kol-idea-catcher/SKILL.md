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
```

## Step 1: 平台识别与提取

### 小红书 (xhslink.com / xiaohongshu.com)

```bash
# 下载页面
curl -L -s "{xhs_link}" -o /tmp/kol_xhs.html

# 提取标题
title=$(grep -oP '<title>.*?</title>' /tmp/kol_xhs.html | head -1 | sed 's/<[^>]*>//g')

# 提取描述
desc=$(grep -oP '<meta name="description" content="[^"]*"' /tmp/kol_xhs.html | head -1 | sed 's/.*content="//;s/"$//')

# 提取作者
author=$(grep -oP '"nickname":"[^"]*"' /tmp/kol_xhs.html | head -1 | sed 's/"nickname":"//;s/"$//')

# 提取图片
img_urls=$(grep -oP 'urlDefault":"[^"]*' /tmp/kol_xhs.html | sed 's/urlDefault":"//g' | sed 's/\\u002F/\//g')
```

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
