#!/bin/sh
set -eu

finance_db="${FINANCE_DB:-/app/data/finance_insight.sqlite3}"
rag_db="${RAG_DB:-/app/data/rag.sqlite3}"

if [ ! -f "$finance_db" ] && [ ! -f "$rag_db" ]; then
  finance_dir=$(dirname "$finance_db")
  rag_dir=$(dirname "$rag_db")
  if [ "$finance_dir" != "$rag_dir" ] || [ "$(basename "$finance_db")" != "finance_insight.sqlite3" ] || [ "$(basename "$rag_db")" != "rag.sqlite3" ]; then
    echo "FinanceInsight: automatic demo initialization requires both standard database filenames in one directory." >&2
    exit 2
  fi
  echo "FinanceInsight: runtime databases are absent; creating synthetic demo data."
  python /app/scripts/init_demo_data.py --data-dir "$finance_dir"
elif [ ! -f "$finance_db" ] || [ ! -f "$rag_db" ]; then
  echo "FinanceInsight: only one runtime database exists. Refusing to overwrite it." >&2
  exit 2
fi

if [ "${FINANCE_BACKEND:-sqlite}" = "mysql" ] && [ "${MYSQL_SYNC_FROM_SQLITE:-false}" = "true" ]; then
  echo "FinanceInsight: synchronizing portable finance data into MySQL."
  python -m finance_insight.ingestion.sync_mysql --sqlite "$finance_db"
fi

exec "$@"
