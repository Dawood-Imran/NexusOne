# PostgreSQL Init Scripts

Files in this directory are mounted into the Postgres container at:

```text
/docker-entrypoint-initdb.d
```

Postgres runs `*.sql`, `*.sql.gz`, and executable shell scripts from this directory only when the database volume is initialized for the first time.

Current files:

- `001_schema.sql` - Creates identity, document metadata, permissions, ticket, business data, ingestion, audit, and feedback tables.
- `002_seed_permission_profiles.sql` - Generated from `data/generated/manifests/permissions.yaml`.
- `003_load_csv_sources.sql` - Loads generated CSV files from `/seed/csv`.
- `004_seed_documents_and_permissions.sql` - Generated from document and CSV manifests.

Planned next step:

1. Add the ingestion pipeline for PDF, Markdown, and selected CSV text chunks.
2. Write chunk metadata into PostgreSQL.
3. Keep all values fictional and local-development only.
