"""Initialize and load the rating-text database.

    python database/pipeline.py init
    python database/pipeline.py load-texts [--csv data/_rating_texts_final.csv]
    python database/pipeline.py status
"""
import argparse
import database as db
 

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Load ACRA rating texts from a single CSV"
    )
    parser.add_argument(
        "--db",
        default=db.DB_PATH,
        help=f"database file (default: {db.DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the rating-text table")
    load = sub.add_parser("load-texts", help="load rating texts from a CSV")
    load.add_argument("--csv", default="data/_rating_texts_final.csv")
    sub.add_parser("status", help="show the number of loaded rating texts")

    args = parser.parse_args(argv)
    con = db.connect(args.db)
    try:
        if args.command == "init":
            print(f"Database ready: {args.db}")
        elif args.command == "load-texts":
            db.load_texts(con, args.csv)
            con.execute("CHECKPOINT")
        else:
            db.status(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
