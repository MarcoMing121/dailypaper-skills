---
name: paper-reader
description: |
  Use when user asks to "read paper", "analyze paper", "summarize paper",
  "读论文", "分析文献", "帮我看一下这篇paper", "论文笔记", or provides a PDF file
  that appears to be an academic paper. Specialized for CV/DL papers.

  Also supports Zotero integration: "读一下这篇论文 ...", "快速看一下这篇论文 ...",
  "批判性分析这篇论文 ...", "读一下 Zotero 里的 XXX", "批量读一下 Zotero 里 VLA 分类下的论文"

  **社交平台支持**: 接收来自 social-paper-finder 的论文信息，支持小红书、Twitter 等平台发现的论文。

  **重要触发词**: "读一下 XXX"、"读一下这篇"、"帮我读" → 必须调用此 skill
metadata:
  {
    "openclaw": { "requires": { "bins": ["python3", "mineru-open-api"], "env": [] } },
  }
---

> **开始前**: 先跟用户打个招呼 🐕

# 学术论文阅读助手 (Paper Reader)

专注 CV/DL 领域，支持 Zotero 集成和 Obsidian 笔记保存。

## ⚠️ Step -1: 上下文检查（CRITICAL - 必须最先执行）

**在开始任何论文阅读前，必须检查上下文使用情况！**

### 检查方法

运行 `session_status` 工具查看当前上下文使用率。

### 上下文阈值

**阈值：50% (100k tokens / 200k total)**

| 上下文使用率 | 操作 |
|--------------|------|
| **< 50%** | 正常继续 |
| **≥ 50%** | ⚠️ 先 compact，再处理论文 |
| **≥ 70%** | 🚨 必须立即 compact |

### 为什么需要检查

1. **长上下文影响推理质量**：上下文过长会降低模型的推理能力
2. **避免认知过载**：确保有足够空间处理复杂任务（图片提取、公式分析）
3. **保证笔记质量**：短上下文下生成的笔记更完整、更准确

### 执行步骤

```
1. 调用 session_status 查看上下文
2. 如果 Context Usage ≥ 50%：
   - 告诉用户："上下文较长，我先 compact 一下再处理"
   - 等待系统 compact
3. Context Usage < 50%：
   - 继续 Step 0
```

### 禁止事项

- ❌ **禁止在长上下文下处理论文**（会导致笔记质量下降）
- ❌ **禁止跳过上下文检查**
- ❌ **禁止忽略阈值警告**

---

## Step 0: 读取共享配置

先读取 `../_shared/user-config.json`，如果 `../_shared/user-config.local.json` 存在，再用它覆盖默认值。

显式生成并在后续统一使用这些变量：

- `VAULT_PATH`
- `NOTES_PATH` = `{VAULT_PATH}/{paper_notes_folder}`
- `CONCEPTS_PATH` = `{VAULT_PATH}/{concepts_folder}`
- `ASSETS_ROOT` = `{VAULT_PATH}/assets`
- `ASSETS_PATH` = `{VAULT_PATH}/assets/{method_name}` (每篇笔记独立的 assets 目录)
- `TOPIC_MOC_PATH` = `{CONCEPTS_PATH}/MOCs`
- `ZOTERO_DB`
- `ZOTERO_STORAGE`
- `AUTO_REFRESH_INDEXES`
- `GIT_COMMIT_ENABLED`
- `GIT_PUSH_ENABLED`

其中 `GIT_PUSH_ENABLED` 只有在 `GIT_COMMIT_ENABLED=true` 时才可能为真。

**⚠️ ASSETS_PATH 说明**：

每篇笔记有独立的 assets 目录，结构如下：
```
VAULT_PATH/
├── Papers/
│   └── 2-VLA/
│       └── Pi05.md          ← 笔记文件
└── assets/
    └── Pi05/                ← 该笔记的 assets 目录
        ├── fig1.png
        └── fig2.png
```

**图片引用格式**：
- 在笔记中使用 Obsidian wikilink：`![[Pi05/fig1.png]]`
- 注意包含方法名前缀，确保路径正确

