#!/usr/bin/env python3
"""
List recent paper notes that need image checking.

Usage:
    python3 list_need_check.py --vault /path/to/vault --limit 10

Output: List of notes that need checking, sorted by creation date (newest first)
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime


def get_recent_notes(vault_path: Path, limit: int = 10) -> list:
    """Get recently created paper notes, newest first."""
    notes_dir = vault_path / "Papers"
    if not notes_dir.exists():
        return []
    
    # Skip patterns (directory MOCs, index files)
    skip_patterns = {"Papers", "1-Continual-Learning", "2-VLA", "3-World-Model", 
                     "4-RL-Theory", "5-Deep-Learning", "6-LNN", "7-Robotics",
                     "_Inbox", "SearchResults", "DailyPapers"}
    
    notes = []
    for md in notes_dir.rglob("*.md"):
        if md.name.startswith("_") or md.name.startswith("."):
            continue
        # Skip directory MOC files
        if md.stem in skip_patterns:
            continue
        stat = md.stat()
        notes.append({
            "path": md,
            "name": md.stem,
            "created": datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "relative": md.relative_to(vault_path),
        })
    
    notes.sort(key=lambda x: x["created"], reverse=True)
    return notes[:limit]


def needs_check(vault_path: Path, note_name: str) -> bool:
    """Check if a note needs image verification."""
    check_file = vault_path / "CheckResults" / f"{note_name}.md"
    if not check_file.exists():
        return True
    
    # Check if note was modified after last check
    note_files = list((vault_path / "Papers").rglob(f"{note_name}.md"))
    if not note_files:
        return False
    
    note_mtime = note_files[0].stat().st_mtime
    check_mtime = check_file.stat().st_mtime
    return note_mtime > check_mtime


def main():
    parser = argparse.ArgumentParser(description="List notes needing image check")
    parser.add_argument("--vault", help="Vault path")
    parser.add_argument("--limit", type=int, default=10, help="Max notes to list")
    parser.add_argument("--all", action="store_true", help="Show all, not just unchecked")
    
    args = parser.parse_args()
    
    vault_path = Path(args.vault) if args.vault else Path("/root/.openclaw/shared/ObsidianVault")
    
    recent = get_recent_notes(vault_path, args.limit)
    
    if not recent:
        print("No paper notes found.")
        return
    
    unchecked = []
    checked = []
    
    for note in recent:
        if needs_check(vault_path, note["name"]):
            unchecked.append(note)
        else:
            checked.append(note)
    
    # Always show unchecked first
    if unchecked:
        print(f"## ⚠️ 需要检查 ({len(unchecked)} 篇)\n")
        for i, note in enumerate(unchecked, 1):
            age = (datetime.now() - note["created"]).days
            print(f"  {i}. **{note['name']}** — 创建于 {note['created'].strftime('%Y-%m-%d')} ({age}天前)")
            print(f"     路径: `{note['relative']}`")
    
    if args.all and checked:
        print(f"\n## ✅ 已检查 ({len(checked)} 篇)\n")
        for note in checked:
            print(f"  - {note['name']} ({note['created'].strftime('%Y-%m-%d')})")
    
    print(f"\n总计: {len(unchecked)} 待检查, {len(checked)} 已检查")


if __name__ == "__main__":
    main()
