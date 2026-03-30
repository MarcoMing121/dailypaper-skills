#!/usr/bin/env python3
"""
Generate Topic MOCs (Map of Content) for Obsidian vault.
Analyzes paper notes and creates cross-category topic pages.
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict

def load_config():
    """Load user configuration."""
    config_path = Path(__file__).parent / "user-config.json"
    with open(config_path) as f:
        return json.load(f)

def extract_paper_metadata(paper_path):
    """Extract metadata from a paper note."""
    with open(paper_path, encoding='utf-8') as f:
        content = f.read()
    
    metadata = {
        'title': '',
        'method_name': '',
        'tags': [],
        'keywords': set(),
        'problem': '',
        'contribution': '',
        'path': paper_path.name
    }
    
    # Extract from YAML frontmatter
    fm_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if title_match:
            metadata['title'] = title_match.group(1).strip('"\'')
        
        method_match = re.search(r'^method_name:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if method_match:
            metadata['method_name'] = method_match.group(1).strip('"\'')
        
        tags_match = re.search(r'^tags:\s*\[(.+?)\]', fm, re.MULTILINE)
        if tags_match:
            tags_str = tags_match.group(1)
            metadata['tags'] = [t.strip().strip('"\'') for t in tags_str.split(',')]
    
    # Extract title from heading if not in frontmatter
    if not metadata['title']:
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            metadata['title'] = title_match.group(1)
    
    # Extract keywords from content
    # Look for technical terms
    tech_patterns = [
        r'\[\[([A-Za-z][A-Za-z0-9_\-\s]+)\]\]',  # Wiki links
        r'\*\*([A-Za-z][A-Za-z0-9_\-\s]+)\*\*',   # Bold terms
    ]
    for pattern in tech_patterns:
        for match in re.finditer(pattern, content):
            keyword = match.group(1).strip()
            if len(keyword) > 2 and len(keyword) < 50:
                metadata['keywords'].add(keyword)
    
    # Extract problem statement
    problem_match = re.search(r'## 核心问题\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
    if problem_match:
        metadata['problem'] = problem_match.group(1).strip()[:200]
    
    # Extract contribution
    contrib_match = re.search(r'## 核心贡献\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
    if contrib_match:
        metadata['contribution'] = contrib_match.group(1).strip()[:300]
    
    return metadata

def discover_topics(papers_metadata, config):
    """Discover topics from paper metadata."""
    # Define topic rules based on tags and keywords
    topic_rules = {
        'VLA-持续学习': {
            'required_tags': ['vla', 'continual-learning', 'catastrophic-forgetting'],
            'min_matches': 2,
            'description': 'VLA 模型如何在学习新任务时避免遗忘？'
        },
        '世界模型': {
            'required_tags': ['world-model', 'jepe', 'prediction'],
            'min_matches': 1,
            'description': '如何构建世界模型以实现预测和规划？'
        },
        '持续学习': {
            'required_tags': ['continual-learning', 'lifelong-learning'],
            'min_matches': 1,
            'description': '如何实现持续学习而不遗忘？'
        },
        '机器人操作': {
            'required_tags': ['robotics', 'manipulation', 'vla'],
            'min_matches': 2,
            'description': '如何让机器人学习操作技能？'
        },
    }
    
    topics = defaultdict(lambda: {'papers': [], 'description': ''})
    
    for paper in papers_metadata:
        paper_tags = set(t.lower() for t in paper['tags'])
        
        for topic_name, rule in topic_rules.items():
            required = set(t.lower() for t in rule['required_tags'])
            matches = len(required & paper_tags)
            
            if matches >= rule['min_matches']:
                topics[topic_name]['papers'].append(paper)
                topics[topic_name]['description'] = rule['description']
    
    # Filter topics with at least 2 papers
    return {k: v for k, v in topics.items() if len(v['papers']) >= 2}

def generate_topic_moc(topic_name, topic_data, config):
    """Generate MOC content for a topic."""
    papers = topic_data['papers']
    description = topic_data['description']
    
    lines = [
        f"# {topic_name}",
        "",
        f"**核心问题**: {description}",
        "",
        f"共 {len(papers)} 篇相关论文",
        "",
        "## 解决方案",
        "",
        "| 方法 | 核心思想 | 论文 |",
        "|------|----------|------|",
    ]
    
    for paper in papers:
        method = paper['method_name'] or paper['title'].split(':')[0]
        contribution = paper['contribution'][:50] + "..." if len(paper['contribution']) > 50 else paper['contribution']
        lines.append(f"| {method} | {contribution} | [[{paper['path'].replace('.md', '')}]] |")
    
    lines.extend([
        "",
        "## 相关概念",
        "",
    ])
    
    # Collect related concepts
    all_keywords = set()
    for paper in papers:
        all_keywords.update(paper['keywords'])
    
    # Filter to concepts that exist
    for kw in sorted(all_keywords)[:10]:
        lines.append(f"- [[{kw}]]")
    
    return '\n'.join(lines)

def main():
    config = load_config()
    vault_path = Path(config['VAULT_PATH'])
    papers_path = Path(config['NOTES_PATH'])
    moc_path = Path(config.get('TOPIC_MOC_PATH', config['CONCEPTS_PATH'] + '/MOCs'))
    
    # Create MOC directory
    moc_path.mkdir(parents=True, exist_ok=True)
    
    # Scan all paper notes
    papers_metadata = []
    for md_file in papers_path.rglob('*.md'):
        # Skip MOC files
        if md_file.stem == md_file.parent.name:
            continue
        papers_metadata.append(extract_paper_metadata(md_file))
    
    print(f"扫描到 {len(papers_metadata)} 篇论文笔记")
    
    # Discover topics
    topics = discover_topics(papers_metadata, config)
    print(f"发现 {len(topics)} 个主题")
    
    # Generate MOCs
    created = 0
    for topic_name, topic_data in topics.items():
        moc_content = generate_topic_moc(topic_name, topic_data, config)
        moc_file = moc_path / f"{topic_name}.md"
        
        with open(moc_file, 'w', encoding='utf-8') as f:
            f.write(moc_content)
        
        print(f"  创建: {moc_file.relative_to(vault_path)}")
        created += 1
    
    print(f"\n✅ 创建了 {created} 个主题 MOC")
    print(f"📁 位置: {moc_path.relative_to(vault_path)}/")

if __name__ == '__main__':
    main()
