# Concept-Weaver 增量更新改进方案

## 1. 增量更新模式实现

### 新增配置选项
```python
# 在 weave_concepts.py 中添加
parser.add_argument('--update-mode', 
                   choices=['full', 'incremental', 'smart'],
                   default='smart',
                   help='更新模式: full=全量, incremental=增量, smart=智能')

parser.add_argument('--since-days', 
                   type=int, 
                   default=7,
                   help='增量模式下，分析最近N天的笔记')
```

### 增量更新逻辑
```python
def get_recent_papers(notes_dir: Path, since_days: int) -> List[Path]:
    """获取最近N天内修改的论文笔记"""
    cutoff_time = datetime.now() - timedelta(days=since_days)
    recent_papers = []
    
    for note_file in notes_dir.glob("*.md"):
        mtime = datetime.fromtimestamp(note_file.stat().st_mtime)
        if mtime > cutoff_time:
            recent_papers.append(note_file)
    
    return recent_papers

def incremental_analysis(notes_dir: Path, concepts_dir: Path, since_days: int = 7):
    """增量关联分析"""
    # 1. 获取最近修改的论文
    recent_papers = get_recent_papers(notes_dir, since_days)
    
    if len(recent_papers) == 0:
        print("📝 最近7天内没有新笔记，跳过分析")
        return
    
    # 2. 只分析新论文与所有现有论文的关联
    existing_papers = get_all_papers(notes_dir)
    target_papers = recent_papers + [p for p in existing_papers if p not in recent_papers]
    
    # 3. 计算关联（只考虑新论文相关的）
    associations = compute_associations(target_papers, focus_papers=recent_papers)
    
    return associations
```

## 2. 智能触发脚本

### 创建智能触发器
```python
#!/usr/bin/env python3
# scripts/smart_trigger.py

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

def should_run_concept_weaver(config_path: str = "../_shared/user-config.json") -> dict:
    """判断是否应该运行 Concept-Weaver"""
    
    # 读取配置
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    notes_dir = Path(config['NOTES_PATH'])
    
    # 检查新论文数量（最近7天）
    recent_cutoff = datetime.now() - timedelta(days=7)
    new_papers = []
    
    for note_file in notes_dir.glob("*.md"):
        mtime = datetime.fromtimestamp(note_file.stat().st_mtime)
        if mtime > recent_cutoff:
            new_papers.append(note_file)
    
    # 检查上次运行时间
    last_run_file = Path("/tmp/last_concept_weaver_run")
    if last_run_file.exists():
        with open(last_run_file, 'r') as f:
            last_run = datetime.fromisoformat(f.read().strip())
        days_since_last = (datetime.now() - last_run).days
    else:
        days_since_last = 999  # 从未运行过
    
    # 决策逻辑
    reasons = []
    should_run = False
    
    if len(new_papers) >= config.get('MIN_NEW_PAPERS_TRIGGER', 5):
        reasons.append(f"新增{len(new_papers)}篇论文 (>={config.get('MIN_NEW_PAPERS_TRIGGER', 5)})")
        should_run = True
    
    if days_since_last >= config.get('MAX_DAYS_BETWEEN_RUNS', 10):
        reasons.append(f"距离上次运行{days_since_last}天 (>={config.get('MAX_DAYS_BETWEEN_RUNS', 10)})")
        should_run = True
    
    # 保存结果
    result = {
        'should_run': should_run,
        'reasons': reasons,
        'new_papers_count': len(new_papers),
        'days_since_last': days_since_last,
        'new_papers': [str(p.name) for p in new_papers[:10]]  # 只显示前10个
    }
    
    if should_run:
        # 更新最后运行时间
        with open(last_run_file, 'w') as f:
            f.write(datetime.now().isoformat())
    
    return result

if __name__ == "__main__":
    result = should_run_concept_weaver()
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

## 3. 优化关联阈值

### 更新关联计算逻辑
```python
def compute_associations(papers: List[PaperMeta], similarity_threshold: float = 0.5) -> Dict:
    """计算论文关联，使用优化的阈值"""
    
    # 分层阈值策略
    STRONG_THRESHOLD = 0.7   # 强关联，自动添加双向链接
    MEDIUM_THRESHOLD = 0.5  # 中关联，添加到相关论文section
    WEAK_THRESHOLD = 0.3    # 弱关联，仅记录不显示
    
    associations = {
        'strong': [],    # 直接添加链接
        'medium': [],   # 添加到相关论文
        'weak': [],      # 仅记录
        'preview': []    # 预览给用户确认
    }
    
    for i, paper_a in enumerate(papers):
        for j, paper_b in enumerate(papers[i+1:], i+1):
            similarity = calculate_similarity(paper_a, paper_b)
            
            assoc_data = {
                'paper_a': paper_a.title,
                'paper_b': paper_b.title,
                'similarity': similarity,
                'reason': get_similarity_reason(paper_a, paper_b)
            }
            
            if similarity >= STRONG_THRESHOLD:
                associations['strong'].append(assoc_data)
            elif similarity >= MEDIUM_THRESHOLD:
                associations['medium'].append(assoc_data)
            elif similarity >= WEAK_THRESHOLD:
                associations['weak'].append(assoc_data)
            
            # 所有关联都加入预览（让用户确认）
            if similarity >= WEAK_THRESHOLD:
                associations['preview'].append(assoc_data)
    
    return associations
