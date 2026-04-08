"""MCP server exposing Metricool tools to Claude.

Wraps the Metricool REST API for brand management, scheduled posts,
and analytics. Reads METRICOOL_API_TOKEN and METRICOOL_BRAND_ID
from environment variables.
"""

import json
import os
import ssl
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("metricool")

API_BASE = "https://app.metricool.com/api/v2"


def _get_token() -> str:
    token = os.environ.get("METRICOOL_API_TOKEN", "")
    if not token or token == "pending_user_token":
        return ""
    return token


def _get_brand_id() -> str:
    return os.environ.get("METRICOOL_BRAND_ID", "3845523")


def _api_request(
    path: str,
    method: str = "GET",
    params: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make authenticated request to Metricool API."""
    token = _get_token()
    if not token:
        return {
            "error": "METRICOOL_API_TOKEN not configured. "
            "Set it in the bot's .env file. "
            "Get your token from metricool.com > Settings > API."
        }

    url = f"{API_BASE}{path}"
    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_brand_info() -> str:
    """Get Metricool brand info including connected social networks.

    Returns brand details, connected platforms (Instagram, TikTok, YouTube, etc.),
    and account metadata.
    """
    result = _api_request("/brands")
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_scheduled_posts(from_date: str, to_date: str) -> str:
    """Get scheduled (not yet published) posts for the brand.

    Args:
        from_date: Start date in ISO 8601 format (e.g. 2026-04-01T00:00:00+02:00)
        to_date: End date in ISO 8601 format (e.g. 2026-04-30T23:59:59+02:00)

    Returns:
        List of scheduled posts with text, media URLs, target networks, and publish dates.
    """
    brand_id = _get_brand_id()
    result = _api_request(
        f"/scheduler/posts",
        params={
            "brandId": brand_id,
            "fromDate": from_date,
            "toDate": to_date,
            "timezone": "Europe/Madrid",
        },
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_post_analytics(
    network: str,
    from_date: str,
    to_date: str,
) -> str:
    """Get analytics for published posts on a social network.

    Args:
        network: Social network (instagram, tiktok, youtube, facebook, twitter)
        from_date: Start date ISO 8601
        to_date: End date ISO 8601

    Returns:
        Post performance data including impressions, reach, engagement, likes, etc.
    """
    brand_id = _get_brand_id()
    result = _api_request(
        f"/analytics/{network}/posts",
        params={
            "brandId": brand_id,
            "from": from_date,
            "to": to_date,
        },
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_best_time_to_post(network: str) -> str:
    """Get the best times to post on a social network based on audience activity.

    Args:
        network: Social network (instagram, tiktok, youtube, facebook, twitter)

    Returns:
        Heatmap of optimal posting times by day and hour.
    """
    brand_id = _get_brand_id()
    result = _api_request(
        f"/best-time/{network}",
        params={"brandId": brand_id},
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
async def get_account_evolution(
    network: str,
    from_date: str,
    to_date: str,
) -> str:
    """Get account growth metrics over time (followers, impressions, etc.).

    Args:
        network: Social network (instagram, tiktok, youtube)
        from_date: Start date ISO 8601
        to_date: End date ISO 8601

    Returns:
        Daily evolution data for followers, reach, impressions, engagement.
    """
    brand_id = _get_brand_id()
    result = _api_request(
        f"/analytics/{network}/evolution",
        params={
            "brandId": brand_id,
            "from": from_date,
            "to": to_date,
        },
    )
    return json.dumps(result, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
