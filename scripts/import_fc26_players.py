#!/usr/bin/env python3
"""Download and import EA FC 26 player data into Supabase/SQLite."""

from __future__ import annotations

import argparse
import json
import logging

from src.seed.import_fc26_players import import_fc26_players


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Import Kaggle FC26 player squads")
    parser.add_argument("--no-download", action="store_true", help="Require local CSV only")
    args = parser.parse_args()
    result = import_fc26_players(download=not args.no_download)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
