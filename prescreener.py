"""
prescreener.py — CLI for Type 2 Diabetes Trial Pre-Screening Agent

Usage:
  python prescreener.py --patient P-3098
"""

from __future__ import annotations

import argparse
import json
import sys

from prescreener.runner import prescreen_patient


def main():
    parser = argparse.ArgumentParser(description="Type 2 Diabetes Trial Pre-Screening Agent")
    parser.add_argument("--patient", required=True, help="Patient ID (e.g. P-3098, P-1842)")
    parser.add_argument("--dataset", default="data/Type2-Diabetes-Trial-Agent-Dataset.json", help="Dataset JSON path")
    parser.add_argument("--output", help="Optional output JSON path")

    args = parser.parse_args()

    result = prescreen_patient(args.patient, args.dataset)
    formatted = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(formatted)
        print(f"Report saved to {args.output}")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
