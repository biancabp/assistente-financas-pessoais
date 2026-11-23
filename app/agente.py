"""Ponto de entrada usado pela interface: chat(thread_id, texto).

- O grafo e criado uma unica vez por processo (o modulo fica em cache no Streamlit,
  entao a memoria do checkpointer sobrevive aos reruns).
- As ferramentas MCP sao assincronas; um event loop dedicado roda em segundo plano e
  chat() continua sincrona para quem chama.
"""
import asyncio
import os
import threading
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True, name="agente-loop").start()
_grafo = None
_lock = threading.Lock()
_modo_stub = False  # True se as ferramentas MCP reais nao carregaram (exposto na interface)

# minimo privilegio: o unico uso real do fetch neste agente e consultar a API do BCB
# (Selic/CDI). Restringir a esses dominios reduz o risco de exfiltracao de dados via URL
# (o agente nao deveria conseguir ser induzido a mandar dados do usuario para outro host).
DOMINIOS_FETCH_PERMITIDOS = ("api.bcb.gov.br",)


def _restringir_fetch(tool_original):
    async def fetch_restrito(**kwargs):
        url = kwargs.get("url", "") or ""
        host = urlparse(url).hostname or ""
        if host not in DOMINIOS_FETCH_PERMITIDOS:
            return (f"[BLOQUEADO por minimo privilegio] O fetch deste agente so pode acessar "
                    f"{', '.join(DOMINIOS_FETCH_PERMITIDOS)} (unico uso real: Selic/CDI). "
                    f"URL pedida: {url or '(vazia)'}")
        return await tool_original.ainvoke(kwargs)

    return StructuredTool.from_function(
        coroutine=fetch_restrito, name=tool_original.name,
        description=tool_original.description, args_schema=tool_original.args_schema,
    )


VERBOSE = os.environ.get("AGENTE_VERBOSE", "1") == "1"  # imprime os nos visitados


def _rodar(coro, timeout=240):
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        return fut.result(timeout)
    except TimeoutError:
        fut.cancel()  # nao deixa a chamada presa rodando em segundo plano
        raise TimeoutError(f"o agente nao respondeu em {timeout}s (limite de requisicoes do Gemini?)")


async def _carregar_ferramentas() -> tuple[list, str]:
    global _modo_stub
    from rag import buscar_documentos

    try:
        from mcp_client import build_client
        from skills_loader import get_skill_catalog, load_skill
        client, tools = build_client(), []
        for servidor in client.connections:  # um servidor fora do ar nao derruba os outros
            try:
                tools += await client.get_tools(server_name=servidor)
            except Exception as e:
                print(f"[agente] servidor MCP '{servidor}' indisponivel: {e}")
        tools = [_restringir_fetch(t) if t.name == "fetch" else t for t in tools]
        _modo_stub = False
        return tools + [load_skill, buscar_documentos], get_skill_catalog()
    except ImportError as e:
        print(f"[agente] MCP/skills indisponivel ({e}); usando ferramentas de teste (stub)")
        from stubs import STUB_CATALOGO, STUB_TOOLS
        _modo_stub = True
        return STUB_TOOLS + [buscar_documentos], STUB_CATALOGO


def get_grafo(**kwargs):
    """Cria (uma vez) e devolve o grafo compilado. kwargs vao para build_graph."""
    global _grafo
    with _lock:
        if _grafo is None:
            from grafo import build_graph
            tools, catalogo = _rodar(_carregar_ferramentas())
            _grafo = build_graph(tools, catalogo, checkpointer=InMemorySaver(), **kwargs)
        return _grafo


def _texto(m) -> str:
    t = getattr(m, "text", "")
    t = t if isinstance(t, str) else (t() if callable(t) else t)  # .text virou propriedade
    return t or (m.content if isinstance(m.content, str) else "")


async def _achat(grafo, thread_id: str, texto: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
    antes = len((await grafo.aget_state(config)).values.get("messages", []))
    async for passo in grafo.astream({"messages": [HumanMessage(texto)]}, config,
                                     stream_mode="updates"):
        if VERBOSE:
            for no, dados in passo.items():
                extra = ""
                for m in (dados or {}).get("messages", []) if isinstance(dados, dict) else []:
                    if getattr(m, "tool_calls", None):
                        extra = " -> " + ", ".join(tc["name"] for tc in m.tool_calls)
                print(f"  [{no}]{extra}", flush=True)
    estado = (await grafo.aget_state(config)).values

    novas = estado["messages"][antes:]
    chamadas = [tc for m in novas if isinstance(m, AIMessage) for tc in (m.tool_calls or [])]
    ultima = next((m for m in reversed(novas) if isinstance(m, AIMessage)), None)
    return {
        "resposta": _texto(ultima) if ultima else "(sem resposta)",
        "tools_called": [tc["name"] for tc in chamadas],
        "skills_loaded": [tc["args"].get("nome") for tc in chamadas if tc["name"] == "load_skill"],
        # extras (a interface pode ignorar)
        "consultas_rag": [tc["args"].get("consulta") for tc in chamadas
                          if tc["name"] == "buscar_documentos"],
        "guardrail": estado.get("motivo") or None,
    }


def chat(thread_id: str, texto: str) -> dict:
    """Envia uma mensagem para a conversa thread_id.
    Devolve {"resposta", "tools_called", "skills_loaded", "consultas_rag", "guardrail", "modo_stub"}."""
    grafo = get_grafo()
    try:
        resultado = _rodar(_achat(grafo, thread_id, texto))
    except Exception as e:
        resultado = {"resposta": f"Desculpe, ocorreu um erro: {type(e).__name__}: {e}",
                    "tools_called": [], "skills_loaded": [], "consultas_rag": [], "guardrail": None}
    resultado["modo_stub"] = _modo_stub
    return resultado


def historico(thread_id: str) -> list:
    """Mensagens salvas no checkpointer para a thread (util para depurar a memoria)."""
    config = {"configurable": {"thread_id": thread_id}}
    return _rodar(get_grafo().aget_state(config)).values.get("messages", [])