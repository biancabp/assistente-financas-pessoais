from pathlib import Path
from langchain_core.tools import tool

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _read_header(text: str) -> dict:
    header = {}
    if text.startswith("---"):
        bloco = text.split("---", 2)[1]
        for linha in bloco.strip().splitlines():
            if ":" in linha:
                k, v = linha.split(":", 1)
                header[k.strip()] = v.strip()
    return header


def get_skill_catalog() -> str:
    """Texto para a mensagem de sistema: uma linha por skill."""
    linhas = []
    for md_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        h = _read_header(md_file.read_text(encoding="utf-8"))
        linhas.append(f"- {h.get('name', md_file.parent.name)}: {h.get('description', '')}")
    return "Skills disponiveis (chame load_skill para ler os passos):\n" + "\n".join(linhas)


@tool
def load_skill(nome: str) -> str:
    """Carrega as instrucoes completas de uma skill pelo nome."""
    disponiveis = sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))
    if nome not in disponiveis:  # tambem impede caminhos como "../.."
        return f"Skill '{nome}' nao encontrada. Disponiveis: {', '.join(disponiveis)}"
    arquivo = SKILLS_DIR / nome / "SKILL.md"
    return arquivo.read_text(encoding="utf-8")