"""CLI: python -m ishikawa --incident checkout-latency [--repo PATH] [--out report.md]"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from .render import to_markdown  # noqa: E402
from .runner import investigate  # noqa: E402
from .schema import RCAReport  # noqa: E402
from .tools import list_incidents  # noqa: E402

DIM, BOLD, RED, GREEN, RESET = "\033[2m", "\033[1m", "\033[31m", "\033[32m", "\033[0m"


async def _run(args: argparse.Namespace) -> int:
    report, elapsed = None, None
    print(f"{BOLD}🐟 Ishikawa investigating '{args.incident}'{RESET}\n")
    if args.repo:
        print(f"{RED}note:{RESET} --repo makes deploys/diffs live, but logs, metrics, config, DB and traffic still come "
              f"from fixture '{args.incident}'. Treat the result as a demo of the pipeline on your history.\n")
    async for ev in investigate(args.incident, repo_path=args.repo, model=args.model):
        if ev["type"] == "tool_call":
            print(f"{DIM}  [{ev['stage']}] → {ev['tool']}({', '.join(f'{k}={v!r}' for k, v in ev['args'].items())}){RESET}")
        elif ev["type"] == "finding":
            print(f"\n{BOLD}── {ev['stage'].upper()} ──{RESET} {DIM}(t+{ev['t']}s){RESET}\n{ev['text']}\n")
        elif ev["type"] == "report":
            report = RCAReport.model_validate(ev["report"])
        elif ev["type"] == "done":
            elapsed = ev["elapsed_s"]
    if report is None:
        print(f"{RED}No report produced.{RESET}")
        return 1
    print(f"{RED}{BOLD}🎯 ROOT CAUSE:{RESET} {report.root_cause}")
    print(f"{BOLD}   culprit:{RESET} {report.culprit}")
    print(f"{GREEN}{BOLD}   fix now:{RESET} {report.immediate_fix}")
    print(f"{DIM}   ({elapsed}s){RESET}")
    if args.out:
        Path(args.out).write_text(to_markdown(report, elapsed))
        print(f"\nReport written to {args.out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="ishikawa", description="Fishbone root-cause analysis for cloud incidents")
    p.add_argument("--incident", default="checkout-latency", help="incident fixture id (see --list)")
    p.add_argument("--repo", help="optional path to a real git repo: deploy/diff tools read its history")
    p.add_argument("--model", help="override ISHIKAWA_MODEL")
    p.add_argument("--out", help="write the Markdown RCA report (with Mermaid fishbone) here")
    p.add_argument("--list", action="store_true", help="list available incidents and exit")
    args = p.parse_args()
    if args.list:
        for inc in list_incidents():
            print(f"{inc['id']:<20} {inc['service']:<14} {inc['title']}")
        return 0
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
