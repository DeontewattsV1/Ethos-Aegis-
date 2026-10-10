"""Regression: HTTP-only clients import with no embedded core installation.

The existing SDK tests run with the monorepo's Python core on sys.path,
which previously concealed the unconditional adapter/core import.
This subprocess uses isolated mode and explicitly blocks core imports.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

SDK_SOURCE = Path(__file__).resolve().parents[1]


def test_http_transport_import_is_independent_of_embedded_core() -> None:
    code = textwrap.dedent(
        """
        import builtins
        import sys

        original_import = builtins.__import__
        def deny_core(name, *args, **kwargs):
            if name == "ethos_aegis" or name.startswith("ethos_aegis."):
                raise ModuleNotFoundError("embedded core must not be loaded by HTTP-only SDK")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = deny_core
        sys.path.insert(0, sys.argv[1])
        from ethos_aegis_sdk import AegisClient, AegisClientError, GuardedResponse
        import ethos_aegis_sdk

        assert "ethos_aegis" not in sys.modules
        assert callable(AegisClient)
        assert issubclass(AegisClientError, Exception)
        assert GuardedResponse is not None

        client = AegisClient(
            transport="http",
            server_url="https://example.test/v1/adjudicate",
            auto_nourish=False,
        )
        assert client._transport == "http"
        assert "OpenAIAdapter" in ethos_aegis_sdk.__all__
        assert "OpenAIAdapter" in dir(ethos_aegis_sdk)
        try:
            ethos_aegis_sdk.NonexistentAdapter
        except AttributeError:
            pass
        else:
            raise AssertionError("Unknown SDK attributes must not be accepted")

        # An explicitly requested core adapter must not silently return a stub.
        try:
            ethos_aegis_sdk.GenericAdapter
        except ModuleNotFoundError:
            pass
        else:
            raise AssertionError("Core adapter must require the absent core")

        assert "ethos_aegis" not in sys.modules
        """
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code, str(SDK_SOURCE)],
        cwd=SDK_SOURCE.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
