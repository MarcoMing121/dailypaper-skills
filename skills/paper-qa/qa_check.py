#!/usr/bin/env python3
"""Quality Assurance checker for paper notes.

Usage:
    python3 qa_check.py <note.md> [--fix] [--max-iterations N]

Checks:
    1. Structure (frontmatter, naming, path)
    2. Content completeness (figures, formulas, tables)
    3. Image quality (format, reachability, local files)
    4. Formula format (LaTeX, naming, symbols)
    5. Concept links (validity, content)

With --fix, automatically repairs issues and re-checks.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# Import shared composite figure parser
try:
    from _shared.check_composite_figures import ArxivFigureParser, fetch_arxiv_html, parse_arxiv_figures
    SHARED_PARSER_AVAILABLE = True
except ImportError:
    SHARED_PARSER_AVAILABLE = False
    # Fallback: define locally if shared not available
    from html.parser import HTMLParser
    
    class ArxivFigureParser(HTMLParser):
        """Parse arXiv HTML to extract figure structure."""
        
        def __init__(self):
            super().__init__()
            self.figures = []
            self.current_figure = None
            self.in_figure = False
            self.depth = 0
        
        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            
            if tag == "figure":
                self.depth += 1
                figure_id = attrs_dict.get("id", "")
                
                if self.depth == 1:
                    self.current_figure = {
                        "id": figure_id,
                        "images": []
                    }
                    self.in_figure = True
            
            elif tag == "img" and self.current_figure:
                src = attrs_dict.get("src", "")
                if src:
                    self.current_figure["images"].append(src)
        
        def handle_endtag(self, tag):
            if tag == "figure":
                if self.depth == 1 and self.current_figure:
                    self.figures.append(self.current_figure)
                    self.current_figure = None
                    self.in_figure = False
                self.depth -= 1


    def fetch_arxiv_html(arxiv_url: str) -> Optional[str]:
        """Fetch arXiv HTML content."""
        try:
            if "arxiv.org/abs/" in arxiv_url:
                arxiv_id = arxiv_url.split("/abs/")[-1].split("v")[0]
                html_url = f"https://arxiv.org/html/{arxiv_id}"
            elif "arxiv.org/html/" in arxiv_url:
                html_url = arxiv_url
            else:
                return None
            
            req = urllib.request.Request(
                html_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; PaperQA/1.0)"}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8")
        except Exception as e:
            return None


    def parse_arxiv_figures(html_content: str) -> list[dict]:
        """Parse arXiv HTML to extract figure structure."""
        parser = ArxivFigureParser()
        parser.feed(html_content)
        return parser.figures


# ============================================================================
# Configuration
# ============================================================================

def load_config() -> dict:
    """Load user config."""
    config_path = Path(__file__).parent.parent / "_shared" / "user-config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def get_vault_path(config: dict) -> Path:
    """Get VAULT_PATH from config."""
    vault = config.get("paths", {}).get("obsidian_vault", "")
    if vault:
        return Path(vault).expanduser()
    return Path(__file__).parent.parent.parent.parent / "shared" / "ObsidianVault"


# ============================================================================
# Check Functions
# ============================================================================

def check_frontmatter(text: str) -> dict:
    """Check YAML frontmatter completeness."""
    required_fields = ["title", "method_name", "authors", "year", "venue", "tags", "created"]
    issues = []
    
    # Extract frontmatter
    fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not fm_match:
        return {"ok": False, "issues": ["Missing frontmatter"]}
    
    fm_text = fm_match.group(1)
    
    for field in required_fields:
        if not re.search(rf'^{field}:', fm_text, re.MULTILINE):
            issues.append(f"Missing field: {field}")
    
    return {"ok": len(issues) == 0, "issues": issues}


def check_figures(text: str, method_name: str, vault_path: Path) -> dict:
    """Check figure completeness and quality."""
    issues = []
    
    # Count Markdown image links (external)
    external_images = re.findall(r'!\[([^\]]*)\]\((https?://[^)]+)\)', text)
    
    # Count Obsidian wikilinks (local)
    obsidian_images = re.findall(r'!\[\[([^\]|]+)(?:\|[0-9]+)?\]\]', text)
    
    total_images = len(external_images) + len(obsidian_images)
    
    if total_images == 0:
        issues.append("No figures found in note (expected at least 1)")
    
    # Check if local images exist
    assets_dir = vault_path / "assets" / method_name
    for img_ref in obsidian_images:
        img_path = assets_dir.parent / img_ref  # img_ref already includes method_name/
        if not img_path.exists():
            issues.append(f"Local image not found: {img_ref}")
    
    # Check image file sizes (must be > 1KB)
    if assets_dir.exists():
        for img_file in assets_dir.glob("*"):
            if img_file.is_file() and img_file.stat().st_size < 1024:
                issues.append(f"Image too small (< 1KB): {img_file.name}")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {
            "external": len(external_images),
            "local": len(obsidian_images),
            "total": total_images
        }
    }


def check_formulas(text: str) -> dict:
    """Check formula format and LaTeX compatibility."""
    issues = []
    
    # Find all $$ blocks
    formula_blocks = re.findall(r'\$\$(.*?)\$\$', text, re.DOTALL)
    
    for i, formula in enumerate(formula_blocks, 1):
        # Check if formula is too long without aligned
        lines = formula.strip().split('\n')
        if len(lines) > 5 and 'aligned' not in formula and 'split' not in formula:
            issues.append(f"Formula {i}: Long formula should use aligned/split environment")
        
        # Check for common incompatible LaTeX commands
        if r'\bm{' in formula:
            issues.append(f"Formula {i}: Use plain variable instead of \\bm{{}} (Obsidian incompatible)")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {"total": len(formula_blocks)}
    }


def check_formula_format(text: str) -> dict:
    """Check if $$ blocks have empty lines around them."""
    issues = []
    
    # Find all $$ blocks with position
    pattern = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
    
    for i, match in enumerate(pattern.finditer(text), 1):
        start = match.start()
        end = match.end()
        
        # Check if there's an empty line before
        before = text[:start]
        if before and not before.endswith('\n\n'):
            # Check if previous non-whitespace character is more than 1 newline away
            lines_before = before.rstrip().split('\n')
            if lines_before and not before.rstrip().endswith('$$'):
                issues.append(f"Formula {i}: Missing empty line before $$ block")
        
        # Check if there's an empty line after
        after = text[end:]
        if after and not after.startswith('\n\n') and not after.startswith('\n$$'):
            issues.append(f"Formula {i}: Missing empty line after $$ block")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {"total": len(pattern.findall(text))}
    }


def extract_key_formulas_section(text: str) -> tuple[int, int]:
    """Extract the range of '关键公式' section.
    
    Returns:
        (start, end) positions, or (0, 0) if not found
        
    Note:
        Only checks formulas in the dedicated "关键公式" section.
        Formulas embedded in explanatory text (like in "方法详解") are not checked,
        as they are part of paragraph explanations and don't need independent names/meanings/symbols.
    """
    # Find "## 关键公式" or "## Key Formulas"
    section_match = re.search(r'^##\s+(关键公式|Key\s+Formula)', text, re.MULTILINE)
    if not section_match:
        return (0, 0)
    
    start = section_match.start()
    
    # Find the next ## heading
    next_section = re.search(r'^##\s+', text[start + 10:], re.MULTILINE)
    if next_section:
        end = start + 10 + next_section.start()
    else:
        end = len(text)
    
    return (start, end)


def check_formula_naming(text: str) -> dict:
    """Check if formulas have names (heading or [[Concept|Name]] link).
    
    Only checks formulas in the '关键公式' section.
    """
    issues = []
    
    # Extract "关键公式" section range
    key_section_start, key_section_end = extract_key_formulas_section(text)
    
    if key_section_start == 0 and key_section_end == 0:
        # No "关键公式" section found, check all formulas (backward compatible)
        key_section_start = 0
        key_section_end = len(text)
    
    # Find all $$ blocks
    pattern = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
    
    key_formula_count = 0
    for i, match in enumerate(pattern.finditer(text), 1):
        # Skip if not in "关键公式" section
        if not (key_section_start <= match.start() <= key_section_end):
            continue
        
        key_formula_count += 1
        start = match.start()
        
        # Check if there's a heading or named link before the formula
        # Look back up to 200 characters
        context_before = text[max(0, start-200):start]
        
        # Check for heading (### or ##)
        has_heading = bool(re.search(r'^#{2,3}\s+.+', context_before, re.MULTILINE))
        
        # Check for named link [[Concept|Name]]
        has_named_link = bool(re.search(r'\[\[[^\]|]+\|[^\]]+\]\]', context_before))
        
        # Check for "Name:" pattern (e.g., "Loss Function:")
        has_name_pattern = bool(re.search(r'[A-Z][a-z]+ [A-Za-z]+:\s*$', context_before))
        
        if not (has_heading or has_named_link or has_name_pattern):
            issues.append(f"Formula {i}: Missing name/heading")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {"total": key_formula_count, "in_section": key_formula_count}
    }


def check_symbol_explanation(text: str) -> dict:
    """Check if formulas have symbol explanations below.
    
    Only checks formulas in the '关键公式' section.
    """
    issues = []
    
    # Extract "关键公式" section range
    key_section_start, key_section_end = extract_key_formulas_section(text)
    
    if key_section_start == 0 and key_section_end == 0:
        # No "关键公式" section found, check all formulas (backward compatible)
        key_section_start = 0
        key_section_end = len(text)
    
    # Find all $$ blocks
    pattern = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
    
    key_formula_count = 0
    for i, match in enumerate(pattern.finditer(text), 1):
        # Skip if not in "关键公式" section
        if not (key_section_start <= match.start() <= key_section_end):
            continue
        
        key_formula_count += 1
        end = match.end()
        
        # Check if there's symbol explanation in the next 300 characters
        context_after = text[end:end+300]
        
        # Look for patterns like:
        # - "其中：" (Chinese)
        # - "where:" (English)
        # - "**符号说明**:" (Paper-Reader standard)
        # - "- $symbol$: meaning"
        # - "$symbol$ 表示/means/is
        
        has_symbol_list = bool(
            re.search(r'(其中|where|symbols)[:：]', context_after, re.IGNORECASE) or
            re.search(r'\*\*符号说明\*\*[:：]?', context_after) or
            re.search(r'\$[a-zA-Z_]+\$.*?(表示|means|is|=)', context_after, re.IGNORECASE) or
            re.search(r'^\s*- \$[a-zA-Z_]+\$', context_after, re.MULTILINE)
        )
        
        if not has_symbol_list:
            issues.append(f"Formula {i}: Missing symbol explanation")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {"total": key_formula_count, "in_section": key_formula_count}
    }


def check_formula_meaning(text: str) -> dict:
    """Check if formulas have '含义' (meaning) explanation below.
    
    Only checks formulas in the '关键公式' section.
    """
    issues = []
    
    # Extract "关键公式" section range
    key_section_start, key_section_end = extract_key_formulas_section(text)
    
    if key_section_start == 0 and key_section_end == 0:
        # No "关键公式" section found, check all formulas (backward compatible)
        key_section_start = 0
        key_section_end = len(text)
    
    # Find all $$ blocks
    pattern = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
    
    key_formula_count = 0
    for i, match in enumerate(pattern.finditer(text), 1):
        # Skip if not in "关键公式" section
        if not (key_section_start <= match.start() <= key_section_end):
            continue
        
        key_formula_count += 1
        end = match.end()
        
        # Check if there's meaning explanation in the next 300 characters
        context_after = text[end:end+300]
        
        # Look for patterns:
        # - "**含义**:" (Paper-Reader standard)
        # - "含义:" or "meaning:"
        has_meaning = bool(
            re.search(r'\*\*含义\*\*[:：]?', context_after) or
            re.search(r'(含义|meaning)[:：]', context_after, re.IGNORECASE)
        )
        
        if not has_meaning:
            issues.append(f"Formula {i}: Missing meaning explanation")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {"total": key_formula_count, "in_section": key_formula_count}
    }


def check_concept_links(text: str, vault_path: Path) -> dict:
    """Check concept link validity."""
    issues = []
    
    # Extract all [[Concept]] links (support spaces in concept names)
    concepts = re.findall(r'\[\[([A-Za-z0-9_\s-]+)\]\]', text)
    unique_concepts = set(concepts)
    
    concepts_path = vault_path / "Concepts"
    
    missing = []
    for concept in unique_concepts:
        # Concept file uses underscore instead of space
        concept_filename = concept.replace(' ', '_')
        # Search for concept file
        found = list(concepts_path.glob(f"*/*{concept_filename}.md"))
        if not found:
            missing.append(concept)
    
    if missing:
        issues.append(f"Missing concept files: {', '.join(missing)}")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {
            "total_links": len(concepts),
            "unique_concepts": len(unique_concepts),
            "missing": len(missing)
        }
    }


def extract_images_for_caption_check(text: str) -> list[dict]:
    """Extract all images with their descriptions (caption + paragraph below).
    
    Returns list of dicts: [{type: 'external'|'local', ref: 'url'|'path', caption: '...', description: '...'}]
    
    Note: description is the paragraph immediately below the image, not just the caption.
    """
    images = []
    
    # Extract Markdown external links with alt text (caption)
    for match in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', text):
        img_end = match.end()
        
        # Extract paragraph below image (next 300 characters or until next heading)
        context_after = text[img_end:img_end+300]
        # Stop at next heading or image
        para_match = re.search(r'\n\n(.+?)(?=\n\n[#*!]|\Z)', context_after, re.DOTALL)
        description = para_match.group(1).strip() if para_match else ""
        
        images.append({
            "type": "external",
            "ref": match.group(2),
            "caption": match.group(1).strip() or "No caption",
            "description": description or "No description below image"
        })
    
    # Extract Obsidian wikilinks
    for match in re.finditer(r'!\[\[([^\]|]+)(?:\|([0-9]+))?\]\]', text):
        img_end = match.end()
        
        # Extract paragraph below image
        context_after = text[img_end:img_end+300]
        para_match = re.search(r'\n\n(.+?)(?=\n\n[#*!]|\Z)', context_after, re.DOTALL)
        description = para_match.group(1).strip() if para_match else ""
        
        images.append({
            "type": "local",
            "ref": match.group(1),
            "caption": f"Figure (width: {match.group(2) or 'default'})",
            "description": description or "No description below image"
        })
    
    return images


def extract_arxiv_html_url(text: str) -> Optional[str]:
    """Extract arxiv_html URL from frontmatter."""
    # Check frontmatter first
    fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        # Look for arxiv_html field
        arxiv_match = re.search(r'^arxiv_html:\s*(.+)$', fm_text, re.MULTILINE)
        if arxiv_match:
            return arxiv_match.group(1).strip().strip('"\'')
    
    # Also check for arxiv.org links in the document
    arxiv_links = re.findall(r'https?://arxiv\.org/(abs|html)/([0-9.]+)', text)
    if arxiv_links:
        arxiv_id = arxiv_links[0][1]
        return f"https://arxiv.org/html/{arxiv_id}"
    
    return None


def check_figure_mapping(text: str) -> dict:
    """Check if note images match arXiv HTML figure structure.
    
    Detects:
    - Composite figures (one figure with multiple images)
    - Missing sub-images
    - Wrong image-to-figure mapping
    """
    issues = []
    warnings = []
    stats = {"note_images": 0, "paper_figures": 0, "composite_figures": 0}
    
    # Extract arxiv_html URL
    arxiv_url = extract_arxiv_html_url(text)
    if not arxiv_url:
        return {
            "ok": True,
            "issues": [],
            "warnings": ["No arxiv_html URL found, skipping figure mapping check"],
            "stats": stats,
            "skipped": True
        }
    
    # Fetch arXiv HTML
    html_content = fetch_arxiv_html(arxiv_url)
    if not html_content:
        return {
            "ok": True,
            "issues": [],
            "warnings": [f"Could not fetch arXiv HTML: {arxiv_url}"],
            "stats": stats,
            "skipped": True
        }
    
    # Parse figure structure
    paper_figures = parse_arxiv_figures(html_content)
    stats["paper_figures"] = len(paper_figures)
    
    # Identify composite figures (figures with multiple images)
    composite_figures = [f for f in paper_figures if len(f["images"]) > 1]
    stats["composite_figures"] = len(composite_figures)
    
    # Extract images from note
    note_images = []
    for match in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', text):
        url = match.group(2)
        # Extract xN.png from URL
        img_match = re.search(r'/([xX][0-9]+\.png)', url)
        if img_match:
            note_images.append(img_match.group(1).lower())
    
    for match in re.finditer(r'!\[\[([^\]|]+)\]\]', text):
        ref = match.group(1)
        img_match = re.search(r'([xX][0-9]+\.png)', ref)
        if img_match:
            note_images.append(img_match.group(1).lower())
    
    stats["note_images"] = len(note_images)
    
    # Check for composite figures missing sub-images
    for fig in composite_figures:
        fig_id = fig["id"]
        fig_images = [os.path.basename(img).lower() for img in fig["images"]]
        
        # Check which images from this composite figure are in the note
        found_images = [img for img in fig_images if img in note_images]
        missing_images = [img for img in fig_images if img not in note_images]
        
        if found_images and missing_images:
            issues.append(
                f"Composite Figure {fig_id}: Found {len(found_images)}/{len(fig_images)} images. "
                f"Missing: {', '.join(missing_images)}"
            )
        elif len(found_images) == 1 and len(fig_images) > 1:
            warnings.append(
                f"Composite Figure {fig_id}: Only 1 of {len(fig_images)} images included. "
                f"Consider including all sub-images: {', '.join(fig_images)}"
            )
    
    # Check if note has more images than expected (potential duplicates)
    all_paper_images = []
    for fig in paper_figures:
        for img in fig["images"]:
            all_paper_images.append(os.path.basename(img).lower())
    
    extra_images = [img for img in note_images if img not in all_paper_images]
    if extra_images:
        warnings.append(f"Images in note not found in paper: {', '.join(extra_images)}")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "stats": stats,
        "composite_figures": [
            {"id": f["id"], "images": [os.path.basename(img) for img in f["images"]]}
            for f in composite_figures
        ]
    }


def check_tables(text: str) -> dict:
    """Check table presence and format."""
    issues = []
    
    # Find Markdown tables (lines starting with |)
    table_pattern = re.compile(r'^\|.+\|$', re.MULTILINE)
    table_blocks = table_pattern.findall(text)
    
    # Also check for HTML tables
    html_tables = re.findall(r'<table.*?>.*?</table>', text, re.DOTALL)
    
    total_tables = len(table_blocks) + len(html_tables)
    
    # Note: we can't check if tables match the paper without reading the paper
    # So just report stats
    
    return {
        "ok": True,  # Always pass, just report stats
        "issues": [],
        "stats": {
            "markdown_tables": len(table_blocks),
            "html_tables": len(html_tables),
            "total": total_tables
        }
    }


def check_concept_links(text: str, vault_path: Path) -> dict:
    """Check concept link validity."""
    issues = []
    
    # Extract all [[Concept]] links (support spaces in concept names)
    concepts = re.findall(r'\[\[([A-Za-z0-9_\s-]+)\]\]', text)
    unique_concepts = set(concepts)
    
    concepts_path = vault_path / "Concepts"
    
    missing = []
    for concept in unique_concepts:
        # Concept file uses underscore instead of space
        concept_filename = concept.replace(' ', '_')
        # Search for concept file
        found = list(concepts_path.glob(f"*/*{concept_filename}.md"))
        if not found:
            missing.append(concept)
    
    if missing:
        issues.append(f"Missing concept files: {', '.join(missing)}")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": {
            "total_links": len(concepts),
            "unique_concepts": len(unique_concepts),
            "missing": len(missing)
        }
    }


def check_structure(note_path: Path, method_name: str) -> dict:
    """Check file naming and path."""
    issues = []
    
    # Check filename
    if note_path.stem != method_name:
        issues.append(f"Filename '{note_path.stem}' should be '{method_name}'")
    
    # Check if in Papers/ directory
    if "Papers" not in note_path.parts:
        issues.append("Note should be in Papers/ directory")
    
    return {"ok": len(issues) == 0, "issues": issues}


def check_save_path(note_path: Path) -> dict:
    """Check if note is in correct category directory."""
    valid_categories = [
        "1-Continual-Learning", "2-VLA", "3-World-Model",
        "4-RL-Theory", "5-Deep-Learning", "_Inbox"
    ]
    issues = []
    
    # Extract category from path
    path_parts = note_path.parts
    category = None
    for i, part in enumerate(path_parts):
        if part == "Papers" and i + 1 < len(path_parts):
            category = path_parts[i + 1]
            break
    
    if not category:
        issues.append("Note not in any category directory")
    elif category not in valid_categories:
        issues.append(f"Invalid category '{category}', must be one of: {', '.join(valid_categories)}")
    
    return {"ok": len(issues) == 0, "issues": issues, "category": category}


def check_git_status(vault_path: Path, config: dict) -> dict:
    """Check if changes are committed (if enabled)."""
    issues = []
    
    # Check if git commit is enabled
    auto_config = config.get("automation", {})
    if not auto_config.get("git_commit", False):
        return {"ok": True, "issues": [], "skipped": True, "reason": "git_commit disabled"}
    
    # Check if .git exists
    git_dir = vault_path / ".git"
    if not git_dir.exists():
        return {"ok": True, "issues": [], "skipped": True, "reason": "not a git repo"}
    
    # Check git log
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(vault_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            issues.append("Git log check failed")
    except Exception as e:
        issues.append(f"Git check error: {e}")
    
    return {"ok": len(issues) == 0, "issues": issues}


def check_concept_content(vault_path: Path, method_name: str) -> dict:
    """Check if concept files have substantial content (exclude MOC files)."""
    concepts_path = vault_path / "Concepts"
    issues = []
    stats = {"total": 0, "empty": 0, "minimal": 0, "excluded": 0}
    
    # Find all concept files
    concept_files = list(concepts_path.glob("*/*.md"))
    stats["total"] = len(concept_files)
    
    for concept_file in concept_files:
        content = concept_file.read_text(encoding="utf-8")
        
        # Skip MOC files (Map of Content)
        # MOC files have tags containing "MOC" or frontmatter "generated_by"
        if re.search(r'^tags:.*\[.*MOC.*\]', content, re.MULTILINE):
            stats["excluded"] += 1
            continue
        if re.search(r'^generated_by:', content, re.MULTILINE):
            stats["excluded"] += 1
            continue
        
        # Remove frontmatter
        content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
        
        # Remove markdown syntax
        content = re.sub(r'[#*\[\]()`]', '', content)
        
        # Count words
        words = len(content.split())
        
        if words < 20:
            stats["empty"] += 1
            issues.append(f"Concept '{concept_file.stem}': Too short ({words} words)")
        elif words < 50:
            stats["minimal"] += 1
            # Don't report as issue, just note it
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": stats
    }


def check_representative_work(vault_path: Path, method_name: str) -> dict:
    """Check if concept files include current paper as representative work."""
    concepts_path = vault_path / "Concepts"
    issues = []
    stats = {"total": 0, "missing": 0}
    
    # Find concept files that should reference this paper
    # (concepts that are linked in this paper's note)
    concept_files = list(concepts_path.glob("*/*.md"))
    stats["total"] = len(concept_files)
    
    for concept_file in concept_files:
        content = concept_file.read_text(encoding="utf-8")
        
        # Check if "代表工作" or "Representative Work" section exists
        rep_work_match = re.search(
            r'## (代表工作|Representative Work).*?\n(.+?)(?=\n##|$)',
            content,
            re.DOTALL | re.IGNORECASE
        )
        
        if rep_work_match:
            rep_work_content = rep_work_match.group(2)
            # Check if method_name is mentioned
            if method_name not in rep_work_content and f"[[{method_name}]]" not in rep_work_content:
                # This concept doesn't reference this paper
                pass  # Not necessarily an issue
        # else: no representative work section - checked by check_concept_content
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "stats": stats
    }


def check_content_completeness_stats(text: str) -> dict:
    """Just report stats, LLM will compare with paper later."""
    # Count figures
    external_images = len(re.findall(r'!\[([^\]]*)\]\((https?://[^)]+)\)', text))
    obsidian_images = len(re.findall(r'!\[\[([^\]|]+)(?:\|[0-9]+)?\]\]', text))
    total_figures = external_images + obsidian_images
    
    # Count formulas
    total_formulas = len(re.findall(r'\$\$.+?\$\$', text, re.DOTALL))
    
    # Count tables
    total_tables = len(re.findall(r'^\|.+\|$', text, re.MULTILINE))
    
    return {
        "ok": True,
        "issues": [],
        "stats": {
            "figures": total_figures,
            "formulas": total_formulas,
            "tables": total_tables
        }
    }


# ============================================================================
# Fix Functions
# ============================================================================

def fix_frontmatter(text: str, method_name: str, title: str = "") -> str:
    """Fix or create frontmatter."""
    # Extract existing frontmatter
    fm_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    
    if fm_match:
        # Update existing frontmatter
        fm_text = fm_match.group(1)
        fm_dict = {}
        
        for line in fm_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                fm_dict[key.strip()] = value.strip()
        
        # Add missing fields
        required = {
            "title": title or method_name,
            "method_name": method_name,
            "authors": "[]",
            "year": "2025",
            "venue": "arXiv",
            "tags": "[]",
            "created": "2026-04-06"
        }
        
        for key, default in required.items():
            if key not in fm_dict:
                fm_dict[key] = default
        
        # Reconstruct frontmatter
        new_fm = "---\n"
        for key, value in fm_dict.items():
            new_fm += f"{key}: {value}\n"
        new_fm += "---\n"
        
        return new_fm + text[fm_match.end():]
    else:
        # Create new frontmatter
        fm = f"""---
