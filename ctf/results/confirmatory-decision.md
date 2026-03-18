# OpenCLI/jelp Decision Memo

- Baseline: `help-only-primed`
- Candidate: `jelp-primed-incremental`
- Confidence interval: `90%` bootstrap
- Bootstrap samples: `4000`
- Base seed: `42`

Interpretation note:

- Columns ending in `_obs` come directly from observed paired runs.
- Columns ending in `_ci_boot` are bootstrap uncertainty estimates.
- `borderline=yes` means at least one bootstrap CI interval crosses a decision threshold, so classification may be sensitive to modest variation.

## Per-model mode summary

### gpt-4.1-mini

| mode                        |   n | success | mean_cmds | median_cmds | mean_errors | mean_total_tok |
| --------------------------- | --: | ------: | --------: | ----------: | ----------: | -------------: |
| help-only                   |  24 |   95.8% |     6.958 |       6.000 |       1.125 |         5352.0 |
| (B) help-only-primed        |  24 |  100.0% |     5.250 |       5.000 |       0.625 |         3928.8 |
| jelp-primed-full            |  24 |  100.0% |     5.292 |       5.000 |       1.417 |         9569.7 |
| (C) jelp-primed-incremental |  24 |   95.8% |     5.125 |       5.000 |       1.375 |         9277.1 |
| jelp-primed-useful          |  24 |  100.0% |     5.167 |       5.000 |       1.083 |         9085.7 |

### gpt-5-mini

| mode                        |   n | success | mean_cmds | median_cmds | mean_errors | mean_total_tok |
| --------------------------- | --: | ------: | --------: | ----------: | ----------: | -------------: |
| help-only                   |  24 |   91.7% |     5.833 |       6.000 |       0.292 |         8148.3 |
| (B) help-only-primed        |  24 |   91.7% |     4.625 |       4.500 |       0.250 |         6454.1 |
| jelp-primed-full            |  24 |   79.2% |     2.375 |       3.000 |       0.000 |         6298.9 |
| (C) jelp-primed-incremental |  24 |  100.0% |     3.333 |       3.000 |       0.292 |         7422.5 |
| jelp-primed-useful          |  24 |   87.5% |     2.833 |       3.000 |       0.250 |         7141.8 |

## Pooled mode summary

| mode                        |   n | success | mean_cmds | median_cmds | mean_errors | mean_total_tok |
| --------------------------- | --: | ------: | --------: | ----------: | ----------: | -------------: |
| help-only                   |  48 |   93.8% |     6.396 |       6.000 |       0.708 |         6750.2 |
| (B) help-only-primed        |  48 |   95.8% |     4.938 |       5.000 |       0.438 |         5191.5 |
| jelp-primed-full            |  48 |   89.6% |     3.833 |       3.000 |       0.708 |         7934.3 |
| (C) jelp-primed-incremental |  48 |   97.9% |     4.229 |       4.000 |       0.833 |         8349.8 |
| jelp-primed-useful          |  48 |   93.8% |     4.000 |       4.000 |       0.667 |         8113.8 |

## Evidence accounting

| scope        | observed_pairs_used | expected_pairs | pair_coverage | baseline_only | candidate_only | bootstrap_samples |  seed |
| ------------ | ------------------: | -------------: | ------------: | ------------: | -------------: | ----------------: | ----: |
| gpt-4.1-mini |                  24 |             24 |        100.0% |             0 |              0 |              4000 |    42 |
| gpt-5-mini   |                  24 |             24 |        100.0% |             0 |              0 |              4000 |    43 |
| all-models   |                  48 |             48 |        100.0% |             0 |              0 |              4000 | 10042 |

## Per-model decision metrics

| model        | observed_pairs_used | expected_pairs | pair_coverage | success_delta_pp_obs | median_cmd_delta_obs | token_ratio_obs | success_ci_boot | median_cmd_ci_boot | token_ratio_ci_boot | success_ci_width | median_cmd_ci_width | token_ratio_ci_width | borderline | ci_favorable | verdict                  |
| ------------ | ------------------: | -------------: | ------------: | -------------------: | -------------------: | --------------: | --------------- | ------------------ | ------------------- | ---------------: | ------------------: | -------------------: | ---------- | ------------ | ------------------------ |
| gpt-4.1-mini |                  24 |             24 |        100.0% |               -4.167 |                0.000 |           2.361 | [-12.50, 0.000] | [-1.000, 0.500]    | [1.953, 2.896]      |            12.50 |               1.500 |                0.943 | yes        | no           | No net benefit currently |
| gpt-5-mini   |                  24 |             24 |        100.0% |                8.333 |               -1.000 |           1.150 | [0.000, 16.67]  | [-2.000, -1.000]   | [1.008, 1.311]      |            16.67 |               1.000 |                0.303 | yes        | yes          | Net benefit now          |

