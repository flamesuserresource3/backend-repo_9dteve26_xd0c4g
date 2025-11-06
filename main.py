import os
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        # Try to import database module
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"

            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    import os as _os

    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# --------- Market Data Integrations ---------

def _get_env(name: str) -> Optional[str]:
    val = os.getenv(name)
    return val


def normalize_quote(symbol: str, provider: str, raw: dict) -> dict:
    symbol = symbol.upper()
    base = {"symbol": symbol, "provider": provider}

    try:
        if provider == "alpha_vantage":
            gq = raw.get("Global Quote", {})
            return {
                **base,
                "price": float(gq.get("05. price", 0) or 0),
                "changePercent": float((gq.get("10. change percent", "0%") or "0").strip("%")),
                "open": float(gq.get("02. open", 0) or 0),
                "high": float(gq.get("03. high", 0) or 0),
                "low": float(gq.get("04. low", 0) or 0),
                "previousClose": float(gq.get("08. previous close", 0) or 0),
                "timestamp": gq.get("07. latest trading day"),
            }
        if provider == "finnhub":
            return {
                **base,
                "price": float(raw.get("c") or 0),
                "changePercent": float(raw.get("dp") or 0),
                "open": float(raw.get("o") or 0),
                "high": float(raw.get("h") or 0),
                "low": float(raw.get("l") or 0),
                "previousClose": float(raw.get("pc") or 0),
                "timestamp": raw.get("t"),
            }
        if provider == "twelve":
            return {
                **base,
                "price": float(raw.get("price") or 0),
                "changePercent": float(raw.get("percent_change") or 0),
                "open": float(raw.get("open") or 0),
                "high": float(raw.get("high") or 0),
                "low": float(raw.get("low") or 0),
                "previousClose": float(raw.get("previous_close") or 0),
                "timestamp": raw.get("timestamp"),
            }
        if provider == "polygon":
            res0 = (raw.get("results") or [{}])[0]
            close = float(res0.get("c") or 0)
            open_ = float(res0.get("o") or 0)
            high = float(res0.get("h") or 0)
            low = float(res0.get("l") or 0)
            prev = float(res0.get("c") or 0)
            return {
                **base,
                "price": close,
                "changePercent": 0.0 if prev == 0 else ((close - prev) / prev) * 100,
                "open": open_,
                "high": high,
                "low": low,
                "previousClose": prev,
                "timestamp": res0.get("t"),
            }
        if provider == "fmp":
            res0 = (raw or [{}])[0]
            return {
                **base,
                "price": float(res0.get("price") or 0),
                "changePercent": 0.0,
                "open": res0.get("open") or 0,
                "high": res0.get("dayHigh") or 0,
                "low": res0.get("dayLow") or 0,
                "previousClose": res0.get("previousClose") or 0,
                "timestamp": res0.get("timestamp") or None,
            }
    except Exception:
        pass

    return {**base, "price": 0.0, "changePercent": 0.0}


@app.get("/api/quote")
def get_quote(symbol: str = Query(..., description="Ticker symbol, e.g., TSLA or NSE:TCS"), provider: str = Query("finnhub", description="alpha_vantage | finnhub | twelve | polygon | fmp")):
    provider = provider.lower()
    symbol = symbol.upper()

    try:
        if provider == "alpha_vantage":
            key = _get_env("ALPHA_VANTAGE_API_KEY")
            if not key:
                raise HTTPException(status_code=400, detail="ALPHA_VANTAGE_API_KEY not set")
            url = "https://www.alphavantage.co/query"
            params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            return normalize_quote(symbol, provider, data)

        if provider == "finnhub":
            key = _get_env("FINNHUB_API_KEY")
            if not key:
                raise HTTPException(status_code=400, detail="FINNHUB_API_KEY not set")
            url = "https://finnhub.io/api/v1/quote"
            params = {"symbol": symbol, "token": key}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            return normalize_quote(symbol, provider, data)

        if provider == "twelve":
            key = _get_env("TWELVE_DATA_API_KEY")
            if not key:
                raise HTTPException(status_code=400, detail="TWELVE_DATA_API_KEY not set")
            url = "https://api.twelvedata.com/quote"
            params = {"symbol": symbol, "apikey": key}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            return normalize_quote(symbol, provider, data)

        if provider == "polygon":
            key = _get_env("POLYGON_API_KEY")
            if not key:
                raise HTTPException(status_code=400, detail="POLYGON_API_KEY not set")
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
            params = {"adjusted": "true", "apiKey": key}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            return normalize_quote(symbol, provider, data)

        if provider == "fmp":
            key = _get_env("FMP_API_KEY")
            if not key:
                raise HTTPException(status_code=400, detail="FMP_API_KEY not set")
            url = "https://financialmodelingprep.com/api/v3/quote-short/{}".format(symbol)
            params = {"apikey": key}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            return normalize_quote(symbol, provider, data)

        raise HTTPException(status_code=400, detail="Unsupported provider")

    except HTTPException:
        raise
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code if e.response else 502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tickers")
def get_tickers(symbols: str = Query(..., description="Comma separated tickers, e.g., TSLA,AAPL,NSE:TCS"), provider: str = Query("finnhub")):
    syms: List[str] = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    out = []
    for s in syms:
        try:
            out.append(get_quote.__wrapped__(s, provider))  # type: ignore
        except HTTPException as e:
            out.append({"symbol": s, "provider": provider, "error": e.detail})
        except Exception as e:
            out.append({"symbol": s, "provider": provider, "error": str(e)})
    return {"data": out}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
