#!/usr/bin/env python3
"""
Concept Weaver - 发现论文之间的关联，构建概念网络

用法:
    python3 weave_concepts.py --notes-dir "/path/to/notes"
    python3 weave_concepts.py --notes-dir "/path/to/notes" --full-scan
"""

import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field, asdict

@dataclass
class PaperMeta:
    """论文元数据"""
    title: str
    path: str = ""
    arxiv_id: str = ""
    keywords: Set[str] = field(default_factory=set)
    problems: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    related_papers: List[str] = field(default_factory=list)
    concepts: Set[str] = field(default_factory=set)  # 从"相关概念" section 提取

    def to_dict(self):
        return {
            "title": self.title,
            "path": self.path,
            "arxiv_id": self.arxiv_id,
            "keywords": list(self.keywords),
            "problems": self.problems,
            "methods": self.methods,
            "related_papers": self.related_papers,
            "concepts": list(self.concepts)
        }

@dataclass
class WeaverState:
    """织网器状态"""
    last_run: str = ""
    processed_papers: Dict[str, str] = field(default_factory=dict)  # paper_name -> mtime
    
    def to_dict(self):
        return {
            "last_run": self.last_run,
            "processed_papers": self.processed_papers
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            last_run=data.get("last_run", ""),
            processed_papers=data.get("processed_papers", {})
        )

