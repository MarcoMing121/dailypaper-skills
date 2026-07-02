---
name: image-check
description: |
  Verify that images in paper notes match their legends and are correctly referenced.
  Use when: "check images", "verify figures", "图片检查", "检查图片", "image quality check".

  Features:
  - Check/generate image legend files (legend.md) for each paper
  - Read original paper (HTML/MinerU) when legend is missing or incomplete
  - Use vision model to verify caption ↔ image match
  - Fill missing captions using vision model
  - Cross-check: note references ↔ legend
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
paper-reader (模型 A)              image-check (模型 B，独立运行)
    ↓                                  ↓
读论文 → 生成笔记 + legend.md        legend.md 存在？
    ↓                                  ├─ 是 → 检查缺失 caption
git commit                            └─ 否 → 读原论文生成 legend
    ↓                                      ↓
完成                                 视觉模型验证 caption ↔ 图片
                                     （缺失 caption → 视觉模型补充）
                                          ↓
                                     检查笔记引用 ↔ legend 匹配
                                          ↓
                                     写入 CheckResults/{Method}.md
```

**关键原则**: 
- paper-reader **不调用** image-check
- image-check **独立运行**，可以读取原论文
- 两个技能可以**并行运行**
- image-check 用**视觉模型**来验证/补充 caption

---

## 完整流程（3 步）

```
Step 1: Legend 检查与生成
    ↓
    legend.md 存在？
      ├─ 是 → 读取 legend，检查缺失 caption
      └─ 否 → 从原论文提取
              ├─ arXiv HTML → <figure> + <figcaption>
              └─ MinerU PDF → 提取图片 + caption
              ↓
              生成 legend.md

Step 2: 视觉验证 + caption 补充
    ↓
    对每张图片：
      ├─ 读取图片文件（或下载外链图片）
      ├─ 发送给视觉模型 + 现有 caption
      ├─ 视觉模型判断：
      │   ├─ caption 存在且准确 → ✅ 通过
      │   ├─ caption 存在但不准确 → 修正 caption
      │   └─ caption 缺失 → 生成新 caption
      └─ 更新 legend.md

Step 3: 一致性检查
    ↓
    ├─ 笔记引用 ↔ legend 匹配？
    ├─ legend 中所有图片都有 caption？
    ├─ 外链可达？（HTTP HEAD）
    └─ 本地文件存在 + 大小合理？
    ↓
    写入 CheckResults/{Method}.md
```

---

## Step 1: Legend 检查与生成

### 1.1 Legend 文件格式

每篇论文在 `assets/{MethodName}/` 目录下有一个 `legend.md`：

```markdown
# Image Legends: {Paper Title}

Generated: 2026-07-02 14:00
Source: html / mineru

