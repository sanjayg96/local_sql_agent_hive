import json
import time
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from hive import hive_app, config
from sandbox_sql import execute_sql

def load_spider_data(limit=None):
    with open("data/dev.json", "r") as f:
        data = json.load(f)
    with open("data/tables.json", "r") as f:
        schemas = {db["db_id"]: db for db in json.load(f)}
    
    if limit:
        return data[:limit], schemas
    return data, schemas

def compare_results(truth_data: list, pred_data: list) -> bool:
    if not truth_data and not pred_data:
        return True
    if not truth_data or not pred_data:
        return False
        
    try:
        truth_set = set([frozenset(row.items()) if isinstance(row, dict) else tuple(row) for row in truth_data])
        pred_set = set([frozenset(row.items()) if isinstance(row, dict) else tuple(row) for row in pred_data])
        return truth_set == pred_set
    except Exception:
        return str(truth_data) == str(pred_data)

def evaluate(batch_size=50, cooldown_seconds=60, limit=None):
    # Pass limit=None to run all 1034 questions
    data, schemas = load_spider_data(limit=limit)
    single_model = ChatOllama(model=config["architect_model"])
    
    metrics = {"zero_shot": {"correct": 0, "latency": 0}, "hive": {"correct": 0, "latency": 0, "retries": 0}}
    total_questions = len(data)
    
    print(f"Benchmarking Zero-Shot ({config['architect_model']}) vs Hive on {total_questions} questions...\n")

    for idx, item in enumerate(data):
        # --- Thermal Throttling Logic ---
        if idx > 0 and idx % batch_size == 0:
            print(f"\n[Thermal Control] Batch of {batch_size} complete. Cooling down for {cooldown_seconds} seconds...")
            time.sleep(cooldown_seconds)
            print("Resuming benchmark...\n")

        db_id = item["db_id"]
        question = item["question"]
        ground_truth_sql = item["query"]
        raw_schema = str(schemas.get(db_id, "No schema found"))
        current_db_path = f"data/database/{db_id}/{db_id}.sqlite"
        
        print(f"[{idx+1}/{total_questions}] DB: {db_id} | Q: {question}")

        gt_result = execute_sql(current_db_path, ground_truth_sql)
        gt_data = gt_result.get("data", [])

        # --- 1. Zero-Shot Baseline ---
        start_time = time.time()
        sys_prompt = f"Write valid SQLite code to answer the user's question. No markdown, just SQL. Schema: {raw_schema}"
        zs_res = single_model.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=question)])
        clean_zs_sql = zs_res.content.replace("```sql", "").replace("```", "").strip()
        
        zs_exec = execute_sql(current_db_path, clean_zs_sql)
        metrics["zero_shot"]["latency"] += (time.time() - start_time)
        
        if zs_exec.get("success") and compare_results(gt_data, zs_exec.get("data", [])):
            metrics["zero_shot"]["correct"] += 1
            print("  -> Zero-Shot: Match ✅")
        else:
            print("  -> Zero-Shot: Failed ❌")

        # --- 2. Multi-Agent Hive ---
        start_time = time.time()
        state_input = {
            "messages": [HumanMessage(content=question)],
            "question": question,
            "raw_schema": raw_schema,
            "db_id": db_id,  
            "retries": 0,
            "trace": []
        }
        
        config_graph = {"configurable": {"thread_id": f"eval_{idx}"}}
        hive_res = hive_app.invoke(state_input, config=config_graph)
        
        metrics["hive"]["latency"] += (time.time() - start_time)
        metrics["hive"]["retries"] += hive_res.get("retries", 0)
        
        hive_exec = hive_res.get("sandbox_result", {})
        if hive_exec.get("success") and compare_results(gt_data, hive_exec.get("data", [])):
            metrics["hive"]["correct"] += 1
            print("  -> Hive: Match ✅")
        else:
            print("  -> Hive: Failed ❌")

    # --- Print Terminal Metrics ---
    print("\n" + "="*45)
    print("🏆 FULL RESULT-SET BENCHMARK")
    print("="*45)
    print(f"Zero-Shot Exact Data Match: {(metrics['zero_shot']['correct']/total_questions)*100:.2f}%")
    print(f"Hive Architecture Exact Match: {(metrics['hive']['correct']/total_questions)*100:.2f}%")
    print("-" * 45)
    print(f"Zero-Shot Avg Latency: {metrics['zero_shot']['latency']/total_questions:.2f}s")
    print(f"Hive Avg Latency: {metrics['hive']['latency']/total_questions:.2f}s")
    print(f"Hive Avg Retries/Query: {metrics['hive']['retries']/total_questions:.2f}")
    print("="*45)

if __name__ == "__main__":
    # Run all questions, cool down for 60s every 50 questions
    evaluate(batch_size=50, cooldown_seconds=60, limit=None)