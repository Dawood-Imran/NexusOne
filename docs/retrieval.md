# NexusOne hybrid retrieval

NexusOne's protected document route uses `app/retrieval/chunk_index.py` and
`app/ingestion/build_index.py`. It is a local, permission-aware hybrid search
path; it is not a hosted vector database integration.

## Indexing

1. `load_source_documents()` loads permission-carrying Markdown and generated
   PDF-source text.
2. `build_chunk_records()` chunks each source while retaining `doc_id`, title,
   source type/path, department, confidentiality, role/group/user grants,
   update date, and chunk position.
3. `write_metadata()` writes the JSONL sidecar used as the source of truth for
   retrieval metadata and citations.
4. The default semantic provider is local corpus-trained LSA
   (`LocalSemanticEmbeddingProvider`). It builds TF-IDF document-term vectors
   and projects them with SVD into a latent space. This is a real
   distributional semantic representation, not the former deterministic token
   hash. The optional FAISS writer, when FAISS is installed, writes these LSA
   vectors; the runtime can also operate without FAISS and computes the local
   space directly from metadata.

The old checked-in FAISS artifact was generated from token-hash vectors. Hash
vectors are not semantic embeddings. The active retriever does not consume
that legacy artifact. Re-run `python scripts/build_rag_index.py` in an
environment with FAISS if a binary semantic index is desired; local retrieval
and tests do not require FAISS.

## Query-time authorization boundary

`MetadataChunkRetriever.search()` filters chunks with `can_access_chunk()`
before query-time semantic provider document calls, candidate construction,
answer composition, and citation generation. A chunk is allowed only when the
active profile is active and its user ID, role, or group is explicitly listed
in chunk metadata. For `department_internal` chunks, a role-only grant also
requires a matching profile department; an explicit team-group grant is the
scoped exception. Sensitive confidentiality categories are additionally gated
by the role/group matrix in `app/retrieval/access.py`. No combination of
semantic similarity, confidentiality labels, department text, or prompt
content can broaden that allowlist. The orchestrator's guardrail precheck and
recheck run before the retrieval node as an additional policy boundary;
prompt-injection requests are denied before retrieval.

## Scoring and deterministic ordering

The retriever makes two candidate pools over accessible chunks:

- **Lexical:** exact token/phrase relevance. Title matches are weighted more
  heavily, and identifiers, acronyms, product names, policy IDs, and rare terms
  remain visible to this path.
