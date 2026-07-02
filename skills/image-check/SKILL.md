---
name: image-check
description: |
  Verify that images in paper notes match their legends and are correctly referenced.
  Use when: "check images", "verify figures", "图片检查", "检查图片", "image quality check".
  Also triggers after paper-reader creates a note (auto-QA).

  Features:
  - Generate image legend files (legend.md) for each paper
  - Cross-check: note references ↔ legend ↔ actual image files
  - Support MinerU/HTML image extraction for verification
  - Write check results to vault root CheckResults/
metadata:
  {
    "openclaw": { "requires": { "bins": ["python3"], "env": [] } },
  }
---

# Image Check Skill

**独立的图片质量检查技能**，用另一个模型/session 运行，不与 paper-reader 混合。

## 使用场景

```
场景 1: paper-reader 刚读完一篇论文，笔记已保存
  → 单独启动 image-check 验证图片质量

场景 2: 3 天定时提醒，批量检查最近的笔记
  → 列出待检查笔记 → 逐个运行 image-check

场景 3: 用户手动要求检查某篇笔记的图片
  → 直接运行 image-check
```

## 与 paper-reader 的关系

```
paper-reader (模型 A)          image-check (模型 B)
    ↓                              ↓
读论文 → 生成笔记              读原论文 → 提取真实图片
    ↓                              ↓
下载图片到 assets/              与笔记对比
    ↓                              ↓
生成 legend.md                  生成检查报告
    ↓                              ↓
git commit                      CheckResults/{Method}.md
    ↓
完成（不调用 image-check）
```

**关键原则**: 
- paper-reader **不调用** image-check
- image-check **独立运行**，可以读取原论文
- 两个技能可以**并行运行**
- image-check 可以用**不同的模型**（如更强的视觉模型）来验证

## 核心功能

1. **Legend 生成**: 为每篇论文创建 `legend.md`，记录所有图片的链接+描述
2. **一致性检查**: 验证笔记引用 ↔ legend ↔ 实际图片文件三者匹配
3. **质量检查**: 验证图片文件存在、大小合理、格式正确
4. **检查报告**: 通过的检查写入 `CheckResults/{MethodName}.md`

---

## Step 1: Legend 文件格式

每篇论文在 `assets/{MethodName}/` 目录下有一个 `legend.md`：

```markdown
# Image Legends: {Paper Title}

| ID | Source | Link | Legend | Used in Note |
|----|--------|------|--------|--------------|
| fig1 | local | ![[MethodName/fig1.png]] | 系统架构概览，展示输入输出流程 | ✅ |
| fig2 | external | ![](https://arxiv.org/html/xxx/x2.png) | 模型内部模块详细结构 | ✅ |
| fig3 | local | ![[MethodName/fig3.png]] | 实验结果对比 | ❌ |
```

**字段说明**:
- **ID**: 图片标识（Figure 编号或文件名）
- **Source**: `local`（已下载到 assets）或 `external`（外部 URL）
- **Link**: Obsidian wikilink 或 Markdown 外链
- **Legend**: 图片描述/图例文字（从论文原文提取）
- **Used in Note**: 是否在笔记中被引用

---

## Step 2: Legend 生成流程

### 2.1 从论文提取 legend

**方法 A: arXiv HTML（首选）**

```bash
# 从 HTML 提取 figure + caption
curl -sL "https://arxiv.org/html/{arxiv_id}" | \
  python3 -c "
import sys, re
html = sys.stdin.read()
figures = re.findall(r'<figure[^>]*>(.*?)</figure>', html, re.DOTALL)
for i, fig in enumerate(figures, 1):
    caption = re.search(r'<figcaption[^>]*>(.*?)</figcaption>', fig, re.DOTALL)
    img = re.search(r'<img[^>]*src=[\"']([^\"']+)[\"']', fig)
    cap_text = re.sub(r'<[^>]+>', '', caption.group(1)).strip() if caption else 'N/A'
    img_url = img.group(1) if img else 'N/A'
    print(f'fig{i}|{img_url}|{cap_text}')
"
```

**方法 B: MinerU PDF 提取**

MinerU 自动提取的图片在 `images/` 目录，legend 从论文 Markdown 中的 figure caption 段落提取。

**方法 C: 手动补充**

如果自动提取失败，从论文 PDF 中手动复制 figure caption。

### 2.2 生成 legend.md