后续统一使用上面的变量。

## 1. 接收论文

| 输入方式      | 示例                                   | 处理方法                     |
| ------------- | -------------------------------------- | ---------------------------- |
| PDF 路径      | `/path/to/paper.pdf`                   | 直接 Read                    |
| arXiv 链接    | `https://arxiv.org/abs/xxxx`           | WebFetch                     |
| Zotero 分类   | "VLA 分类的论文"                       | 查询数据库 → 列出 → 用户选择 |
| Zotero 搜索   | "Zotero 里的 π0.5"                     | 搜索标题 → 找到 PDF          |
| 无 PDF        | Zotero 条目无附件                      | 从网上获取（见下方）         |
| **社交平台**  | 来自 social-paper-finder 的结构化信息  | 见下方「社交上下文」         |

### 1.1 社交上下文（来自 social-paper-finder）

当论文信息来自社交平台（小红书、Twitter）时，会收到额外的上下文：

```json
{
  "paper": { "arxiv_id": "xxx", "title": "...", "url": "..." },
  "social_context": {
    "platform": "xiaohongshu" | "twitter",
    "author": { "name": "博主名", "id": "xxx" },
    "summary": "博主观点...",
    "comments": ["评论1", "评论2", ...]  // 最多10条
  }
}
```

**处理方式**：
1. 正常阅读论文，生成笔记
2. 在笔记末尾添加「发现来源」section（见模板）
3. 明确标注社交内容为二手解读，非论文原文

### 无 PDF 时的获取流程

1. `python3 assets/zotero_helper.py info {item_id}` 获取论文信息
2. 按优先级获取：arXiv HTML（外链）> **MinerU PDF 解析** > 项目主页 > arXiv PDF > DOI
3. 判断 arXiv ID：从 URL / Zotero extra 字段 / 标题搜索
4. 首选 MinerU：下载 PDF 后提取（图片 + 表格 + 公式最完整）
5. 跳过条件：既无 PDF 也无在线来源 / 非论文内容

> Zotero 详细操作见 `references/zotero-guide.md`

### ⚠️ 1.5 并行分块提取大论文（CRITICAL - Subagent 模式）

> **更新 (2026-04-04)**：改用 subagent 并行处理，提升大论文处理效率。

#### 问题
- arXiv HTML 可能很大（100KB+，1742 行）
- 一次性读取会导致 API 超时、token 超限、模型处理失败
- **串行分块读取速度慢**

#### 解决方案：并行 Subagent 提取

**核心思路**：
- 每个 chunk 由一个独立的 subagent 处理
- 所有 subagent **并行运行**
- 主 session 汇总结果后生成笔记

**流程图**：

```
┌─────────────────────────────────────────────────────────────┐
│  Main Session                                                │
│  1. 下载 HTML → 检查行数                                      │
│  2. 分割成 chunks（每块 ≤300 行）                             │
│  3. 并行 spawn subagents                                     │
│     ├─ Subagent 1 (chunk 1) ──┐                             │
│     ├─ Subagent 2 (chunk 2) ──┼──→ 返回结构化 JSON           │
│     ├─ Subagent 3 (chunk 3) ──┤                             │
│     └─ Subagent N (chunk N) ──┘                             │
│  4. 汇总所有 JSON 结果                                        │
│  5. 生成完整笔记                                              │
└─────────────────────────────────────────────────────────────┘
```

#### Step 1: 下载与分割

