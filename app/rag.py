"""RAG: download das cartilhas oficiais, indexacao (FAISS) e a ferramenta buscar_documentos.

Uso pela linha de comando (a partir da raiz do repositorio):
    python app/rag.py          # baixa os PDFs e constroi o indice
"""
import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.tools import tool

RAIZ = Path(__file__).resolve().parent.parent
DOCS_DIR = RAIZ / "rag" / "docs"
INDICE_DIR = RAIZ / "rag" / "indice"
FONTES_JSON = RAIZ / "rag" / "fontes.json"

EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
# abaixo deste valor de similaridade (cosseno) a busca e considerada fraca
# sem nem precisar perguntar ao LLM avaliador
LIMIAR_SIMILARIDADE = float(os.environ.get("RAG_LIMIAR", "0.30"))

FONTES = [
    {
        "id": "bcb_caderno_financas_pessoais",
        "titulo": "Caderno de Educação Financeira – Gestão de Finanças Pessoais (Cuidando do seu dinheiro)",
        "orgao": "Banco Central do Brasil",
        "ano": 2026,
        "url": "https://www.bcb.gov.br/content/cidadaniafinanceira/documentos_cidadania/Cuidando_do_seu_dinheiro_Gestao_de_Financas_Pessoais/caderno_cidadania_financeira.pdf",
    },
    {
        "id": "cvm_guia_planejamento",
        "titulo": "Guia de Planejamento Financeiro",
        "orgao": "Comissão de Valores Mobiliários (CVM)",
        "ano": None,
        "url": "https://www.gov.br/investidor/pt-br/educacional/publicacoes-educacionais/guias/guia-de-planejamento-financeiro/guia-planejamento-financeiro.pdf/@@download/file",
    },
    {
        "id": "cvm_caderno_1",
        "titulo": "Caderno CVM de Educação Financeira nº 1",
        "orgao": "Comissão de Valores Mobiliários (CVM)",
        "ano": None,
        "url": "https://www.gov.br/investidor/pt-br/educacional/publicacoes-educacionais/cadernos/cvm-caderno-1.pdf/@@download/file",
    },
    {
        "id": "cvm_caderno_10",
        "titulo": "Caderno CVM nº 10 – Diversificação e composição de carteiras",
        "orgao": "Comissão de Valores Mobiliários (CVM)",
        "ano": None,
        "url": "https://www.gov.br/previdencia/pt-br/outros/imagens/2016/08/CVM-Caderno-10semISBNparaimpressao.pdf",
    },
    {
        "id": "fgc_garantia",
        "titulo": "Material informativo sobre a garantia do FGC (versão dez/2025)",
        "orgao": "Fundo Garantidor de Créditos (FGC)",
        "ano": 2025,
        "url": "https://fgc.org.br/documents/d/guest/material-para-corretoras_versao-dezembro2025",
    },
]


# ---------------------------------------------------------------------------
# 1. Download
# ---------------------------------------------------------------------------
def baixar_documentos() -> list[dict]:
    import requests

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    baixados = []
    for f in FONTES:
        destino = DOCS_DIR / f"{f['id']}.pdf"
        if not destino.exists():
            try:
                r = requests.get(f["url"], timeout=60, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    raise ValueError("o arquivo baixado nao e um PDF")
                destino.write_bytes(r.content)
            except Exception as e:  # segue com os outros documentos
                print(f"[ERRO] {f['id']}: {e}")
                continue
        baixados.append({**f, "arquivo": destino.name,
                         "data_download": date.today().isoformat()})
        print(f"[ok] {f['titulo']} ({destino.stat().st_size // 1024} KB)")
    FONTES_JSON.write_text(json.dumps(baixados, ensure_ascii=False, indent=2), encoding="utf-8")
    return baixados


# ---------------------------------------------------------------------------
# 2. Indexacao
# ---------------------------------------------------------------------------
def get_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    # embeddings normalizados: distancia L2^2 = 2 - 2*cosseno
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL,
                                 encode_kwargs={"normalize_embeddings": True})


def carregar_pdfs() -> list[Document]:
    from langchain_community.document_loaders import PyPDFLoader

    fontes = json.loads(FONTES_JSON.read_text(encoding="utf-8"))
    docs = []
    for f in fontes:
        for pagina in PyPDFLoader(str(DOCS_DIR / f["arquivo"])).load():
            texto = " ".join(pagina.page_content.split())
            if len(texto) < 80:  # capas, paginas em branco
                continue
            docs.append(Document(page_content=texto, metadata={
                "fonte": f["titulo"], "orgao": f["orgao"], "url": f["url"],
                "pagina": pagina.metadata.get("page", 0) + 1,
            }))
    return docs


def indexar(docs: list[Document], embeddings, destino: Path | None = INDICE_DIR):
    from langchain_community.vectorstores import FAISS
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150).split_documents(docs)
    vs = FAISS.from_documents(chunks, embeddings)
    if destino is not None:
        vs.save_local(str(destino))
    print(f"Indice: {len(docs)} paginas -> {len(chunks)} trechos")
    return vs


def construir_indice():
    baixar_documentos()
    return indexar(carregar_pdfs(), get_embeddings())


@lru_cache(maxsize=1)
def carregar_indice():
    from langchain_community.vectorstores import FAISS

    if not (INDICE_DIR / "index.faiss").exists():
        raise FileNotFoundError("Indice nao encontrado. Rode antes: python app/rag.py")
    return FAISS.load_local(str(INDICE_DIR), get_embeddings(),
                            allow_dangerous_deserialization=True)  # indice gerado por nos


# ---------------------------------------------------------------------------
# 3. Ferramenta
# ---------------------------------------------------------------------------
def buscar(vs, consulta: str, k: int = 4) -> tuple[str, dict]:
    pares = vs.similarity_search_with_score(consulta, k=k)
    linhas, scores = [], []
    for i, (doc, dist) in enumerate(pares, 1):
        sim = round(1 - float(dist) / 2, 3)  # cosseno a partir de L2^2
        scores.append(sim)
        m = doc.metadata
        linhas.append(f"[{i}] Fonte: {m['fonte']} ({m['orgao']}), p. {m['pagina']} | "
                      f"similaridade {sim}\n{doc.page_content}")
    artefato = {"consulta": consulta, "scores": scores,
                "max_score": max(scores) if scores else 0.0,
                "fontes": [d.metadata["fonte"] for d, _ in pares]}
    if not linhas:
        return "Nenhum trecho encontrado.", artefato
    return "\n\n".join(linhas), artefato


@tool(response_format="content_and_artifact")
def buscar_documentos(consulta: str) -> tuple[str, dict]:
    """Busca trechos nas cartilhas oficiais de educacao financeira (Banco Central, CVM e
    FGC). Use para conceitos, orientacoes e regras (orcamento, endividamento,
    credito, reserva, planejamento, renda fixa, diversificacao, FGC). Escreva uma consulta curta e especifica,
    com termos que provavelmente aparecem no texto."""
    return buscar(carregar_indice(), consulta)


if __name__ == "__main__":
    construir_indice()