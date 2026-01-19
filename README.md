# Copilot Money CLI

Command-line interface for [Copilot Money](https://copilot.money), a personal finance app. Authenticate once and query accounts, transactions, holdings, and allocation data from your terminal.

> **Note:** This is an unofficial tool and is not affiliated with Copilot Money.

## Install

```bash
pip install copilot-money-cli
```

Or install from source:

```bash
git clone https://github.com/jayhickey/copilot-money-cli.git
cd copilot-money-cli
pip install -e .
```

## Quick start

```bash
copilot-money config init
# ✓ Saved refresh token from chrome
copilot-money accounts
# Accounts
# ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
# ┃ Name             ┃ Type       ┃ Balance      ┃
# ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
# │ Chase Checking   │ DEPOSITORY │ $4,210.12    │
# │ Fidelity IRA     │ INVESTMENT │ $28,450.33   │
# │ Amex Platinum    │ CREDIT     │ -$1,253.44   │
# └──────────────────┴────────────┴──────────────┘
```

## Commands

```bash
copilot-money refresh
# { "refreshed": ["conn_123", "conn_456", ...] }

copilot-money accounts --type CREDIT
# Accounts
# ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
# ┃ Name             ┃ Type       ┃ Balance      ┃
# ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
# │ Amex Platinum    │ CREDIT     │ -$1,253.44   │
# │ Student Loan     │ LOAN       │ -$8,450.00   │
# └──────────────────┴────────────┴──────────────┘

copilot-money accounts --json
# [
#   {
#     "id": "acc_123",
#     "name": "Chase Checking",
#     "balance": 4210.12,
#     "type": "DEPOSITORY"
#   }
# ]

copilot-money transactions --count 3
# Transactions
# ┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
# ┃ Date       ┃ Amount    ┃ Description        ┃
# ┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
# │ 2024-10-02 │ -$12.45   │ Coffee Shop        │
# │ 2024-10-01 │ -$54.20   │ Grocery Market     │
# │ 2024-09-30 │ $2,200.00 │ Payroll Deposit    │
# └────────────┴───────────┴────────────────────┘

copilot-money networth
# Net Worth
# ┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
# ┃ Category   ┃ Amount       ┃
# ┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
# │ Assets     │ $32,660.45   │
# │ Liabilities│ -$9,703.44   │
# │ Net Worth  │ $22,957.01   │
# └────────────┴──────────────┘

copilot-money holdings --group account
# Brokerage Account — $28,450.33 (100.0%)
# ┏━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┓
# ┃ Symbol ┃ Name                         ┃ Quantity ┃ Price    ┃ Value        ┃
# ┡━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━┩
# │ VTI    │ Vanguard Total Stock Market  │ 35.0000  │ $250.00  │ $8,750.00    │
# │ BND    │ Vanguard Total Bond Market   │ 55.0000  │ $72.00   │ $3,960.00    │
# └────────┴──────────────────────────────┴──────────┴──────────┴──────────────┘

copilot-money allocation
# Asset Allocation
# ┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
# ┃ Asset Class  ┃ Value        ┃ %            ┃
# ┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
# │ STOCKS       │ $18,000.00   │ 72.0%        │
# │   └ US       │ $12,600.00   │ 50.4% (70%)  │
# │   └ International │ $5,400.00│ 21.6% (30%) │
# │ BONDS        │ $7,000.00    │ 28.0%        │
# │ TOTAL        │ $25,000.00   │ 100%         │
# └──────────────┴──────────────┴──────────────┘
# Stock/Bond Ratio: 72/28
# US/International: 70/30

copilot-money config show
# Configuration
# ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
# ┃ Setting          ┃ Value                                                ┃
# ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
# │ Config path      │ /Users/you/.config/copilot-money/config.json         │
# │ Refresh token    │ ✓ set                                                │
# │ Token source     │ chrome                                               │
# │ Access token     │ ✓ cached                                             │
# │ Token valid      │ ✓ yes                                                │
# └──────────────────┴──────────────────────────────────────────────────────┘

copilot-money config init --source manual
# Enter refresh token: ********
# ✓ Saved refresh token from manual input
```

## Authentication

Configuration is stored at `~/.config/copilot-money/config.json`. The CLI can
auto-detect your Copilot Money refresh token from supported browsers on macOS.

- Auto-detect: `copilot-money config init`
- Explicit source: `copilot-money config init --source arc|chrome|safari|firefox`
- Manual entry: `copilot-money config init --source manual` or `--token "..."`

### Privacy Note

When using browser auto-detection, the CLI reads your browser's local IndexedDB 
storage to find your Copilot Money session token. This happens **locally on your 
machine** — no data is sent anywhere except to Copilot Money's API (which you're 
already authenticated with). The token is stored in `~/.config/copilot-money/config.json`.

If you prefer not to have the CLI access browser storage, use `--source manual` 
and paste your token directly.

## Requirements

- Python 3.10+
- macOS for browser token extraction (manual token entry works everywhere)

## License

MIT