```bash
# 1. 下载 HTML
ARXIV_ID="2508.10333"
curl -sL "https://arxiv.org/html/${ARXIV_ID}" -o /tmp/paper_${ARXIV_ID}.html

# 2. 检查行数
LINES=$(wc -l < /tmp/paper_${ARXIV_ID}.html)
echo "Total lines: $LINES"

# 3. 如果 > 500，分割成 chunks
if [ $LINES -gt 500 ]; then
  # 每块最多 300 行
  CHUNK_SIZE=300
  NUM_CHUNKS=$(( ($LINES + $CHUNK_SIZE - 1) / $CHUNK_SIZE ))
  
  for i in $(seq 1 $NUM_CHUNKS); do
    START=$(( ($i - 1) * $CHUNK_SIZE + 1 ))
    END=$(( $i * $CHUNK_SIZE ))
    [ $END -gt $LINES ] && END=$LINES
    sed -n "${START},${END}p" /tmp/paper_${ARXIV_ID}.html > /tmp/paper_chunk_${i}.html
    echo "Created chunk $i: lines $START-$END"
  done
fi

# 4. 提取图片 URLs（独立于文本分块）
grep -E '<img.*src=' /tmp/paper_${ARXIV_ID}.html | \
  sed 's/.*src="\([^"]*\)".*/\1/' > /tmp/images_${ARXIV_ID}.txt
```

#### Step 2: 并行 Spawn Subagents

**使用 `sessions_spawn` 并行启动多个 subagent**：

```xml
<!-- 每个 chunk 一个 subagent，并行运行 -->
<sessions_spawn runtime="subagent" mode="run" 
  task="Extract structured information from /tmp/paper_chunk_1.html (lines 1-300).
        Return JSON with: {sections, figures, formulas, tables, key_insights}." 
  label="chunk-1-extractor" />

<sessions_spawn runtime="subagent" mode="run"
  task="Extract structured information from /tmp/paper_chunk_2.html (lines 301-600).
        Return JSON with: {sections, figures, formulas, tables, key_insights}." 
  label="chunk-2-extractor" />

<!-- ... 更多 subagents ... -->
```

**关键点**：
- `mode="run"` — 一次性任务，完成后自动结束
- 不指定 `timeoutSeconds` — 让 subagent 自然完成
- **所有 subagent 同时启动**，无需等待前一个

#### Step 3: Subagent 输出格式

**每个 subagent 必须返回结构化 JSON**：

```json
{
  "chunk_id": 1,
  "lines": "1-300",
  "sections": [
    {
      "title": "Introduction",
      "content": "核心内容摘要..."
    }
  ],
  "figures": [
    {
      "id": "Figure 1",
      "caption": "...",
      "url": "https://arxiv.org/html/xxx/assets/x1.png"
    }
  ],
  "formulas": [
    {
      "name": "Loss Function",
      "latex": "$$L = \\sum_{i} ...$$",
      "meaning": "损失函数定义",
      "symbols": {"L": "loss", "i": "index"}
    }
  ],
  "tables": [
    {
      "id": "Table 1",
      "caption": "实验结果对比",
      "content": "Markdown 表格..."
    }
  ],
  "key_insights": [
    "本文提出的方法...",
    "核心贡献是..."
  ]
}
```

#### Step 4: 主 Session 汇总

**等待所有 subagent 完成后，汇总结果**：

```bash
# 检查 subagent 完成状态
subagents action=list recentMinutes=5

# 收集所有 subagent 的输出
# (OpenClaw 会自动将 subagent 结果返回给主 session)
```

**汇总逻辑**：
1. 合并所有 `sections` → 构建完整大纲
2. 合并所有 `figures` → 确保图片数量完整
3. 合并所有 `formulas` → 去重、检查符号一致性
4. 合并所有 `tables` → 完整保留
5. 合并所有 `key_insights` → 提取核心贡献

#### 图片提取（独立于文本分块）

图片 URLs 单独提取，不受分块限制：

```bash
# 主 session 直接提取所有图片 URLs
grep -E '<img.*src=' /tmp/paper_${ARXIV_ID}.html | \
  sed 's/.*src="\([^"]*\)".*/\1/' > /tmp/images.txt
```

#### 禁止事项

- ❌ 禁止在主 session 读取大 HTML 文件（>500 行）
- ❌ 禁止串行等待每个 subagent（必须并行 spawn）
- ❌ 禁止 subagent 返回非结构化文本（必须返回 JSON）

#### 自检清单

