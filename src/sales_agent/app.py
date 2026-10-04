"""Streamlit Presentation Layer for the Multi-Provider Sales DB Agent."""

import streamlit as st
from sales_agent.agent import SalesAgent

# Page configuration
st.set_page_config(page_title="Sales DB Autonomous Agent", page_icon="📊", layout="centered")

st.title("📊 Sales Database Analytics Agent")
st.caption("Gemini sales agent | PostgreSQL facts | optional schema guidance")

# Initialize agent once per session state
if "agent" not in st.session_state:
    try:
        st.session_state.agent = SalesAgent()
        st.session_state.ready = True
        st.session_state.init_error = None
    except Exception as e:
        st.session_state.agent = None
        st.session_state.ready = False
        st.session_state.init_error = str(e)

# Sidebar: Environment & Capability Diagnostics
with st.sidebar:
    st.header("Runtime Diagnostics")
    if st.session_state.ready:
        st.success("Agent Online")
        st.write(f"**Provider:** `{st.session_state.agent.provider.upper()}`")
        st.write(f"**Target Model:** `{(st.session_state.agent.model or 'catalog selection on first use')}`")
    else:
        st.error("Agent Offline")
        st.warning(st.session_state.init_error)
        st.markdown(
            "**Prerequisites to run:**\n"
            "1. Export `DATABASE_URL` in your private shell environment\n"
            "2. Export `GEMINI_API_KEY`; optionally select `GEMINI_MODEL`."
        )

# Initialize chat conversation history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hello! I can query the configured sales database when you ask. Ask me any question about customers, orders, products, or revenue.",
        }
    ]

# Render conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User query input
if prompt := st.chat_input("Ask a question about sales..."):
    if not st.session_state.ready:
        st.error(f"Agent cannot run: {st.session_state.init_error}")
        st.stop()

    # Append and render user prompt
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Execute ReAct loop and render assistant response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing schema and executing queries..."):
            answer = st.session_state.agent.run(prompt)
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