```python
def generate_legend(method_name, paper_title, figures):
    """
    figures: list of dict with keys: id, source, link, caption
    """
    lines = [
        f"# Image Legends: {paper_title}",
        "",
        "| ID | Source | Link | Legend | Used in Note |",
        "|----|--------|------|--------|--------------|",
    ]
    for fig in figures:
        lines.append(
            f"| {fig['id']} | {fig['source']} | {fig['link']} | {fig['caption']} | ❌ |"
        )
    return "\n".join(lines)
```

---

## Step 3: 一致性检查

### 3.1 三向匹配检查

```bash
# 1. 从笔记提取引用的图片
grep -oP '!\[\[([^\]|]+)(?:\|[0-9]+)?\]\]' {note_path} | sed 's/!\[\[//; s/\|[0-9]*//; s/\]\]//'
grep -oP '!\[([^\]]*)\]\((https?://[^)]+)\)' {note_path}

# 2. 从 legend.md 提取记录的图片
# 3. 从 assets/ 目录提取实际存在的文件
ls {vault}/assets/{method_name}/

# 4. 三向对比
```

### 3.2 检查项

| 检查 | 说明 | 结果 |
|------|------|------|
| **引用存在** | 笔记中引用的图片在 legend 中有记录 | ✅/❌ |
| **文件存在** | legend 中 local 类型的图片在 assets/ 中存在 | ✅/❌ |
| **文件大小** | 图片文件 > 10KB（不是空文件或损坏） | ✅/❌ |
| **格式正确** | 图片格式为 jpg/png/gif/webp | ✅/❌ |
| **legend 完整** | 所有图片都有 legend 描述 | ✅/❌ |
| **引用完整** | legend 中标记 Used 的图片确实在笔记中被引用 | ✅/❌ |

---

## Step 4: 检查报告

通过的检查写入 `{VAULT_PATH}/CheckResults/{MethodName}.md`：

```markdown
---
title: "Image Check: {MethodName}"
date: {YYYY-MM-DD HH:MM}
status: passed | failed
paper_path: Papers/{category}/{MethodName}.md
---

# Image Check Report: {MethodName}

## 检查结果

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 引用存在 | ✅ | 9/9 图片在 legend 中有记录 |
| 文件存在 | ✅ | 9/9 本地文件存在 |
| 文件大小 | ✅ | 所有文件 > 10KB |
| legend 完整 | ✅ | 所有图片有描述 |

## 图片列表

| ID | 状态 | Legend |
|----|------|--------|
| fig1 | ✅ | 系统架构概览 |
| fig2 | ✅ | 模型架构图 |
...
```

---

## Step 5: 无 Legend 时的自动验证（CRITICAL）

**当论文笔记没有 legend.md 时，image-check 必须自行读取原论文来验证图片质量。**

### 5.1 获取原论文（与 paper-reader 相同的提取流程）

**image-check 使用与 paper-reader 完全相同的提取流程**：

```
获取原论文
    ↓
arXiv HTML 可用？
  ├─ 行数 ≤ 500 → 直接提取 figure + caption
  ├─ 行数 > 500 → 分块（300行/块）→ 逐块提取 → 合并
  └─ 不可用 → 降级到 MinerU
                ├─ PDF < 1MB → 直接 MinerU 提取
                └─ PDF ≥ 1MB → split_pdf_for_mineru.sh 分割 → 逐块 MinerU → 合并
```

```bash
# 1. 从笔记 frontmatter 提取 arxiv_id 或 url
ARXIV_ID=$(grep -oP 'arxiv.*?(\d{4}\.\d{4,5})' {note_path} | head -1 | grep -oP '\d{4}\.\d{4,5}')

# 2. 检查 arXiv HTML 是否可用
curl -sI "https://arxiv.org/html/${ARXIV_ID}" | head -1
```

### 5.2 提取"真实"图片信息

**方法 A: arXiv HTML 提取（首选，速度快）**

与 paper-reader 相同：
- 小文件（≤500 行）：直接提取 `<figure>` + `<figcaption>`
- 大文件（>500 行）：分 300 行/块，逐块提取后合并

```bash
# 提取所有 figure + caption + image URL
curl -sL "https://arxiv.org/html/${ARXIV_ID}" | \
  python3 -c "
import sys, re
html = sys.stdin.read()
figures = re.findall(r'<figure[^>]*>(.*?)</figure>', html, re.DOTALL)
for i, fig in enumerate(figures, 1):
    caption = re.search(r'<figcaption[^>]*>(.*?)</figcaption>', fig, re.DOTALL)
    img = re.search(r'<img[^>]*src=[\"']([^\"']+)[\"']', fig)
    cap_text = re.sub(r'<[^>]+>', '', caption.group(1)).strip() if caption else 'N/A'
    img_url = img.group(1) if img else 'N/A'
    print(f'fig{i}|{img_url}|{cap_text}')
"
```