- [ ] 已检查 HTML 行数？
- [ ] 行数 > 500 已分割？
- [ ] 所有 subagent 已并行启动？
- [ ] 每个 subagent 返回了有效 JSON？
- [ ] 已汇总所有 chunks 的结果？

---

## 2. 阅读模式

| 模式         | 触发词                   | 输出                 |
| ------------ | ------------------------ | -------------------- |
| **快速摘要** | "快速看一下"、"quick"    | 3-5 句核心贡献       |
| **完整解析** | "详细分析"、默认         | 结构化笔记（用模板） |
| **批判分析** | "批判性分析"、"critique" | 方法论优缺点评估     |
| **知识提取** | "提取公式"、"技术细节"   | 公式 + 算法伪代码    |
| **第一性原理分析** | "深度分析"、"第一性原理"、"6点分析" | 按6点框架深度解析论文 |

## 3. 笔记生成

**模板**: 严格遵循 `assets/paper-note-template.md`，不可自行简化。

### 核心质量规则

1. **零遗漏**: 论文中所有 Figure、所有公式、所有 Table 必须全部出现在笔记中
2. **内联概念链接**: 正文中首次出现的技术术语必须用 `[[概念]]` 链接，不仅仅是结尾
3. **严禁 ASCII 流程图**: 用结构化 Markdown 列表 + `$数学符号$` 描述架构
4. **公式完整性**: 每个公式必须有名称（`[[概念|名称]]`）、LaTeX 公式、含义、符号说明
5. **MinerU 优先**: 使用 MinerU 自动提取图片、表格、公式，无需手动处理
6. **第一性原理分析**: 当使用"深度分析"、"第一性原理"、"6点分析"模式时，必须在笔记中包含完整的6点框架分析

> 公式/图片/表格的详细质量规范见 `references/quality-standards.md`

### ⚠️ 图片处理（MinerU 自动化）

**核心原则**：MinerU 自动处理图片、表格、公式，无需手动下载或检查可达性。

**自检清单**：
- [ ] 已使用 MinerU 提取 PDF 内容？
- [ ] 已检查 MinerU 输出的 images/ 目录？
- [ ] 图片已复制到 `ASSETS_PATH` 并在笔记中引用？
- [ ] 图片数量与论文 Figure 数量一致？

### 图片获取流程（外链优先 + MinerU + 项目主页兜底）

**核心原则：外链优先，MinerU 其次，项目主页兜底**

> **为什么外链优先？**
> - 最简单直接，无需下载和处理
> - 图片与 arXiv 保持同步

**优先级**：arXiv HTML（外链）> MinerU PDF（本地）> 项目主页（外链）

**Step 1: arXiv HTML（首选，外链）**

```bash
# 1. 检查官方 HTML
curl -sI "https://arxiv.org/html/{arxiv_id}" | head -1

# 2. 如果返回 200，提取图片（用外链写入笔记）
curl -sL "https://arxiv.org/html/{arxiv_id}" | grep -E '<figure|<img.*src='
```

**图片 URL 格式**：
```
✅ 正确：https://arxiv.org/html/2603.19312v2/x1.png
❌ 错误：https://ar5iv.labs.arxiv.org/html/2603.07648/assets/x1.png
```

**Step 2: MinerU PDF 解析（本地，外链不可用时使用）**

**当 arXiv HTML 没有图片时**，用 MinerU 从 PDF 提取：

```bash
# 1. 下载 PDF
curl -sL "https://arxiv.org/pdf/${ARXIV_ID}.pdf" -o /tmp/paper_${ARXIV_ID}.pdf

# 2. MinerU extract（已配置 token）
mineru-open-api extract /tmp/paper_${ARXIV_ID}.pdf -o /tmp/paper_mineru_${ARXIV_ID}/ -f md,json --language en --model pipeline

# 3. 输出结构
# /tmp/paper_mineru_${ARXIV_ID}/
# ├── paper.md          ← Markdown 内容（含 LaTeX 公式）
# ├── paper.json        ← 结构化 JSON
# └── images/           ← 自动提取的图片
```

