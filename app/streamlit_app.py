import uuid

import streamlit as st

try:
    from agente import chat  # grafo + memoria (app/agente.py)
except ImportError as e:  # so para ver a interface sem o resto do projeto
    st.warning(f"agente indisponivel ({e}); usando respostas de teste")

    def chat(thread_id: str, texto: str) -> dict:
        return {"resposta": f"(stub) voce disse: {texto}", "tools_called": [],
                "skills_loaded": [], "consultas_rag": [], "guardrail": None}

st.set_page_config(page_title="Assistente de Finanças", page_icon="💰")
st.title("💰 Assistente de Finanças Pessoais")
st.caption("Educação financeira: orçamento, dívidas, reserva, crédito e conceitos de investimento. "
           "Não faz recomendação personalizada de investimento.")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.msgs = []

with st.sidebar:
    st.caption(f"Conversa: {st.session_state.thread_id[:8]}")
    if st.button("Nova conversa"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.msgs = []
        st.rerun()


def detalhes(m: dict):
    with st.expander("Ferramentas e skills usadas"):
        st.write("**Ferramentas:**", ", ".join(m.get("tools_called") or []) or "nenhuma")
        st.write("**Skills:**", ", ".join(m.get("skills_loaded") or []) or "nenhuma")
        if m.get("consultas_rag"):
            st.write("**Consultas ao RAG:**", " | ".join(m["consultas_rag"]))
        if m.get("guardrail"):
            st.write("**Guardrail:**", m["guardrail"])


for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            detalhes(m)

if prompt := st.chat_input("Pergunte sobre finanças..."):
    st.session_state.msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            r = chat(st.session_state.thread_id, prompt)
    st.session_state.msgs.append({"role": "assistant", "content": r["resposta"], **{
        k: r.get(k) for k in ("tools_called", "skills_loaded", "consultas_rag", "guardrail")}})
    st.rerun()