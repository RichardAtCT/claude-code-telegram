"""MCP server exposing Interactive Brokers tools to Claude.

Connects to IB Gateway via TWS API (port 4001) using ib_insync.
Reads IBKR_ACCOUNT_ID and IBKR_PORT from environment variables.

Requires IB Gateway or TWS to be running and authenticated.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ibkr")


def _get_port() -> int:
    return int(os.environ.get("IBKR_PORT", "4001"))


def _get_account_id() -> str:
    return os.environ.get("IBKR_ACCOUNT_ID", "U15431190")


def _connect_ib():
    """Create a synchronous IB connection (runs in thread for MCP)."""
    from ib_insync import IB
    ib = IB()
    ib.connect("127.0.0.1", _get_port(), clientId=99, readonly=True, timeout=10)
    return ib


def _run_sync(func):
    """Run an ib_insync function synchronously and return result."""
    try:
        ib = _connect_ib()
        try:
            result = func(ib)
            return result
        finally:
            ib.disconnect()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def check_status() -> str:
    """Check if IB Gateway is running and connected.

    Returns connection status and account info.
    """
    def _check(ib):
        managed = ib.managedAccounts()
        return {
            "connected": ib.isConnected(),
            "accounts": managed,
            "server_version": ib.client.serverVersion(),
        }

    result = await asyncio.to_thread(_run_sync, _check)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_positions() -> str:
    """Get all open positions in the IBKR portfolio.

    Returns each position with: symbol, quantity, average cost, market price,
    market value, unrealized P&L, and realized P&L.
    """
    def _positions(ib):
        positions = ib.positions()
        result = []
        for pos in positions:
            contract = pos.contract
            result.append({
                "symbol": contract.symbol,
                "secType": contract.secType,
                "exchange": contract.exchange or contract.primaryExchange,
                "currency": contract.currency,
                "quantity": float(pos.position),
                "avg_cost": float(pos.avgCost),
                "market_value": round(float(pos.position) * float(pos.avgCost), 2),
                "conId": contract.conId,
            })
        return result

    result = await asyncio.to_thread(_run_sync, _positions)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_account_summary() -> str:
    """Get IBKR account summary: balance, buying power, total P&L, margin.

    Returns key account metrics including net liquidation value,
    available funds, total cash, and unrealized P&L.
    """
    def _summary(ib):
        account_id = _get_account_id()
        values = ib.accountSummary(account_id)
        summary = {}
        important_tags = [
            "NetLiquidation", "TotalCashValue", "BuyingPower",
            "GrossPositionValue", "UnrealizedPnL", "RealizedPnL",
            "AvailableFunds", "MaintMarginReq", "ExcessLiquidity",
        ]
        for v in values:
            if v.tag in important_tags:
                summary[v.tag] = {
                    "value": v.value,
                    "currency": v.currency,
                }
        return summary

    result = await asyncio.to_thread(_run_sync, _summary)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_portfolio() -> str:
    """Get detailed portfolio with real-time P&L for each position.

    Returns positions with current market value, unrealized and realized P&L,
    and percentage return. More detailed than get_positions.
    """
    def _portfolio(ib):
        account_id = _get_account_id()
        items = ib.portfolio(account_id)
        result = []
        for item in items:
            contract = item.contract
            result.append({
                "symbol": contract.symbol,
                "secType": contract.secType,
                "currency": contract.currency,
                "quantity": float(item.position),
                "market_price": float(item.marketPrice),
                "market_value": float(item.marketValue),
                "avg_cost": float(item.averageCost),
                "unrealized_pnl": float(item.unrealizedPNL),
                "realized_pnl": float(item.realizedPNL),
                "return_pct": round(
                    (float(item.unrealizedPNL) / (abs(float(item.averageCost) * float(item.position)))) * 100, 2
                ) if item.averageCost and item.position else 0,
                "conId": contract.conId,
            })
        return result

    result = await asyncio.to_thread(_run_sync, _portfolio)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def search_stock(query: str) -> str:
    """Search for a stock/ETF by ticker symbol.

    Args:
        query: Stock ticker symbol (e.g. 'AAPL', 'TSLA', 'SPY')

    Returns:
        Contract details including conId, exchange, and description.
    """
    def _search(ib):
        from ib_insync import Stock
        contract = Stock(query, "SMART", "USD")
        details = ib.reqContractDetails(contract)
        results = []
        for d in details[:5]:
            c = d.contract
            results.append({
                "symbol": c.symbol,
                "conId": c.conId,
                "exchange": c.exchange,
                "primaryExchange": c.primaryExchange,
                "currency": c.currency,
                "secType": c.secType,
                "longName": d.longName,
                "industry": d.industry,
                "category": d.category,
                "subcategory": d.subcategory,
            })
        return results

    result = await asyncio.to_thread(_run_sync, _search)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_market_data(symbol: str, currency: str = "USD") -> str:
    """Get real-time market data snapshot for a stock.

    Args:
        symbol: Stock ticker (e.g. 'AAPL')
        currency: Currency (default 'USD', use 'EUR' for European stocks)

    Returns:
        Current bid, ask, last price, volume, and other market data.
    """
    def _market(ib):
        from ib_insync import Stock
        contract = Stock(symbol, "SMART", currency)
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract, snapshot=True)
        ib.sleep(2)  # Wait for data
        return {
            "symbol": symbol,
            "bid": float(ticker.bid) if ticker.bid else None,
            "ask": float(ticker.ask) if ticker.ask else None,
            "last": float(ticker.last) if ticker.last else None,
            "close": float(ticker.close) if ticker.close else None,
            "volume": int(ticker.volume) if ticker.volume else None,
            "high": float(ticker.high) if ticker.high else None,
            "low": float(ticker.low) if ticker.low else None,
        }

    result = await asyncio.to_thread(_run_sync, _market)
    return json.dumps(result, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
