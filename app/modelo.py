"""Criacao dos modelos. A chave vem da variavel de ambiente GOOGLE_API_KEY."""
import os


def _checar_chave():
    if not os.environ.get("GOOGLE_API_KEY") and os.environ.get("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]  # aceita os dois nomes
    if not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError("Defina a variavel de ambiente GOOGLE_API_KEY (veja .env.example).")


def get_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI

    _checar_chave()
    return ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
                                  max_retries=2, timeout=90)


def get_guard_llm():
    """Modelo menor para guardrails e avaliacao do RAG (mais barato e com limite maior)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    _checar_chave()
    return ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_GUARD_MODEL", "gemini-3.5-flash-lite"),
                                  max_retries=2, timeout=60)