**MinerU 优势**（vs pdfimages / 外链）：
- **表格识别**：自动转换为 Markdown 表格
- **公式识别**：LaTeX 格式输出
- **图片提取**：自动分离并保存到 images/ 目录
- **OCR 支持**：80+ 语言
- **内容完整**：不会遗漏任何 Figure

**Step 3: 项目主页（外链，MinerU 也失败时使用）**

查找项目主页图片：
```bash
# 1. 从摘要/HTML 查找项目主页 URL
grep -E 'project page|github.io|our website' /tmp/paper_html.txt

# 2. 提取图片 URL，用外链写入笔记
```

**Step 4: 复制 MinerU 图片到 Vault**

```bash
VAULT=/root/.openclaw/shared/ObsidianVault
ASSETS_PATH=$VAULT/assets/{method_name}

mkdir -p $ASSETS_PATH
cp /tmp/paper_mineru_${ARXIV_ID}/images/*.jpg $ASSETS_PATH/

# 重命名为有意义的文件名（按 Figure 编号）
mv $ASSETS_PATH/xxx.jpg $ASSETS_PATH/fig1-overview.jpg
```

**笔记中引用**：

| 来源 | 格式 | 示例 |
|------|------|------|
| **arXiv HTML（首选）** | Markdown 外链 | `![](https://arxiv.org/html/xxx/x1.png)` |
| MinerU PDF | Obsidian wikilink | `![[NCP/fig1-overview.jpg\|500]]` |
| 项目主页 | Markdown 外链 | `![](https://project.page/xxx.png)` |

### ⚠️ 禁止事项

- ❌ **禁止使用 ar5iv 链接**（可能返回空白图片）
- ❌ **禁止跳过图片**（必须包含所有 Figure）
- ❌ **禁止从 PDF 用 pdfimages**（用 MinerU 替代）

### 公式格式

每个公式必须包含：名称（`[[概念|名称]]`）、LaTeX `$$` 块（前后留空行）、含义、符号列表。
`$$` 块前后**必须有空行**否则 Obsidian 不渲染。超长公式用 `aligned` 拆分。

## 4. Obsidian 保存

### 文件命名

只用**方法名/模型名**：`{方法名}.md`（如 `Pi05.md`，不加年份前缀）。
方法名判断：标题冒号前 / Abstract 中 "We propose XXX" / 希腊字母转 ASCII。
不确定时保存到 `_Inbox/`。

### 保存路径

按研究兴趣分类：

| 分类 | 路径 | 适用论文 |
|------|------|----------|
| **1-Continual-Learning** | `{NOTES_PATH}/1-Continual-Learning/` | 持续学习、灾难性遗忘、终身学习 |
| **2-VLA** | `{NOTES_PATH}/2-VLA/` | Vision-Language-Action、机器人策略 |
| **3-World-Model** | `{NOTES_PATH}/3-World-Model/` | 世界模型、JEPA、预测模型 |
| **4-RL-Theory** | `{NOTES_PATH}/4-RL-Theory/` | 强化学习理论、奖励建模 |
| **5-Deep-Learning** | `{NOTES_PATH}/5-Deep-Learning/` | 深度学习基础、架构创新 |
| **_Inbox** | `{NOTES_PATH}/_Inbox/` | 待分类 |

**分类判断**：看论文 tags 的第一个标签 + Abstract 核心问题。

### YAML frontmatter

```yaml
---
title: "论文标题"
method_name: "MethodName"
authors: [Author1, Author2]
year: 2025
venue: arXiv
tags: [tag1, tag2] # 小写连字符，3-8 个
zotero_collection: 3-Robotics/1-VLX/VLA
image_source: online
created: YYYY-MM-DD
---
```

Tags 判断：看 Related Work 小标题 + Abstract 关键词。第一个 tag 是最核心主题。

### 保存后自动执行

1. 只有在 `AUTO_REFRESH_INDEXES=true` 时才刷新目录页：
   ```bash
   python3 ../_shared/generate_concept_mocs.py
   python3 ../_shared/generate_paper_mocs.py
   ```
