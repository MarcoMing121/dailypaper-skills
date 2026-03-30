# 概念自动归类规则

概念库位置：`{CONCEPTS_PATH}`

先用 `find {CONCEPTS_PATH} -type d` 查看已有子目录，再按下表分类：

## 概念分类目录

| 目录 | 归类标准 | 示例 |
|------|----------|------|
| `1-Foundations/` | 基础概念、理论框架、核心问题 | Catastrophic_Forgetting, Stability-Plasticity_Dilemma, Representational_Drift, Continual_Learning |
| `2-Methods/` | 方法、算法、训练策略 | Adapter, LoRA, MoE, EWC, Experience_Replay, Knowledge_Distillation, PackNet |
| `3-Architectures/` | 模型架构、系统设计 | VLA, CLIP, World-Model, Diffusion_Transformer, LOTUS, MOTUS |
| `4-RL/` | 强化学习相关 | RL, Policy_Learning, Reward_Modeling, Actor-Critic, PPO |
| `5-Robotics/` | 机器人相关 | Skill_Learning, Robot_Robustness, Manipulation |
| `6-Techniques/` | 具体技术、实现细节 | Flow_Matching, Diffusion_Policy, Continual_Backpropagation, Autoencoder |
| `7-Datasets/` | 数据集、benchmark | LIBERO, RoboTwin, Franka_Robot |

## 分类决策流程

```
概念出现
    ↓
是数据集？ → 7-Datasets/
    ↓ 否
是模型/架构？ → 3-Architectures/
    ↓ 否
是 RL 相关？ → 4-RL/
    ↓ 否
是机器人相关？ → 5-Robotics/
    ↓ 否
是具体技术/算法？ → 2-Methods/ 或 6-Techniques/
    ↓ 否
是基础概念？ → 1-Foundations/
```

### 2-Methods vs 6-Techniques 区分

| | 2-Methods | 6-Techniques |
|---|-----------|--------------|
| **特点** | 通用方法、可组合 | 具体技术、实现细节 |
| **例子** | Adapter, LoRA, MoE | Flow-Matching, Diffusion-Policy |
| **判断** | 可以单独作为方法使用 | 通常作为方法的组成部分 |

## 概念笔记模板

```markdown
---
type: concept
aliases: [中文别名, 英文别名]
---

# 概念名称

## 定义
{一句话定义}

## 数学形式
$$公式$$

**符号说明**：
- $x$: ...
- $y$: ...

## 核心要点
1. ...
2. ...

## 代表工作
- [[Paper1]]: ...
- [[Paper2]]: ...

## 相关概念
- [[相关概念1]]
- [[相关概念2]]
```

## 文件命名规则

- 使用英文，单词间用下划线或连字符
- 例：`Catastrophic_Forgetting.md`、`Flow-Matching.md`
- 避免空格（虽然允许，但不推荐）

## 注意事项

1. **幂等性**：重复运行不会创建重复概念
2. **不强制创建**：只链接已存在的概念，记录待创建列表
3. **用户确认**：批量创建前询问用户
