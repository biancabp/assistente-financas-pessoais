"""Ferramentas de mentira para testar o grafo sem a parte da Pessoa B.
Mesmos nomes e assinaturas das ferramentas reais."""
import math

from langchain_core.tools import tool


@tool
def reserva_emergencia(despesas_mensais: float, meses_cobertura: int = 6,
                       reserva_atual: float = 0.0, aporte_mensal: float = 0.0) -> dict:
    """Calcula a meta da reserva de emergencia, quanto falta e em quantos meses se chega la."""
    meta = despesas_mensais * meses_cobertura
    falta = max(meta - reserva_atual, 0.0)
    meses = math.ceil(falta / aporte_mensal) if aporte_mensal > 0 and falta > 0 else (0 if falta == 0 else None)
    return {"meta": meta, "falta": falta, "meses_para_atingir": meses}


@tool
def juros_compostos(capital: float, taxa_mensal_pct: float, meses: int,
                    aporte_mensal: float = 0.0) -> dict:
    """Calcula o montante final com juros compostos e aportes mensais (taxa em % ao mes)."""
    i = taxa_mensal_pct / 100
    f = (1 + i) ** meses
    m = capital * f + (aporte_mensal * (f - 1) / i if i else aporte_mensal * meses)
    return {"montante": round(m, 2)}


@tool
def load_skill(nome: str) -> str:
    """Carrega as instrucoes completas de uma skill pelo nome."""
    return f"(stub) passos da skill {nome}"


STUB_TOOLS = [reserva_emergencia, juros_compostos, load_skill]
STUB_CATALOGO = ("Skills disponiveis (chame load_skill para ler os passos):\n"
                 "- quitacao-dividas: Monta um plano de quitacao de dividas.\n"
                 "- renda-fixa-vs-poupanca: Compara poupanca, CDB e LCI/LCA.")