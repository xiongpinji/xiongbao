# X-Agent v1.1.3 External GA Gates

These gates close the gap between a locally verified candidate and a formal GA
release. They do not authorize a provider call, code signing, deployment, or
production mutation by themselves.

## Paid model evaluation

The `promptfoo-eval` CI job is manual-only. Before dispatching it, configure:

- secret `XAGENT_LLM_DEEPSEEK_API_KEY`;
- variable `XAGENT_PAID_EVAL_AUTHORIZED=true`;
- variables `XAGENT_PAID_EVAL_PRICING_SOURCE`,
  `XAGENT_PAID_EVAL_PRICE_VERIFIED_AT`,
  `XAGENT_PAID_EVAL_BALANCE_VERIFIED_AT`, and
  `XAGENT_PAID_EVAL_MAX_USD`;
- workflow input `paid_eval_source_sha` equal to the exact candidate SHA;
- workflow input `paid_eval_authorization=one_batch_8_calls`.

Price and balance timestamps must be timezone-aware and no more than 24 hours
old. The preflight fixes the provider/model, limits application attempts to one,
requires exactly eight serial evaluations, and caps the declared batch cost at
USD 1. Promptfoo provider and scheduler retries are disabled. See the official
[rate-limit and retry documentation](https://www.promptfoo.dev/docs/configuration/rate-limits/)
and [HTTP provider configuration](https://www.promptfoo.dev/docs/providers/http/).

A successful run uploads the preflight, raw Promptfoo result, and the final
same-SHA evidence JSON. If a provider request has an unknown outcome, do not
rerun automatically; record it as `needs_attention/submission_unknown` and
obtain a new explicit authorization before another batch.

The final evidence must preserve the fixed preflight contract and prove an
exact `8/0/0` success/failure/error matrix. Editing the preflight provider,
model, authorization, retry, cost, or freshness fields after preflight makes
the evidence invalid.

## Desktop signing

`scripts/collect_desktop_artifacts.py` verifies both MSI and NSIS artifacts with
Windows Authenticode. Only two valid publisher signatures with trusted
timestamp certificates are classified as `signed_timestamped_candidate`.
Unsigned, mixed, invalid, or untimestamped results cannot satisfy the formal GA
signing gate.

## Target environment

Complete `XAGENT_1_1_3_TARGET_ENV_SIGNOFF_PACKET.md` only after Hosted CI, paid
model, signed desktop, backup, migration, health, browser, and rollback evidence
exists. Every evidence reference is a relative path plus SHA-256; every file is
a schema-versioned JSON object internally bound to the same 40-character source
SHA. Hosted CI must prove all required components passed; paid-model evidence
must prove the fixed real-call contract and `8/0/0` result; desktop evidence must
contain valid timestamped MSI and NSIS signatures. Backup, migration, health,
browser, and rollback documents must name their matching gate and report
`status=passed`. Duplicate packet fields are rejected. The target gate also
requires explicit authorization and four signoffs formatted as
`identity / YYYY-MM-DD`.

This gate validates the offline authorization packet. A PASS is not evidence
that deployment or target-environment acceptance happened unless the referenced
target evidence was produced by those real operations.
