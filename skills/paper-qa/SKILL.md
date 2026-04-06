---
name: paper-qa
description: |
  Auto-activated after paper-reader creates a note.
  Runs QA checks and generates detailed report.
  
  **核心原则**: 只检查和报告，不自动修复

metadata:
  {
    "openclaw": { "requires": { "bins": ["python3"], "env": [] } }
  }
---

# Paper Note QA Subagent

## 任务目标

检查论文笔记质量，生成详细报告，**不自动修复**。

## 工作流程

```
Step 1: 运行 QA 检查脚本
    ↓
Step 2: 分析检查结果
    ↓
Step 3: 生成详细报告
    ├─ 通过项 ✅
    └─ 问题项 ❌ (具体说明)
    ↓
返回报告给用户
```

## Step 1: 运行检查

```bash
python3 skills/paper-qa/qa_check.py {笔记路径}
```

输出示例：
```json
{
  "final_status": "failed",
  "checks": {
    "concepts": {
      "ok": false,
      "issues": ["Missing concept files: Concept_A, Concept_B"]
    },
    "formula_naming": {
      "ok": false,
      "issues": ["Formula 4: Missing name/heading"]
    }
  }
}
```

## Step 2: 分析问题

根据检查结果，整理问题类型：

| 检查项 | 问题示例 | 说明 |
|--------|----------|------|
| **frontmatter** | 缺少字段 | 需要手动补充 |
| **figures** | 图片不可达 | 需要手动下载或替换 URL |
| **formulas** | LaTeX 不兼容 | 需要手动修改 |
| **concepts** | 概念文件缺失 | 需要手动创建概念笔记 |
| **formula_naming** | 公式缺少命名 | 需要手动添加命名 |
| **symbol_explanation** | 公式缺少符号说明 | 需要手动添加符号说明 |
| **image_caption** | 图片与描述不匹配 | 需要手动修正描述 |

## Step 3: 生成报告

**人类可读格式**：

```
============================================================
QA Report: Papers/4-RL-Theory/MaxRL.md
Final Status: FAILED
============================================================

✅ PASSED CHECKS:
  • Structure: File naming, save path
  • Frontmatter: All required fields present
  • Figures: 3 images found, all accessible
  • Formulas: 14 formulas, LaTeX compatible

❌ FAILED CHECKS:
  • Concepts: Missing 3 concept files
    - RLOO
    - Pass_at_k_Optimization
    - Maximum_Likelihood_Estimation
  
  • Formula Naming: 2 formulas missing names
    - Formula 4
    - Formula 5
  
  • Symbol Explanation: 12 formulas missing symbol lists
    - Formulas: 1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14

📌 RECOMMENDED ACTIONS:
  1. Create 3 missing concept notes
  2. Add names to formulas 4 and 5
  3. Add symbol explanations to 12 formulas
```

---

## ⚠️ 不自动修复的原因

1. **内容质量优先**：自动修复可能引入错误
2. **用户控制**：用户应审查和批准所有修改
3. **透明性**：用户清楚知道笔记的哪些部分需要改进

---

## 检查覆盖范围

### 基础结构检查
- [x] 文件命名
- [x] YAML frontmatter
- [x] 保存路径分类
- [x] Git 状态

### 内容完整性检查
- [x] Figure 数量统计
- [x] 公式数量统计
- [x] Table 数量统计
- [x] 概念链接有效性

### 图片质量检查
- [x] 图片格式
- [x] 图片可达性
- [x] 本地图片存在
- [x] 图片大小 > 1KB
- [x] 图片描述提取（供用户参考）
- [x] **图片映射验证**: 检测组合图完整性（使用 `_shared/check_composite_figures.py`）

### 图片映射检查（自动检测）

**检测逻辑**：使用共享脚本 `../_shared/check_composite_figures.py`

1. 从笔记 frontmatter 提取 `arxiv_html` URL
2. 抓取 arXiv HTML 并解析 `<figure>` 嵌套结构
3. 识别组合图（一个 Figure 包含多张图片）
4. 对比笔记中的图片与论文中的图片

**检测示例**：
```
❌ Composite Figure S4.F6: Found 1/4 images. Missing: x9.png, x10.png, x11.png
```

脚本提取所有图片及其描述，LLM 需要检查：

1. **图片 URL 与描述是否匹配**
   - 访问 `https://arxiv.org/html/{arxiv_id}` 查看原图
   - 对比笔记中的 Figure 标题和图片 URL
   - 注意：arXiv 的 `xN.png` 编号与论文 Figure 编号不一定一致

2. **图片描述是否准确**
   - 描述应与图片内容一致
   - 如 Figure 6 标题为"Planning Performance"，但图片实际显示"Training Curves"→ 需修正

3. **图片链接来源**
   - ✅ 正确：`arxiv.org/html/...`
   - ❌ 错误：`ar5iv.labs.arxiv.org/...`（可能返回空白图片）

### 公式质量检查
- [x] LaTeX 格式（空行）
- [x] 公式命名
- [x] 符号说明
- [x] LaTeX 兼容性

### 概念库检查
- [x] 链接有效性
- [x] 概念内容质量
- [x] 代表工作

---

## 输出格式

**JSON 格式**（供程序解析）：
```bash
python3 qa_check.py note.md --json
```

**人类可读格式**（默认）：
```bash
python3 qa_check.py note.md
```
