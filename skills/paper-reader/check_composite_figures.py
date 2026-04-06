#!/usr/bin/env python3
"""Check for composite figures in arXiv HTML.

Usage:
    python3 check_composite_figures.py <arxiv_id_or_url>

Output (JSON):
    {
      "paper_figures": [
        {"id": "S4.F6", "images": ["x8.png", "x9.png", "x10.png", "x11.png"], "is_composite": true}
      ],
      "composite_figures": [...],
      "stats": {"total": 30, "composite": 9}
    }
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser


class ArxivFigureParser(HTMLParser):
    """Parse arXiv HTML to extract figure structure."""
    
    def __init__(self):
        super().__init__()
        self.figures = []
        self.current_figure = None
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
        
        elif tag == "img" and self.current_figure:
            src = attrs_dict.get("src", "")
            if src:
                self.current_figure["images"].append(os.path.basename(src))
    
    def handle_endtag(self, tag):
        if tag == "figure":
            if self.depth == 1 and self.current_figure:
                self.figures.append(self.current_figure)
                self.current_figure = None
            self.depth -= 1


def fetch_arxiv_html(arxiv_id: str) -> str:
    """Fetch arXiv HTML content."""
    # Normalize arxiv_id
    arxiv_id = arxiv_id.strip()
    if arxiv_id.startswith("http"):
        # Extract ID from URL
        match = re.search(r'(\d{4}\.\d{4,5})', arxiv_id)
        if match:
            arxiv_id = match.group(1)
    
    url = f"https://arxiv.org/html/{arxiv_id}"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; PaperReader/1.0)"}
    )
    
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_figures(html_content: str) -> list[dict]:
    """Parse arXiv HTML to extract figure structure."""
    parser = ArxivFigureParser()
    parser.feed(html_content)
    return parser.figures


def main():
    parser = argparse.ArgumentParser(description="Check composite figures in arXiv HTML")
    parser.add_argument("arxiv_id", help="arXiv ID or URL (e.g., 2603.19312)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    try:
        html_content = fetch_arxiv_html(args.arxiv_id)
        figures = parse_figures(html_content)
        
        # Mark composite figures
        for fig in figures:
            fig["is_composite"] = len(fig["images"]) > 1
        
        composite_figures = [f for f in figures if f["is_composite"]]
        
        result = {
            "paper_figures": figures,
            "composite_figures": composite_figures,
            "stats": {
                "total": len(figures),
                "composite": len(composite_figures)
            }
        }
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"COMPOSITE FIGURE CHECK: {args.arxiv_id}")
            print(f"{'='*60}\n")
            
            print(f"Total Figures: {result['stats']['total']}")
            print(f"Composite Figures: {result['stats']['composite']}\n")
            
            if composite_figures:
                print("⚠️ COMPOSITE FIGURES (must include ALL sub-images):\n")
                for fig in composite_figures:
                    print(f"  Figure {fig['id']}:")
                    print(f"    Images: {', '.join(fig['images'])}")
                    print()
            else:
                print("✅ No composite figures found.\n")
            
            print(f"{'='*60}\n")
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
