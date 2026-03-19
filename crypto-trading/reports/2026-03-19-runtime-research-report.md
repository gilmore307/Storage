# Crypto Trading Runtime Research Report

Date: 2026-03-19

## Summary

- Row count: 230
- Forward field: fwd_ret_1h
- Forward fields: fwd_ret_15m, fwd_ret_1h, fwd_ret_4h

## Key takeaway

- The research pipeline successfully converted existing `regime-local-history.jsonl` runtime artifacts into a research dataset and report.
- This first report is structurally useful, but forward-return metrics are still `null` because the replay path does not yet attach a future price series for label generation.
- So this version supports behavior analysis (which strategy tends to trigger in which regime), but not yet edge / profitability comparison.

## Regime Quality

### trend

- sample_count: 112
- avg_confidence: 0.8810209010475196
- avg_fwd_ret_15m: None
- positive_rate_fwd_ret_15m: None
- avg_fwd_ret_1h: None
- positive_rate_fwd_ret_1h: None
- avg_fwd_ret_4h: None
- positive_rate_fwd_ret_4h: None

### compression

- sample_count: 113
- avg_confidence: 0.7612672964430963
- avg_fwd_ret_15m: None
- positive_rate_fwd_ret_15m: None
- avg_fwd_ret_1h: None
- positive_rate_fwd_ret_1h: None
- avg_fwd_ret_4h: None
- positive_rate_fwd_ret_4h: None

### chaotic

- sample_count: 5
- avg_confidence: 0.6787624290837664
- avg_fwd_ret_15m: None
- positive_rate_fwd_ret_15m: None
- avg_fwd_ret_1h: None
- positive_rate_fwd_ret_1h: None
- avg_fwd_ret_4h: None
- positive_rate_fwd_ret_4h: None

## Strategy × Regime Matrix

### Regime: trend

#### Strategy: trend

- sample_count: 112
- enter_rate: 0.6160714285714286
- arm_rate: 0.38392857142857145
- watch_rate: 0.0
- hold_rate: 0.0
- avg_score: 2.392857142857143
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: range

- sample_count: 112
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 2.4285714285714284
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: compression

- sample_count: 112
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 1.2767857142857142
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: crowded

- sample_count: 112
- enter_rate: 0.0
- arm_rate: 0.10714285714285714
- watch_rate: 0.8928571428571429
- hold_rate: 0.0
- avg_score: 0.6964285714285714
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: shock

- sample_count: 112
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 0.22321428571428573
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

### Regime: compression

#### Strategy: trend

- sample_count: 113
- enter_rate: 0.0
- arm_rate: 0.2831858407079646
- watch_rate: 0.7168141592920354
- hold_rate: 0.0
- avg_score: 0.5663716814159292
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: range

- sample_count: 113
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 1.4513274336283186
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: compression

- sample_count: 113
- enter_rate: 0.0
- arm_rate: 0.02654867256637168
- watch_rate: 0.9734513274336283
- hold_rate: 0.0
- avg_score: 0.19469026548672566
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: crowded

- sample_count: 113
- enter_rate: 0.0
- arm_rate: 0.017699115044247787
- watch_rate: 0.9823008849557522
- hold_rate: 0.0
- avg_score: 1.0176991150442478
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: shock

- sample_count: 113
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 0.07079646017699115
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

### Regime: chaotic

#### Strategy: trend

- sample_count: 5
- enter_rate: 0.6
- arm_rate: 0.0
- watch_rate: 0.4
- hold_rate: 0.0
- avg_score: 2.6
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: range

- sample_count: 5
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 3.0
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: compression

- sample_count: 5
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 2.0
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: crowded

- sample_count: 5
- enter_rate: 0.0
- arm_rate: 1.0
- watch_rate: 0.0
- hold_rate: 0.0
- avg_score: 2.0
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

#### Strategy: shock

- sample_count: 5
- enter_rate: 0.0
- arm_rate: 0.0
- watch_rate: 1.0
- hold_rate: 0.0
- avg_score: 0.0
- avg_forward_return: None
- avg_enter_forward_return: None
- avg_arm_forward_return: None
- positive_forward_rate: None

## Interpretation Notes

- In the observed `trend` samples, the `trend` executor is the only strategy that meaningfully triggers `enter` and `arm` actions at scale.
- `range` mostly stays in `watch` during `trend` samples, which is directionally consistent with the intended design.
- `crowded` occasionally arms in `trend` samples, suggesting it may be surfacing potential fade setups inside strong trend contexts.
- `shock` is effectively inactive in these runtime samples, matching the earlier concern that it is the least aligned with the current execution architecture.

## Current limitation

- To make this report useful for strategy retention / deletion decisions, the next step is attaching forward price labels (`fwd_ret_15m`, `fwd_ret_1h`, `fwd_ret_4h`) to replayed runtime rows.
- Once that is added, this same report structure can start answering not only who triggers, but who actually performs.