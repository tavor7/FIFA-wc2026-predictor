#!/usr/bin/env python3
"""Load bundled WC data into the database (no API keys required)."""

from __future__ import annotations

import argparse
import json
import logging

from src.seed.load_seeds import ensure_baseline_data, load_all_seeds


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Feed WC 2026 seed data into the database")
    parser.add_argument("--force", action="store_true", help="Reload all fixtures and standings")
    args = parser.parse_args()

    result = load_all_seeds() if args.force else ensure_baseline_data(run_predictions=True)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
