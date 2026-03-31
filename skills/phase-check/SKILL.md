---
name: phase-check
description: |
  检查分阶段研究系统的当前状态。触发词："检查阶段系统"、"系统状态"、"当前阶段"。

metadata:
  { "openclaw": { "requires": { "bins": [], "env": [] } } }
---

# Phase Check - 分阶段研究系统状态检查

快速检查当前系统处于哪个阶段、运行了多久、下一步建议。

## 检查步骤

### Step 1: 读取当前阶段

```bash
cat /tmp/current_phase 2>/dev/null || echo "未初始化"
```

### Step 2: 读取配置文件

```bash
cat /root/.openclaw/workspaces/paper-agent/dailypaper-skills/_shared/user-config.json
```

提取关键字段：
- `PHASE`: 当前阶段
- `PHASE_START_DATE`: 阶段开始时间

### Step 3: 计算运行天数

从 `PHASE_START_DATE` 计算已运行天数，与建议时长对比。

### Step 4: 检查 Cron 任务

```bash
crontab -l 2>/dev/null
```

## 阶段说明

| 阶段 | 名称 | 建议时长 | 特点 |
|------|------|----------|------|
| `phase1_manual` | 集中阅读期 | 30 天 | 手动控制，无自动化 |
| `phase2_smart` | 关联发现期 | 90 天 | 智能触发，每周整理 |
| `phase3_auto` | 知识整合期 | 180 天 | 全自动，每日运行 |

## 输出格式

```markdown
## 📊 分阶段研究系统状态

| 项目 | 值 |
|------|-----|
| **当前阶段** | {阶段名称} ({phase_key}) |
| **开始时间** | {PHASE_START_DATE} |
| **已运行** | {days} 天 |
| **建议时长** | {next_check} 天 |
| **状态** | {正常/建议切换} |

### 阶段特点
- {该阶段的配置说明}

### Cron 任务
- {当前运行的定时任务}

### 建议
- {是否应该切换阶段 / 还需要多少天}
```

## 切换命令提示

如果需要切换阶段，提示用户：

```bash
# 检查是否该切换
./scripts/switch_phase.sh check

# 切换到下一阶段
./scripts/switch_phase.sh next
```