**方法 B: MinerU PDF 提取（HTML 不可用时自动降级）**

与 paper-reader 完全相同的流程：
1. 下载 PDF
2. 检查大小 → ≥1MB 则用 `split_pdf_for_mineru.sh` 分割
3. 逐个 chunk 调用 `mineru-open-api extract`
4. 合并图片和 Markdown
5. 从 Markdown 提取 figure caption

```bash
# 完整流程（自动）
python3 check_images.py --note /path/to/note.md --generate-legend
```

**MinerU 优势**:
- 表格识别（HTML 中表格可能是图片）
- 公式识别（LaTeX 格式输出）
- 支持所有 PDF（不依赖 arXiv HTML 可用性）
- 大 PDF 自动分割（复用 paper-reader 的 split 脚本）

**自动降级逻辑**:
```
arXiv HTML 可用？
  ├─ 是 → 提取图片
  │       图片数量 ≥ 2？
  │         ├─ 是 → 使用 HTML 结果 ✅
  │         └─ 否 → 降级到 MinerU 🔄
  └─ 否 → 直接 MinerU 🔄
```

### 5.3 交叉验证

**验证逻辑**:

```
原论文图片 (HTML/MinerU)
    ↓ 提取
真实图片列表 (URL + caption)
    ↓ 对比
笔记引用的图片
    ↓ 检查
1. 笔记中的图片 URL 是否在原论文中存在？
2. 原论文的重要图片（Figure 1-N）是否都在笔记中？
3. 图片 caption 是否与原论文一致？
```

### 5.4 自动生成 Legend

验证完成后，自动生成 legend.md 保存结果：

```bash
python3 skills/image-check/scripts/generate_legend.py \
    --note {note_path} \
    --assets {assets_dir} \
    --arxiv {arxiv_id} \
    --title "{paper_title}"
```

### 5.5 完整验证流程

```
输入: 论文笔记 .md（无 legend.md）
    ↓
1. 从 frontmatter 提取 arxiv_id
    ↓
2. 获取原论文图片（HTML 或 MinerU）
    ↓
3. 提取笔记中引用的图片
    ↓
4. 交叉验证：
   - 原论文有 Figure 1-9，笔记引用了几张？
   - 笔记引用的图片 URL 是否在原论文中？
   - caption 是否匹配？
    ↓
5. 检查本地文件（如果引用了 assets/）
    ↓
6. 生成 legend.md
    ↓
7. 写入 CheckResults/{Method}.md
```

---

## Step 6: 批量检查（定时任务用）

### 获取最近创建的笔记

```python
from pathlib import Path
from datetime import datetime

def get_recent_notes(vault_path, limit=10):
    """获取最近创建的论文笔记，按日期降序"""
    notes_dir = Path(vault_path) / "Papers"
    notes = []
    for md in notes_dir.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        stat = md.stat()
        notes.append({
            "path": md,
            "created": datetime.fromtimestamp(stat.st_ctime),
            "name": md.stem
        })
    notes.sort(key=lambda x: x["created"], reverse=True)
    return notes[:limit]
```

### 检查状态

```python
def needs_check(vault_path, method_name):
    """判断是否需要检查"""
    check_file = Path(vault_path) / "CheckResults" / f"{method_name}.md"
    if not check_file.exists():
        return True
    # 检查是否笔记有更新
    note_mtime = ...  # 获取笔记修改时间
    check_mtime = datetime.fromtimestamp(check_file.stat().st_mtime)
    return note_mtime > check_mtime
```

---

## 使用方式

### 单篇检查

```
检查一下 SkillBlender 的图片
→ 运行 image-check 流程
```

### 批量检查（定时任务）

```
提醒我检查最近的论文笔记图片
→ 获取 top 10 最近笔记
→ 列出需要检查的
→ 提醒用户
```

---

## 与 paper-reader 的集成

paper-reader 在保存笔记后应自动：
1. 生成 `assets/{MethodName}/legend.md`
2. 将 legend 信息嵌入笔记的图表章节

### Legend 生成脚本

```bash
# 在 paper-reader 流程末尾调用
python3 skills/image-check/scripts/generate_legend.py \
    --note {note_path} \
    --assets {assets_dir} \
    --output {assets_dir}/legend.md
```
