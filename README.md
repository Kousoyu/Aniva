# Aniva

Aniva is a **Digital Life Substrate** research prototype.
It is not a chatbot, not an LLM wrapper, and not a general-purpose agent.

It studies how local rules, history, and structural plasticity can produce
open-ended, path-dependent behavior in a small neural system.

## What Aniva is not

- not a chat assistant
- not a wrapper around a language model
- not a behavior-tree agent
- not a claim of consciousness, personhood, or digital life already achieved

## Current stage

The current public evidence chain is closed through Phase 10E / 10F.
The strongest supported conclusion is:

> Tag formation support is trace[src] × phi[tgt] support geometry,
> not direct h[u] history gating.

That result comes from the following diagnostic chain:

- Phase 10E: historical-context diagnostics and validation attempts
- Phase 10F: support geometry audits, true trace/phi capture, and subgraph decomposition

## Recommended reading

1. `docs/phase10E_10F_tag_support_diagnostic_chain_summary.md`
2. `docs/phase9D_summary.md`
3. `docs/phase9D_to_phase10_transition.md`

## Install

```bash
pip install -e ".[dev]"
```

## Test

```bash
python -m pytest tests/ -q
```

## Repository layout

- `aniva/` — core runtime, environment, experiments, and diagnostics
- `docs/` — phase notes, designs, and evidence summaries
- `tests/` — unit and integration tests

## Public boundaries

This repository contains an experimental research prototype.
APIs, diagnostics, and file formats may change.

Most readers should start from the docs summaries, not raw result CSV files.

This project does not claim to validate consciousness, personhood, or the
existence of digital life.

Large event-level result files are intentionally kept out of source control when
possible; smaller summary artifacts and notes are the primary public record.
