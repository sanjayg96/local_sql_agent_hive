import streamlit as st
import uuid
from langchain_core.messages import HumanMessage, AIMessage
from hive import hive_app

st.set_page_config(page_title="Data Hive Chat", page_icon="🐝", layout="wide")
st.title("🐝 Hive Text-to-SQL Multi-Agent")

# Initialize session state
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4()) # Unique thread for MemorySaver
if "messages" not in st.session_state:
    st.session_state.messages = []
if "schema_context" not in st.session_state:
    # Dummy schema for UI purposes. In production, load from data/tables.json based on selected DB
    st.session_state.schema_context = "Table: users (id, name, age), Table: orders (id, user_id, amount, year)"

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat Input
if prompt := st.chat_input("Ask a question about your database (e.g., 'Show me total orders by year')"):
    # Add user message to UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Swarm is processing..."):
            # Graph configuration
            config_graph = {"configurable": {"thread_id": st.session_state.thread_id}}
            state_input = {
                "question": prompt,
                "raw_schema": st.session_state.schema_context,
                "retries": 0,
                "trace": [] 
            }

            # If it's a follow-up, LangGraph MemorySaver uses thread_id to append to existing messages internally
            # We just pass the new human message in
            state_input["messages"] = [HumanMessage(content=prompt)]

            # Invoke Graph
            result = hive_app.invoke(state_input, config=config_graph)
            
            # Extract final answer
            final_message = result["messages"][-1].content
            st.markdown(final_message)
            st.session_state.messages.append({"role": "assistant", "content": final_message})

            # --- Trace Viewer Expander ---
            with st.expander("🔍 View Agent Trace (Under the Hood)", expanded=False):
                for step in result["trace"]:
                    st.markdown(f"**{step['agent']}** ({step['action']})")
                    st.code(step['data'], language="sql" if step["agent"] == "Architect" else "json")
                
                if result["retries"] > 0:
                    st.warning(f"Auditor caught errors and self-corrected {result['retries']} times.")