2. 只有在 `GIT_COMMIT_ENABLED=true` 时才做 git：
   - 先确认 `VAULT_PATH/.git` 存在
   - `git add {新增文件} {paper_notes_folder}/` 后必须真的有 staged changes
   - 满足条件后再执行：

   ```bash
   cd {VAULT_PATH} && git add {新增文件} {paper_notes_folder}/ && git commit -m "add paper note: {方法名}"
   ```

   - 只有在 `GIT_PUSH_ENABLED=true` 且仓库已配置远端时才 push

## 5. 概念库维护（每篇论文必做）

概念库位置：`{CONCEPTS_PATH}`

### ⚠️ 链接格式规则（CRITICAL）

**概念文件命名**: 使用下划线连接单词

```
✅ 正确: Experience_Replay.md
❌ 错误: Experience Replay.md (空格)
❌ 错误: Experience-Replay.md (连字符)
```

**概念链接格式**: 必须与文件名完全匹配

```
✅ 正确: [[Experience_Replay]]
❌ 错误: [[Experience Replay]] (空格不匹配)
❌ 错误: [[Experience-Replay]] (连字符不匹配)
```

**为什么必须用下划线？**
- Obsidian 的 `[[Wiki Link]]` 语法会将空格视为合法，但文件系统更倾向于下划线
- 保持一致性：文件名和链接必须一一对应
- 避免"链接存在但无法跳转"的问题

**检查方法**:
```bash
# 检查链接是否匹配文件
# 如果链接是 [[Experience_Replay]]
ls Concepts/*/*Experience_Replay.md  # 应该找到文件
```

### 流程

#### Step 1: 扫描概念链接

```bash
# 提取所有 [[概念]] 链接
grep -oE '\[\[([A-Za-z0-9_-]+)\]\]' {笔记路径} | \
  sed 's/\[\[\(.*\)\]\]/\1/' | sort -u
```

#### Step 2: 检查缺失概念

```bash
# 检查每个概念是否存在
for concept in $(grep -oE '\[\[([A-Za-z0-9_-]+)\]\]' {笔记路径} | sed 's/\[\[\(.*\)\]\]/\1/' | sort -u); do
  if ! find Concepts -name "${concept}.md" | grep -q .; then
    echo "missing: $concept"
  fi
done
```

#### Step 3: 并行创建缺失概念（Subagent 模式）

> **更新 (2026-04-04)**: 使用 subagent 并行创建概念，提升效率。

**适用场景**：缺失概念 ≥ 3 个时使用并行模式

**并行 Spawn 示例**：

```xml
<sessions_spawn runtime="subagent" mode="run"
  task="Create concept note for Implicit_Grounding.
        
        1. Read the paper note at {VAULT_PATH}/Papers/2-VLA/ReconVLA.md
        2. Extract definition, math formulas, key points about Implicit_Grounding
        3. Create concept file at {VAULT_PATH}/Concepts/3-Architectures/Implicit_Grounding.md
        4. Follow the template in references/concept-categories.md
        5. Include ReconVLA as representative work
        
        Required sections:
        - 定义 (one sentence definition with paper citation)
        - 数学形式 (LaTeX with symbol explanation)
        - 核心要点 (2-3 key points from paper)
        - 代表工作 (list ReconVLA)
        - 相关概念 (other concepts from the paper)"
  label="concept-Implicit_Grounding" />

<sessions_spawn runtime="subagent" mode="run"
  task="Create concept note for Visual_Grounding..."
  label="concept-Visual_Grounding" />

<!-- 更多 subagents... -->
```

**关键点**：
- `mode="run"` — 一次性任务，完成后自动结束
- 所有 subagent **并行启动**
- 每个 subagent 独立读取论文笔记并创建概念文件

**优势**：

| 方式 | 速度 | 上下文消耗 |
|------|------|-----------|
| 串行创建 | 3个×30秒=90秒 | 高（主 session 承担） |
| 并行创建 | ~30秒完成全部 | 低（分散到 subagent） |

