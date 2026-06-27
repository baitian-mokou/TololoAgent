# Wikidata Owner Override

Date: 2026-06-24

## Status

This Wikidata push is running as an `owner-approved exception`.

The shadow/materialization gate has passed, but this is still not an active-source cutover.

## Scope

- `ACTIVE_SOURCE` remains `zh_wikipedia`
- no multi-source fusion is enabled
- the Wikidata namespace is shadow-materialized into the existing graph and embedding paths
- Wikidata is now registered as a formal second source in shadow mode
- this does not authorize flipping `ACTIVE_SOURCE` or treating Wikidata as the formal active source

## Gate Expectation During This Exception

- `query_count > 0`
- required category coverage is present
- source metadata remains auditable
- gate evaluation still uses the normal threshold; owner override only authorizes the shadow materialization work, not a standards bypass

## Non-goals

- this document does not authorize flipping `ACTIVE_SOURCE`
- this document does not authorize GraphRAG, SAG, or unrelated source expansion
- this document does not claim cutover readiness for `ACTIVE_SOURCE=wikidata`
