from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional, TypeVar

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from copilot_money.api import CopilotAPI
from copilot_money.config import (
    ARC_LEVELDB_PATH,
    CHROME_LEVELDB_PATH,
    CONFIG_FILE,
    CopilotConfig,
    FIREFOX_PROFILES_DIR,
    SAFARI_LOCALSTORAGE_DIR,
    get_source_path,
    get_token_auto,
    get_token_from_arc,
    get_token_from_chrome,
    get_token_from_firefox,
    get_token_from_safari,
    load_config,
    save_config,
)
from copilot_money.models import Account, AccountType, Holding, SecurityType, Transaction

app = typer.Typer(help="Copilot Money CLI")
config_app = typer.Typer(help="Manage configuration")
app.add_typer(config_app, name="config")
console = Console()

CONFIG_SOURCES = {"arc", "chrome", "safari", "firefox", "manual"}
T = TypeVar("T")


def resolve_token_from_source(source: str) -> Optional[str]:
    source = source.lower()
    if source == "arc":
        return get_token_from_arc()
    if source == "chrome":
        return get_token_from_chrome()
    if source == "safari":
        return get_token_from_safari()
    if source == "firefox":
        return get_token_from_firefox()
    return None


@contextmanager
def api_client() -> Iterable[CopilotAPI]:
    api = CopilotAPI()
    try:
        yield api
    finally:
        api.close()


def run_api_action(action: Callable[[CopilotAPI], T]) -> T:
    try:
        with api_client() as api:
            return action(api)
    except RuntimeError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        console.print(
            f"[red]✗[/red] API request failed (status {status}). Try `copilot config refresh`."
        )
        raise typer.Exit(code=1)
    except httpx.HTTPError as exc:
        console.print(f"[red]✗[/red] Network error: {exc}")
        raise typer.Exit(code=1)


def format_currency(amount: float) -> Text:
    value = f"${abs(amount):,.2f}"
    if amount < 0:
        return Text(f"-{value}", style="red")
    return Text(value, style="green")


def load_accounts(api: CopilotAPI) -> list[Account]:
    query = "{ accounts { id name balance type } }"
    data = api.query(query)
    return [Account.model_validate(item) for item in data.get("accounts", [])]


def load_transactions(api: CopilotAPI, count: int) -> list[Transaction]:
    query = (
        "{ transactions(first: "
        + str(count)
        + ") { edges { node { id name amount date } } } }"
    )
    data = api.query(query)
    edges = data.get("transactions", {}).get("edges", [])
    return [Transaction.model_validate(edge.get("node", {})) for edge in edges]


def load_holdings(api: CopilotAPI) -> tuple[list[Holding], dict[str, Account]]:
    query = """{ 
        holdings { 
            id 
            quantity 
            accountId 
            security { 
                symbol 
                name 
                type 
                currentPrice 
            } 
        } 
        accounts {
            id
            name
            balance
            type
        }
    }"""
    data = api.query(query)
    holdings = [Holding.model_validate(h) for h in data.get("holdings", [])]
    accounts = {a["id"]: Account.model_validate(a) for a in data.get("accounts", [])}
    return holdings, accounts


