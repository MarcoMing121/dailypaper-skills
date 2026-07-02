#!/usr/bin/env python3
"""
Generate image legend file for a paper note.

Usage:
    python3 generate_legend.py --note /path/to/note.md --assets /path/to/assets/MethodName --output /path/to/assets/MethodName/legend.md

Or with arXiv HTML:
    python3 generate_legend.py --arxiv 2506.09366 --assets /path/to/assets/MethodName --output /path/to/assets/MethodName/legend.md
"""

import argparse
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime


def extract_figures_from_html(arxiv_id: str) -> list:
    """Extract figures and captions from arXiv HTML."""
    url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30
        )
        html = result.stdout
    except Exception as e:
        print(f"Warning: Failed to fetch HTML: {e}")
        return []
    
    figures = []
    # Find figure elements - capture the whole figure block
    fig_pattern = re.compile(r'<figure[^>]*>(.*?)</figure>', re.DOTALL)
    img_pattern = re.compile(r'<img[^>]*src=["\']([^"\']+)["\']', re.DOTALL)
    caption_pattern = re.compile(r'<figcaption[^>]*>(.*?)</figcaption>', re.DOTALL)
    
    for i, fig_match in enumerate(fig_pattern.finditer(html), 1):
        fig_html = fig_match.group(1)
        
        # Extract image URL
        img_match = img_pattern.search(fig_html)
        img_url = img_match.group(1) if img_match else ""
        if img_url and not img_url.startswith("http"):
            img_url = f"https://arxiv.org/html/{arxiv_id}/{img_url}"
        
        # Extract filename from URL as the canonical ID
        # e.g., https://arxiv.org/html/2506.09366/x1.png -> x1
        filename = Path(img_url).stem if img_url else f"fig{i}"
        ext = Path(img_url).suffix if img_url else ".png"
        
        # Extract caption
        cap_match = caption_pattern.search(fig_html)
        caption = ""
        if cap_match:
            # Strip HTML tags
            caption = re.sub(r'<[^>]+>', '', cap_match.group(1)).strip()
        
        figures.append({
            "id": filename,  # Use filename stem as ID (e.g., x1, x2)
            "source": "external",
            "link": f"![]({img_url})",
            "caption": caption[:200] if caption else "N/A",  # Truncate long captions
            "filename": f"{filename}{ext}",
        })
    
    return figures


def extract_figures_from_note(note_path: Path) -> list:
    """Extract figure references from a paper note."""
    text = note_path.read_text(encoding="utf-8")
    figures = []
    
    # Match Obsidian wikilinks: ![[MethodName/fig1.png]] or ![[fig1.png|500]]
    wikilink_pattern = re.compile(r'!\[\[([^\]|]+?)(?:\|(\d+))?\]\]')
    for match in wikilink_pattern.finditer(text):
        link = match.group(1)
        figures.append({
            "id": Path(link).stem,
            "source": "local",
            "link": f"![[{link}]]",
            "caption": "",  # Will be filled from legend if available
        })
    
    # Match external markdown images: ![alt](url)
    ext_pattern = re.compile(r'!\[([^\]]*)\]\((https?://[^)]+)\)')
    for match in ext_pattern.finditer(text):
        alt = match.group(1)
        url = match.group(2)
        figures.append({
            "id": alt or url.split("/")[-1].split(".")[0],
            "source": "external",
            "link": f"![{alt}]({url})",
            "caption": "",
        })
    
    return figures


def extract_figures_from_assets(assets_dir: Path) -> list:
    """List actual image files in assets directory."""
    figures = []
    if not assets_dir.exists():
        return figures
    
    for img_file in sorted(assets_dir.iterdir()):
        if img_file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
            figures.append({
                "id": img_file.stem,
                "source": "local",
                "link": f"![[{assets_dir.name}/{img_file.name}]]",
                "caption": "",
                "file": str(img_file),
                "size": img_file.stat().st_size,
            })
    
    return figures


def generate_legend_md(paper_title: str, method_name: str, figures: list, used_ids: set) -> str:
    """Generate the legend markdown content."""
    lines = [
        f"# Image Legends: {paper_title}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "| ID | Source | Link | Legend | Used in Note |",
        "|----|--------|------|--------|--------------|",
    ]
    
    for fig in figures:
        used = "✅" if fig["id"] in used_ids else "❌"
        caption = fig.get("caption", "") or "待补充"
        # Escape pipe characters in caption
        caption = caption.replace("|", "\\|")
        lines.append(f"| {fig['id']} | {fig['source']} | {fig['link']} | {caption} | {used} |")
    
    lines.extend([
        "",
        "---",
        "",
        f"Total: {len(figures)} images | Used: {len(used_ids)} | Unused: {len(figures) - len(used_ids)}",
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate image legend for paper note")
    parser.add_argument("--note", help="Path to paper note .md file")
    parser.add_argument("--arxiv", help="arXiv ID for HTML extraction")
    parser.add_argument("--assets", required=True, help="Assets directory path")
    parser.add_argument("--output", help="Output legend.md path (default: assets/legend.md)")
    parser.add_argument("--title", help="Paper title (extracted from note if not provided)")
    parser.add_argument("--method", help="Method name (extracted from filename if not provided)")
    
    args = parser.parse_args()
    
    assets_dir = Path(args.assets)
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = Path(args.output) if args.output else assets_dir / "legend.md"
    
    # Extract method name
    method_name = args.method
    if not method_name and args.note:
        method_name = Path(args.note).stem
    if not method_name:
        method_name = assets_dir.name
    
    # Extract title
    title = args.title
    if not title and args.note:
        note_text = Path(args.note).read_text(encoding="utf-8")
        title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', note_text, re.MULTILINE)
        title = title_match.group(1) if title_match else method_name
    
    # Collect figures from all sources
    all_figures = {}
    
    # From arXiv HTML (best captions)
    if args.arxiv:
        html_figures = extract_figures_from_html(args.arxiv)
        for fig in html_figures:
            all_figures[fig["id"]] = fig
    
    # From note references
    if args.note:
        note_figures = extract_figures_from_note(Path(args.note))
        for fig in note_figures:
            if fig["id"] not in all_figures:
                all_figures[fig["id"]] = fig
            else:
                # Update link if note uses local version
                all_figures[fig["id"]]["link"] = fig["link"]
    
    # From actual files
    file_figures = extract_figures_from_assets(assets_dir)
    for fig in file_figures:
        if fig["id"] not in all_figures:
            all_figures[fig["id"]] = fig
    
    # Determine which are used in note
    used_ids = set()
    if args.note:
        note_text = Path(args.note).read_text(encoding="utf-8")
        for fig_id, fig_info in all_figures.items():
            # Check by filename stem
            if fig_id in note_text:
                used_ids.add(fig_id)
                continue
            # Check by URL (for external images)
            link = fig_info.get("link", "")
            url_match = re.search(r'\((https?://[^)]+)\)', link)
            if url_match and url_match.group(1) in note_text:
                used_ids.add(fig_id)
                continue
            # Check by filename
            filename = fig_info.get("filename", "")
            if filename and filename in note_text:
                used_ids.add(fig_id)
    
    # Generate legend
    figures_list = sorted(all_figures.values(), key=lambda x: x["id"])
    legend_content = generate_legend_md(title, method_name, figures_list, used_ids)
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(legend_content, encoding="utf-8")
    print(f"✅ Legend written to: {output_path}")
    print(f"   Total figures: {len(figures_list)}")
    print(f"   Used in note: {len(used_ids)}")


if __name__ == "__main__":
    main()
