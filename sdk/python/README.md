# Ethos Aegis Python SDK

Source-installable input-screening client for the local Ethos Aegis core or an independently configured HTTP(S) server. Embedded mode requires the core package.

```bash
python -m pip install -e ./python
python -m pip install -e ./sdk/python
```

```python
from ethos_aegis_sdk import AegisClient

response = AegisClient(auto_nourish=False).guard("Explain a computer", llm_fn=lambda text: "A model response")
print(response.was_blocked, response.content)
```

See the [SDK guide](../README.md) for transport behavior, support status and limits. MIT license; copyright 2026 The Ethos Aegis Project.