@app.command()
def accounts(
    account_type: Optional[AccountType] = typer.Option(
        None, "--type", help="Filter by account type"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show accounts."""
    accounts_list = run_api_action(load_accounts)
    if account_type:
        accounts_list = [acct for acct in accounts_list if acct.type == account_type]

    if json_output:
        typer.echo(json.dumps([acct.model_dump() for acct in accounts_list], indent=2))
        return

    table = Table(title="Accounts")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Balance", justify="right")
    for account in accounts_list:
        balance = account.balance
        if account.type in {AccountType.CREDIT, AccountType.LOAN}:
            balance = -abs(balance)
        table.add_row(account.name, account.type.value, format_currency(balance))
    console.print(table)


@app.command()
def transactions(
    count: int = typer.Option(20, "-n", "--count", help="Number of transactions"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show recent transactions."""
    transactions_list = run_api_action(lambda api: load_transactions(api, count))

    if json_output:
        typer.echo(
            json.dumps([item.model_dump() for item in transactions_list], indent=2, default=str)
        )
        return

    table = Table(title="Transactions")
    table.add_column("Date", style="dim")
    table.add_column("Amount", justify="right")
    table.add_column("Description")
    for txn in transactions_list:
        table.add_row(str(txn.date), format_currency(txn.amount), txn.name)
    console.print(table)


@app.command()
def networth() -> None:
    """Show net worth summary."""
    accounts_list = run_api_action(load_accounts)

    assets = sum(
        acct.balance
        for acct in accounts_list
        if acct.type not in {AccountType.CREDIT, AccountType.LOAN}
    )
    liabilities = sum(
        abs(acct.balance)
        for acct in accounts_list
        if acct.type in {AccountType.CREDIT, AccountType.LOAN}
    )
    net_worth = assets - liabilities

    table = Table(title="Net Worth")
    table.add_column("Category")
    table.add_column("Amount", justify="right")
    table.add_row("Assets", format_currency(assets))
    table.add_row("Liabilities", format_currency(-liabilities))
    table.add_row("Net Worth", format_currency(net_worth))
    console.print(table)


@app.command()
def holdings(
    security_type: Optional[SecurityType] = typer.Option(
        None, "--type", "-t", help="Filter by security type (EQUITY, ETF, MUTUAL_FUND, CRYPTO, BOND, OTHER)"
    ),
    group_by: str = typer.Option(
        "type", "--group", "-g", help="Group by: type, account, symbol, or none"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show investment holdings with current values."""
    holdings_list, _accounts = run_api_action(load_holdings)

    # Filter by type if specified
    if security_type:
        holdings_list = [h for h in holdings_list if h.security.type == security_type]

    # Calculate values
    holdings_data = []
    for h in holdings_list:
        acct = accounts.get(h.account_id)
        holdings_data.append({
            "symbol": h.security.symbol,
            "name": h.security.name,
            "type": h.security.type.value,
            "quantity": h.quantity,
            "price": h.security.current_price or 0,
            "value": h.value,
            "account": acct.name if acct else "Unknown",
            "account_id": h.account_id,
        })

    if json_output:
        typer.echo(json.dumps(holdings_data, indent=2))
        return

    # Sort by value descending
    holdings_data.sort(key=lambda x: -x["value"])

    if group_by == "none":
        # Flat list
        table = Table(title="Holdings")
        table.add_column("Symbol", style="bold")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Quantity", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("Account")
        for h in holdings_data:
            if h["value"] > 0.01:
                table.add_row(
                    h["symbol"],
                    h["name"][:30],
                    h["type"],
                    f"{h['quantity']:,.4f}",
                    f"${h['price']:,.2f}",
                    format_currency(h["value"]),
                    h["account"][:20],
                )
        console.print(table)
    else:
        # Group by type, account, or symbol
        grouped: dict[str, list[dict]] = {}
        for h in holdings_data:
            if group_by == "type":
                key = h["type"]
            elif group_by == "account":
                key = h["account"]
            elif group_by == "symbol":
                key = h["symbol"]
            else:
                key = h["type"]
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(h)

        # Sort groups by total value
        group_totals = [(k, sum(h["value"] for h in v)) for k, v in grouped.items()]
        group_totals.sort(key=lambda x: -x[1])

        total = sum(t[1] for t in group_totals)

        for group_name, group_total in group_totals:
            if group_total < 0.01:
                continue
            pct = (group_total / total * 100) if total > 0 else 0
            table = Table(title=f"{group_name} — ${group_total:,.2f} ({pct:.1f}%)")
            table.add_column("Symbol", style="bold")
            table.add_column("Name")
            table.add_column("Quantity", justify="right")
            table.add_column("Price", justify="right")
            table.add_column("Value", justify="right")
            if group_by != "account":
                table.add_column("Account")

            items = sorted(grouped[group_name], key=lambda x: -x["value"])
            for h in items:
                if h["value"] > 0.01:
                    row = [
                        h["symbol"],
                        h["name"][:35],
                        f"{h['quantity']:,.4f}",
                        f"${h['price']:,.2f}",
                        format_currency(h["value"]),
                    ]
                    if group_by != "account":
                        row.append(h["account"][:20])
                    table.add_row(*row)
            console.print(table)
            console.print()

        # Summary table
        summary = Table(title="Summary")
        summary.add_column("Category")
        summary.add_column("Value", justify="right")
        summary.add_column("%", justify="right")
        for group_name, group_total in group_totals:
            if group_total > 0.01:
                pct = (group_total / total * 100) if total > 0 else 0
                summary.add_row(group_name, format_currency(group_total), f"{pct:.1f}%")
        summary.add_row("TOTAL", format_currency(total), "100%", style="bold")
        console.print(summary)


# Asset class mappings for allocation breakdown
US_STOCK_SYMBOLS = {"VOO", "VTI", "FZROX", "NVDA", "GOOG", "AAPL", "GOOGL", "MSFT", "AMZN", "META", "TSLA", "SPY", "IVV", "SCHB", "ITOT", "SWTSX"}
INTL_STOCK_SYMBOLS = {"VXUS", "FZILX", "IXUS", "VEA", "VWO", "IEFA", "EFA", "EEM", "SCHF", "SWISX"}
BOND_SYMBOLS = {"VGIT", "SGOV", "BND", "BNDX", "VBTLX", "AGG", "TLT", "IEF", "SHY", "VTIP", "SCHZ"}
CASH_SYMBOLS = {"SPAXX", "FDRXX", "VMFXX", "SWVXX"}
CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL"}

# Target date funds - approximate allocations by year
# Format: (stock_pct, us_stock_pct_of_stocks) - most TDFs are ~60% US, 40% intl for stocks
TARGET_DATE_ALLOC = {
    "2055": (0.90, 0.60), "2060": (0.90, 0.60), "2065": (0.90, 0.60),
    "2050": (0.88, 0.60), "2045": (0.85, 0.60), "2040": (0.80, 0.60),
    "2035": (0.75, 0.60), "2030": (0.65, 0.60), "2025": (0.55, 0.60),
    "2020": (0.45, 0.60), "2015": (0.35, 0.60), "2010": (0.30, 0.60),
}


def classify_asset(symbol: str, name: str, sec_type: str) -> tuple[str, float, float]:
    """Classify a holding into asset class.
    
    Returns: (class, stock_pct, us_pct_of_stocks)
    - class: STOCKS_US, STOCKS_INTL, BONDS, CRYPTO, CASH, OTHER, or TARGET_DATE
    - stock_pct: percentage that is stocks (for target date funds)
    - us_pct_of_stocks: percentage of stock portion that is US (for target date funds)
    """
    symbol_upper = symbol.upper()
    name_upper = name.upper()
    
    # Check for target date funds first
    for year, (stock_pct, us_pct) in TARGET_DATE_ALLOC.items():
        if year in name_upper or f"TARGET {year}" in name_upper:
            return "TARGET_DATE", stock_pct, us_pct
    
    if symbol_upper in US_STOCK_SYMBOLS:
        return "STOCKS_US", 1.0, 1.0
    if symbol_upper in INTL_STOCK_SYMBOLS:
        return "STOCKS_INTL", 1.0, 0.0
    if symbol_upper in BOND_SYMBOLS:
        return "BONDS", 0.0, 0.0
    if symbol_upper in CASH_SYMBOLS:
        return "CASH", 0.0, 0.0
    if symbol_upper in CRYPTO_SYMBOLS or sec_type == "CRYPTO":
        return "CRYPTO", 0.0, 0.0
    
    # Heuristics based on name
    if any(kw in name_upper for kw in ["TREASURY", "BOND", "FIXED INCOME"]):
        return "BONDS", 0.0, 0.0
    if any(kw in name_upper for kw in ["INTERNATIONAL", "INTL", "FOREIGN", "EMERGING", "EX-US", "EX US"]):
        return "STOCKS_INTL", 1.0, 0.0
    if any(kw in name_upper for kw in ["S&P 500", "S&P500", "TOTAL MARKET", "TOTAL STOCK"]):
        return "STOCKS_US", 1.0, 1.0
    if any(kw in name_upper for kw in ["MONEY MARKET", "CASH"]):
        return "CASH", 0.0, 0.0
    
    # Default based on security type
    if sec_type == "EQUITY":
        return "STOCKS_US", 1.0, 1.0  # Assume US for individual stocks
    if sec_type == "BOND":
        return "BONDS", 0.0, 0.0
    
    return "OTHER", 0.5, 0.5  # Unknown


@app.command()
def allocation(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show asset allocation breakdown (stocks vs bonds vs crypto, US vs international)."""
    holdings_list, accounts = run_api_action(load_holdings)

    # Classify and calculate
    totals = {
        "STOCKS_US": 0.0, 
        "STOCKS_INTL": 0.0, 
        "BONDS": 0.0, 
        "CRYPTO": 0.0, 
        "CASH": 0.0, 
        "OTHER": 0.0
    }
    details: dict[str, list[dict]] = {k: [] for k in totals}
    
    for h in holdings_list:
        value = h.value
        if value <= 0:
            continue
            
        asset_class, stock_pct, us_pct = classify_asset(
            h.security.symbol, 
            h.security.name, 
            h.security.type.value
        )
        
        if asset_class == "TARGET_DATE":
            # Split target date funds into US stocks, intl stocks, and bonds
            stock_value = value * stock_pct
            bond_value = value * (1 - stock_pct)
            us_stock_value = stock_value * us_pct
            intl_stock_value = stock_value * (1 - us_pct)
            
            totals["STOCKS_US"] += us_stock_value
            totals["STOCKS_INTL"] += intl_stock_value
            totals["BONDS"] += bond_value
            
            details["STOCKS_US"].append({
                "symbol": h.security.symbol,
                "name": h.security.name,
                "value": us_stock_value,
                "note": f"({stock_pct*us_pct:.0%} of fund)"
            })
            details["STOCKS_INTL"].append({
                "symbol": h.security.symbol,
                "name": h.security.name,
                "value": intl_stock_value,
                "note": f"({stock_pct*(1-us_pct):.0%} of fund)"
            })
            details["BONDS"].append({
                "symbol": h.security.symbol,
                "name": h.security.name,
                "value": bond_value,
                "note": f"({1-stock_pct:.0%} of fund)"
            })
        else:
            totals[asset_class] += value
            details[asset_class].append({
                "symbol": h.security.symbol,
                "name": h.security.name,
                "value": value,
                "note": ""
            })

    total = sum(totals.values())
    total_stocks = totals["STOCKS_US"] + totals["STOCKS_INTL"]
    
    if json_output:
        result = {
            "total": total,
            "allocation": {k: {"value": v, "percent": v/total*100 if total else 0} 
                          for k, v in totals.items() if v > 0},
            "summary": {
                "stocks": total_stocks,
                "stocks_us": totals["STOCKS_US"],
                "stocks_intl": totals["STOCKS_INTL"],
                "bonds": totals["BONDS"],
                "crypto": totals["CRYPTO"],
            },
            "details": {k: v for k, v in details.items() if v}
        }
        typer.echo(json.dumps(result, indent=2))
        return

    # Summary table
    summary = Table(title="Asset Allocation")
    summary.add_column("Asset Class")
    summary.add_column("Value", justify="right")
    summary.add_column("%", justify="right")
    
    # Show stocks with US/Intl breakdown
    if total_stocks > 0.01:
        stocks_pct = (total_stocks / total * 100) if total else 0
        summary.add_row("STOCKS", format_currency(total_stocks), f"{stocks_pct:.1f}%", style="bold")
        
        us_pct = (totals["STOCKS_US"] / total * 100) if total else 0
        intl_pct = (totals["STOCKS_INTL"] / total * 100) if total else 0
        us_of_stocks = (totals["STOCKS_US"] / total_stocks * 100) if total_stocks else 0
        intl_of_stocks = (totals["STOCKS_INTL"] / total_stocks * 100) if total_stocks else 0
        
        summary.add_row("  └ US", format_currency(totals["STOCKS_US"]), f"{us_pct:.1f}% ({us_of_stocks:.0f}% of stocks)")
        summary.add_row("  └ International", format_currency(totals["STOCKS_INTL"]), f"{intl_pct:.1f}% ({intl_of_stocks:.0f}% of stocks)")
    
    for asset_class in ["BONDS", "CRYPTO", "CASH", "OTHER"]:
        value = totals[asset_class]
        if value > 0.01:
            pct = (value / total * 100) if total else 0
            summary.add_row(asset_class, format_currency(value), f"{pct:.1f}%")
    
    summary.add_row("TOTAL", format_currency(total), "100%", style="bold")
    console.print(summary)
    console.print()
    
    # Ratios
    stock_bond_total = total_stocks + totals["BONDS"]
    if stock_bond_total > 0:
        stock_pct = total_stocks / stock_bond_total * 100
        bond_pct = totals["BONDS"] / stock_bond_total * 100
        console.print(f"[bold]Stock/Bond Ratio:[/bold] {stock_pct:.0f}/{bond_pct:.0f}")
    
    if total_stocks > 0:
        us_ratio = totals["STOCKS_US"] / total_stocks * 100
        intl_ratio = totals["STOCKS_INTL"] / total_stocks * 100
        console.print(f"[bold]US/International:[/bold] {us_ratio:.0f}/{intl_ratio:.0f}")


@config_app.command("show")
def config_show() -> None:
    """Show configuration status."""
    config = load_config()

    table = Table(title="Configuration")
    table.add_column("Setting")
    table.add_column("Value")

    table.add_row("Config path", str(CONFIG_FILE))
    table.add_row("Arc LevelDB", str(ARC_LEVELDB_PATH))
    table.add_row("Chrome LevelDB", str(CHROME_LEVELDB_PATH))
    table.add_row("Safari LocalStorage", str(SAFARI_LOCALSTORAGE_DIR))
    table.add_row("Firefox Profiles", str(FIREFOX_PROFILES_DIR))
    table.add_row("Refresh token", "✓ set" if config.refresh_token else "✗ missing")
    table.add_row("Token source", config.source or "none")
    table.add_row("Source path", config.source_path or "n/a")
    table.add_row("Access token", "✓ cached" if config.access_token else "✗ not cached")

    if config.expires_at:
        expires = datetime.fromtimestamp(config.expires_at, tz=timezone.utc)
        table.add_row("Expires at", expires.strftime("%Y-%m-%d %H:%M:%S UTC"))
    else:
        table.add_row("Expires at", "n/a")

    table.add_row("Token valid", "✓ yes" if config.is_access_token_valid() else "✗ no (will refresh)")
    console.print(table)


@config_app.command("init")
def config_init(
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Token source: arc, chrome, safari, firefox, manual",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="Refresh token to save directly",
    ),
) -> None:
    """Initialize configuration with a refresh token."""
    source_value = source.lower() if source else None

    if token:
        config = CopilotConfig(refresh_token=token, source="manual")
        save_config(config)
        console.print("[green]✓[/green] Saved refresh token from manual input")
        return

    if source_value and source_value not in CONFIG_SOURCES:
        console.print("[red]✗[/red] Invalid source. Use arc, chrome, safari, firefox, or manual.")
        raise typer.Exit(code=1)

    if source_value == "manual":
        manual_token = typer.prompt("Enter refresh token", hide_input=True)
        config = CopilotConfig(refresh_token=manual_token, source="manual")
        save_config(config)
        console.print("[green]✓[/green] Saved refresh token from manual input")
        return

    if source_value:
        fetched_token = resolve_token_from_source(source_value)
        if not fetched_token:
            console.print(f"[red]✗[/red] Could not find token for source: {source_value}")
            raise typer.Exit(code=1)
        config = CopilotConfig(
            refresh_token=fetched_token,
            source=source_value,
            source_path=get_source_path(source_value),
        )
        save_config(config)
        console.print(f"[green]✓[/green] Saved refresh token from {source_value}")
        return

    fetched_token, detected_source = get_token_auto()
    if not fetched_token or not detected_source:
        console.print("[red]✗[/red] Could not auto-detect a refresh token")
        raise typer.Exit(code=1)
    config = CopilotConfig(
        refresh_token=fetched_token,
        source=detected_source,
        source_path=get_source_path(detected_source),
    )
    save_config(config)
    console.print(f"[green]✓[/green] Saved refresh token from {detected_source}")


@config_app.command("refresh")
def config_refresh() -> None:
    """Re-fetch refresh token from the saved source."""
    config = load_config()

    if config.source == "manual":
        console.print("[yellow]![/yellow] Manual source configured; re-run init to update.")
        return

    if config.source:
        fetched_token = resolve_token_from_source(config.source)
        if fetched_token:
            config.refresh_token = fetched_token
            config.source_path = get_source_path(config.source)
            save_config(config)
            console.print(f"[green]✓[/green] Refreshed token from {config.source}")
            return
        console.print(f"[red]✗[/red] Could not find token from {config.source}")
        raise typer.Exit(code=1)

    fetched_token, detected_source = get_token_auto()
    if fetched_token and detected_source:
        config.refresh_token = fetched_token
        config.source = detected_source
        config.source_path = get_source_path(detected_source)
        save_config(config)
        console.print(f"[green]✓[/green] Refreshed token from {detected_source}")
        return

    console.print("[red]✗[/red] Could not auto-detect a refresh token")
    raise typer.Exit(code=1)


@config_app.command("clear")
def config_clear() -> None:
    """Delete the saved configuration."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        console.print("[green]✓[/green] Deleted configuration")
        return
    console.print("[yellow]![/yellow] No configuration file found")


@app.command()
def refresh(
    connection_id: Optional[str] = typer.Argument(
        None, help="Specific connection ID to refresh (refreshes all if omitted)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Refresh bank connections to fetch latest data."""
    if connection_id:
        query = f'query {{ refreshConnection(itemId: "{connection_id}") {{ id }} }}'
    else:
        query = "query { refreshAllConnections { id } }"

    def do_refresh(api: CopilotAPI) -> list[str]:
        data = api.query(query)
        if connection_id:
            conn = data.get("refreshConnection")
            return [conn["id"]] if conn else []
        else:
            return [c["id"] for c in data.get("refreshAllConnections", [])]

    connection_ids = run_api_action(do_refresh)

    if json_output:
        print(json.dumps({"refreshed": connection_ids}, indent=2))
    else:
        print(f"✓ Refreshed {len(connection_ids)} connection(s)")
        if connection_ids:
            for cid in connection_ids[:5]:
                print(f"  • {cid}")
            if len(connection_ids) > 5:
                print(f"  ... and {len(connection_ids) - 5} more")
