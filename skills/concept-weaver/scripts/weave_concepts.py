#!/usr/bin/env python3
"""
Concept Weaver - 发现论文之间的关联，构建概念网络

用法:
    python3 weave_concepts.py --notes-dir "/path/to/notes" --auto-update full
"""

import os
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass, field

@dataclass
class PaperMeta:
    """论文元数据"""
    title: str
    arxiv_id: str = ""
    keywords: Set[str] = field(default_factory=set)
    problems: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    related_papers: List[str] = field(default_factory=list)
    concepts: Set[str] = field(default_factory=set)

class ConceptWeaver:
    """概念织网器"""
    
    # 关键词分类词典
    KEYWORD_CATEGORIES = {
        "VLA": ["vla", "vision-language-action", "vision language action"],
        "持续学习": ["continual learning", "lifelong learning", "持续学习", "终身学习", "catastrophic forgetting"],
        "世界模型": ["world model", "世界模型", "jea", "predictive model", "dynamics model"],
        "MoE": ["moe", "mixture of experts", "expert routing"],
        "Adapter": ["adapter", "lora", "parameter-efficient"],
        "RL": ["reinforcement learning", "rl", "policy learning", "mdp"],
        "技能学习": ["skill learning", "atomic skill", "skill plugin"],
        "机器人": ["robot", "manipulation", "grasping", "locomotion"],
    }
    
    # 方法关键词
    METHOD_KEYWORDS = {
        "Adapter", "MoE", "Autoencoder", "Attention", "Transformer",
        "JEPA", "Diffusion", "VAE", "SSM", "Mamba", "LNN"
    }
    
    def __init__(self, notes_dir: str, concepts_dir: str = None, 
                 similarity_threshold: float = 0.5):
        self.notes_dir = Path(notes_dir)
        self.concepts_dir = Path(concepts_dir or f"{notes_dir}/_概念")
        self.similarity_threshold = similarity_threshold
        self.papers: Dict[str, PaperMeta] = {}
        self.concept_papers: Dict[str, Set[str]] = defaultdict(set)
        self.similarity_matrix: Dict[str, Dict[str, float]] = defaultdict(dict)
        
    def scan_papers(self) -> Dict[str, PaperMeta]:
        """扫描所有论文笔记"""
        papers = {}
        
        for md_file in self.notes_dir.glob("*.md"):
            if md_file.name.startswith("_") or md_file.name.startswith("概念"):
                continue
                
            content = md_file.read_text(encoding="utf-8")
            meta = self._extract_meta(md_file.stem, content)
            papers[md_file.stem] = meta
            
        self.papers = papers
        return papers
    
    def _extract_meta(self, filename: str, content: str) -> PaperMeta:
        """从笔记内容提取元数据"""
        meta = PaperMeta(title=filename)
        
        # 提取 arXiv ID
        arxiv_match = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5})', content)
        if arxiv_match:
            meta.arxiv_id = arxiv_match.group(1)
        
        # 提取关键词
        content_lower = content.lower()
        for category, keywords in self.KEYWORD_CATEGORIES.items():
            for kw in keywords:
                if kw.lower() in content_lower:
                    meta.keywords.add(category)
                    meta.concepts.add(category)
                    break
        
        # 提取方法关键词
        for method in self.METHOD_KEYWORDS:
            if method.lower() in content_lower:
                meta.methods.append(method)
        
        # 提取问题（从"核心问题" section）
        problem_match = re.search(r'## 核心问题\s*(.+?)(?=##|---|$)', content, re.DOTALL)
        if problem_match:
            problem_text = problem_match.group(1)
            # 简单提取关键问题
            if "持续学习" in problem_text or "遗忘" in problem_text:
                meta.problems.append("持续学习")
            if "泛化" in problem_text:
                meta.problems.append("泛化能力")
            if "推理" in problem_text and "速度" in problem_text:
                meta.problems.append("推理效率")
        
        # 提取相关论文
        related_match = re.search(r'## 相关论文\s*(.+?)(?=##|---|$)', content, re.DOTALL)
        if related_match:
            related_text = related_match.group(1)
            # 提取 [[PaperName]] 格式
            meta.related_papers = re.findall(r'\[\[([^\]]+)\]\]', related_text)
        
        return meta
    
    def compute_similarity(self) -> Dict[str, Dict[str, float]]:
        """计算论文之间的相似度"""
        paper_names = list(self.papers.keys())
        
        for i, name_a in enumerate(paper_names):
            for j, name_b in enumerate(paper_names[i+1:], i+1):
                sim = self._jaccard_similarity(
                    self.papers[name_a].keywords,
                    self.papers[name_b].keywords
                )
                
                # 加权：方法相似性
                methods_a = set(self.papers[name_a].methods)
                methods_b = set(self.papers[name_b].methods)
                if methods_a and methods_b:
                    method_sim = len(methods_a & methods_b) / len(methods_a | methods_b)
                    sim = 0.6 * sim + 0.4 * method_sim
                
                self.similarity_matrix[name_a][name_b] = sim
                self.similarity_matrix[name_b][name_a] = sim
        
        return dict(self.similarity_matrix)
    
    def _jaccard_similarity(self, set_a: Set[str], set_b: Set[str]) -> float:
        """计算 Jaccard 相似度"""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
    
    def update_notes(self) -> int:
        """更新论文笔记，添加关联"""
        updated_count = 0
        
        for paper_name, meta in self.papers.items():
            # 找到强关联的论文
            strong_relations = []
            for other_name, sim in self.similarity_matrix.get(paper_name, {}).items():
                if sim >= self.similarity_threshold:
                    strong_relations.append((other_name, sim, 
                                           self._get_relation_reason(paper_name, other_name)))
            
            if not strong_relations:
                continue
            
            # 排序
            strong_relations.sort(key=lambda x: x[1], reverse=True)
            
            # 读取原笔记
            note_path = self.notes_dir / f"{paper_name}.md"
            content = note_path.read_text(encoding="utf-8")
            
            # 检查是否已有「相关论文」section
            if "## 🔗 相关论文" in content or "## 相关论文" in content:
                continue  # 已有，跳过
            
            # 生成关联 section
            relations_md = self._generate_relations_section(strong_relations[:5])
            
            # 追加到笔记末尾
            new_content = content.rstrip() + "\n\n" + relations_md
            note_path.write_text(new_content, encoding="utf-8")
            updated_count += 1
        
        return updated_count
    
    def _get_relation_reason(self, paper_a: str, paper_b: str) -> str:
        """获取关联原因"""
        meta_a = self.papers[paper_a]
        meta_b = self.papers[paper_b]
        
        shared_concepts = meta_a.concepts & meta_b.concepts
        if shared_concepts:
            return f"共同主题: {', '.join(shared_concepts)}"
        
        shared_methods = set(meta_a.methods) & set(meta_b.methods)
        if shared_methods:
            return f"共同方法: {', '.join(shared_methods)}"
        
        return "相关研究"
    
    def _generate_relations_section(self, relations: List[Tuple[str, float, str]]) -> str:
        """生成相关论文 section"""
        md = "## 🔗 相关论文\n\n"
        
        for other_name, sim, reason in relations:
            md += f"- [[{other_name}]] (相似度: {sim:.2f}) - {reason}\n"
        
        return md
    
    def generate_concept_mocs(self) -> int:
        """生成概念 MOC 页面"""
        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        
        # 按概念聚合论文
        for paper_name, meta in self.papers.items():
            for concept in meta.concepts:
                self.concept_papers[concept].add(paper_name)
        
        moc_count = 0
        for concept, papers in self.concept_papers.items():
            if len(papers) < 2:
                continue
            
            moc_path = self.concepts_dir / f"{concept}.md"
            moc_content = self._generate_concept_moc(concept, papers)
            moc_path.write_text(moc_content, encoding="utf-8")
            moc_count += 1
        
        return moc_count
    
    def _generate_concept_moc(self, concept: str, papers: Set[str]) -> str:
        """生成单个概念的 MOC 内容"""
        md = f"# {concept}\n\n"
        md += f"> 相关论文: {len(papers)} 篇\n\n"
        md += "## 📄 相关论文\n\n"
        
        for paper_name in sorted(papers):
            meta = self.papers[paper_name]
            md += f"- [[{paper_name}]]"
            if meta.arxiv_id:
                md += f" (arXiv:{meta.arxiv_id})"
            md += "\n"
        
        md += "\n## 🔗 概念关联\n\n"
        
        # 添加方法对比
        methods_papers = defaultdict(list)
        for paper_name in papers:
            for method in self.papers[paper_name].methods:
                methods_papers[method].append(paper_name)
        
        if methods_papers:
            md += "### 方法对比\n\n"
            md += "| 方法 | 论文 |\n|------|------|\n"
            for method, related_papers in sorted(methods_papers.items()):
                paper_links = ", ".join(f"[[{p}]]" for p in related_papers)
                md += f"| {method} | {paper_links} |\n"
        
        md += f"\n---\n*生成时间: 2026-03-27*\n"
        return md
    
    def generate_report(self) -> str:
        """生成执行报告"""
        report = "📊 概念织网报告\n"
        report += "=" * 40 + "\n\n"
        
        report += f"发现 {len(self.papers)} 篇论文\n"
        report += f"识别 {len(self.concept_papers)} 个概念\n\n"
        
        # 强关联统计
        strong_relations = []
        for paper_a, relations in self.similarity_matrix.items():
            for paper_b, sim in relations.items():
                if sim >= self.similarity_threshold and paper_a < paper_b:
                    strong_relations.append((paper_a, paper_b, sim))
        
        strong_relations.sort(key=lambda x: x[2], reverse=True)
        
        if strong_relations:
            report += f"🔗 强关联 ({len(strong_relations)})\n"
            for a, b, sim in strong_relations[:10]:
                reason = self._get_relation_reason(a, b)
                report += f"  - {a} ↔ {b} ({sim:.2f}) - {reason}\n"
        
        # 概念聚合
        report += "\n📁 概念聚合\n"
        for concept, papers in sorted(self.concept_papers.items(), 
                                      key=lambda x: len(x[1]), reverse=True)[:5]:
            report += f"  - {concept}: {len(papers)} 篇\n"
        
        return report