| ID | Source | Link | Legend | Used in Note |
|----|--------|------|--------|--------------|
| x1 | external | ![](https://arxiv.org/html/xxx/x1.png) | 系统架构概览 | ✅ |
| x2 | external | ![](https://arxiv.org/html/xxx/x2.png) | 待补充 | ✅ |
| x3 | local | ![[Method/x3.png]] | 实验结果 | ❌ |
```

**字段说明**:
- **ID**: 图片标识（文件名 stem）
- **Source**: `external`（外部 URL）或 `local`（已下载到 assets）
- **Link**: Obsidian wikilink `![[...]]` 或 Markdown 外链 `![](url)`
- **Legend**: 图片描述（"待补充" = 需要视觉模型填充）
- **Used in Note**: 是否在笔记中被引用

### 1.2 生成流程

```bash
# 使用 arXiv HTML
python3 scripts/generate_legend.py \
    --note /path/to/note.md \
    --assets /path/to/assets/Method \
    --arxiv 2506.09366 \
    --title "Paper Title"

# 使用 MinerU PDF（HTML 不可用时）
python3 scripts/generate_legend.py \
    --note /path/to/note.md \
    --assets /path/to/assets/Method \
    --title "Paper Title"
```

**Legend 来源优先级**:
1. arXiv HTML `<figcaption>` → 最完整
2. MinerU Markdown → 图片引用中的 caption
3. 论文正文中的 "Figure X" 描述段落
4. 视觉模型生成（Step 2）

---

## Step 2: 视觉验证 + caption 补充

### 2.1 视觉模型验证

对 legend 中每张图片：

```bash
# 准备验证数据
python3 scripts/verify_image_visual.py \
    --image /path/to/image.png \
    --caption "Figure 1: SkillBlender 架构图" \
    --title "SkillBlender"
```

**输出 JSON**（供视觉模型使用）:
```json
{
  "ok": true,
  "image_path": "/path/to/image.png",
  "image_base64": "...",
  "mime": "image/png",
  "caption": "Figure 1: ...",
  "prompt": "请验证此图片..."
}
```

### 2.2 视觉模型判断

**调用方（agent）拿到 JSON 后**:
1. 读取 `image_base64` 显示图片给视觉模型
2. 发送 `prompt` 给视觉模型
3. 解析模型返回的结果

**三种情况**:
| caption 状态 | 视觉模型动作 | 结果 |
|-------------|-------------|------|
| 存在且准确 | 验证通过 | ✅ |
| 存在但不准确 | 修正 caption | 更新 legend.md |
| 缺失（"待补充"） | 生成新 caption | 填充 legend.md |

### 2.3 更新 legend.md

视觉验证完成后，更新 legend.md 中的 caption：
- 修正不准确的 caption
- 填充 "待补充" 的 caption
- 标记验证状态

---

## Step 3: 一致性检查

### 3.1 检查项

| 检查 | 说明 | 结果 |
|------|------|------|
| **legend_exists** | legend.md 是否存在 | ✅/❌ |
| **local_files_exist** | 本地文件是否完整 | ✅/❌ |
| **file_sizes** | 文件大小 > 10KB | ✅/❌ |
| **legend_complete** | 所有图片都有 caption（非"待补充"） | ✅/❌ |
| **external_links** | 外链可达（HTTP HEAD） | ✅/❌ |
| **reference_match** | 笔记引用 ↔ legend 匹配 | ✅/❌ |

### 3.2 外链检查

```bash
# 对笔记中的每个外部图片链接
curl -sI -o /dev/null -w "%{http_code}" "https://arxiv.org/html/xxx/x1.png"
# 期望 200
```

### 3.3 引用匹配

```python
# 从笔记提取引用
note_refs = extract_refs(note_text)  # ['x1', 'x2', ...]

# 从 legend 提取
legend_ids = [l['id'] for l in legends]

# 对比
unmatched = set(note_refs) - set(legend_ids)
```

---

## 检查报告

通过的检查写入 `{VAULT_PATH}/CheckResults/{MethodName}.md`：

```markdown
---
title: "Image Check: {MethodName}"
date: 2026-07-02 14:50
status: passed
paper_path: Papers/7-Robotics/Method.md
---

# Image Check Report: {MethodName}

## 检查结果

| 检查项 | 状态 | 详情 |
|--------|------|------|
| legend_exists | ✅ | Auto-generated from html |
| local_files_exist | ✅ | All local files exist |
| file_sizes | ✅ | All files > 10KB |
| legend_complete | ✅ | All captions filled (vision verified) |
| external_links | ✅ | All 9 external links reachable |
| reference_match | ✅ | All references match |
| visual_verify | ✅ | 9/9 images verified |
```

---

## 使用方式

### 单篇检查

```
检查一下 HOVER 的图片
→ 运行 image-check
```

### 视觉验证

```
检查 HOVER 的图片（用视觉模型验证）
→ 运行 image-check + 视觉模型
```

### 批量检查（定时任务）

```
3 天定时提醒
→ list_need_check.py --limit 10
→ 发送到 #paper-research 提醒用户
```

---

## 脚本列表

| 脚本 | 用途 |
|------|------|
| `scripts/generate_legend.py` | 生成 legend.md（从 HTML/MinerU） |
| `scripts/check_images.py` | 一致性检查（文件/链接/引用） |
| `scripts/verify_image_visual.py` | 准备视觉验证数据 |
| `scripts/list_need_check.py` | 列出待检查笔记 |
