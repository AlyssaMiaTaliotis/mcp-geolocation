from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse
import uvicorn
import httpx

mcp = FastMCP("geo-mcp")

# Tool 1: Detect user location from IP
@mcp.tool()
async def get_my_location() -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get("https://ipwho.is/")
        return r.json()

# Tool 2: Get current weather
@mcp.tool()
async def get_weather(lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current_weather=true"
    )
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.json().get("current_weather", {})

# Tool 3: Get time info based on lat/lon
@mcp.tool()
async def get_local_time(lat: float, lon: float) -> dict:
    url = f"http://worldtimeapi.org/api/timezone"
    async with httpx.AsyncClient() as client:
        zones = await client.get(url)
        timezones = zones.json()
        # fallback: return UTC if no matching timezone
        return {"timezone": "UTC", "datetime": "Unknown"}

# Tool 4: Get country info
@mcp.tool()
async def get_country_info(country: str) -> dict:
    url = f"https://restcountries.com/v3.1/name/{country}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
        if isinstance(data, list) and data:
            info = data[0]
            return {
                "name": info.get("name", {}).get("common"),
                "population": info.get("population"),
                "region": info.get("region"),
                "capital": info.get("capital", [None])[0],
                "currency": list(info.get("currencies", {}).keys())[0] if info.get("currencies") else None,
                "languages": list(info.get("languages", {}).values()) if info.get("languages") else []
            }
        return {}

# Tool 5: Geo Summary
@mcp.tool()
async def get_geo_summary() -> dict:
    location = await get_my_location()
    lat = location.get("latitude")
    lon = location.get("longitude")
    country = location.get("country")

    weather = await get_weather(lat, lon)
    time_info = await get_local_time(lat, lon)
    country_info = await get_country_info(country)

    return {
        "location": f"{location.get('city')}, {country}",
        "ip": location.get("ip"),
        "lat": lat,
        "lon": lon,
        "weather": weather,
        "time": time_info,
        "country_info": country_info,
    }

# SSE App
def create_app():
    sse = SseServerTransport("/messages/")

    # Root route for homepage / healthcheck
    async def root(request: Request):
        return JSONResponse(
            {"message": "Geo MCP is live."},
            status_code=202
        )

    # SSE endpoint for NANDA Inspector
    async def handle_sse(request: Request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read, write):
            await mcp._mcp_server.run(
                read,
                write,
                mcp._mcp_server.create_initialization_options()
            )

    # Build and return the Starlette app
    return Starlette(
        routes=[
            Route("/", endpoint=root),  # New root route
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

