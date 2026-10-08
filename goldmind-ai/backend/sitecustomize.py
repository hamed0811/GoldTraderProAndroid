"""
GoldTrader Pro LAN bridge.

This module is loaded automatically by Python's site initialization when the
backend directory is on sys.path. It adds a small read-only mobile state API
and UDP discovery without changing the trading/signal endpoint.
"""
import functools
import json
import socket
import threading

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    _latest = {
        "price": "",
        "symbol": "XAUUSD",
        "signal": None,
        "protection": {"mode": "OFF"},
    }
    _patched = False
    _original_add_api_route = FastAPI.add_api_route

    def _state_from_signal(req, signal):
        order = getattr(signal, "order", None)
        order_type = getattr(getattr(order, "type", None), "value", "none")
        if order_type == "buy_stop":
            side, state = "BUY", "BUY"
        elif order_type == "sell_stop":
            side, state = "SELL", "SELL"
        else:
            side, state = "—", "WAIT"

        veto = bool(getattr(signal, "veto", True))
        if veto:
            state, side = "WAIT", "—"

        return {
            "price": str(getattr(req, "bid", "")),
            "symbol": getattr(req, "symbol", "XAUUSD"),
            "signal": {
                "state": state,
                "side": side,
                "entry": getattr(order, "entry", 0.0) if order else 0.0,
                "sl": getattr(order, "sl", 0.0) if order else 0.0,
                "tp1": getattr(order, "tp", 0.0) if order else 0.0,
                "confidence": getattr(signal, "confidence", 0.0),
                "reasons": getattr(signal, "veto_reason", "") or (getattr(order, "comment", "") if order else ""),
                "timestamp_utc": getattr(signal, "timestamp_utc", ""),
                "veto": veto,
            },
            "protection": {"mode": "OFF"},
        }

    def _add_api_route(self, path, endpoint, *args, **kwargs):
        global _patched
        if path == "/signal" and not getattr(endpoint, "_goldtrader_wrapped", False):
            original = endpoint

            @functools.wraps(original)
            async def wrapped(*a, **kw):
                result = await original(*a, **kw)
                req = kw.get("req") if "req" in kw else (a[0] if a else None)
                if req is not None:
                    try:
                        _latest.clear()
                        _latest.update(_state_from_signal(req, result))
                    except Exception:
                        pass
                return result

            wrapped._goldtrader_wrapped = True
            endpoint = wrapped

            result = _original_add_api_route(self, path, endpoint, *args, **kwargs)

            if not _patched:
                _patched = True

                async def mobile_state():
                    return JSONResponse(_latest)

                _original_add_api_route(
                    self,
                    "/api/state",
                    mobile_state,
                    methods=["GET"],
                    include_in_schema=False,
                )
            return result

        return _original_add_api_route(self, path, endpoint, *args, **kwargs)

    FastAPI.add_api_route = _add_api_route

    def _discover():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", 8766))
            while True:
                data, addr = sock.recvfrom(256)
                if data.strip() == b"GOLDTRADER_DISCOVER":
                    reply = f"GOLDTRADER_SERVER|{addr[0]}|8000".encode("utf-8")
                    sock.sendto(reply, addr)
        finally:
            sock.close()

    threading.Thread(target=_discover, name="goldtrader-discovery", daemon=True).start()

except Exception:
    # Never prevent the existing MT5/OpenAI backend from starting.
    pass
