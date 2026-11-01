"""Helpers shared by all loader commands: settings, JSONL reading, rejects, summaries."""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psycopg

DB_DIR = Path(__file__).resolve().parents[1]
REJECT_DIR = DB_DIR / "rejects"


def clean(text):
    """Trim and collapse runs of whitespace. The stored form of a name."""
    return " ".join(text.split())


def normalize(text):
    """The matching form of a name: cleaned and case-folded."""
    return clean(text).casefold()


# --- database connection ----------------------------------------------------------------------

def read_env_file(path=DB_DIR / ".env"):
    values = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def connect(dbname=None):
    """Connect using db/.env (environment variables override it). Autocommit, so each loader
    controls its own transaction."""
    env = read_env_file()

    def get(key, default=""):
        return os.environ.get(key, env.get(key, default))

    return psycopg.connect(
        host=get("POSTGRES_HOST", "127.0.0.1"),
        port=get("POSTGRES_PORT", "5432"),
        user=get("POSTGRES_USER"),
        password=get("POSTGRES_PASSWORD"),
        dbname=dbname or get("POSTGRES_DB"),
        autocommit=True,
    )


# --- reading and rejecting --------------------------------------------------------------------

def read_jsonl(path):
    """Return ([(line_number, object)], [reject]) for a JSON Lines file. Blank lines are ignored.
    A line that is not a JSON object becomes a reject instead of stopping the load."""
    rows, rejects = [], []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                rejects.append(reject(number, f"invalid JSON: {exc.msg}", line.rstrip("\n")))
                continue
            if not isinstance(obj, dict):
                rejects.append(reject(number, "line is not a JSON object", obj))
                continue
            rows.append((number, obj))
    return rows, rejects


def reject(line_number, reason, row):
    return {"line": line_number, "reason": reason, "row": row}


def write_rejects(rejects, kind, reject_dir):
    """Write rejected rows to a timestamped JSONL file. Returns the path, or None if nothing to write."""
    if not rejects:
        return None
    reject_dir = Path(reject_dir)
    reject_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = reject_dir / f"{kind}-{stamp}.jsonl"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for item in rejects:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return str(path)


# --- summary ----------------------------------------------------------------------------------

@dataclass
class Summary:
    command: str
    source: str = ""
    read: int = 0
    inserted: int = 0
    skipped: int = 0
    rejected: int = 0
    warnings: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    reject_reasons: list = field(default_factory=list)
    reject_file: str = None

    def warn(self, message):
        self.warnings.append(message)  # printed once, in the summary

    def add(self, key, amount=1):
        self.details[key] = self.details.get(key, 0) + amount

    def finish(self, rejects, kind, reject_dir):
        """Record the rejects and write the reject file. Call only after the transaction committed."""
        self.rejected = len(rejects)
        self.reject_reasons = [r["reason"] for r in rejects]
        self.reject_file = write_rejects(rejects, kind, reject_dir)
        return self

    def lines(self):
        out = [f"== {self.command}" + (f": {self.source}" if self.source else "") + " ==",
               f"rows read:  {self.read}",
               f"inserted:   {self.inserted}",
               f"skipped:    {self.skipped}",
               f"rejected:   {self.rejected}",
               f"warnings:   {len(self.warnings)}"]
        for key, value in self.details.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value) or "-"
            out.append(f"  {key}: {value}")
        for w in self.warnings:
            out.append(f"  WARNING: {w}")
        if self.reject_file:
            out.append(f"  rejects written to: {self.reject_file}")
            for reason in self.reject_reasons:
                out.append(f"    - {reason}")
        return out