#### Step 4: 主 Session 汇总

等待所有 subagent 完成后，汇总结果：

- 统计新增概念数量
- 刷新概念目录页（如果 `AUTO_REFRESH_INDEXES=true`）

### Subagent 任务模板

**每个 subagent 必须接收完整的内容规范**：

```
Create concept note for {Concept_Name}.

1. Read the paper note at {笔记路径}
2. Extract from the paper:
   - 定义: one sentence definition with paper citation
   - 数学形式: LaTeX formula with symbol explanation
   - 核心要点: 2-3 key points extracted from paper
   - 代表工作: list the current paper
   - 相关概念: other [[Concept]] links from the paper
3. Determine concept category:
   - 1-Foundations/: 基础概念、理论
   - 2-Methods/: 方法、算法
   - 3-Architectures/: 模型架构
   - 4-RL/: 强化学习
   - 5-Robotics/: 机器人相关
   - 6-Techniques/: 具体技术
   - 7-Datasets/: 数据集
4. Create file at {CONCEPTS_PATH}/{category}/{Concept_Name}.md
5. Use template from references/concept-categories.md
```

**禁止事项**：
- ❌ 禁止简化指令（如"快速创建"、"精简版"）
- ❌ 禁止跳过必填项
- ❌ 禁止创建空概念

### 创建概念时必须填充内容

**⚠️ CRITICAL - 禁止创建空的概念笔记！**

使用 `references/concept-categories.md` 中的模板，**必须从论文中提取**以下信息填充：

| 必填项 | 来源 | 说明 |
|--------|------|------|
| **定义** | Abstract/Introduction/Preliminary | 一句话定义，必须引用论文原文或转述 |
| **数学形式** | 论文中的公式 | LaTeX 格式，含符号说明 |
| **核心要点** | 从论文提取 | 2-3 个关键点，不能是空的 |
| **代表工作** | 当前论文 | 必须添加当前论文 |
| **相关概念** | 笔记中其他概念 | 使用 `[[Concept_Name]]` 格式 |

**禁止事项**:
- ❌ 禁止创建只有标题和空 section 的概念
- ❌ 禁止使用通用描述代替论文特定内容
- ❌ 禁止跳过任何必填项

**每个新概念必须有实质内容，否则视为任务失败。**

> 分类规则和模板见 `references/concept-categories.md`

### 概念分类目录

概念按学科层级分类到以下目录：

| 目录 | 归类标准 | 示例 |
|------|----------|------|
| `1-Foundations/` | 基础概念、理论 | Catastrophic_Forgetting, Stability-Plasticity_Dilemma |
| `2-Methods/` | 方法、算法 | Adapter, LoRA, MoE, EWC |
| `3-Architectures/` | 模型架构 | VLA, CLIP, World-Model |
| `4-RL/` | 强化学习 | RL, Policy-Learning |
| `5-Robotics/` | 机器人相关 | Skill-Learning, Robot-Robustness |
| `6-Techniques/` | 具体技术 | Flow-Matching, Diffusion-Policy |
| `7-Datasets/` | 数据集 | LIBERO, RoboTwin |

### 自检

- [ ] 笔记中所有 `[[概念]]` 链接的概念笔记都存在？
- [ ] 概念笔记包含本论文作为"代表工作"？

## 6. 完成后自动 QA（CRITICAL - 必须执行）

### ⚠️ 自动 QA 流程

**笔记创建完成后，必须启动 QA subagent 进行自动检查和修复！**

### 流程

```
创建笔记
    ↓
启动 QA subagent (sessions_spawn)
    ↓
┌─────────────────────────────────┐
│  QA Subagent (LLM + 脚本):       │
│  1. 运行检查脚本                  │
│  2. 分析问题                      │
│  3. 自动修复所有问题               │
│     ├─ Frontmatter → 补全字段     │
│     ├─ 图片不可达 → 下载图片       │
│     ├─ 公式格式 → 修正 LaTeX      │
│     ├─ 概念缺失 → 创建概念笔记     │
│     └─ 内容遗漏 → 补充内容         │
│  4. 重新检查验证                   │
│  5. 循环直到通过（最多 3 轮）      │
└─────────────────────────────────┘
    ↓
返回 QA 报告
```