def main():
    parser = argparse.ArgumentParser(description="概念织网器")
    parser.add_argument("--notes-dir", required=True, help="笔记目录路径")
    parser.add_argument("--concepts-dir", help="概念目录路径")
    parser.add_argument("--auto-update", choices=["full", "moc_only", "links_only", "none"],
                       default="full", help="自动更新模式")
    parser.add_argument("--similarity-threshold", type=float, default=0.5,
                       help="关联强度阈值")
    
    args = parser.parse_args()
    
    weaver = ConceptWeaver(
        notes_dir=args.notes_dir,
        concepts_dir=args.concepts_dir,
        similarity_threshold=args.similarity_threshold
    )
    
    # 执行流程
    print("🔍 扫描论文笔记...")
    weaver.scan_papers()
    
    print("🔗 计算关联矩阵...")
    weaver.compute_similarity()
    
    updated_notes = 0
    generated_mocs = 0
    
    if args.auto_update in ["full", "links_only"]:
        print("📝 更新笔记关联...")
        updated_notes = weaver.update_notes()
    
    if args.auto_update in ["full", "moc_only"]:
        print("📁 生成概念 MOC...")
        generated_mocs = weaver.generate_concept_mocs()
    
    # 输出报告
    print("\n" + weaver.generate_report())
    print(f"\n✅ 完成！更新笔记 {updated_notes} 篇，生成 MOC {generated_mocs} 个")

if __name__ == "__main__":
    main()
