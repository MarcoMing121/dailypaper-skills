---
name: paper-checker
description: |
  Use when user asks to "check paper", "verify paper note", "补充论文信息",
  "检查笔记完整性", "fix paper note", or provides an existing paper note
  that needs information verification or content enhancement.

  **与 paper-reader 的区别**:
  - paper-reader: 创建新笔记
  - paper-checker: 检查/更新已有笔记

  **触发场景**:
  - "检查一下这篇笔记"
  - "补充这篇论文的公式"
  - "这个笔记缺了什么"
  - "验证图片链接是否有效"
  - "补全概念链接"

metadata:
  {
    "openclaw": { "requires": { "bins": ["python3", "mineru-open-api"], "env": [] } },
  }
---

> **开始前**: 先跟用户打个招呼 🐕

# 论文笔记检查助手 (Paper Checker)

检查已有论文笔记的完整性，补充缺失信息，修复问题。

## ⚠️ Step -1: 上下文检查（CRITICAL）

**阈值：50% (100k tokens / 200k total)**

| 上下文使用率 | 操作 |
|--------------|------|
| **< 50%** | 正常继续 |
| **≥ 50%** | ⚠️ 先 compact |

---

## Step 0: 读取共享配置

与 paper-reader 相同，读取 `../_shared/user-config.json`，显式生成变量：

- `VAULT_PATH`
- `NOTES_PATH`
- `CONCEPTS_PATH`
- `ASSETS_ROOT`
- `ZOTERO_DB`
- `ZOTERO_STORAGE`
- `AUTO_REFRESH_INDEXES`
- `GIT_COMMIT_ENABLED`
- `GIT_PUSH_ENABLED`

---

## 1. 接收笔记

| 输入方式 | 示例 | 处理方法 |
|----------|------|----------|
| 笔记路径 | `Papers/2-VLA/Pi05.md` | 直接 Read |
| 方法名 | "Pi05 的笔记" | 搜索 .md 文件 |
| arXiv ID | "arXiv 2511.00091 的笔记" | 搜索方法名或 arxiv_id |

---

## 2. 检查模式

| 模式 | 触发词 | 检查内容 |
|------|--------|----------|
| **完整性检查** | "检查笔记"、"完整性" | 图片、公式、表格、概念链接 |
| **图片修复** | "图片问题"、"修复图片" | 验证图片可访问性、下载替换失效图片 |
| **公式补全** | "补充公式"、"公式缺失" | 从原文提取缺失公式、添加符号说明 |
| **概念链接** | "概念链接"、"补全概念" | 检查缺失概念、创建概念笔记 |
| **全面检查** | 默认 | 所有检查项 |

---

## 3. 检查流程

### 3.1 图片检查

```bash
# 提取笔记中所有图片链接
grep -oE '!\[[^\]]*\]\([^)]+\)' {笔记路径}

# 检查图片可达性
for url in $(grep -oE 'https://[^)]+' {笔记路径}); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url")
  if [ "$code" != "200" ]; then
    echo "❌ $code: $url"
  fi
done
```

**问题类型**:
| 问题 | 解决方案 |
|------|----------|
| 外链图片 404 | 从 arXiv HTML / MinerU PDF 重新提取 |
| 本地图片缺失 | 检查 assets/ 目录，补充缺失图片 |
| 图片路径错误 | 修正路径格式 |

### 3.2 公式检查

```bash
# 提取所有公式块
grep -E '^\$\$|\$\$$' {笔记路径}

# 检查公式命名
grep -B2 '^\$\$' {笔记路径} | grep -E '\[\[' | wc -l
```

**检查项**:
- [ ] 每个公式有名称链接 `[[公式名]]`
- [ ] 每个公式有含义说明
- [ ] 每个公式有符号解释 table
- [ ] $$ 块前后有空行

### 3.3 表格检查

```bash
# 统计论文中的 Table 数量（从原文）
# 统计笔记中的表格数量
# 对比是否一致
```

### 3.4 概念链接检查

```bash
# 提取概念链接
grep -oE '\[\[([A-Za-z0-9_-]+)\]\]' {笔记路径} | sed 's/\[\[\(.*\)\]\]/\1/' | sort -u

# 检查概念文件是否存在
for concept in $(grep -oE '\[\[([A-Za-z0-9_-]+)\]\]' {笔记路径} | sed 's/\[\[\(.*\)\]\]/\1/' | sort -u); do
  if ! find Concepts -name "${concept}.md" | grep -q .; then
    echo "❌ missing: $concept"
  fi
done
```

---

## 4. 信息补充流程

### 4.1 从原文重新提取

当发现笔记缺失内容时，从原文重新提取：

**Step 1: 定位原文**

```bash
# 从笔记 YAML 获取 arxiv_id
arxiv_id=$(grep 'arxiv_id:' {笔记路径} | awk '{print $2}' | tr -d '"')

# 或从 zotero_collection 查找
zotero_path=$(grep 'zotero_collection:' {笔记路径} | awk '{print $2}')
```

**Step 2: 使用 MinerU 提取完整内容**

```bash
# 下载 PDF
curl -sL "https://arxiv.org/pdf/${arxiv_id}.pdf" -o /tmp/paper_${arxiv_id}.pdf

# MinerU 提取
mineru-open-api extract /tmp/paper_${arxiv_id}.pdf -o /tmp/paper_mineru_${arxiv_id}/ -f md,json --language en --model pipeline
```

**Step 3: 对比笔记与原文**

| 内容类型 | 检查方法 | 补充方式 |
|----------|----------|----------|
| Figure | 统计数量 | 添加缺失图片 |
| Table | 统计数量 | 添加缺失表格 |
| 公式 | 对比 MinerU LaTeX | 补充缺失公式 |
| 符号说明 | 检查 symbols table | 添加符号解释 |

### 4.2 大论文分块提取

**如果原文 > 500 行，使用并行 subagent 提取**（与 paper-reader 流程一致）。

---

## 5. 修复操作

### 5.1 图片修复

```bash
# 1. 从 arXiv HTML 获取正确图片 URL
curl -sL "https://arxiv.org/html/${arxiv_id}" | grep -E '<img.*src='

# 2. 或从 MinerU images/ 获取本地图片
ls /tmp/paper_mineru_${arxiv_id}/images/

# 3. 复制到 assets/ 目录
cp /tmp/paper_mineru_${arxiv_id}/images/*.jpg ${VAULT_PATH}/assets/${method_name}/

# 4. 更新笔记中的图片链接
```

### 5.2 公式补充

在笔记中添加完整公式块：

```markdown
[[公式名称|公式英文名]]

$$
\mathcal{L} = \sum_{i} ...
$$

**含义**: 损失函数定义

**符号说明**:
| 符号 | 含义 |
|------|------|
| $\mathcal{L}$ | 损失函数 |
| $i$ | 数据索引 |
```

### 5.3 概念创建

**使用并行 subagent 批量创建缺失概念**（与 paper-reader 流程一致）。

---

## 6. QA 检查

**修复完成后，运行 QA 检查验证**（使用 paper-qa skill）。

---

## 7. Git 提交

```bash
cd ${VAULT_PATH}
git add {修改的笔记} {新增的概念} assets/
git commit -m "fix: {method_name} - {修复内容摘要}"
git push  # 如果 GIT_PUSH_ENABLED=true
```

---

## 参考文件

- **`../paper-reader/SKILL.md`** — 论文阅读主流程
- **`../paper-qa/SKILL.md`** — QA 检查流程
- **`../paper-reader/references/quality-standards.md`** — 质量规范
