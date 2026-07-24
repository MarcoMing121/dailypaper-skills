#!/usr/bin/env python3
"""
Batch image checker — process multiple paper notes in one run.

Usage:
    # Check specific papers by name
    python3 batch_check.py --papers FastSAC Gallant Pi05

    # Check papers from a file list (one name per line)
    python3 batch_check.py --from-file papers_list.txt

    # Check all unchecked recent papers
    python3 batch_check.py --unchecked --limit 20

    # Dry run — only list what would be checked
    python3 batch_check.py --unchecked --limit 20 --dry-run

Output:
    - Per-paper results printed to stdout
    - Summary report written to {VAULT_PATH}/CheckResults/batch_report.md
"""

import argparse
import json
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


VAULT_PATH = Path("/root/.openclaw/shared/ObsidianVault")
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"


def find_note(vault: Path, name: str) -> Path | None:
    """Find a paper note by method name."""
    candidates = list(vault.glob(f"Papers/**/{name}.md"))
    if candidates:
        return candidates[0]
    return None


def run_check(note_path: Path, vault: Path) -> dict:
    """Run image check on a single paper note. Returns result dict."""
    method_name = note_path.stem

    result = {
        "name": method_name,
        "note_path": str(note_path.relative_to(vault)),
        "status": "unknown",
        "checks": {},
        "errors": [],
    }

    # Run check_images.py (it handles legend auto-generation internally)
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_images.py"),
             "--note", str(note_path),
             "--vault", str(vault),
             "--json"],
            capture_output=True, text=True, timeout=120
        )
        if proc.stdout.strip():
            try:
                check_data = json.loads(proc.stdout.strip())
                result["checks"]["check_images"] = check_data
                # Determine status from check_images output
                if check_data.get("status") == "passed":
                    result["status"] = "checked"
                else:
                    result["status"] = "failed"
                    result["failures"] = check_data.get("issues", [])
            except json.JSONDecodeError:
                result["checks"]["check_images_output"] = proc.stdout.strip()[-2000:]
                result["status"] = "checked"
        if proc.returncode != 0 and proc.stderr.strip():
            result["errors"].append(f"check_images.py stderr: {proc.stderr.strip()[-500:]}")
    except subprocess.TimeoutExpired:
        result["errors"].append("check_images.py timed out (120s)")
        result["status"] = "error"
    except Exception as e:
        result["errors"].append(f"check_images.py error: {e}")
        result["status"] = "error"

    if result["errors"] and result["status"] != "failed":
        result["status"] = "error"

    return result


def get_unchecked_papers(vault: Path, limit: int) -> list[str]:
    """Get names of recently created papers that haven't been checked."""
    check_results_dir = vault / "CheckResults"
    checked = set()
    if check_results_dir.exists():
        for f in check_results_dir.glob("*.md"):
            if f.name != "batch_report.md":
                checked.add(f.stem)

    notes_dir = vault / "Papers"
    if not notes_dir.exists():
        return []

    papers = []
    for md in notes_dir.rglob("*.md"):
        if md.name.startswith("_") or md.name.startswith("."):
            continue
        if md.stem in checked:
            continue
        papers.append({
            "name": md.stem,
            "created": datetime.fromtimestamp(md.stat().st_ctime),
        })

    papers.sort(key=lambda x: x["created"], reverse=True)
    return [p["name"] for p in papers[:limit]]


def write_batch_report(results: list[dict], vault: Path):
    """Write a summary report to CheckResults/batch_report.md."""
    report_path = vault / "CheckResults" / "batch_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(results)
    checked = sum(1 for r in results if r["status"] == "checked")
    failed = sum(1 for r in results if r["status"] == "failed")
    errors = sum(1 for r in results if r["status"] == "error")

    lines = [
        f"# Batch Image Check Report",
        f"",
        f"**Date**: {now}",
        f"**Total**: {total} papers",
        f"**Checked**: {checked}",
        f"**Failed**: {failed}",
        f"**Errors**: {errors}",
        f"",
        f"## Results",
        f"",
        f"| Paper | Status | Details |",
        f"|-------|--------|---------|",
    ]

    for r in results:
        status_emoji = {
            "checked": "✅",
            "failed": "⚠️",
            "error": "❌",
        }.get(r["status"], "❓")
        errors = f" ({'; '.join(r['errors'][:2])})" if r["errors"] else ""
        failures = ""
        if r.get("failures"):
            failures = f" [{len(r['failures'])} issues]"
        lines.append(f"| {r['name']} | {status_emoji} {r['status']} | {errors}{failures} |")

    lines.append("")
    lines.append(f"*Generated by image-check batch runner*")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Batch image checker")
    parser.add_argument("--papers", nargs="+", help="Specific paper names to check")
    parser.add_argument("--from-file", help="File with paper names (one per line)")
    parser.add_argument("--unchecked", action="store_true", help="Check all unchecked recent papers")
    parser.add_argument("--limit", type=int, default=10, help="Max papers for --unchecked mode")
    parser.add_argument("--vault", default=str(VAULT_PATH), help="Vault path")
    parser.add_argument("--dry-run", action="store_true", help="Only list papers, don't check")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()
    vault = Path(args.vault)

    # Collect paper names
    paper_names = []
    if args.papers:
        paper_names = args.papers
    elif args.from_file:
        p = Path(args.from_file)
        if not p.exists():
            print(f"❌ File not found: {args.from_file}", file=sys.stderr)
            sys.exit(1)
        paper_names = [line.strip() for line in p.read_text().splitlines() if line.strip()]
    elif args.unchecked:
        paper_names = get_unchecked_papers(vault, args.limit)
    else:
        # Default: check recent unchecked papers
        paper_names = get_unchecked_papers(vault, args.limit)

    if not paper_names:
        print("✅ No papers to check!")
        return

    print(f"📋 Papers to check: {len(paper_names)}")
    for i, name in enumerate(paper_names, 1):
        print(f"  {i}. {name}")

    if args.dry_run:
        print("\n🔍 Dry run — not running checks.")
        return

    # Resolve note paths
    papers_to_check = []
    for name in paper_names:
        note_path = find_note(vault, name)
        if note_path:
            papers_to_check.append((name, note_path))
        else:
            print(f"⚠️  Note not found: {name}")

    if not papers_to_check:
        print("❌ No valid notes found to check.")
        sys.exit(1)

    # Run checks
    print(f"\n🔄 Running checks on {len(papers_to_check)} papers...\n")
    results = []

    if args.parallel > 1:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_check, note_path, vault): name
                for name, note_path in papers_to_check
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    status_emoji = "✅" if result["status"] == "checked" else "❌"
                    print(f"  {status_emoji} {name}: {result['status']}")
                except Exception as e:
                    results.append({"name": name, "status": "error", "checks": {}, "errors": [str(e)], "note_path": ""})
                    print(f"  ❌ {name}: error — {e}")
    else:
        for i, (name, note_path) in enumerate(papers_to_check, 1):
            print(f"  [{i}/{len(papers_to_check)}] {name}...", end=" ", flush=True)
            result = run_check(note_path, vault)
            results.append(result)
            status_emoji = "✅" if result["status"] == "checked" else "❌"
            print(f"{status_emoji} {result['status']}")

    # Write report
    report_path = write_batch_report(results, vault)
    print(f"\n📄 Report: {report_path.relative_to(vault)}")

    # Summary
    checked = sum(1 for r in results if r["status"] == "checked")
    failed = sum(1 for r in results if r["status"] == "failed")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"\n📊 Summary: {checked} checked, {failed} failed, {errors} errors")

    # JSON output
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
