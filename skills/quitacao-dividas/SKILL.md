---
name: quitacao-dividas
description: Monta um plano de quitacao de dividas comparando avalanche e bola de neve. Use quando o usuario quiser sair das dividas ou perguntar qual pagar primeiro.
---

# Montar plano de quitacao de dividas

Use quando o usuario quiser sair das dividas ou perguntar qual pagar primeiro.

## Passos
1. Pergunte, se faltar: para cada divida, o nome, o saldo, a taxa de juros mensal e a parcela minima. Pergunte tambem quanto ele consegue pagar por mes no total.
2. Confira se o orcamento mensal cobre a soma das parcelas minimas. Se nao cobrir, avise e sugira renegociar ou aumentar o orcamento antes de continuar.
3. Chame `plano_quitacao_dividas` duas vezes com os mesmos dados: `metodo="avalanche"` e `metodo="bola_de_neve"`.
4. Compare os dois resultados: meses ate quitar, total de juros e ordem de quitacao. Explique a diferenca (avalanche costuma pagar menos juros; bola de neve da vitorias rapidas).
5. Use `buscar_documentos` para citar uma orientacao de educacao financeira (por exemplo, cartilha do Banco Central sobre endividamento) que sustente a recomendacao.
6. Termine com um resumo curto: metodo sugerido, prazo e proximo passo concreto. Nao recomende produtos financeiros especificos.