import json
import logging
from typing import Annotated, TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from sandbox_sql import execute_sql  # Your existing module

# Load Config
with open("config.json", "r") as f:
    config = json.load(f)

# Initialize Models (Memory Management via keep_alive)
# Analyst: Keep alive for 5m (lightweight, highly used)
analyst_llm = ChatOllama(model=config["analyst_model"], format="json", keep_alive="5m")
# Architect: Keep alive for 5m (core generator)
architect_llm = ChatOllama(model=config["architect_model"], keep_alive="5m")
# Auditor: Drop immediately after use (keep_alive=0) to free RAM since it only runs on errors
auditor_llm = ChatOllama(model=config["auditor_model"], keep_alive=0)

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "The chat history"]
    question: str
    raw_schema: str
    db_id: str
    pruned_schema: str
    sql_query: str
    sandbox_result: Dict[str, Any]
    retries: int
    trace: List[Dict[str, str]] # For Streamlit UI

# --- Nodes ---
def analyze_schema(state: AgentState):
    """
    Agent 1: Schema Analyst. 
    For small databases (like Spider), passing the full schema is better than pruning.
    We format it cleanly for the Architect.
    """
    # Instead of destructive pruning, we structure the raw schema perfectly for the coder.
    structured_schema = f"### DATABASE SCHEMA ###\n{state['raw_schema']}\n"
    
    state["trace"].append({"agent": "Analyst", "action": "Structured Schema", "data": "Full schema passed."})
    return {"pruned_schema": structured_schema, "trace": state["trace"]}

def generate_sql(state: AgentState):
    """Agent 2: Writes the raw SQLite query."""
    sys_prompt = """You are an elite expert SQLite developer. 
    Write ONLY valid SQLite code to answer the user's question based on the schema provided. 
    Pay strict attention to table relationships and foreign keys for JOINs.
    Do not use markdown formatting like ```sql. Just the raw query."""
    
    if state["retries"] > 0 and state.get("sandbox_result"):
        error_msg = state["sandbox_result"].get("error", "Unknown error")
        prev_data = state["sandbox_result"].get("data", [])
        
        sys_prompt += f"\n\n### SELF-CORRECTION ###\n"
        sys_prompt += f"PREVIOUS QUERY: {state['sql_query']}\n"
        
        if not state["sandbox_result"].get("success"):
            sys_prompt += f"EXECUTION ERROR: {error_msg}\nFix the syntax or column names."
        elif len(prev_data) == 0:
            sys_prompt += f"LOGICAL ERROR: The query executed but returned no data ([]). You likely missed a JOIN, used the wrong WHERE condition, or queried the wrong table. Rethink the logic."

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"Schema:\n{state['pruned_schema']}\n\nQuestion: {state['question']}")
    ]
    
    response = architect_llm.invoke(messages)
    clean_sql = response.content.replace("```sql", "").replace("```", "").strip()
    
    state["trace"].append({"agent": "Architect", "action": "Generated SQL", "data": clean_sql})
    return {"sql_query": clean_sql, "trace": state["trace"]}

def run_sandbox(state: AgentState):
    """Agent 3: Executes the SQL against the local DB dynamically."""
    # Dynamically route to the correct Spider database
    db_path = f"data/database/{state['db_id']}/{state['db_id']}.sqlite"
    
    result = execute_sql(db_path, state["sql_query"])
    state["trace"].append({"agent": "Sandbox", "action": "Executed Query", "data": str(result)})
    return {"sandbox_result": result, "trace": state["trace"]}

def audit_result(state: AgentState):
    """Agent 4: Checks for execution errors AND empty logical returns."""
    result = state["sandbox_result"]
    
    # Trigger a retry if execution fails OR if it returns an empty list (likely a bad JOIN)
    is_empty_return = result.get("success") and len(result.get("data", [])) == 0
    
    if not result.get("success") or is_empty_return:
        reason = "Execution Error" if not result.get("success") else "Empty Logic Result"
        state["trace"].append({"agent": "Auditor", "action": f"Retry Triggered ({reason})", "data": result.get('error', 'Returned []')})
        return {"retries": state["retries"] + 1, "trace": state["trace"]}
    
    # If successful and returned data, format final answer
    state["trace"].append({"agent": "Auditor", "action": "Approved", "data": str(result['data'])})
    return {"messages": [AIMessage(content=str(result["data"]))] }

# --- Routing Logic ---
def route_audit(state: AgentState):
    if state["sandbox_result"].get("success") or state["retries"] >= config["max_retries"]:
        return END
    return "generate_sql"

# --- Graph Compilation ---
workflow = StateGraph(AgentState)

workflow.add_node("analyze_schema", analyze_schema)
workflow.add_node("generate_sql", generate_sql)
workflow.add_node("run_sandbox", run_sandbox)
workflow.add_node("audit_result", audit_result)

workflow.set_entry_point("analyze_schema")
workflow.add_edge("analyze_schema", "generate_sql")
workflow.add_edge("generate_sql", "run_sandbox")
workflow.add_edge("run_sandbox", "audit_result")
workflow.add_conditional_edges("audit_result", route_audit)

# Use MemorySaver to maintain conversational context across graph invocations
memory = MemorySaver()
hive_app = workflow.compile(checkpointer=memory)