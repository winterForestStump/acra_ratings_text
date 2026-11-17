"""Load rating-text records from the scraper CSV into a single DuckDB table."""
from pathlib import Path
import duckdb
import pandas as pd

DB_PATH = "data/rating_texts.duckdb"
TABLE_NAME = "rating_texts"
CSV_COLUMNS = ("full_name","name_rus","country","sector","activity",
               "INN","OGRN","scale","rating","outlook","date","link","text")
KEY_COLUMNS = ("date", "link")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rating_texts (
    full_name VARCHAR,
    name_rus VARCHAR,
    country VARCHAR,
    sector VARCHAR,
    activity VARCHAR,
    INN VARCHAR,
    OGRN VARCHAR,
    scale VARCHAR,
    rating VARCHAR,
    outlook VARCHAR,
    date DATE NOT NULL,
    link VARCHAR NOT NULL,
    text VARCHAR NOT NULL,
    UNIQUE (date, link)
)
"""


def connect(db_path=DB_PATH):
    """Open the dedicated rating-text database and ensure its schema exists."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        unexpected = tables - {TABLE_NAME}
        if unexpected:
            raise ValueError(
                f"{path} contains unrelated tables {sorted(unexpected)}; "
                "use a dedicated database path"
            )

        con.execute(SCHEMA)
        columns = [
            row[0] for row in con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()
        ]
        if columns != list(CSV_COLUMNS):
            raise ValueError(
                f"{path} has an incompatible {TABLE_NAME} table; "
                "use a new database path"
            )

        unique_keys = con.execute(
            """
            SELECT constraint_column_names
            FROM duckdb_constraints()
            WHERE table_name = ? AND constraint_type = 'UNIQUE'
            """,
            [TABLE_NAME],
        ).fetchall()
        if not any(tuple(row[0]) == KEY_COLUMNS for row in unique_keys):
            raise ValueError(
                f"{path} does not enforce uniqueness on (date, link); "
                "use a new database path"
            )
    except (duckdb.Error, ValueError):
        con.close()
        raise
    return con


def _read_csv(csv_path):
    """Read the requested columns, discarding scraper-only metadata."""
    source = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig")
    normalized = [str(column).strip().lower() for column in source.columns]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{csv_path}: duplicate column names after normalization")

    column_map = dict(zip(normalized, source.columns))
    required = [column.lower() for column in CSV_COLUMNS]
    missing = [column for column in required if column not in column_map]
    if missing:
        raise ValueError(f"{csv_path}: missing columns {missing}")

    df = source[[column_map[column] for column in required]].copy()
    df.columns = CSV_COLUMNS

    for column in CSV_COLUMNS:
        if column != "text":
            df[column] = df[column].str.strip().replace("", pd.NA)

    missing_key = df["date"].isna() | df["link"].isna()
    if missing_key.any():
        raise ValueError(
            f"{csv_path}: {int(missing_key.sum())} rows have an empty date or link"
        )

    parsed_dates = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        examples = df.loc[invalid_dates, "date"].head(3).tolist()
        raise ValueError(f"{csv_path}: unreadable dates, for example {examples}")
    df["date"] = parsed_dates.dt.date

    empty_text = df["text"].isna() | df["text"].str.strip().eq("")
    skipped_empty_text = int(empty_text.sum())
    df = df.loc[~empty_text].copy()

    duplicate_keys = int(df.duplicated(subset=KEY_COLUMNS, keep="last").sum())
    df = df.drop_duplicates(subset=KEY_COLUMNS, keep="last")
    df = df.astype(object).where(df.notna(), None)
    return df, skipped_empty_text, duplicate_keys


def load_texts(con, csv_path):
    """Insert successful texts, ignoring keys that have already been loaded."""
    df, skipped_empty_text, duplicate_keys = _read_csv(csv_path)
    if df.empty:
        print(
            "Texts: 0 inserted "
            f"({skipped_empty_text} empty-text rows skipped)"
        )
        return

    before = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchall()[0][0]
    con.register("incoming_texts", df)
    columns = ", ".join(f'"{column}"' for column in CSV_COLUMNS)
    try:
        con.execute(
            f"""
            INSERT INTO {TABLE_NAME} ({columns})
            SELECT {columns} FROM incoming_texts
            ON CONFLICT (date, link) DO NOTHING
            """
        )
    finally:
        con.unregister("incoming_texts")

    after = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchall()[0][0]
    inserted = after - before
    already_present = len(df) - inserted
    print(
        f"Texts: {inserted} inserted, {already_present} existing keys skipped; "
        f"{duplicate_keys} duplicate CSV keys and "
        f"{skipped_empty_text} empty-text rows skipped"
    )


def status(con):
    """Print the number of loaded rows and the covered date range."""
    count, first_date, last_date = con.execute(
        f"SELECT COUNT(*), MIN(date), MAX(date) FROM {TABLE_NAME}"
    ).fetchall()[0]
    print(f"rating_texts: {count}")
    print(f"date range:   {first_date or 'n/a'} to {last_date or 'n/a'}")
