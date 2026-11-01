"""load-vocabulary: controlled vocabulary (method, dataset, task, setting) and aliases."""
from .common import REJECT_DIR, Summary, clean, normalize, read_jsonl, reject

# type -> (table, name column, alias table, id column). Settings have no alias table.
TYPES = {
    "method": ("method", "canonical_name", "method_alias", "method_id"),
    "dataset": ("dataset", "canonical_name", "dataset_alias", "dataset_id"),
    "task": ("task", "canonical_name", "task_alias", "task_id"),
    "setting": ("setting", "name", None, "setting_id"),
}


def vocabulary_maps(conn, vocab_type):
    """Return ({normalized name: id}, {normalized alias: id}) for one vocabulary type."""
    table, name_col, alias_table, id_col = TYPES[vocab_type]
    names = {normalize(n): i for i, n in conn.execute(f"SELECT {id_col}, {name_col} FROM {table}")}
    aliases = {}
    if alias_table:
        aliases = {normalize(a): i for a, i in conn.execute(f"SELECT alias, {id_col} FROM {alias_table}")}
    return names, aliases


def check_entry(row):
    """Return a reason string if the entry is invalid, else None."""
    if row.get("type") not in TYPES:
        return f"unknown type {row.get('type')!r} (expected one of {', '.join(TYPES)})"
    name = row.get("canonical_name")
    if not isinstance(name, str) or not name.strip():
        return "canonical_name must be a non-empty string"
    aliases = row.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
        return "aliases must be a list of non-empty strings"
    if row["type"] == "setting" and aliases:
        return "settings cannot have aliases (no alias table); aliases must be []"
    return None


def load_vocabulary(conn, path, reject_dir=REJECT_DIR):
    summary = Summary("load-vocabulary", str(path))
    rows, rejects = read_jsonl(path)
    summary.read = len(rows) + len(rejects)

    with conn.transaction():
        maps = {t: vocabulary_maps(conn, t) for t in TYPES}
        for number, row in rows:
            reason = check_entry(row)
            if reason:
                rejects.append(reject(number, reason, row))
                continue
            vocab_type = row["type"]
            table, name_col, alias_table, id_col = TYPES[vocab_type]
            names, aliases = maps[vocab_type]
            name = clean(row["canonical_name"])
            key = normalize(name)

            if key in names:
                entity_id = names[key]
                summary.skipped += 1
            elif key in aliases:
                rejects.append(reject(number, f"canonical name {name!r} is already an alias of another entry", row))
                continue
            else:
                entity_id = conn.execute(
                    f"INSERT INTO {table} ({name_col}) VALUES (%s) "
                    f"ON CONFLICT ({name_col}) DO NOTHING RETURNING {id_col}", (name,)).fetchone()[0]
                names[key] = entity_id
                summary.inserted += 1

            for alias in row.get("aliases", []):
                alias = clean(alias)
                akey = normalize(alias)
                if akey == key:
                    continue  # same as the canonical name
                if akey in aliases:
                    if aliases[akey] != entity_id:
                        summary.warn(f"alias {alias!r} for {name!r} already belongs to another {vocab_type}; ignored")
                    else:
                        summary.add("aliases_skipped")
                elif akey in names and names[akey] != entity_id:
                    summary.warn(f"alias {alias!r} for {name!r} is the canonical name of another {vocab_type}; ignored")
                else:
                    cur = conn.execute(
                        f"INSERT INTO {alias_table} (alias, {id_col}) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING",
                        (alias, entity_id))
                    aliases[akey] = entity_id
                    summary.add("aliases_inserted" if cur.rowcount else "aliases_skipped")

    summary.details.setdefault("aliases_inserted", 0)
    summary.details.setdefault("aliases_skipped", 0)
    return summary.finish(rejects, "vocabulary", reject_dir)
