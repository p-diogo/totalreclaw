# Roadmap

End-to-end encrypted memory for AI agents — portable, yours forever. This page is what TotalReclaw is building toward, at a glance. For what has already shipped, see [`CHANGELOG-public.md`](../CHANGELOG-public.md).

Last updated 2026-04-23.

---

## Q2 2026 (now)

- **Plug-and-play setup across any agent host.** `hermes plugins install` / `openclaw skills install` → agent-driven QR pairing → encrypted memory live in under a minute. Works on Docker, Railway, managed hosts, and across any browser or phone. Recovery phrase never crosses the model context.
- **Cross-client memory portability.** One recovery phrase → the same encrypted vault across Hermes, OpenClaw, NanoClaw, ZeroClaw, and Claude Code via MCP. Switch clients without re-entering or re-importing anything.

## Q3 2026

- **Autonomous memory curation.** Agents decide what is worth remembering, when to promote a fact to pinned, and when to retype or re-scope an existing memory. Less manual upkeep, sharper recall over time.
- **Quantified recall quality.** TotalReclaw reports scores on published long-context memory benchmarks (LongMemEval and similar) so "is your agent remembering the right thing?" becomes measurable rather than anecdotal.

## Q4 2026

- **Pattern learning.** The memory graph infers user preferences, workflows, and working styles from stored facts. Recall surfaces relevant context at the right moment without needing to be asked.

## Horizon (2027+)

Research and exploratory directions — no commitment on ordering.

- Multi-device coordination — phone, laptop, and cloud agents share one live vault in real time.
- Plugin SDK for third-party agent runtimes so any host can adopt TotalReclaw.
- Team and shared vaults that preserve end-to-end encryption semantics.
- Deeper knowledge-graph semantics: cross-agent contradiction resolution, supersession chains, temporal queries.

---

## How to read this page

This roadmap describes capabilities and outcomes, not the work plan behind them. Items are aspirational and subject to change as we learn from usage. For the current setup experience, see the [guides](guides/) — in particular [`hermes-setup.md`](guides/hermes-setup.md), [`openclaw-setup.md`](guides/openclaw-setup.md), and [`zeroclaw-setup.md`](guides/zeroclaw-setup.md). For shipped changes, see [`CHANGELOG-public.md`](../CHANGELOG-public.md).

Licensed under the terms in [`LICENSE`](../LICENSE).
