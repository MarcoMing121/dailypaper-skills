#!/usr/bin/env python3
"""
Check image consistency: note references ↔ legend ↔ actual files.

Usage:
    python3 check_images.py --note /path/to/note.md --vault /path/to/vault

Output: JSON report + human-readable summary
"""

import argparse
import re
import json
import sys
from pathlib import Path
from datetime import datetime


def load_config():
    """Load user config for vault path."""
    config_path = Path(__file__).parent.parent.parent / "_shared" / "user_config.py"
    if config_path.exists():
        sys.path.insert(0, str(config_path.parent))
        from user_config import obsidian_vault_path
        return {"vault_path": str(obsidian_vault_path())}
    return {}


def extract_note_images(text: str) -> dict:
    """Extract all image references from a paper note."""
    images = {"local": [], "external": []}
    
    # Obsidian wikilinks: ![[MethodName/fig1.png]] or ![[fig1.png|500]]
    for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|(\d+))?\]\]', text):
        link = match.group(1)
        images["local"].append({
            "link": link,
            "filename": Path(link).name,
            "stem": Path(link).stem,
        })
    
    # External markdown images: ![alt](url)
    for match in re.finditer(r'!\[([^\]]*)\]\((https?://[^)]+)\)', text):
        images["external"].append({
            "alt": match.group(1),
            "url": match.group(2),
            "stem": match.group(1) or match.group(2).split("/")[-1].split(".")[0],
        })
    
    return images


def load_legend(legend_path: Path) -> list:
    """Parse legend.md file."""
    if not legend_path.exists():
        return []
    
    text = legend_path.read_text(encoding="utf-8")
    legends = []
    
    for line in text.split("\n"):
        if line.startswith("|") and not line.startswith("|--") and "ID" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]  # Remove empty first/last
            if len(parts) >= 4:
                legends.append({
                    "id": parts[0],
                    "source": parts[1],
                    "link": parts[2],
                    "legend": parts[3],
                    "used": parts[4] == "✅" if len(parts) > 4 else False,
                })
    
    return legends


def check_images(note_path: Path, vault_path: Path) -> dict:
    """Run all image checks."""
    method_name = note_path.stem
    
    # Determine assets directory
    # Try to find it in the note text
    note_text = note_path.read_text(encoding="utf-8")
    
    # Look for assets path patterns
    assets_candidates = [
        vault_path / "assets" / method_name,
    ]
    
    # Also check from image links in note
    for match in re.finditer(r'!\[\[([^\]|]+)/', note_text):
        dir_name = match.group(1)
        assets_candidates.append(vault_path / "assets" / dir_name)
    
    assets_dir = None
    for candidate in assets_candidates:
        if candidate.exists():
            assets_dir = candidate
            break
    
    if not assets_dir:
        assets_dir = vault_path / "assets" / method_name
    
    legend_path = assets_dir / "legend.md"
    
    # Collect data
    note_images = extract_note_images(note_text)
    legends = load_legend(legend_path)
    
    # Actual files in assets
    actual_files = {}
    if assets_dir.exists():
        for f in assets_dir.iterdir():
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                actual_files[f.stem] = {
                    "path": str(f),
                    "size": f.stat().st_size,
                    "name": f.name,
                }
    
    # Run checks
    checks = {}
    issues = []
    
    # Check 1: Legend exists
    checks["legend_exists"] = {
        "ok": legend_path.exists(),
        "detail": f"Legend file: {legend_path}" if legend_path.exists() else "Legend file missing",
    }
    if not legend_path.exists():
        issues.append("Legend file missing")
    
    # Check 2: Local files exist
    local_stems = {img["stem"] for img in note_images["local"]}
    missing_files = []
    for stem in local_stems:
        if stem not in actual_files:
            missing_files.append(stem)
    checks["local_files_exist"] = {
        "ok": len(missing_files) == 0,
        "detail": f"Missing: {missing_files}" if missing_files else "All local files exist",
        "missing": missing_files,
    }
    if missing_files:
        issues.append(f"Missing local files: {missing_files}")
    
    # Check 3: File sizes
    small_files = []
    for stem, info in actual_files.items():
        if info["size"] < 10240:  # < 10KB
            small_files.append(f"{info['name']} ({info['size']} bytes)")
    checks["file_sizes"] = {
        "ok": len(small_files) == 0,
        "detail": f"Too small: {small_files}" if small_files else "All files > 10KB",
    }
    if small_files:
        issues.append(f"Small files: {small_files}")
    
    # Check 4: Legend completeness
    if legends:
        no_legend = [l for l in legends if not l["legend"] or l["legend"] == "待补充"]
        checks["legend_complete"] = {
            "ok": len(no_legend) == 0,
            "detail": f"Missing legends: {[l['id'] for l in no_legend]}" if no_legend else "All legends filled",
        }
    else:
        checks["legend_complete"] = {
            "ok": False,
            "detail": "No legend file to check",
        }
    
    # Check 5: Note references match legend
    if legends:
        legend_ids = {l["id"] for l in legends}
        note_stems = {img["stem"] for img in note_images["local"] + note_images["external"]}
        unmatched = note_stems - legend_ids
        checks["reference_match"] = {
            "ok": len(unmatched) == 0,
            "detail": f"Not in legend: {unmatched}" if unmatched else "All references match",
        }
    else:
        checks["reference_match"] = {
            "ok": False,
            "detail": "No legend to compare against",
        }
    
    # Stats
    stats = {
        "note_local_images": len(note_images["local"]),
        "note_external_images": len(note_images["external"]),
        "actual_files": len(actual_files),
        "legend_entries": len(legends),
        "total_note_refs": len(note_images["local"]) + len(note_images["external"]),
    }
    
    all_ok = all(c["ok"] for c in checks.values())
    
    return {
        "method": method_name,
        "note": str(note_path),
        "assets_dir": str(assets_dir),
        "legend_path": str(legend_path),
        "checks": checks,
        "stats": stats,
        "issues": issues,
        "status": "passed" if all_ok else "failed",
    }


