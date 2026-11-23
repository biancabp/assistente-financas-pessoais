import math

from mcp.server.fastmcp import FastMCP
from typing_extensions import TypedDict


class Divida(TypedDict):
    nome: str
    saldo: float
    taxa_mensal_pct: float
    parcela_minima: float


mcp = FastMCP("financas")


@mcp.tool()
def juros_compostos(capital: float, taxa_mensal_pct: float, meses: int,
                    aporte_mensal: float = 0.0) -> dict:
    """Calcula o montante final com juros compostos e aportes mensais (taxa em % ao mes)."""
    i = taxa_mensal_pct / 100
    fator = (1 + i) ** meses
    aportes = aporte_mensal * (fator - 1) / i if i else aporte_mensal * meses
    montante = capital * fator + aportes
    investido = capital + aporte_mensal * meses
    return {
        "montante": round(montante, 2),
        "total_investido": round(investido, 2),
        "juros": round(montante - investido, 2),
    }


@mcp.tool()
def reserva_emergencia(despesas_mensais: float, meses_cobertura: int = 6,
                       reserva_atual: float = 0.0, aporte_mensal: float = 0.0) -> dict:
    """Calcula a meta da reserva de emergencia, quanto falta e em quantos meses se chega la."""
    meta = despesas_mensais * meses_cobertura
    falta = max(meta - reserva_atual, 0.0)
    meses = math.ceil(falta / aporte_mensal) if aporte_mensal > 0 and falta > 0 else (0 if falta == 0 else None)
    return {
        "meta": round(meta, 2),
        "falta": round(falta, 2),
        "meses_para_atingir": meses,
    }


@mcp.tool()
def financiamento(valor: float, taxa_mensal_pct: float, meses: int, sistema: str = "price") -> dict:
    """Simula financiamento pelo sistema 'price' (parcela fixa) ou 'sac' (amortizacao constante)."""
    if valor <= 0 or meses <= 0 or taxa_mensal_pct < 0:
        return {"erro": "valor e meses devem ser maiores que zero e a taxa nao pode ser negativa"}
    i = taxa_mensal_pct / 100
    sistema = sistema.lower()
    if sistema == "price":
        parcela = valor * i / (1 - (1 + i) ** -meses) if i else valor / meses
        total = parcela * meses
        return {
            "sistema": "price",
            "primeira_parcela": round(parcela, 2),
            "ultima_parcela": round(parcela, 2),
            "total_pago": round(total, 2),
            "total_juros": round(total - valor, 2),
        }
    if sistema == "sac":
        amort = valor / meses
        primeira = amort + valor * i
        ultima = amort + amort * i
        total_juros = sum((valor - amort * k) * i for k in range(meses))
        return {
            "sistema": "sac",
            "primeira_parcela": round(primeira, 2),
            "ultima_parcela": round(ultima, 2),
            "total_pago": round(valor + total_juros, 2),
            "total_juros": round(total_juros, 2),
        }
    return {"erro": "sistema deve ser 'price' ou 'sac'"}


@mcp.tool()
def plano_quitacao_dividas(dividas: list[Divida], orcamento_mensal: float,
                           metodo: str = "avalanche") -> dict:
    """Simula a quitacao de dividas. Cada divida: {nome, saldo, taxa_mensal_pct, parcela_minima}.
    metodo: 'avalanche' (maior juros primeiro) ou 'bola_de_neve' (menor saldo primeiro)."""
    if metodo not in ("avalanche", "bola_de_neve"):
        return {"erro": "metodo deve ser 'avalanche' ou 'bola_de_neve'"}
    if not dividas:
        return {"erro": "informe pelo menos uma divida"}
    ds = [{**d, "saldo": float(d["saldo"]), "parcela_minima": float(d["parcela_minima"]),
           "taxa_mensal_pct": float(d["taxa_mensal_pct"])} for d in dividas]
    minimos = sum(d["parcela_minima"] for d in ds)
    if orcamento_mensal < minimos:
        return {"erro": f"orcamento ({orcamento_mensal}) menor que a soma das parcelas minimas ({minimos})"}

    if metodo == "bola_de_neve":
        chave = lambda d: d["saldo"]
    else:
        chave = lambda d: -d["taxa_mensal_pct"]

    mes, juros_total, quitacao = 0, 0.0, []
    while any(d["saldo"] > 0.005 for d in ds) and mes < 600:
        mes += 1
        for d in ds:
            if d["saldo"] > 0.005:
                j = d["saldo"] * d["taxa_mensal_pct"] / 100
                d["saldo"] += j
                juros_total += j
        restante = orcamento_mensal
        ativos = sorted([d for d in ds if d["saldo"] > 0.005], key=chave)
        for d in ativos:
            pg = min(d["parcela_minima"], d["saldo"])
            d["saldo"] -= pg
            restante -= pg
        for d in ativos:
            if restante <= 0:
                break
            pg = min(restante, d["saldo"])
            d["saldo"] -= pg
            restante -= pg
        for d in ativos:
            if d["saldo"] <= 0.005 and d["nome"] not in [q["nome"] for q in quitacao]:
                quitacao.append({"nome": d["nome"], "mes": mes})

    if any(d["saldo"] > 0.005 for d in ds):
        return {"erro": "o orcamento nao cobre os juros: as dividas nao sao quitadas em 600 meses"}
    return {
        "metodo": metodo,
        "meses_ate_quitar": mes,
        "total_juros": round(juros_total, 2),
        "ordem_quitacao": quitacao,
    }


@mcp.tool()
def simular_renda_fixa(valor: float, meses: int, taxa_anual_pct: float = 0.0,
                       taxa_mensal_pct: float = 0.0, aporte_mensal: float = 0.0,
                       isento_ir: bool = False) -> dict:
    """Simula uma aplicacao de renda fixa e devolve o montante bruto, o IR e o montante liquido.
    Informe a taxa ANUAL (ex.: CDI ou Selic em % a.a. ja multiplicada pelo percentual do produto)
    ou a taxa MENSAL (ex.: 0.5 para a poupanca). A conversao anual -> mensal e feita aqui.
    IR regressivo sobre o rendimento (prazo em dias = meses x 365/12): 22,5% ate 180 dias, 20% ate 360,
    17,5% ate 720 e 15% acima. isento_ir=True para poupanca e LCI/LCA (pessoa fisica).
    Simplificacao: com aportes, todo o rendimento usa a aliquota do prazo total."""
    if valor < 0 or meses <= 0:
        return {"erro": "valor nao pode ser negativo e meses deve ser maior que zero"}
    if taxa_mensal_pct:
        i = taxa_mensal_pct / 100
    else:
        i = (1 + taxa_anual_pct / 100) ** (1 / 12) - 1
    fator = (1 + i) ** meses
    bruto = valor * fator + (aporte_mensal * (fator - 1) / i if i else aporte_mensal * meses)
    investido = valor + aporte_mensal * meses
    rendimento = bruto - investido
    dias = round(meses * 365 / 12)
    aliquota = 0.0 if isento_ir else (0.225 if dias <= 180 else 0.20 if dias <= 360
                                      else 0.175 if dias <= 720 else 0.15)
    ir = max(rendimento, 0) * aliquota
    return {
        "taxa_mensal_usada_pct": round(i * 100, 4),
        "total_investido": round(investido, 2),
        "montante_bruto": round(bruto, 2),
        "aliquota_ir_pct": aliquota * 100,
        "imposto_renda": round(ir, 2),
        "montante_liquido": round(bruto - ir, 2),
        "rendimento_liquido": round(rendimento - ir, 2),
    }


if __name__ == "__main__":
    mcp.run()  # transporte stdio