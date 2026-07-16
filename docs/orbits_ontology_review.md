# ORBITS Ontology Review

Scope: preview-only ontology review for `月球 / ORBITS`. No ontology or triple files are modified.

## Finding

The current conflict is not a simple value disagreement. `wikidata` gives `地球`, which is a known celestial entity and a plausible direct orbit target for the Moon. `zh_wikipedia` gives `太阳系内密度第二高`, which is a descriptive phrase rather than an orbit target.

## Interpretation

- ORBITS should normally mean direct orbital parent, not a free-text descriptive statement.
- The `zh_wikipedia` object is best treated as an extraction error candidate.
- The ontology should add object validation for ORBITS instead of silently accepting descriptive phrases.

## Candidate Rules

- ORBITS object must be a known celestial-body entity or an accepted entity alias/QID.
- Descriptive phrases are invalid ORBITS objects.
- Failed ORBITS object validation should mark the record as `extraction_error_candidate`.

No formal ontology change is applied in this phase.
