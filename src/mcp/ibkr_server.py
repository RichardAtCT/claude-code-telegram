"""MCP server exposing Interactive Brokers tools to Claude.

Connects to IB Gateway via TWS API (port 4001) using ib_insync.
Falls back to a local JSON cache when the gateway is offline.
Cache is at IBKR_CACHE_PATH (default: C:/Users/ander/Documents/GitHub/portfolio_cache.json).

Reads IBKR_ACCOUNT_ID and IBKR_PORT from environment variables.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ibkr")

CACHE_PATH = Path(
    os.environ.get(
        "IBKR_CACHE_PATH",
        "C:/Users/ander/Documents/GitHub/portfolio_cache.json",
    )
)


def _get_port() -> int:
    return int(os.environ.get("IBKR_PORT", "4001"))


def _get_account_id() -> str:
    return os.environ.get("IBKR_ACCOUNT_ID", "U15431190")


def _read_cache() -> Dict[str, Any]:
    """Read the local portfolio cache."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _write_cache(data: Dict[str, Any]) -> None:
    """Write portfolio data to the local cache."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def _connect_and_fetch(fetch_fn):
    """Try to connect to IB Gateway, run fetch_fn, update cache, disconnect.

    If the gateway is offline, returns cached data with last_updated timestamp.
    """
    from ib_insync import IB

    ib = IB()
    try:
        ib.connect("127.0.0.1", _get_port(), clientId=99, readonly=True, timeout=10)
        result = fetch_fn(ib)
        ib.disconnect()

        # Update cache
        now = datetime.now(timezone.utc).isoformat()
        cache = _read_cache()
        cache["last_updated"] = now
        cache["account_id"] = _get_account_id()
        cache["gateway_online"] = True
        if isinstance(result, list):
            cache["positions"] = result
        elif isinstance(result, dict):
            cache.update(result)
        _write_cache(cache)

        return {"data": result, "source": "live", "last_updated": now}
    except Exception as e:
        ib.disconnect() if ib.isConnected() else None
        # Fall back to cache
        cache = _read_cache()
        if cache:
            cache["gateway_online"] = False
            return {
                "data": cache.get("positions", cache),
                "source": "cache",
                "last_updated": cache.get("last_updated", "unknown"),
                "note": f"IB Gateway offline. Mostrando datos del cache ({cache.get('last_updated', 'fecha desconocida')}). Error: {e}",
            }
        return {"error": f"IB Gateway no disponible y no hay cache. Arranca IB Gateway. Error: {e}"}


@mcp.tool()
async def check_status() -> str:
    """Check if IB Gateway is running and connected. Returns live or cached status."""

    def _check(ib):
        return {
            "connected": ib.isConnected(),
            "accounts": ib.managedAccounts(),
            "server_version": ib.client.serverVersion(),
        }

    result = await asyncio.to_thread(_connect_and_fetch, _check)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_positions() -> str:
    """Get all open positions. Returns live data if gateway is up, cached data if not.

    Each position includes: symbol, quantity, avg cost, market value, unrealized P&L.
    The response includes 'source' (live/cache) and 'last_updated' timestamp.
    """

    def _positions(ib):
        positions = ib.positions()
        result = []
        for pos in positions:
            c = pos.contract
            result.append({
                "symbol": c.symbol,
                "secType": c.secType,
                "currency": c.currency,
                "quantity": float(pos.position),
                "avg_cost": float(pos.avgCost),
                "conId": c.conId,
            })
        return result

    result = await asyncio.to_thread(_connect_and_fetch, _positions)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_portfolio() -> str:
    """Get detailed portfolio with real-time P&L. Falls back to cache if offline.

    Returns positions with market value, unrealized/realized P&L, and return %.
    Includes 'source' (live/cache) and 'last_updated' timestamp.
    """

    def _portfolio(ib):
        account_id = _get_account_id()
        items = ib.portfolio(account_id)
        result = []
        for item in items:
            c = item.contract
            cost_basis = abs(float(item.averageCost) * float(item.position))
            result.append({
                "symbol": c.symbol,
                "secType": c.secType,
                "currency": c.currency,
                "quantity": float(item.position),
                "market_price": float(item.marketPrice),
                "market_value": float(item.marketValue),
                "avg_cost": float(item.averageCost),
                "unrealized_pnl": float(item.unrealizedPNL),
                "realized_pnl": float(item.realizedPNL),
                "return_pct": round(
                    (float(item.unrealizedPNL) / cost_basis) * 100, 2
                ) if cost_basis > 0 else 0,
                "conId": c.conId,
            })
        return result

    result = await asyncio.to_thread(_connect_and_fetch, _portfolio)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_account_summary() -> str:
    """Get account summary: balance, buying power, P&L. Falls back to cache."""

    def _summary(ib):
        account_id = _get_account_id()
        values = ib.accountSummary(account_id)
        summary = {}
        for v in values:
            if v.tag in [
                "NetLiquidation", "TotalCashValue", "BuyingPower",
                "GrossPositionValue", "UnrealizedPnL", "RealizedPnL",
                "AvailableFunds", "MaintMarginReq", "ExcessLiquidity",
            ]:
                summary[v.tag] = {"value": v.value, "currency": v.currency}
        return summary

    result = await asyncio.to_thread(_connect_and_fetch, _summary)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def search_stock(query: str) -> str:
    """Search for a stock/ETF by ticker symbol.

    Args:
        query: Stock ticker (e.g. 'AAPL', 'TSLA', 'SPY')
    """

    def _search(ib):
        from ib_insync import Stock
        contract = Stock(query, "SMART", "USD")
        details = ib.reqContractDetails(contract)
        return [
            {
                "symbol": d.contract.symbol,
                "conId": d.contract.conId,
                "exchange": d.contract.primaryExchange,
                "currency": d.contract.currency,
                "longName": d.longName,
                "industry": d.industry,
                "category": d.category,
            }
            for d in details[:5]
        ]

    result = await asyncio.to_thread(_connect_and_fetch, _search)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_cached_portfolio() -> str:
    """Read the local portfolio cache directly (no gateway needed).

    Returns the last saved positions with the timestamp of when they were updated.
    Use this when you know the gateway is offline.
    """
    cache = _read_cache()
    if not cache:
        return json.dumps({"error": "No cache available. Need at least one gateway connection to create it."})
    return json.dumps({
        "source": "cache",
        "last_updated": cache.get("last_updated", "unknown"),
        "account_id": cache.get("account_id"),
        "positions": cache.get("positions", []),
    }, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
