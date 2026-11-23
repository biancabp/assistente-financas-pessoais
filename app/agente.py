"""Ponto de entrada usado pela interface: chat(thread_id, texto).

- O grafo e criado uma unica vez por processo (o modulo fica em cache no Streamlit,
  entao a memoria do checkpointer sobrevive aos reruns).
- As ferramentas MCP sao assincronas; um event loop dedicado roda em segundo plano e
  chat() continua sincrona para quem chama.
"""
import asyncio
import os
import threading

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True, name="agente-loop").start()
_grafo = None
_lock = threading.Lock()


VERBOSE = os.environ.get("AGENTE_VERBOSE", "1") == "1"  # imprime os nos visitados


def _rodar(coro, timeout=240):
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        return fut.result(timeout)
    except TimeoutError:
        fut.cancel()  # nao deixa a chamada presa rodando em segundo plano
        raise TimeoutError(f"o agente nao respondeu em {timeout}s (limite de requisicoes do Gemini?)")


async def _carregar_ferramentas() -> tuple[list, str]:
    from rag import buscar_documentos

    try:  # parte da Pessoa B
        from mcp_client import build_client
        from skills_loader import get_skill_catalog, load_skill
        client, tools = build_client(), []
        for servidor in client.connections:  # um servidor fora do ar nao derruba os outros
            try:
                tools += await client.get_tools(server_name=servidor)
            except Exception as e:
                print(f"[agente] servidor MCP '{servidor}' indisponivel: {e}")
        return tools + [load_skill, buscar_documentos], get_skill_catalog()
    except ImportError as e:
        print(f"[agente] parte da Pessoa B indisponivel ({e}); usando ferramentas de teste")
        from stubs import STUB_CATALOGO, STUB_TOOLS
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
    Devolve {"resposta", "tools_called", "skills_loaded", "consultas_rag", "guardrail"}."""
    grafo = get_grafo()
    try:
        return _rodar(_achat(grafo, thread_id, texto))
    except Exception as e:
        return {"resposta": f"Desculpe, ocorreu um erro: {type(e).__name__}: {e}",
                "tools_called": [], "skills_loaded": [], "consultas_rag": [], "guardrail": None}


def historico(thread_id: str) -> list:
    """Mensagens salvas no checkpointer para a thread (util para depurar a memoria)."""
    config = {"configurable": {"thread_id": thread_id}}
    return _rodar(get_grafo().aget_state(config)).values.get("messages", [])