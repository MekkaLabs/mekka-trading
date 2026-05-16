---
name: risk_small_cap_advisor
type: risk
triggers: [SMALL_CAP]
---
## Small Cap Risk Advisory

Asset is classified as **SMALL_CAP** — special risk rules apply.

### Risk Rules (SMALL_CAP)
- Maximum leverage: **2×** (Batman gate 5c enforces this automatically)
- Minimum liquidity check: reject if 24h volume < $5M
- Slippage tolerance: wider — small caps have thin order books
- Exit strategy: plan the exit before entry (illiquidity risk)

### Trading Considerations
- Higher manipulation risk (pump-and-dump patterns)
- News-driven volatility is extreme — check for catalysts before entry
- Correlation to BTC is often high in risk-off but breaks in risk-on
- Recommended holding period: shorter than large/mid cap positions

### Confidence Requirements
- LONG small cap: confidence >= 0.75 required (higher bar than large cap)
- SHORT small cap: confidence >= 0.80 (shorting illiquid = high risk)
