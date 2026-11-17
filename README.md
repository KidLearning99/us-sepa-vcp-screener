# US SEPA+VCP Screener

Automated daily screener for US stocks (NYSE, NASDAQ, NYSE American) using Minervini's SEPA trend template, VCP scoring, stage classification and basic fundamentals. US sibling of [asx-sepa-vcp-screener](https://github.com/KidLearning99/asx-sepa-vcp-screener).

- **Universe:** US common stocks over US$5B market cap (from the Nasdaq screener API; preferreds, warrants, units and rights excluded). Change with the `MIN_MARKET_CAP` env var. `data/us_universe.txt` is a fallback snapshot.
- **Data:** Yahoo Finance via `yfinance`.
- **Schedule:** GitHub Actions, after the US close and mid-session, Mon-Fri. Output is deployed to the `gh-pages` branch.

Educational and research use only. Not financial advice. Prices in USD.
