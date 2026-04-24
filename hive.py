import json
import sqlite3
import logging
from typing import Annotated, TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from sandbox_sql import execute_sql

# Load Config
with open("config.json", "r") as f:
    config = json.load(f)

# Initialize Models
architect_llm = ChatOllama(model=config["architect_model"], keep_alive="5m")
auditor_llm = ChatOllama(model=config["auditor_model"], keep_alive=0)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "The chat history"]
    question: str
    raw_schema: str
    db_id: str
    pruned_schema: str
    sql_query: str
    sandbox_result: Dict[str, Any]
    retries: int
    error_classification: str # NEW: Tracks the type of error for targeted retries
    trace: List[Dict[str, str]]

def get_table_peek(db_path: str) -> str:
    """Helper: Fetches 3 sample rows from every table to prevent categorical hallucinations."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"]
        
        peek_info = "\n### TABLE SAMPLES (LIMIT 3) ###\n"
        for table in tables:
            cursor.execute(f"PRAGMA table_info('{table}');")
            columns = [col[1] for col in cursor.fetchall()]
            cursor.execute(f"SELECT * FROM '{table}' LIMIT 3;")
            rows = cursor.fetchall()
            peek_info += f"-- Table: {table} --\nColumns: {', '.join(columns)}\nSample Data: {rows}\n\n"
        conn.close()
        return peek_info
    except Exception as e:
        return f"Could not load samples: {str(e)}"

def analyze_schema(state: AgentState):
    """Agent 1: Schema Analyst + Peek Method."""
    db_path = f"data/database/{state['db_id']}/{state['db_id']}.sqlite"
    peek_data = get_table_peek(db_path)
    
    # Combine full schema with the actual row data
    structured_schema = f"### DATABASE SCHEMA ###\n{state['raw_schema']}\n{peek_data}"
    
    state["trace"].append({"agent": "Analyst", "action": "Structured Schema w/ Peek", "data": "Full schema + 3-row samples attached."})
    return {"pruned_schema": structured_schema, "trace": state["trace"]}

def generate_sql(state: AgentState):
    """Agent 2: Writes the raw SQLite query with Targeted Self-Correction."""
    sys_prompt = """You are an elite expert SQLite developer. 
    Write ONLY valid SQLite code to answer the user's question based on the schema and sample data.
    Pay strict attention to table relationships and foreign keys for JOINs.
    Look at the sample data to understand categorical formats (e.g., 'M' vs 'Male').
    Do not use markdown formatting like ```sql. Just the raw query."""
    
    if state["retries"] > 0 and state.get("sandbox_result"):
        error_msg = state["sandbox_result"].get("error", "Unknown error")
        error_class = state.get("error_classification", "UNKNOWN")
        
        sys_prompt += f"\n\n### TARGETED SELF-CORRECTION ###\n"
        sys_prompt += f"PREVIOUS QUERY: {state['sql_query']}\n"
        
        if error_class == "SYNTAX_ERROR":
            sys_prompt += f"ERROR CLASSIFICATION: Syntax/Execution Failure.\n"
            sys_prompt += f"SQLITE ERROR: {error_msg}\n"
            sys_prompt += "Fix the syntax, table name, or column name exactly as SQLite suggests."
        elif error_class == "EMPTY_LOGIC":
            sys_prompt += f"ERROR CLASSIFICATION: Logical Failure (Returned Empty Data).\n"
            sys_prompt += "The query executed successfully but returned zero rows ([]). You likely missed a required JOIN, used an overly restrictive WHERE clause, or checked for a value that doesn't exist in the format you provided. Rethink the logic."

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"Schema & Data:\n{state['pruned_schema']}\n\nQuestion: {state['question']}")
    ]
    
    response = architect_llm.invoke(messages)
    clean_sql = response.content.replace("```sql", "").replace("```", "").strip()
    
    state["trace"].append({"agent": "Architect", "action": "Generated SQL", "data": clean_sql})
    return {"sql_query": clean_sql, "trace": state["trace"]}

def run_sandbox(state: AgentState):
    db_path = f"data/database/{state['db_id']}/{state['db_id']}.sqlite"
    result = execute_sql(db_path, state["sql_query"])
    state["trace"].append({"agent": "Sandbox", "action": "Executed Query", "data": str(result)})
    return {"sandbox_result": result, "trace": state["trace"]}

def audit_result(state: AgentState):
    """Agent 4: Classifies errors for the Architect."""
    result = state["sandbox_result"]
    is_empty_return = result.get("success") and len(result.get("data", [])) == 0
    
    if not result.get("success") or is_empty_return:
        error_class = "SYNTAX_ERROR" if not result.get("success") else "EMPTY_LOGIC"
        reason = result.get('error') if error_class == "SYNTAX_ERROR" else "Returned []"
        
        state["trace"].append({"agent": "Auditor", "action": f"Retry Triggered ({error_class})", "data": reason})
        return {"retries": state["retries"] + 1, "error_classification": error_class, "trace": state["trace"]}
    
    state["trace"].append({"agent": "Auditor", "action": "Approved", "data": str(result['data'])})
    return {"messages": [AIMessage(content=str(result["data"]))]}

# --- Routing Logic ---
def route_audit(state: AgentState):
    if state["sandbox_result"].get("success") and len(state["sandbox_result"].get("data", [])) > 0:
        return END
    if state["retries"] >= config["max_retries"]:
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

memory = MemorySaver()
hive_app = workflow.compile(checkpointer=memory)