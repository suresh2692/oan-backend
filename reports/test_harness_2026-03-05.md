# OAN Backend Test Harness Report
**Date:** 2026-03-05
**Server:** ec2-user@98.90.156.237 (oan_backend container)
**Model:** qwen/qwen3.5-flash-02-23 via OpenRouter

## Results

| # | Category | Status | E2E ms | LLM ms | Tools | Tokens P/C/T | Response |
|---|----------|--------|--------|--------|-------|--------------|----------|
| 1 | crop_price | success | 3756.3 | 3544.44 | 1 | 8873/208/9081 | In Adama, Teff prices vary by variety as of February 26, 202... |
| 2 | livestock_price | success | 2956.1 | 2778.44 | 1 | 8463/195/8658 | Oxen in Dubti are trading around 70,000 to 75,000 Birr as of... |
| 3 | rag_knowledge | success | 11398.0 | 11212.68 | 1 | 10120/160/10280 | For teff, the recommended spacing when sowing in rows is 20... |
| 4 | rag_knowledge | success | 9782.8 | 9603.09 | 1 | 10381/209/10590 | Mastitis is an inflammation of the udder caused by bacterial... |
| 5 | rag_knowledge | success | 9521.4 | 9516.42 | 1 | 10898/269/11167 | To prepare land for maize, start by plowing the field 3 to 4... |
| 6 | weather | success | 32054.2 | 32047.84 | 1 | 8314/123/8437 | I couldn't find weather data for Adama. The location might n... |
| 7 | market_list | success | 3340.3 | 3114.03 | 1 | 8836/161/8997 | Here are the crops available in Bishoftu: Avocado, Banana,... |
| 8 | greeting | success | 1864.6 | 1859.68 | 0 | 4149/170/4319 | Hello! I'm AgriHelp, your agricultural assistant. I can help... |

## Totals

| Metric | Value |
|--------|-------|
| Pass rate | 8/8 (100%) |
| Avg E2E latency | 9,334 ms |
| Avg LLM latency | 9,210 ms |
| Total tool calls | 7 |
| Total prompt tokens | 70,034 |
| Total completion tokens | 1,495 |
| Total tokens | 71,529 |

## Notes
- Token tracking confirmed working via `stream_options={"include_usage": True}` with OpenRouter
- Usage chunk arrives with empty `choices[]` — must be captured before the `if not chunk.choices: continue` guard
- Weather query (test #6) had elevated latency (32s) due to geocoding + forecast API chain
- Greeting query (test #8) uses 0 tools as expected