### 启动 QA Subagent

**使用 `sessions_spawn` 启动 QA subagent，它会运行检查并生成报告：**

```xml
<sessions_spawn runtime="subagent" mode="run"
  task="Run QA check on paper note and generate report.

**Skill to use**: skills/paper-qa/SKILL.md

**Steps**:
1. Read the QA skill at skills/paper-qa/SKILL.md
2. Run QA script: python3 skills/paper-qa/qa_check.py {笔记路径}
3. Analyze the results
4. Generate a human-readable report with:
   - Passed checks ✅
   - Failed checks ❌ (with specific issues)
   - Recommended actions

**Output**: Return the QA report in human-readable format.

**Note**: DO NOT auto-fix. Just report issues for user to decide."
  label="qa-{method_name}" />
```

### QA 检查项目

| 检查项 | 说明 | 结果示例 |
|--------|------|----------|
| **structure** | 文件命名、路径 | ✅ PASS |
| **frontmatter** | 必需字段完整性 | ✅ PASS |
| **save_path** | 保存路径分类 | ✅ PASS (category: 2-VLA) |
| **git_status** | Git 状态 | ✅ PASS |
| **content_stats** | Figure/Table/公式数量统计 | ✅ PASS (figures: 3, tables: 27) |
| **concepts** | 概念链接有效性 | ❌ FAIL (Missing: RLOO, Pass_at_k) |
| **figures** | 图片格式、可达性、大小 | ✅ PASS |
| **formulas** | LaTeX 兼容性 | ✅ PASS |
| **formula_format** | $$ 块前后空行 | ✅ PASS |
| **formula_naming** | 公式命名 | ❌ FAIL (Formula 4, 5 missing names) |
| **symbol_explanation** | 符号说明 | ❌ FAIL (12 formulas missing symbols) |
| **concept_content** | 概念内容质量 | ❌ FAIL (1 concept too short) |
| **representative_work** | 代表工作 | ✅ PASS |

### QA 报告示例

```
============================================================
QA Report: Papers/4-RL-Theory/MaxRL.md
Final Status: FAILED
============================================================

✅ PASSED CHECKS:
  Structure, Frontmatter, Save_path, Git_status,
  Content_stats, Figures, Formulas, Formula_format,
  Representative_work

❌ FAILED CHECKS:
  Concepts: Missing 3 concept files
    - RLOO
    - Pass_at_k_Optimization
    - Maximum_Likelihood_Estimation

  Formula_naming: 2 formulas missing names
    - Formula 4
    - Formula 5

  Symbol_explanation: 12 formulas missing symbol lists

📌 RECOMMENDED ACTIONS:
  1. Create 3 missing concept notes
  2. Add names to formulas 4 and 5
  3. Add symbol explanations to 12 formulas
```

### 用户看到报告后

- 可以手动修复问题
- 或让 agent 帮助修复特定问题
- 完全透明，用户掌控

### 自检清单（QA 通过后确认）

- [ ] QA 检查全部通过？
- [ ] 如果有失败项，是否已修复？

## 7. 交互式功能

完成解析后询问：深入解释？对比其他论文？保存到 Obsidian？
保存后自动创建缺失概念笔记，报告新增概念数量。

## 8. 批量处理

支持 Zotero 分类批量处理（默认递归子分类）。流程：递归获取论文 → 去重 → 跳过已有笔记 → 依次处理 → 汇总。

## 参考文件（按需查阅）

- **`references/zotero-guide.md`** — Zotero 查询、分类、PDF 路径获取、智能分类判断
- **`references/concept-categories.md`** — 概念自动归类的 16 个子目录规则 + 模板
- **`references/quality-standards.md`** — 公式/图片/表格的详细质量规范 + 自检清单