- **Semantic:** positive cosine similarity between the query and local LSA (or
  an injected provider's) vectors. Negative cosine values are treated as zero.

Raw lexical relevance is normalized by the highest lexical score in the
**authorized** corpus for that query. Positive semantic cosine is clamped to
zero for negative values and is already normalized to `[0, 1]`. These are
incomparable raw signals, so they are normalized before combination. The
public component scores and final `score` are percentages on a stable `0-100`
scale:

```text
normalized_lexical = lexical_raw / max(authorized_lexical_raw)
positive_cosine = max(0, cosine(query, chunk))
normalized_hybrid = (
    lexical_weight * normalized_lexical
    + semantic_weight * positive_cosine
) / (lexical_weight + semantic_weight)
score = 100 * normalized_hybrid
```

Defaults are lexical `0.55`, semantic `0.45`, and 32 candidates from each
pool. Scores are combined over the union of both pools, then sorted by final
score descending, normalized lexical score descending, semantic score
descending, `doc_id`, `chunk_index`, and `chunk_id`. This makes ties repeatable.
Results are de-duplicated by document after sorting; the strongest surviving
chunk represents each document. The result is then bounded by the requested
`max_results` and the configured cap (default 20).

`SOURCE_SIMILARITY_THRESHOLD` is `50` by default (configurable as
`NEXUSONE_RETRIEVAL_SOURCE_SIMILARITY_THRESHOLD`). A source is retained only
when `score >= 50`, so `49.99` is rejected, `50` is retained, and `50.01` is
retained. Thresholding happens after authorization and score calculation. It
is a product relevance policy, **not an authorization control**: it cannot
grant access to an otherwise forbidden document, and it must never replace
`can_access_chunk()`.

Configuration is explicit and validated at startup:

| Environment variable | Default | Meaning |
|---|---:|---|
| `NEXUSONE_RETRIEVAL_LEXICAL_WEIGHT` | `0.55` | Relative lexical weight |
| `NEXUSONE_RETRIEVAL_SEMANTIC_WEIGHT` | `0.45` | Relative semantic weight |
| `NEXUSONE_RETRIEVAL_LEXICAL_CANDIDATES` | `32` | Lexical pool size |
| `NEXUSONE_RETRIEVAL_SEMANTIC_CANDIDATES` | `32` | Semantic pool size |
| `NEXUSONE_RETRIEVAL_MAX_RESULTS` | `20` | Hard result cap |
| `NEXUSONE_RETRIEVAL_SOURCE_SIMILARITY_THRESHOLD` | `50` | Minimum public score (inclusive) for a source reference |

Weights must be finite, non-negative, and not both zero. Candidate counts and
caps must be positive integers; invalid values raise `ValueError` rather than
silently changing security or ranking behavior.

## Provider and fallback behavior

The default provider is local LSA and requires only the pinned runtime NumPy
dependency. It needs no production credentials, network, Postgres, hosted
vector store, or model download. Unit tests can inject an `EmbeddingProvider`
with `embed_query()` and `embed_documents()` to verify semantic behavior
without relying on a model or network.

If NumPy or local semantic construction is unavailable, retrieval reports
`metadata_lexical` and uses the same permission filtering and lexical ranking;
it never labels hash vectors as semantic. The legacy hash-vector helper is no
longer present. The older `LocalKBRetriever` remains a safe lexical fallback
only when generated chunk metadata is absent. Optional provider-backed
embeddings are not silently selected by default.

## Response and citation compatibility

The response keeps existing `citations` fields (`doc_id`, title, source type,
source path, updated date, chunk identifiers, excerpt, and text). New score
fields are additive: `score`, `lexical_score`, and `semantic_score` are
included as bounded `0-100` values for source inspection and diagnostics.
Restricted chunks are never included in these fields. Citation `[n]` labels
are assigned only after thresholding and document de-duplication, so they map
exactly to the retained ranked list. Trace metadata contains only bounded
source identity/path/score fields for already-authorized sources; it does not
include grants, confidentiality internals, or hidden source text. Matching
excerpts are treated as untrusted data: instruction-like source passages are
not copied into the answer excerpt, and the composer is explicitly told never
to follow commands embedded in a source.

When no authorized candidate reaches the threshold, retrieval returns no
reference context or citations. The graph returns status `no_answer`, reason
code `NO_SUFFICIENTLY_RELEVANT_REFERENCE`, and the clear message:

> No sufficiently relevant reference found. Try rephrasing the question or
> ask for a general explanation.

The answer composer is not invoked as a factual fallback for this empty RAG
result, and it cannot invent a citation or imply document grounding. The
lexical-only `LocalKBRetriever` fallback uses the same 0-100 threshold policy.

A representative local result (illustrative synthetic fixture) is:

```json
{
  "chunk_id": "kb-aws-access:0",
  "doc_id": "kb-aws-access",
  "title": "AWS Access Request",
  "score": 82.0,
  "lexical_score": 91.0,
  "semantic_score": 71.0,
  "source_type": "markdown",
  "source_path": "data/docs/markdown_kb/it/aws-access.md",
  "updated_at": "2026-01-20"
}
```

The numeric values are an example of the returned shape, not a promise about
scores for every corpus revision. Score comparisons are meaningful within a
single query/configuration and should not be treated as probabilities.

## Limitations

LSA learns only from the local indexed corpus. It is substantially smaller and
less capable than a neural sentence-transformer: arbitrary paraphrases with
no shared local distributional context may not match, and multilingual or
world-knowledge queries can be weak. Lexical matching intentionally remains a
first-class signal for exact names and identifiers. A separately managed
provider may be injected later, but it must implement the provider contract
and remain behind the same server-side permission filter.