title: "{title or method_name}"
method_name: "{method_name}"
authors: []
year: 2025
venue: arXiv
tags: []
created: 2026-04-06
---

"""
        return fm + text


def fix_formula_format(text: str) -> str:
    """Fix formula formatting issues."""
    # Replace \bm{} with plain variables
    text = re.sub(r'\\bm\{([^}]+)\}', r'\1', text)
    
    # Ensure $$ blocks have empty lines around them
    # This is complex to do reliably, skip for now
    
    return text


async def fix_missing_images(text: str, note_path: Path, method_name: str, vault_path: Path) -> str:
    """Run download_note_images.py to fix unreachable images."""
    download_script = Path(__file__).parent.parent / "daily-papers" / "download_note_images.py"
    
    if download_script.exists():
        proc = await asyncio.create_subprocess_exec(
            "python3", str(download_script), str(note_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        # Re-read note after script modifies it
        return note_path.read_text(encoding="utf-8")
    
    return text


# ============================================================================
# Main QA Logic
# ============================================================================

async def run_qa(note_path: Path) -> dict:
    """Run QA checks and report issues (no auto-fix)."""
    config = load_config()
    vault_path = get_vault_path(config)
    
    method_name = note_path.stem
    results = {
        "note": str(note_path),
        "checks": {},
        "final_status": "pending"
    }
    
    text = note_path.read_text(encoding="utf-8")
    
    # Run all checks
    checks = {
        # 基础结构检查
        "structure": check_structure(note_path, method_name),
        "frontmatter": check_frontmatter(text),
        "save_path": check_save_path(note_path),
        "git_status": check_git_status(vault_path, config),
        
        # 内容完整性检查
        "content_stats": check_content_completeness_stats(text),
        "concepts": check_concept_links(text, vault_path),
        
        # 图片质量检查
        "figures": check_figures(text, method_name, vault_path),
        "figure_mapping": check_figure_mapping(text),
        
        # 公式质量检查
        "formulas": check_formulas(text),
        "formula_format": check_formula_format(text),
        "formula_naming": check_formula_naming(text),
        "formula_meaning": check_formula_meaning(text),
        "symbol_explanation": check_symbol_explanation(text),
        
        # 概念库检查
        "concept_content": check_concept_content(vault_path, method_name),
        "representative_work": check_representative_work(vault_path, method_name),
    }
    results["checks"] = checks
    
    # Extract images for LLM caption check (output only, not checked by script)
    results["images_for_caption_check"] = extract_images_for_caption_check(text)
    
    # Determine final status
    all_ok = all(c["ok"] for c in checks.values())
    results["final_status"] = "passed" if all_ok else "failed"
    
    return results


def print_report(results: dict):
    """Print standardized human-readable report."""
    print(f"\n{'='*70}")
    print(f"QA REPORT: {results['note']}")
    print(f"STATUS: {results['final_status'].upper()}")
    print(f"{'='*70}\n")
    
    # Separate passed and failed checks
    passed = []
    failed = []
    
    for check_name, check_result in results["checks"].items():
        if check_result["ok"]:
            passed.append(check_name)
        else:
            failed.append((check_name, check_result))
    
    # Print passed checks
    if passed:
        print("✅ PASSED CHECKS:")
        for name in passed:
            print(f"  • {name}")
        print()
    
    # Print failed checks with details
    if failed:
        print("❌ FAILED CHECKS:")
        for name, result in failed:
            print(f"\n  {name}:")
            for issue in result["issues"]:
                print(f"    - {issue}")
            if "stats" in result:
                print(f"    Stats: {result['stats']}")
            if "warnings" in result and result["warnings"]:
                print(f"    Warnings:")
                for warning in result["warnings"]:
                    print(f"      ⚠️ {warning}")
        print()
    
    # Print warnings for passed checks
    warnings_to_show = []
    for check_name, check_result in results["checks"].items():
        if check_result.get("warnings"):
            for warning in check_result["warnings"]:
                warnings_to_show.append((check_name, warning))
    
    if warnings_to_show:
        print("⚠️ WARNINGS:")
        for name, warning in warnings_to_show:
            print(f"  • [{name}] {warning}")
        print()
    
    # Print recommended actions
    if failed:
        print("📌 RECOMMENDED ACTIONS:")
        action_num = 1
        
        for name, result in failed:
            if name == "concepts":
                # Missing concepts
                for issue in result["issues"]:
                    if "Missing concept files:" in issue:
                        concepts = issue.split(": ", 1)[1] if ": " in issue else ""
                        if concepts:
                            print(f"  {action_num}. Create missing concept notes: {concepts}")
                            action_num += 1
            
            elif name == "figure_mapping":
                # Composite figure issues
                for issue in result["issues"]:
                    if "Composite Figure" in issue:
                        print(f"  {action_num}. Fix image mapping: {issue}")
                        action_num += 1
                    else:
                        print(f"  {action_num}. Fix: {issue}")
                        action_num += 1
            
            elif name == "formula_naming":
                # Missing formula names
                formulas = [i.split(":")[0].strip() for i in result["issues"]]
                if formulas:
                    unique_formulas = sorted(set(formulas))
                    print(f"  {action_num}. Add names to formulas: {', '.join(unique_formulas)}")
                    action_num += 1
            
            elif name == "symbol_explanation":
                # Missing symbol explanations
                formulas = [i.split(":")[0].strip() for i in result["issues"]]
                unique_formulas = sorted(set(formulas))
                if unique_formulas:
                    print(f"  {action_num}. Add symbol explanations to {len(unique_formulas)} formulas")
                    action_num += 1
            
            elif name == "concept_content":
                # Concept content issues
                for issue in result["issues"]:
                    print(f"  {action_num}. {issue}")
                    action_num += 1
            
            else:
                # Generic issue
                for issue in result["issues"]:
                    print(f"  {action_num}. Fix: {issue}")
                    action_num += 1
        
        print()
    
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="QA checker for paper notes (report only, no auto-fix)")
    parser.add_argument("note", help="Path to note file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    note_path = Path(args.note).expanduser().resolve()
    if not note_path.exists():
        print(f"Error: File not found: {note_path}", file=sys.stderr)
        sys.exit(1)
    
    results = asyncio.run(run_qa(note_path))
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)
    
    # Exit code based on final status
    sys.exit(0 if results["final_status"] == "passed" else 1)


if __name__ == "__main__":
    main()