def write_check_result(vault_path: Path, result: dict):
    """Write check result to CheckResults/ directory."""
    check_dir = vault_path / "CheckResults"
    check_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = check_dir / f"{result['method']}.md"
    
    lines = [
        "---",
        f'title: "Image Check: {result["method"]}"',
        f'date: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'status: {result["status"]}',
        f'paper_path: {result["note"]}',
        "---",
        "",
        f'# Image Check Report: {result["method"]}',
        "",
        "## 检查结果",
        "",
        "| 检查项 | 状态 | 详情 |",
        "|--------|------|------|",
    ]
    
    for check_name, check_result in result["checks"].items():
        status = "✅" if check_result["ok"] else "❌"
        lines.append(f"| {check_name} | {status} | {check_result['detail']} |")
    
    lines.extend([
        "",
        "## 统计",
        "",
        f"- 笔记中本地图片引用: {result['stats']['note_local_images']}",
        f"- 笔记中外链图片引用: {result['stats']['note_external_images']}",
        f"- Assets 目录实际文件: {result['stats']['actual_files']}",
        f"- Legend 条目数: {result['stats']['legend_entries']}",
        "",
    ])
    
    if result["issues"]:
        lines.extend([
            "## ⚠️ 需要修复",
            "",
        ])
        for issue in result["issues"]:
            lines.append(f"- {issue}")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def print_report(result: dict):
    """Print human-readable report."""
    print(f"\n{'='*60}")
    print(f"Image Check: {result['method']}")
    print(f"Status: {result['status'].upper()}")
    print(f"{'='*60}\n")
    
    for name, check in result["checks"].items():
        icon = "✅" if check["ok"] else "❌"
        print(f"  {icon} {name}: {check['detail']}")
    
    print(f"\nStats: {result['stats']['total_note_refs']} refs, "
          f"{result['stats']['actual_files']} files, "
          f"{result['stats']['legend_entries']} legends")


def main():
    parser = argparse.ArgumentParser(description="Check image consistency")
    parser.add_argument("--note", required=True, help="Path to paper note .md")
    parser.add_argument("--vault", help="Vault path (auto-detected if not provided)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--write", action="store_true", help="Write result to CheckResults/")
    
    args = parser.parse_args()
    
    vault_path = Path(args.vault) if args.vault else None
    if not vault_path:
        config = load_config()
        vault_path = Path(config.get("vault_path", "/root/.openclaw/shared/ObsidianVault"))
    
    note_path = Path(args.note)
    if not note_path.exists():
        print(f"Error: Note not found: {note_path}")
        sys.exit(1)
    
    result = check_images(note_path, vault_path)
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    
    if args.write:
        output = write_check_result(vault_path, result)
        print(f"\n📄 Report written to: {output}")
    
    sys.exit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
