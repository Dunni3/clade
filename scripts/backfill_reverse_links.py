#!/usr/bin/env python3
"""One-off script to backfill missing reverse links in the Hearth DB.

Cards and morsels can link to each other, and _create_reverse_links() ensures
bidirectionality. But cards/morsels created before that function was added
are missing their reverse links. This script finds and creates them.

Usage (on EC2):
    python3 scripts/backfill_reverse_links.py /opt/hearth/data/hearth.db

Or dry-run first:
    python3 scripts/backfill_reverse_links.py /opt/hearth/data/hearth.db --dry-run
"""

import argparse
import sqlite3
import sys


def backfill(db_path: str, dry_run: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    inserted = 0

    # 1. card -> morsel links: ensure morsel -> card reverse exists
    rows = conn.execute(
        "SELECT card_id, object_id FROM kanban_card_links WHERE object_type = 'morsel'"
    ).fetchall()
    for card_id, morsel_id in rows:
        exists = conn.execute(
            "SELECT 1 FROM morsel_links WHERE morsel_id = ? AND object_type = 'card' AND object_id = ?",
            (int(morsel_id), str(card_id)),
        ).fetchone()
        if not exists:
            print(f"  card #{card_id} -> morsel #{morsel_id}: missing reverse (morsel -> card)")
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO morsel_links (morsel_id, object_type, object_id) VALUES (?, 'card', ?)",
                    (int(morsel_id), str(card_id)),
                )
            inserted += 1

    # 2. morsel -> card links: ensure card -> morsel reverse exists
    rows = conn.execute(
        "SELECT morsel_id, object_id FROM morsel_links WHERE object_type = 'card'"
    ).fetchall()
    for morsel_id, card_id in rows:
        exists = conn.execute(
            "SELECT 1 FROM kanban_card_links WHERE card_id = ? AND object_type = 'morsel' AND object_id = ?",
            (int(card_id), str(morsel_id)),
        ).fetchone()
        if not exists:
            print(f"  morsel #{morsel_id} -> card #{card_id}: missing reverse (card -> morsel)")
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO kanban_card_links (card_id, object_type, object_id) VALUES (?, 'morsel', ?)",
                    (int(card_id), str(morsel_id)),
                )
            inserted += 1

    # 3. card -> card links: ensure reverse card -> card exists
    rows = conn.execute(
        "SELECT card_id, object_id FROM kanban_card_links WHERE object_type = 'card'"
    ).fetchall()
    for card_id, target_card_id in rows:
        exists = conn.execute(
            "SELECT 1 FROM kanban_card_links WHERE card_id = ? AND object_type = 'card' AND object_id = ?",
            (int(target_card_id), str(card_id)),
        ).fetchone()
        if not exists:
            print(f"  card #{card_id} -> card #{target_card_id}: missing reverse (card -> card)")
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO kanban_card_links (card_id, object_type, object_id) VALUES (?, 'card', ?)",
                    (int(target_card_id), str(card_id)),
                )
            inserted += 1

    # 4. morsel -> morsel links: ensure reverse morsel -> morsel exists
    rows = conn.execute(
        "SELECT morsel_id, object_id FROM morsel_links WHERE object_type = 'morsel'"
    ).fetchall()
    for morsel_id, target_morsel_id in rows:
        exists = conn.execute(
            "SELECT 1 FROM morsel_links WHERE morsel_id = ? AND object_type = 'morsel' AND object_id = ?",
            (int(target_morsel_id), str(morsel_id)),
        ).fetchone()
        if not exists:
            print(f"  morsel #{morsel_id} -> morsel #{target_morsel_id}: missing reverse (morsel -> morsel)")
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO morsel_links (morsel_id, object_type, object_id) VALUES (?, 'morsel', ?)",
                    (int(target_morsel_id), str(morsel_id)),
                )
            inserted += 1

    if inserted == 0:
        print("All links are already bidirectional. Nothing to do.")
    else:
        action = "Would insert" if dry_run else "Inserted"
        print(f"\n{action} {inserted} reverse link(s).")

    if not dry_run:
        conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing reverse links in Hearth DB")
    parser.add_argument("db_path", help="Path to hearth.db")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    args = parser.parse_args()

    print(f"{'DRY RUN — ' if args.dry_run else ''}Backfilling reverse links in {args.db_path}\n")
    backfill(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
