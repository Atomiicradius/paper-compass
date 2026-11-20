"""PostgreSQL -> Neo4j projection spec (data-and-contracts.md section 2).

Shared by the sync and the verification script so both use the same mapping.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeSpec:
    label: str
    key: str            # ID property, same name as the PostgreSQL primary key
    sql: str            # must return the key column plus the properties to set


@dataclass(frozen=True)
class RelSpec:
    rel_type: str
    src_label: str
    src_key: str
    dst_label: str
    dst_key: str
    sql: str            # must return columns named src, dst (and optional props)
    props: tuple[str, ...] = ()


NODES: tuple[NodeSpec, ...] = (
    NodeSpec("Institution", "institution_id", "SELECT institution_id, name, country FROM institution"),
    NodeSpec("Venue", "venue_id", "SELECT venue_id, name, type FROM venue"),
    NodeSpec("Author", "author_id", "SELECT author_id, name, external_id FROM author"),
    NodeSpec("Paper", "paper_id", "SELECT paper_id, title, year, doi FROM paper"),
    NodeSpec("Method", "method_id", "SELECT method_id, canonical_name, description FROM method"),
    NodeSpec("Dataset", "dataset_id", "SELECT dataset_id, canonical_name, description FROM dataset"),
    NodeSpec("Task", "task_id", "SELECT task_id, canonical_name, description FROM task"),
    NodeSpec("Topic", "topic_id", "SELECT topic_id, name, description FROM topic"),
    NodeSpec("Setting", "setting_id", "SELECT setting_id, name FROM setting"),
    NodeSpec(
        "Experiment",
        "experiment_id",
        "SELECT experiment_id, confidence, source_sentence, extractor, reviewed FROM experiment",
    ),
    NodeSpec("Result", "result_id", "SELECT result_id, metric, value::float8 AS value, context FROM result"),
)

RELS: tuple[RelSpec, ...] = (
    RelSpec("WROTE", "Author", "author_id", "Paper", "paper_id",
            "SELECT author_id AS src, paper_id AS dst, author_order AS \"order\" FROM paper_author", ("order",)),
    RelSpec("AFFILIATED_WITH", "Author", "author_id", "Institution", "institution_id",
            "SELECT author_id AS src, institution_id AS dst FROM author WHERE institution_id IS NOT NULL"),
    RelSpec("PUBLISHED_IN", "Paper", "paper_id", "Venue", "venue_id",
            "SELECT paper_id AS src, venue_id AS dst FROM paper WHERE venue_id IS NOT NULL"),
    RelSpec("CITES", "Paper", "paper_id", "Paper", "paper_id",
            "SELECT citing_paper_id AS src, cited_paper_id AS dst FROM citation"),
    RelSpec("ABOUT", "Paper", "paper_id", "Topic", "topic_id",
            "SELECT paper_id AS src, topic_id AS dst FROM paper_topic"),
    RelSpec("HAS_EXPERIMENT", "Paper", "paper_id", "Experiment", "experiment_id",
            "SELECT paper_id AS src, experiment_id AS dst FROM experiment"),
    RelSpec("USES_METHOD", "Experiment", "experiment_id", "Method", "method_id",
            "SELECT experiment_id AS src, method_id AS dst FROM experiment"),
    RelSpec("EVALUATED_ON", "Experiment", "experiment_id", "Dataset", "dataset_id",
            "SELECT experiment_id AS src, dataset_id AS dst FROM experiment WHERE dataset_id IS NOT NULL"),
    RelSpec("SOLVES", "Experiment", "experiment_id", "Task", "task_id",
            "SELECT experiment_id AS src, task_id AS dst FROM experiment WHERE task_id IS NOT NULL"),
    RelSpec("IN_SETTING", "Experiment", "experiment_id", "Setting", "setting_id",
            "SELECT experiment_id AS src, setting_id AS dst FROM experiment WHERE setting_id IS NOT NULL"),
    RelSpec("REPORTS", "Experiment", "experiment_id", "Result", "result_id",
            "SELECT experiment_id AS src, result_id AS dst FROM result"),
    # Derived Paper shortcut edges, generated from experiments (one edge per distinct pair).
    RelSpec("USES_METHOD", "Paper", "paper_id", "Method", "method_id",
            "SELECT DISTINCT paper_id AS src, method_id AS dst FROM experiment"),
    RelSpec("EVALUATED_ON", "Paper", "paper_id", "Dataset", "dataset_id",
            "SELECT DISTINCT paper_id AS src, dataset_id AS dst FROM experiment WHERE dataset_id IS NOT NULL"),
    RelSpec("SOLVES", "Paper", "paper_id", "Task", "task_id",
            "SELECT DISTINCT paper_id AS src, task_id AS dst FROM experiment WHERE task_id IS NOT NULL"),
    RelSpec("REPORTS", "Paper", "paper_id", "Result", "result_id",
            "SELECT DISTINCT e.paper_id AS src, r.result_id AS dst FROM result r JOIN experiment e USING (experiment_id)"),
)
