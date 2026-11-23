import io
import os
import sys
from pathlib import Path

import mcp.client.stdio as _mcp_stdio
from langchain_mcp_adapters.client import MultiServerMCPClient

SERVER = str(Path(__file__).resolve().parent.parent / "mcp_servers" / "financas_server.py")


def _corrigir_stderr_jupyter():
    """No Jupyter/Colab o sys.stderr nao tem fileno(), e o MCP usa ele como stderr do
    subprocesso do servidor (erro 'UnsupportedOperation: fileno'). Nesse caso, o log de
    erros dos servidores vai para o stderr real do processo. Fora do Jupyter nada muda."""
    try:
        sys.stderr.fileno()
        return
    except (AttributeError, io.UnsupportedOperation, ValueError):
        pass
    destino = sys.__stderr__ if sys.__stderr__ is not None else open(os.devnull, "w")
    func = getattr(_mcp_stdio.stdio_client, "__wrapped__", None)
    if func is not None and func.__defaults__:
        func.__defaults__ = (destino,)


def build_client() -> MultiServerMCPClient:
    _corrigir_stderr_jupyter()
    return MultiServerMCPClient({
        "financas": {"command": sys.executable, "args": [SERVER], "transport": "stdio"},
        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "transport": "stdio"},
    })


async def get_mcp_tools():
    return await build_client().get_tools()