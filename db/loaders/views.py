"""refresh-views: refresh every materialized view without blocking readers."""
from psycopg import sql

from .common import Summary


def refresh_views(conn):
    """REFRESH MATERIALIZED VIEW CONCURRENTLY on every view in the public schema.
    The connection must be in autocommit mode (CONCURRENTLY cannot run inside a transaction)."""
    summary = Summary("refresh-views")
    names = [r[0] for r in conn.execute(
        "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public' ORDER BY matviewname")]
    summary.read = len(names)
    for name in names:
        conn.execute(sql.SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}").format(sql.Identifier(name)))
    summary.details["views_refreshed"] = len(names)
    return summary
