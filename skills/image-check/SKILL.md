---
name: image-check
description: |
  Post-processing image verification for paper notes. Runs AFTER paper-reader.
  Uses vision model to verify image captions are correct, fix wrong ones,
  and identify missing figures from the paper.

  Use when: "check images", "verify figures", "图片检查", "检查图片", "image quality check".
metadata:
  {
    "openclaw": { "requires": { "bins": ["python3"], "env": [] } },
  }
---

# Image Check — 视觉验证引擎

**在 paper-reader 之后运行**，用视觉模型验证笔记中的图片描述是否准确。

## 为什么需要

paper-reader 的模型视觉能力有限，可能：
- 图片 caption 写错（把架构图说成结果图）
- 漏掉论文中的重要图片
- caption 过于笼统（"Figure 1" 而非具体内容描述）

image-check 用**视觉能力强的模型**来修正这些问题。

## 流程

```
paper-reader 完成 → 笔记 + assets/
        ↓
image-check 开始
        ↓
Step 1: image_understand.py → figure_manifest.json
        ├─ 提取笔记中的所有图片引用
        ├─ 从 arXiv HTML 获取论文原始图片
        ├─ 对每张图准备 base64 数据
        └─ 输出 manifest（含 base64 + 笔记 caption + 原始 caption）
        ↓
Step 2: Agent 调视觉模型
        ├─ 读 manifest.json
        ├─ 对每张图：发送 image_base64 + prompt
        ├─ 视觉模型回答：图片实际内容
        └─ Agent 对比笔记 caption vs 真实内容
        ↓
Step 3: 修正笔记 + 生成 legend
        ├─ 错误 caption → 修正笔记中对应段落
        ├─ 缺失图片 → 建议用户添加
        ├─ 生成/更新 legend.md（带视觉验证的 caption）
        └─ 写入 CheckResults/{Method}.md
```

## 使用方式

### 单篇检查（推荐流程）

```
用户: 检查 HOVER 的图片
Agent:
  1. 运行 image_understand.py --note HOVER.md --output /tmp/hover_manifest.json
  2. 读 manifest，对每张图调视觉模型
  3. 对比 caption，修正错误
  4. 更新 legend.md
  5. 写 CheckResults/HOVER.md
```

### 批量检查

```
用户: 检查最近 10 篇笔记的图片
Agent:
  1. 运行 batch_check.py（默认 10 篇未检查的）
  2. 对每篇运行完整视觉验证流程
  3. 汇总报告
```

---

## Step 1: 提取图片信息

```bash
python3 scripts/image_understand.py \
    --note /path/to/Papers/7-Robotics/HOVER.md \
    --output /tmp/hover_manifest.json
```

**输出 `figure_manifest.json`**:

```json
{
  "note": "/path/to/HOVER.md",
  "assets_dir": "/path/to/assets/HOVER",
  "arxiv_id": "2506.09366",
  "total_figures": 8,
  "in_note": 5,
  "missing_from_note": 3,
  "figures": [
    {
      "id": "fig1_architecture",
      "in_note": true,
      "reference": "![[HOVER/fig1_architecture.png]]",
      "section": "方法",
      "note_caption": "HOVER 架构概览",
      "image_base64": "iVBORw0KGgo...",
      "mime": "image/png",
      "html_caption": "Figure 1: Overview of the HOVER framework...",
      "vision_caption": "",
      "needs_fix": false,
      "vision_analyzed": false
    },
    {
      "id": "x3",
      "in_note": false,
      "html_caption": "Figure 3: Comparison with baselines on...",
      "image_base64": "...",
      "vision_caption": ""
    }
  ]
}
```

**字段说明**:
- `in_note`: 是否在笔记中被引用
- `note_caption`: 笔记中图片下方的描述文字
- `html_caption`: 论文 HTML 中的原始 caption
- `vision_caption`: 视觉模型生成的 caption（待填充）
- `needs_fix`: Agent 判断是否需要修正

---

## Step 2: 视觉验证

Agent 读取 manifest 后，对每张图执行：

### Prompt 模板

```
This is Figure {id} from paper "{title}".
The paper's caption says: "{html_caption}"
The note describes it as: "{note_caption}"

Please describe what this image actually shows:
1. Figure type (architecture diagram / experimental result / example / flowchart / table)
2. Key elements visible
3. Is the note's caption accurate? (yes/no/partial)
4. If not accurate, suggest a better caption.

Respond in JSON:
{
  "figure_type": "architecture",
  "key_elements": ["encoder", "decoder", "attention"],
  "caption_accurate": true,
  "suggested_caption": null
}
```

### 判断逻辑

| 情况 | 操作 |
|------|------|
| note_caption 准确 | ✅ 标记通过 |
| note_caption 不准确 | 📝 用 suggested_caption 修正笔记 |
| note_caption 为空/太笼统 | 📝 用 vision_caption 填充 |
| 图片不在笔记中 | ⚠️ 提示用户是否添加 |

---

## Step 3: 修正与输出

### 修正笔记 caption

```python
# 在笔记中找到图片引用，替换其下方的 caption
old_text = "![[HOVER/fig1.png]]\nHOVER 架构"  # 原 caption
new_text = "![[HOVER/fig1.png]]\nHOVER 整体架构：Encoder-Decoder 结构，包含视觉编码器和动作解码器"  # 修正后
```

### 生成 legend.md

```markdown
# Image Legends: HOVER

Generated: 2026-07-06 16:00 (vision verified)

| ID | Source | Link | Legend | Used | Verified |
|----|--------|------|--------|------|----------|
| fig1 | local | ![[HOVER/fig1.png]] | HOVER 整体架构：Encoder-Decoder... | ✅ | ✅ |
| x3 | external | ![](https://arxiv.org/.../x3.png) | 基线对比实验结果 | ❌ | ✅ |
```

### 写检查报告

```markdown
# Image Check: HOVER
Status: passed (with fixes)

## 修正记录
- fig1: caption 从 "HOVER 架构" 修正为 "HOVER 整体架构：Encoder-Decoder..."
- x3: 新增（论文中有但笔记遗漏）

## 检查结果
| 检查项 | 状态 |
|--------|------|
| vision_verify | ✅ 5/5 verified |
| caption_fixed | 📝 1 fixed |
| missing_found | ⚠️ 1 missing |
```

---

## 脚本列表

| 脚本 | 用途 |
|------|------|
| `image_understand.py` | **核心** — 提取图片 + 准备 base64 + 输出 manifest |
| `check_images.py` | 一致性检查（无视觉模型的轻量检查） |
| `batch_check.py` | 批量运行 check_images.py |
| `generate_legend.py` | 从 HTML/MinerU 生成 legend（无视觉验证） |

## 配置

- **Vault 路径**: 从 `_shared/user_config.py` 读取，或用 `--vault` 参数
- **Assets 路径**: `{VAULT_PATH}/assets/{MethodName}`
- **Check 结果**: `{VAULT_PATH}/CheckResults/{MethodName}.md`
