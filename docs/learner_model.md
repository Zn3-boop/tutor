# Learner model

## Bayesian Knowledge Tracing

For each topic, ECV-Tutor stores the probability that the learner has mastered the skill, `pL0`, plus four parameters:

- `pL0`: initial/current mastery probability
- `pT`: probability of learning after an opportunity while unmastered
- `pG`: probability of guessing correctly while unmastered
- `pS`: probability of slipping (answering incorrectly while mastered)

Defaults are `pL0=0.25`, `pG=0.15`, `pS=0.10`, and `pT = 0.08 + 0.10 * learner_skill`. All probabilities are clamped to `[0.001, 0.999]`.

## Observation update

For an observation `correct`, the likelihoods are:

```text
P(correct | mastered)   = 1 - pS
P(correct | unmastered) = pG
P(wrong   | mastered)   = pS
P(wrong   | unmastered) = 1 - pG
```

Bayes update:

```text
posterior = P(observation | mastered) * pL0
            ---------------------------------------------
            P(observation | mastered) * pL0
            + P(observation | unmastered) * (1 - pL0)

pL_next = posterior + (1 - posterior) * pT
```

The new value is persisted as `pL0`; counters (`n_correct`, `n_wrong`, `updates`) support reports and misconception analysis. Every update is clamped, preventing numerical drift outside the probability interval.

## Diagnostic prior

A completed diagnostic computes per-topic observed accuracy `pc`. The initial report prior is:

```text
prior(topic) = clamp(sqrt(pc), 0.02, 0.98)
```

The square-root transform avoids making a small diagnostic overly punitive. Topics not yet updated by question-level BKT retain their seeded prior; topics already updated keep the observed BKT state.

## Personalization

After at least three observations, every third update may adapt guess/slip toward a persistent high error rate. This is intentionally a small, bounded personalization heuristic rather than a full parameter estimator. It runs locally and deterministically.

## Planning interaction

The planning module reads `mastery_summary` and course prerequisites. It topologically orders topics, detects cycles, and schedules learning/review actions. The learner model itself remains independent of the planner, so BKT unit tests can run with a plain in-memory student dictionary.

## Evaluation expectations

Core tests assert hand-calculated update behavior, monotonic improvement on repeated correct evidence, degradation after wrong evidence, valid probability bounds, diagnostic priors, weakest-topic ordering, and reset/empty-state behavior. Simulated student profiles exercise fast, average, and struggling trajectories separately from the real demo student.
