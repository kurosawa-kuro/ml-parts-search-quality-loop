"""Small argparse CLI adapted from the Python ML starter's entrypoint pattern."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parts_search_quality_loop.artifacts.store import verify_run
from parts_search_quality_loop.config.loader import STAGES, load_settings
from parts_search_quality_loop.errors import FoundationError
from parts_search_quality_loop.pipelines.bootstrap import run_bootstrap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parts search quality loop foundation (no ML yet)")
    parser.add_argument("--project", type=Path, default=Path("env/project.yaml"))
    parser.add_argument("--config", type=Path, default=Path("env/config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("config-check", help="Validate public config; never loads secrets")
    check.add_argument("--stage", choices=STAGES, default="foundation")
    bootstrap = commands.add_parser("bootstrap", help="Write a local foundation run, without ML")
    bootstrap.add_argument("--run-id")
    verify = commands.add_parser("verify-artifact", help="Verify a completed run and its checksums")
    verify.add_argument("run_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify-artifact":
            manifest = verify_run(args.run_dir)
            output = {"verified": True, "run_id": manifest["run_id"]}
        else:
            settings = load_settings(args.project, args.config)
            if args.command == "config-check":
                blockers = settings.blockers(args.stage)
                output = {
                    "valid": True,
                    "stage": args.stage,
                    "ready": not blockers,
                    "blockers": blockers,
                    "scope": "configuration_only",
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return 1 if blockers else 0
            path = run_bootstrap(settings, args.run_id)
            output = {"run_dir": str(path), "ml_executed": False}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except FoundationError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except OSError:
        print(json.dumps({"error": "Filesystem operation failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
