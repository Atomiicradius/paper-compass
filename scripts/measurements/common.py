"""Shared helpers for the two measurement scripts (HNSW recall, recursive CTE vs Cypher).

Read-only: every Postgres session is opened with default_transaction_read_only = on, and the Neo4j sessions only run
MATCH queries. Passwords are read from db/.env at run time and are never printed, logged or written to a result file.

Run with the same Python the API uses (the "api-venv" interpreter). The embeddings venv's site-packages is put first on
sys.path, exactly as the API launcher does, so the same psycopg / numpy build is used. Set PC_EMBEDDINGS_SITE if it lives
somewhere else.
"""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EMBEDDINGS_SITE = Path(os.environ.get("PC_EMBEDDINGS_SITE", str(REPO.parent / "paper-compass-main" / "db" / "embeddings" / ".venv" / "Lib" / "site-packages")))
if EMBEDDINGS_SITE.is_dir():
    sys.path.insert(0, str(EMBEDDINGS_SITE))  # first: one consistent set of packages, as in the API launcher
sys.path.insert(1 if EMBEDDINGS_SITE.is_dir() else 0, str(REPO))

DATABASE = os.environ.get("PC_MEASURE_DB", "pc_demo_opps")
SEED = 42
RESULTS = Path(__file__).resolve().parent / "results"


def read_env() -> dict[str, str]:
    """db/.env as a dict (values are never printed)."""
    env: dict[str, str] = {}
    for line in (REPO / "db" / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def pg_connect():
    """A READ-ONLY psycopg connection to the measurement database."""
    import psycopg

    env = read_env()
    dsn = f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@127.0.0.1:{env.get('POSTGRES_PORT', '5432')}/{DATABASE}"
    conn = psycopg.connect(dsn, options="-c default_transaction_read_only=on")
    conn.autocommit = True
    # The API opens a new connection per request, so no statement is ever re-used. psycopg would otherwise prepare a
    # repeated statement after 5 runs and re-use ONE cached plan, which would mix the settings of the configurations.
    conn.prepare_threshold = None
    return conn


def neo4j_driver():
    from neo4j import GraphDatabase

    env = read_env()
    return GraphDatabase.driver("bolt://127.0.0.1:7687", auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile: the smallest value that at least p % of the values are <= to. No interpolation."""
    s = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(s)))
    return s[rank - 1]


def median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def machine() -> dict:
    """CPU, RAM, OS and Docker, as reported by the machine itself."""
    info: dict = {"os": platform.platform(), "python": sys.version.split()[0]}

    def ps(cmd: str) -> str:
        try:
            return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:
            return ""

    info["cpu"] = ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")
    info["cpu_cores"] = ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).NumberOfCores")
    info["cpu_logical"] = ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).NumberOfLogicalProcessors")
    ram = ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
    info["ram_gb"] = round(int(ram) / 2**30, 1) if ram.isdigit() else None
    try:
        out = subprocess.run(["docker", "info", "--format", "{{json .}}"], capture_output=True, text=True, timeout=30).stdout
        d = json.loads(out)
        info["docker"] = {"server_version": d.get("ServerVersion"), "os": d.get("OperatingSystem"), "kernel": d.get("KernelVersion"),
                          "cpus_for_docker": d.get("NCPU"), "memory_for_docker_gb": round(d.get("MemTotal", 0) / 2**30, 1)}
        ps_out = subprocess.run(["docker", "ps", "--format", "{{.Names}}|{{.Image}}"], capture_output=True, text=True, timeout=30).stdout
        info["docker"]["containers"] = [line for line in ps_out.splitlines() if line.startswith(("pc-postgres", "pc-neo4j"))]
    except Exception as e:  # docker missing or not answering
        info["docker"] = {"error": type(e).__name__}
    return info


def save(name: str, data: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
