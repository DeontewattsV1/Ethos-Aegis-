"""Opt-in mitmproxy addon: emit only authorized host/status/TLS observations.

Usage: mitmdump -s tools/mitmproxy/ethos_aegis_addon.py --set aegis_hosts=app.example.test
Run only in an operator-owned test session. This addon does not start a proxy.
"""
import json

from mitmproxy import ctx


class EthosAegisFlowSummary:
    def load(self, loader):
        loader.add_option("aegis_hosts", str, "", "Comma-separated exact authorized hostnames; default none")

    def response(self, flow):
        allowed = {item.strip().lower().rstrip(".") for item in ctx.options.aegis_hosts.split(",") if item.strip()}
        host = flow.request.host.lower().rstrip(".")
        if host not in allowed or flow.response is None:
            return
        print(json.dumps({"schema": "ethos-aegis.flow.v1", "host": host,
                          "status": flow.response.status_code, "tls": flow.request.scheme == "https"}), flush=True)


addons = [EthosAegisFlowSummary()]
