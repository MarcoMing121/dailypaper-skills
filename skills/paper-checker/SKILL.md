---
name: paper-checker
description: |
  当用户讨论论文时，如果笔记信息不够详细，查阅原文补充答案。

  **核心场景**：
  - 用户问："PLD 的探测视野 α 具体是多少？"
  - 笔记只有一句话提到，不够详细
  - Agent 从原文中查找完整信息

  **触发词**：
  - "查一下原文"
  - "原文怎么说的"
  - "详细信息在论文哪里"
  - "这篇论文的公式 X 是什么意思"

  **与 paper-reader 区别**：
  - paper-reader: 创建新笔记（读完整论文）
  - paper-checker: 查阅原文回答具体问题（定向搜索）

metadata:
  {
    "openclaw": { "requires": { "bins": ["python3", "mineru-open-api"], "env": [] } },
  }
---

# 论文原文查阅助手 (Paper Checker)

当笔记信息不足时，查阅原文补充答案。

## Step 0: 读取共享配置

与 paper-reader 相同，读取 `../_shared/user-config.json`。

---

## 1. 接收查询

| 输入 | 示例 |
|------|------|
| 笔记路径 | `Papers/2-VLA/PLD.md` |
| 用户问题 | "探测视野 α 的最佳值是怎么得出的？" |

---

## 2. 定位原文

### Step 2.1: 从笔记获取论文信息

```bash
# 提取 arxiv_id
arxiv_id=$(grep 'arxiv_id:' {笔记路径} | awk '{print $2}' | tr -d '"')

# 或从 title 搜索
title=$(grep 'title:' {笔记路径} | sed 's/title: *//' | tr -d '"')
```

### Step 2.2: 下载/提取原文

**优先级**：MinerU PDF > arXiv HTML

```bash
# 下载 PDF
curl -sL "https://arxiv.org/pdf/${arxiv_id}.pdf" -o /tmp/paper_${arxiv_id}.pdf

# MinerU 提取（完整内容：文本 + 图片 + 公式 + 表格）
mineru-open-api extract /tmp/paper_${arxiv_id}.pdf \
  -o /tmp/paper_mineru_${arxiv_id}/ \
  -f md,json \
  --language en \
  --model pipeline
```

---

## 3. 定向搜索

### Step 3.1: 关键词提取

从用户问题中提取关键词：

| 问题类型 | 搜索策略 |
|----------|----------|
| 参数值 | `grep -i "α\|alpha\|probing" paper.md` |
| 公式含义 | 搜索公式编号 `grep -E "Equation|公式"` |
| 实验细节 | `grep -i "experiment\|ablation"` |
| 方法细节 | 搜索方法名相关 section |

### Step 3.2: 内容定位

```bash
# 在 MinerU Markdown 中搜索
grep -B5 -A10 -i "{关键词}" /tmp/paper_mineru_${arxiv_id}/paper_${arxiv_id}.md

# 提取相关段落
sed -n '/{section名}/,/^## /p' /tmp/paper_mineru_${arxiv_id}/paper_${arxiv_id}.md
```

### Step 3.3: 公式查找

```bash
# 提取所有公式块
grep -E '^\$\$|\$\$$' /tmp/paper_mineru_${arxiv_id}/paper_${arxiv_id}.md

# 找到目标公式后，提取上下文
sed -n '/{公式关键词}/,/^$$/p' ...
```

---

## 4. 返回答案

### 格式

```markdown
**原文出处**: Section X.X / Equation Y

**完整内容**:
[原文段落或公式]

**解读**:
[用简单语言解释]
```

### 示例

**用户问题**: "PLD 的探测视野 α 最佳值是多少？"

**返回**:
```
**原文出处**: Section 4.5 Ablation on Probing Horizon

**完整内容**:
"We ablate the probing horizon α in {0.0, 0.2, 0.4, 0.6, 0.8}. 
Performance peaks at α=0.6 (Figure 11), where the probing covers 
60% of episode length before residual takeover."

**解读**:
- α=0.6 是最佳探测视野比例
- 意味着 episode 的前 60% 时间由基策略探测
- 过小（α=0）偏离基策略分布，过大（α=1）数据支持过窄
```

---

## 5. 大论文处理

**如果原文 > 500 行**，使用分块搜索：

```bash
# 只搜索相关 section
grep -n "^## " paper.md | grep -i "{关键词}"
sed -n '/^{section}/,/^## /p' paper.md > /tmp/relevant_section.md
```

**不要全文进 context**，只提取相关段落。

---

## 6. 图片/表格查询

如果用户问图表：

```bash
# MinerU images/ 目录
ls /tmp/paper_mineru_${arxiv_id}/images/

# 从 JSON 获取图片描述
jq '.images[] | select(.id=="Figure X")' paper.json
```

---

## 参考文件

- **`../paper-reader/SKILL.md`** — MinerU 提取流程
- **`../paper-reader/references/zotero-guide.md`** — Zotero 查询
