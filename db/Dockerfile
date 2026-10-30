# PostgreSQL 16.15 (Debian), pinned by digest, plus pgvector from the PGDG apt repository.
FROM postgres:16@sha256:1beaa3084eee2676f20a9cd9928f0bf2c5bf674f8e49f81017912183d377c61c

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends postgresql-16-pgvector=0.8.7-1.pgdg13+1 \
    && rm -rf /var/lib/apt/lists/*
