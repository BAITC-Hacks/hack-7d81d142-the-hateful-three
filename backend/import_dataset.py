"""Operator CLI: python -m backend.import_dataset '../data (1).zip'."""

import argparse
import json
from pathlib import Path

from backend.core.database import get_session_factory
from backend.services.analytics import analysis_write, run_analysis
from backend.services.dataset_import import import_archive


def main():
    parser = argparse.ArgumentParser(description="Import a starter ZIP into an empty MoneyGraph database.")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with get_session_factory()() as session:
        with analysis_write(session):
            import_archive(session, args.archive.read_bytes())
            result = run_analysis(session)
            session.commit()
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