## Pooled decision metrics

| scope      | observed_pairs_used | expected_pairs | pair_coverage | success_delta_pp_obs | median_cmd_delta_obs | token_ratio_obs | success_ci_boot | median_cmd_ci_boot | token_ratio_ci_boot | success_ci_width | median_cmd_ci_width | token_ratio_ci_width | borderline | ci_favorable | verdict                               |
| ---------- | ------------------: | -------------: | ------------: | -------------------: | -------------------: | --------------: | --------------- | ------------------ | ------------------- | ---------------: | ------------------: | -------------------: | ---------- | ------------ | ------------------------------------- |
| all-models |                  48 |             48 |        100.0% |                2.083 |               -1.000 |           1.608 | [-4.167, 8.333] | [-1.000, -1.000]   | [1.385, 1.878]      |            12.50 |               0.000 |                0.493 | yes        | no           | Promising, strategy adjustment needed |

## Cost adjustment impact

| scope        | raw_verdict_no_cost                   | cost_adjusted_verdict                 | changed_by_cost | token_ratio_obs | token_ratio_threshold | reason |
| ------------ | ------------------------------------- | ------------------------------------- | --------------- | --------------: | --------------------: | ------ |
| gpt-4.1-mini | No net benefit currently              | No net benefit currently              | no              |           2.361 |                  1.75 | -      |
| gpt-5-mini   | Net benefit now                       | Net benefit now                       | no              |           1.150 |                  1.75 | -      |
| all-models   | Promising, strategy adjustment needed | Promising, strategy adjustment needed | no              |           1.608 |                  1.75 | -      |

## Final verdict

- `model-sensitive / not yet general`

## Decision drivers

- `all-models`: observed pairs `48/48` (coverage `100.0%`)
- `success_delta_pp_obs=2.083` vs threshold `>= 0.0`: `pass`; `success_ci_boot=[-4.167, 8.333]`
- `median_cmd_delta_obs=-1.000` vs threshold `<= -0.5`: `pass`; `median_cmd_ci_boot=[-1.000, -1.000]`
- `token_ratio_obs=1.608` vs threshold `<= 1.75`: `pass`; `token_ratio_ci_boot=[1.385, 1.878]`
- `ci_favorable` gate (`success_ci_low >= 0.0` and `cmd_ci_high <= -0.5`): `fail` (success part: `fail`, command part: `pass`)
- `borderline`: `yes` (success_ci includes threshold 0.0pp; token_ratio_ci includes threshold 1.75)
- Derived verdict: `Promising, strategy adjustment needed`

### Per-model drivers

**gpt-4.1-mini**

- observed pairs `24/24` (coverage `100.0%`)
- `success_delta_pp_obs=-4.167` vs threshold `>= 0.0`: `fail`; `success_ci_boot=[-12.50, 0.000]`
- `median_cmd_delta_obs=0.000` vs threshold `<= -0.5`: `fail`; `median_cmd_ci_boot=[-1.000, 0.500]`
- `token_ratio_obs=2.361` vs threshold `<= 1.75`: `fail`; `token_ratio_ci_boot=[1.953, 2.896]`
- `ci_favorable` gate (`success_ci_low >= 0.0` and `cmd_ci_high <= -0.5`): `fail` (success part: `fail`, command part: `fail`)
- `borderline`: `yes` (success_ci includes threshold 0.0pp; median_cmd_ci includes threshold -0.5)
- Derived verdict: `No net benefit currently`

**gpt-5-mini**

- observed pairs `24/24` (coverage `100.0%`)
- `success_delta_pp_obs=8.333` vs threshold `>= 0.0`: `pass`; `success_ci_boot=[0.000, 16.67]`
- `median_cmd_delta_obs=-1.000` vs threshold `<= -0.5`: `pass`; `median_cmd_ci_boot=[-2.000, -1.000]`
- `token_ratio_obs=1.150` vs threshold `<= 1.75`: `pass`; `token_ratio_ci_boot=[1.008, 1.311]`
- `ci_favorable` gate (`success_ci_low >= 0.0` and `cmd_ci_high <= -0.5`): `pass` (success part: `pass`, command part: `pass`)
- `borderline`: `yes` (success_ci includes threshold 0.0pp)
- Derived verdict: `Net benefit now`

## Caveats

- Verdict is cost-adjusted for current model behavior and prompting strategy.
- Token ratio is point-estimated from mean total tokens in paired runs.
- CIs are bootstrap estimates; low pair counts widen uncertainty.