class ConceptWeaver:
    """概念织网器"""
    
    # 关键词分类词典
    KEYWORD_CATEGORIES = {
        "VLA": ["vla", "vision-language-action", "vision language action"],
        "持续学习": ["continual learning", "lifelong learning", "持续学习", "终身学习", "catastrophic forgetting"],
        "世界模型": ["world model", "世界模型", "jepa", "predictive model", "dynamics model"],
        "MoE": ["moe", "mixture of experts", "expert routing"],
        "Adapter": ["adapter", "lora", "parameter-efficient"],
        "RL": ["reinforcement learning", "rl", "policy learning", "mdp"],
        "技能学习": ["skill learning", "atomic skill", "skill plugin"],
        "机器人": ["robot", "manipulation", "grasping", "locomotion"],
        "OCR": ["ocr", "optical character recognition", "text recognition"],
        "文档解析": ["document parsing", "document understanding", "layout analysis"],
        "数据中心": ["data-centric", "data quality", "data difficulty", "data diversity"],
    }
    
    # 方法关键词
    METHOD_KEYWORDS = {
        "Adapter", "MoE", "Autoencoder", "Attention", "Transformer",
        "JEPA", "Diffusion", "VAE", "SSM", "Mamba", "LNN"
    }
    
    def __init__(self, notes_dir: str, concepts_dir: str = None, 
                 similarity_threshold: float = 0.3):
        self.notes_dir = Path(notes_dir)
        self.concepts_dir = Path(concepts_dir or f"{notes_dir}/_概念")
        self.state_file = self.notes_dir / ".weaver_state.json"
        self.similarity_threshold = similarity_threshold
        self.papers: Dict[str, PaperMeta] = {}
        self.concept_papers: Dict[str, Set[str]] = defaultdict(set)
        self.similarity_matrix: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.state = WeaverState()
        
    def load_state(self) -> WeaverState:
        """加载状态文件"""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                self.state = WeaverState.from_dict(data)
            except:
                self.state = WeaverState()
        return self.state
    
    def save_state(self):
        """保存状态文件"""
        self.state.last_run = datetime.now().isoformat()
        self.state_file.write_text(json.dumps(self.state.to_dict(), indent=2), encoding="utf-8")
    
    def get_paper_mtime(self, path: str) -> str:
        """获取论文修改时间"""
        try:
            mtime = Path(path).stat().st_mtime
            return datetime.fromtimestamp(mtime).isoformat()
        except:
            return ""
    
    def is_paper_changed(self, paper_name: str, path: str) -> bool:
        """检查论文是否已改变"""
        current_mtime = self.get_paper_mtime(path)
        stored_mtime = self.state.processed_papers.get(paper_name, "")
        return current_mtime != stored_mtime
    
    def scan_papers(self, incremental: bool = True) -> Dict[str, PaperMeta]:
        """扫描论文笔记（增量或全量）"""
        papers = {}
        
        for md_file in self.notes_dir.rglob("*.md"):
            if md_file.name.startswith("_") or md_file.name.startswith("概念") or md_file.name == ".weaver_state.json":
                continue
            
            # 增量模式：只处理新/修改的论文
            if incremental:
                if not self.is_paper_changed(md_file.stem, str(md_file)):
                    continue
            
            content = md_file.read_text(encoding="utf-8")
            meta = self._extract_meta(md_file.stem, content)
            meta.path = str(md_file)
            papers[md_file.stem] = meta
            
            # 更新状态
            self.state.processed_papers[md_file.stem] = self.get_paper_mtime(str(md_file))
            
        self.papers = papers
        return papers
    
    def _extract_meta(self, filename: str, content: str) -> PaperMeta:
        """从笔记内容提取元数据"""
        meta = PaperMeta(title=filename)
        
        # 提取 arXiv ID
        arxiv_match = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5})', content)
        if arxiv_match:
            meta.arxiv_id = arxiv_match.group(1)
        
        # 优先从"## 🔗 相关概念" section 提取概念
        concept_match = re.search(r'## 🔗 相关概念\s*(.+?)(?=##|---|$)', content, re.DOTALL)
        if concept_match:
            concept_text = concept_match.group(1)
            # 提取 [[ConceptName]] 格式
            concepts = re.findall(r'\[\[([^\]]+)\]\]', concept_text)
            meta.concepts = set(concepts)
        
        # 如果没有相关概念 section，从全文提取关键词
        if not meta.concepts:
            content_lower = content.lower()
            for category, keywords in self.KEYWORD_CATEGORIES.items():
                for kw in keywords:
                    if kw.lower() in content_lower:
                        meta.keywords.add(category)
                        meta.concepts.add(category)
                        break
        
        # 提取方法关键词
        for method in self.METHOD_KEYWORDS:
            if method.lower() in content.lower():
                meta.methods.append(method)
        
        # 提取问题（从"核心问题" section）
        problem_match = re.search(r'## 核心问题\s*(.+?)(?=##|---|$)', content, re.DOTALL)
        if problem_match:
            problem_text = problem_match.group(1)
            if "持续学习" in problem_text or "遗忘" in problem_text:
                meta.problems.append("持续学习")
            if "泛化" in problem_text:
                meta.problems.append("泛化能力")
        
        return meta
    
    def compute_similarity(self, all_papers: Dict[str, PaperMeta] = None) -> Dict[str, Dict[str, float]]:
        """计算论文之间的相似度（基于共同概念）"""
        # 合并已有论文和新论文
        papers = all_papers or self.papers
        paper_names = list(papers.keys())
        
        for i, name_a in enumerate(paper_names):
            for j, name_b in enumerate(paper_names[i+1:], i+1):
                concepts_a = papers[name_a].concepts
                concepts_b = papers[name_b].concepts
                
                if not concepts_a or not concepts_b:
                    continue
                
                # Jaccard 相似度
                intersection = len(concepts_a & concepts_b)
                union = len(concepts_a | concepts_b)
                sim = intersection / union if union > 0 else 0.0
                
                self.similarity_matrix[name_a][name_b] = sim
                self.similarity_matrix[name_b][name_a] = sim
        
        return dict(self.similarity_matrix)
    
    def update_notes(self, all_papers: Dict[str, PaperMeta] = None) -> int:
        """更新论文笔记，添加关联"""
        papers = all_papers or self.papers
        updated_count = 0
        
        for paper_name, meta in self.papers.items():
            # 找到强关联的论文
            strong_relations = []
            for other_name, sim in self.similarity_matrix.get(paper_name, {}).items():
                if sim >= self.similarity_threshold:
                    reason = self._get_relation_reason(paper_name, other_name, papers)
                    strong_relations.append((other_name, sim, reason))
            
            if not strong_relations:
                continue
            
            # 排序
            strong_relations.sort(key=lambda x: x[1], reverse=True)
            
            # 读取原笔记
            note_path = Path(meta.path)
            content = note_path.read_text(encoding="utf-8")
            
            # 检查是否已有「相关论文」section
            if "## 🔗 相关论文" in content:
                # 移除旧的 section
                content = re.sub(r'\n*## 🔗 相关论文.*(?=\n## |\n---|\Z)', '', content, flags=re.DOTALL)
            
            # 生成新的关联 section
            relations_md = self._generate_relations_section(strong_relations[:5])
            
            # 追加到笔记末尾
            new_content = content.rstrip() + "\n\n" + relations_md
            note_path.write_text(new_content, encoding="utf-8")
            updated_count += 1
        
        return updated_count
    
    def _get_relation_reason(self, paper_a: str, paper_b: str, papers: Dict[str, PaperMeta]) -> str:
        """获取关联原因"""
        meta_a = papers.get(paper_a, PaperMeta(title=paper_a))
        meta_b = papers.get(paper_b, PaperMeta(title=paper_b))
        
        shared_concepts = meta_a.concepts & meta_b.concepts
        if shared_concepts:
            return f"共同概念: {', '.join(sorted(shared_concepts))}"
        
        shared_methods = set(meta_a.methods) & set(meta_b.methods)
        if shared_methods:
            return f"共同方法: {', '.join(sorted(shared_methods))}"
        
        return "相关研究"
    
    def _generate_relations_section(self, relations: List[Tuple[str, float, str]]) -> str:
        """生成相关论文 section（显示相似度分数）"""
        md = "## 🔗 相关论文\n\n"
        md += "| 论文 | 相似度 | 关联原因 |\n"
        md += "|------|--------|----------|\n"
        
        for other_name, sim, reason in relations:
            md += f"| [[{other_name}]] | **{sim:.2f}** | {reason} |\n"
        
        return md
    
    def generate_concept_mocs(self, all_papers: Dict[str, PaperMeta] = None) -> int:
        """生成概念 MOC 页面"""
        papers = all_papers or self.papers
        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        
        # 按概念聚合论文
        for paper_name, meta in papers.items():
            for concept in meta.concepts:
                self.concept_papers[concept].add(paper_name)
        
        moc_count = 0
        for concept, concept_papers in self.concept_papers.items():
            if len(concept_papers) < 2:
                continue
            
            moc_path = self.concepts_dir / f"{concept}.md"
            moc_content = self._generate_concept_moc(concept, concept_papers, papers)
            moc_path.write_text(moc_content, encoding="utf-8")
            moc_count += 1
        
        return moc_count
    
    def _generate_concept_moc(self, concept: str, papers_set: Set[str], all_papers: Dict[str, PaperMeta]) -> str:
        """生成单个概念的 MOC 内容"""
        md = f"# {concept}\n\n"
        md += f"> 相关论文: {len(papers_set)} 篇\n\n"
        md += "## 📄 相关论文\n\n"
        
        for paper_name in sorted(papers_set):
            meta = all_papers.get(paper_name, PaperMeta(title=paper_name))
            md += f"- [[{paper_name}]]"
            if meta.arxiv_id:
                md += f" (arXiv:{meta.arxiv_id})"
            md += "\n"
        
        md += "\n## 🔗 概念关联\n\n"
        
        # 计算论文间的关联
        md += "### 论文关联矩阵\n\n"
        
        paper_list = sorted(papers_set)
        md += "| | " + " | ".join(paper_list) + " |\n"
        md += "|" + "---|" * (len(paper_list) + 1) + "\n"
        
        for paper_a in paper_list:
            row = [paper_a]
            for paper_b in paper_list:
                if paper_a == paper_b:
                    row.append("-")
                else:
                    sim = self.similarity_matrix.get(paper_a, {}).get(paper_b, 0)
                    row.append(f"{sim:.2f}" if sim > 0 else "-")
            md += "| " + " | ".join(row) + " |\n"
        
        md += f"\n---\n*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        return md
    
    def generate_report(self, new_count: int = 0) -> str:
        """生成执行报告"""
        report = "📊 概念织网报告\n"
        report += "=" * 40 + "\n\n"
        
        if new_count > 0:
            report += f"🆕 新增/修改论文: {new_count} 篇\n\n"
        
        report += f"📚 总论文数: {len(self.papers)} 篇\n"
        report += f"🏷️ 识别概念: {len(self.concept_papers)} 个\n\n"
        
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
                report += f"  - {a} ↔ {b} ({sim:.2f})\n"
        
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
                       default="full", help="自动更新模式 (默认: full)")
    parser.add_argument("--full-scan", action="store_true", 
                       help="全量扫描（默认为增量模式）")
    parser.add_argument("--similarity-threshold", type=float, default=0.3,
                       help="关联强度阈值 (默认: 0.3)")
    
    args = parser.parse_args()
    
    weaver = ConceptWeaver(
        notes_dir=args.notes_dir,
        concepts_dir=args.concepts_dir,
        similarity_threshold=args.similarity_threshold
    )
    
    # 加载状态
    if not args.full_scan:
        weaver.load_state()
        print("📦 加载上次状态...")
    
    # 扫描论文
    mode = "全量" if args.full_scan else "增量"
    print(f"🔍 {mode}扫描论文笔记...")
    new_papers = weaver.scan_papers(incremental=not args.full_scan)
    
    if not new_papers and not args.full_scan:
        print("✅ 没有新增/修改的论文，跳过处理")
        return
    
    # 计算相似度
    print("🔗 计算关联矩阵...")
    weaver.compute_similarity()
    
    updated_notes = 0
    generated_mocs = 0
    
    # 更新笔记
    if args.auto_update in ["full", "links_only"]:
        print("📝 更新笔记关联...")
        updated_notes = weaver.update_notes()
    
    # 生成 MOC
    if args.auto_update in ["full", "moc_only"]:
        print("📁 生成概念 MOC...")
        generated_mocs = weaver.generate_concept_mocs()
    
    # 保存状态
    weaver.save_state()
    
    # 输出报告
    print("\n" + weaver.generate_report(len(new_papers)))
    print(f"\n✅ 完成！更新笔记 {updated_notes} 篇，生成 MOC {generated_mocs} 个")

if __name__ == "__main__":
    main()