```

## 4. 运行前预览功能

### 添加预览模式
```python
def preview_associations(associations: dict, preview_limit: int = 10):
    """预览关联结果，让用户确认"""
    
    print("\n" + "="*60)
    print("📊 关联分析预览")
    print("="*60)
    
    # 强关联（自动添加）
    if associations['strong']:
        print(f"\n🔥 强关联 ({len(associations['strong'])}对) - 将自动添加链接:")
        for assoc in associations['strong'][:preview_limit]:
            print(f"  • {assoc['paper_a']} ↔ {assoc['paper_b']}")
            print(f"    相似度: {assoc['similarity']:.2f}, 原因: {assoc['reason']}")
    
    # 中关联（需确认）
    if associations['medium']:
        print(f"\n⚡ 中关联 ({len(associations['medium'])}对) - 需确认是否添加:")
        for i, assoc in enumerate(associations['medium'][:preview_limit]):
            print(f"  {i+1}. {assoc['paper_a']} → {assoc['paper_b']}")
            print(f"     相似度: {assoc['similarity']:.2f}, 原因: {assoc['reason']}")
    
    # 用户确认
    if associations['medium']:
        print(f"\n💭 确认添加上述中关联到笔记？(y/n/all/none): ", end="")
        response = input().strip().lower()
        
        if response == 'all':
            confirmed = associations['medium']
        elif response == 'none':
            confirmed = []
        elif response == 'y':
            # 这里简化处理，实际应该让用户选择具体哪些
            confirmed = associations['medium'][:3]  # 默认选前3个
        else:
            confirmed = []
        
        associations['confirmed_medium'] = confirmed
    
    return associations
```

## 5. 配置更新

### 更新 user-config.json 模板
```json
{
  "MIN_NEW_PAPERS_TRIGGER": 5,
  "MAX_DAYS_BETWEEN_RUNS": 10,
  "SIMILARITY_THRESHOLD_STRONG": 0.7,
  "SIMILARITY_THRESHOLD_MEDIUM": 0.5,
  "SIMILARITY_THRESHOLD_WEAK": 0.3,
  "AUTO_UPDATE_CONCEPTS": false,
  "UPDATE_MODE": "smart",
  "PREVIEW_BEFORE_UPDATE": true,
  "PHASE": "phase1_manual"
}
```

## 6. 回滚功能

### 创建备份和恢复机制
```python
#!/usr/bin/env python3
# scripts/backup_manager.py

import shutil
from datetime import datetime
from pathlib import Path

def backup_notes_before_update(notes_dir: Path):
    """更新前备份笔记"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"/tmp/notes_backup_{timestamp}")
    
    # 只备份论文笔记（不包括概念笔记）
    paper_backup = backup_dir / "papers"
    paper_backup.mkdir(parents=True, exist_ok=True)
    
    for note_file in notes_dir.glob("*.md"):
        if not note_file.name.startswith("_"):  # 排除概念笔记
            shutil.copy2(note_file, paper_backup / note_file.name)
    
    # 保存备份信息
    backup_info = {
        'timestamp': timestamp,
        'backup_path': str(backup_dir),
        'files_count': len(list(paper_backup.glob("*.md")))
    }
    
    with open(backup_dir / "backup_info.json", 'w') as f:
        json.dump(backup_info, f, indent=2)
    
    return backup_info

def rollback_to_backup(backup_timestamp: str):
    """回滚到指定备份"""
    backup_dir = Path(f"/tmp/notes_backup_{backup_timestamp}")
    
    if not backup_dir.exists():
        print(f"❌ 备份不存在: {backup_dir}")
        return False
    
    notes_dir = Path("../ObsidianVault/论文笔记")  # 根据实际路径调整
    
    # 恢复文件
    paper_backup = backup_dir / "papers"
    for backup_file in paper_backup.glob("*.md"):
        shutil.copy2(backup_file, notes_dir / backup_file.name)
    
    print(f"✅ 已回滚到备份 {backup_timestamp}")
    return True
```

## 7. 主题化整理功能

### 添加主题过滤
```python
parser.add_argument('--focus-theme', 
                   type=str,
                   help='只分析特定主题的论文，如 "VLA"、"持续学习"')

def filter_by_theme(papers: List[PaperMeta], theme: str) -> List[PaperMeta]:
    """按主题过滤论文"""
    theme_keywords = {
        'VLA': ['vla', 'vision-language-action', '视觉语言动作'],
        '持续学习': ['continual learning', '终身学习', 'catastrophic forgetting'],
        '世界模型': ['world model', '世界模型', 'jea', 'predictive model'],
        'MoE': ['moe', 'mixture of experts', '专家混合'],
        '机器人': ['robot', 'manipulation', '机器人', '操作']
    }
    
    keywords = theme_keywords.get(theme, [theme.lower()])
    
    filtered = []
    for paper in papers:
        paper_text = (paper.title + ' ' + ' '.join(paper.keywords)).lower()
        if any(kw in paper_text for kw in keywords):
            filtered.append(paper)
    
    return filtered
```