# import json
# import time
# import random
# import sys
# from langchain_ollama import ChatOllama
# from langchain_core.messages import HumanMessage, SystemMessage
# from hive import hive_app, config, get_table_peek
# from sandbox_sql import execute_sql

# # --- FRONTIER MODEL PRICING (e.g., GPT-4o) ---
# COST_PER_1M_INPUT = 2.50  
# COST_PER_1M_OUTPUT = 10.00 

# def estimate_tokens(text: str) -> int:
#     """Heuristic: 1 token is roughly 4 characters."""
#     return len(str(text)) // 4

# def calculate_cost(input_str: str, output_str: str) -> float:
#     in_tokens = estimate_tokens(input_str)
#     out_tokens = estimate_tokens(output_str)
#     return (in_tokens / 1_000_000 * COST_PER_1M_INPUT) + (out_tokens / 1_000_000 * COST_PER_1M_OUTPUT)

# def format_time(seconds: float) -> str:
#     """Formats seconds into readable HH:MM:SS."""
#     m, s = divmod(int(seconds), 60)
#     h, m = divmod(m, 60)
#     if h > 0: return f"{h}h {m}m {s}s"
#     return f"{m}m {s}s"

# def load_spider_data(sample_size=500):
#     with open("data/dev.json", "r") as f:
#         data = json.load(f)
#     with open("data/tables.json", "r") as f:
#         schemas = {db["db_id"]: db for db in json.load(f)}
    
#     # Mathematical representation: Random seeded sample
#     random.seed(42)
#     sampled_data = random.sample(data, min(sample_size, len(data)))
#     return sampled_data, schemas

# def compare_results(truth_data: list, pred_data: list) -> bool:
#     if not truth_data and not pred_data: return True
#     if not truth_data or not pred_data: return False
#     try:
#         truth_set = set([frozenset(row.items()) if isinstance(row, dict) else tuple(row) for row in truth_data])
#         pred_set = set([frozenset(row.items()) if isinstance(row, dict) else tuple(row) for row in pred_data])
#         return truth_set == pred_set
#     except Exception:
#         return str(truth_data) == str(pred_data)

# def render_hud(idx, total, zs_correct, hive_correct, total_cost_saved, start_time):
#     """Renders an inline updating HUD with Elapsed Time and ETA."""
#     zs_acc = (zs_correct / idx) * 100 if idx > 0 else 0
#     hive_acc = (hive_correct / idx) * 100 if idx > 0 else 0
    
#     # Time Calculations
#     elapsed = time.time() - start_time
#     if idx > 0:
#         time_per_item = elapsed / idx
#         eta_seconds = time_per_item * (total - idx)
#         eta_str = format_time(eta_seconds)
#     else:
#         eta_str = "Calculating..."
        
#     elapsed_str = format_time(elapsed)

#     # Progress Bars
#     bar_len = 25
#     zs_fill = int((zs_acc / 100) * bar_len)
#     hive_fill = int((hive_acc / 100) * bar_len)
#     zs_bar = "█" * zs_fill + "-" * (bar_len - zs_fill)
#     hive_bar = "█" * hive_fill + "-" * (bar_len - hive_fill)
    
#     # Move cursor up 7 lines and overwrite
#     sys.stdout.write("\033[7A") 
#     sys.stdout.write(f"\033[K━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
#     sys.stdout.write(f"\033[K 🏆 REAL-TIME BENCHMARK [{idx}/{total}]\n")
#     sys.stdout.write(f"\033[K ⏱️  Elapsed: {elapsed_str} | ETA: {eta_str}\n")
#     sys.stdout.write(f"\033[K ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
#     sys.stdout.write(f"\033[K Single SLM:     [{zs_bar}] {zs_acc:>5.1f}%\n")
#     sys.stdout.write(f"\033[K Swarm of SLMs:  [{hive_bar}] {hive_acc:>5.1f}%\n")
#     sys.stdout.write(f"\033[K 💰 Est. API Cost Saved: ${total_cost_saved:.4f}\n")
#     sys.stdout.flush()

# def evaluate(sample_size=500, batch_size=50, cooldown_seconds=60):
#     data, schemas = load_spider_data(sample_size)
#     single_model = ChatOllama(model=config["architect_model"])
    
#     zs_correct, hive_correct = 0, 0
#     total_cost_saved = 0.0
#     total_questions = len(data)
#     eval_start_time = time.time()
    
#     print(f"Initializing Hive Swarm Evaluation on {total_questions} randomized samples from Spider dataset...\n")
#     print(f"💻 Hardware: Apple Silicon (Target: M5 24GB)")
#     # Print blank lines to make room for the 7-line HUD
#     print("\n\n\n\n\n\n") 
#     render_hud(0, total_questions, 0, 0, 0.0, eval_start_time)

#     for idx, item in enumerate(data):
        
#         # --- THERMAL CONTROL ---
#         if idx > 0 and idx % batch_size == 0:
#             sys.stdout.write("\033[7A") 
#             sys.stdout.write("\033[K")
#             print(f"\n🌡️  [Thermal Control] Batch of {batch_size} complete. Cooling down for {cooldown_seconds}s...")
#             time.sleep(cooldown_seconds)
#             print("\n\n\n\n\n") # Re-make room for HUD
            
#         db_id = item["db_id"]
#         question = item["question"]
#         ground_truth_sql = item["query"]
#         raw_schema = str(schemas.get(db_id, "No schema found"))
#         current_db_path = f"data/database/{db_id}/{db_id}.sqlite"
        
#         # Ground Truth
#         gt_result = execute_sql(current_db_path, ground_truth_sql)
#         gt_data = gt_result.get("data", [])
        
#         # --- 1. Zero-Shot Baseline ---
#         sys_prompt = f"Write valid SQLite code. No markdown. Schema: {raw_schema}"
#         zs_res = single_model.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=question)])
#         clean_zs_sql = zs_res.content.replace("```sql", "").replace("```", "").strip()
#         zs_exec = execute_sql(current_db_path, clean_zs_sql)
#         zs_match = zs_exec.get("success") and compare_results(gt_data, zs_exec.get("data", []))
#         if zs_match: zs_correct += 1
        
#         total_cost_saved += calculate_cost(sys_prompt + question, zs_res.content)

#         # --- 2. Multi-Agent Hive ---
#         state_input = {
#             "messages": [HumanMessage(content=question)],
#             "question": question,
#             "raw_schema": raw_schema,
#             "db_id": db_id,  
#             "retries": 0,
#             "trace": []
#         }
        
#         config_graph = {"configurable": {"thread_id": f"eval_{idx}"}}
#         hive_res = hive_app.invoke(state_input, config=config_graph)
        
#         hive_exec = hive_res.get("sandbox_result", {})
#         hive_match = hive_exec.get("success") and compare_results(gt_data, hive_exec.get("data", []))
#         if hive_match: hive_correct += 1
        
#         # Approximate Swarm Cost 
#         peek_estimate = get_table_peek(current_db_path)
#         swarm_in_chars = (len(sys_prompt) + len(raw_schema) + len(peek_estimate) + len(question)) * (hive_res.get("retries", 0) + 1)
#         swarm_out_chars = len(hive_res.get("sql_query", "")) * (hive_res.get("retries", 0) + 1)
#         total_cost_saved += calculate_cost("a"*swarm_in_chars, "a"*swarm_out_chars)

#         # --- Log & Update UI ---
#         sys.stdout.write("\033[7A") # Move up above HUD
#         sys.stdout.write("\033[K")  # Clear line
#         # log_msg = f"[{idx+1:03d}] DB: {db_id:<15} | ZS: {'✅' if zs_match else '❌'} | Swarm: {'✅' if hive_match else '❌'}"
#         # print(log_msg)
#         print("\n\n\n\n\n\n") # Push down to make room for HUD again
#         render_hud(idx + 1, total_questions, zs_correct, hive_correct, total_cost_saved, eval_start_time)

# if __name__ == "__main__":
#     # Runs 500 questions, cooling down for 60 seconds every 50 questions
#     evaluate(sample_size=500, batch_size=50, cooldown_seconds=70)

import json
import time
import random
import sys
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from hive import hive_app, config, get_table_peek
from sandbox_sql import execute_sql

# --- FRONTIER MODEL PRICING (e.g., GPT-4o) ---
COST_PER_1M_INPUT = 2.50  
COST_PER_1M_OUTPUT = 10.00 

def estimate_tokens(text: str) -> int:
    """Heuristic: 1 token is roughly 4 characters."""
    return len(str(text)) // 4

def calculate_cost(input_str: str, output_str: str) -> float:
    in_tokens = estimate_tokens(input_str)
    out_tokens = estimate_tokens(output_str)
    return (in_tokens / 1_000_000 * COST_PER_1M_INPUT) + (out_tokens / 1_000_000 * COST_PER_1M_OUTPUT)

def format_time(seconds: float) -> str:
    """Formats seconds into readable HH:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"

def load_spider_data(sample_size=500):
    with open("data/dev.json", "r") as f:
        data = json.load(f)
    with open("data/tables.json", "r") as f:
        schemas = {db["db_id"]: db for db in json.load(f)}
    
    # Random seeded sample for mathematical representation
    random.seed(42)
    sampled_data = random.sample(data, min(sample_size, len(data)))
    return sampled_data, schemas

def compare_results(truth_data: list, pred_data: list) -> bool:
    if not truth_data and not pred_data: return True
    if not truth_data or not pred_data: return False
    try:
        truth_set = set([frozenset(row.items()) if isinstance(row, dict) else tuple(row) for row in truth_data])
        pred_set = set([frozenset(row.items()) if isinstance(row, dict) else tuple(row) for row in pred_data])
        return truth_set == pred_set
    except Exception:
        return str(truth_data) == str(pred_data)

def render_hud(idx, total, zs_correct, hive_correct, total_cost_saved, start_time, zs_lat_total, hive_lat_total, hive_ret_total):
    """Renders an inline updating HUD with Latency, Retries, Time, and Cost."""
    zs_acc = (zs_correct / idx) * 100 if idx > 0 else 0
    hive_acc = (hive_correct / idx) * 100 if idx > 0 else 0
    
    # Averages
    zs_avg_lat = zs_lat_total / idx if idx > 0 else 0.0
    hive_avg_lat = hive_lat_total / idx if idx > 0 else 0.0
    hive_avg_ret = hive_ret_total / idx if idx > 0 else 0.0
    
    # Time Calculations
    elapsed = time.time() - start_time
    if idx > 0:
        time_per_item = elapsed / idx
        eta_seconds = time_per_item * (total - idx)
        eta_str = format_time(eta_seconds)
    else:
        eta_str = "Calculating..."
        
    elapsed_str = format_time(elapsed)

    # Progress Bars
    bar_len = 20
    zs_fill = int((zs_acc / 100) * bar_len)
    hive_fill = int((hive_acc / 100) * bar_len)
    zs_bar = "█" * zs_fill + "-" * (bar_len - zs_fill)
    hive_bar = "█" * hive_fill + "-" * (bar_len - hive_fill)
    
    # Move cursor up 7 lines and overwrite
    sys.stdout.write("\033[7A") 
    sys.stdout.write(f"\033[K━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    sys.stdout.write(f"\033[K 🏆 REAL-TIME BENCHMARK [{idx}/{total}]\n")
    sys.stdout.write(f"\033[K ⏱️  Elapsed: {elapsed_str} | ETA: {eta_str}\n")
    sys.stdout.write(f"\033[K ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    sys.stdout.write(f"\033[K Single SLM::    [{zs_bar}] {zs_acc:>5.1f}% | Avg. Latency: {zs_avg_lat:>4.1f}s\n")
    sys.stdout.write(f"\033[K Swarm of SLMs:  [{hive_bar}] {hive_acc:>5.1f}% | Avg. Latency: {hive_avg_lat:>4.1f}s  | Avg. Retries: {hive_avg_ret:.1f}\n")
    sys.stdout.write(f"\033[K 💰 Est. API Cost Saved: ${total_cost_saved:.4f}\n")
    sys.stdout.flush()

def evaluate(sample_size=500, batch_size=50, cooldown_seconds=60):
    data, schemas = load_spider_data(sample_size)
    single_model = ChatOllama(model=config["architect_model"])
    
    # Trackers
    zs_correct, hive_correct = 0, 0
    zs_lat_total, hive_lat_total, hive_ret_total = 0.0, 0.0, 0
    total_cost_saved = 0.0
    total_questions = len(data)
    eval_start_time = time.time()
    
    print(f"Initializing Hive Swarm Evaluation on {total_questions} randomized samples from Spider dataset...\n")
    print(f"💻 Hardware: Apple Silicon (Target: M5 24GB)")
    # Print blank lines to make room for the 7-line HUD
    print("\n\n\n\n\n\n") 
    render_hud(0, total_questions, 0, 0, 0.0, eval_start_time, 0.0, 0.0, 0)

    for idx, item in enumerate(data):
        
        # --- THERMAL CONTROL ---
        if idx > 0 and idx % batch_size == 0:
            sys.stdout.write("\033[7A") 
            sys.stdout.write("\033[K")
            print(f"\n🌡️  [Thermal Control] Batch of {batch_size} complete. Cooling down for {cooldown_seconds}s...")
            time.sleep(cooldown_seconds)
            print("\n\n\n\n\n") # Re-make room for HUD
            
        db_id = item["db_id"]
        question = item["question"]
        ground_truth_sql = item["query"]
        raw_schema = str(schemas.get(db_id, "No schema found"))
        current_db_path = f"data/database/{db_id}/{db_id}.sqlite"
        
        # Ground Truth
        gt_result = execute_sql(current_db_path, ground_truth_sql)
        gt_data = gt_result.get("data", [])
        
        # --- 1. Zero-Shot Baseline ---
        zs_start = time.time()
        sys_prompt = f"Write valid SQLite code. No markdown. Schema: {raw_schema}"
        zs_res = single_model.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=question)])
        clean_zs_sql = zs_res.content.replace("```sql", "").replace("```", "").strip()
        zs_exec = execute_sql(current_db_path, clean_zs_sql)
        
        zs_latency = time.time() - zs_start
        zs_lat_total += zs_latency
        
        zs_match = zs_exec.get("success") and compare_results(gt_data, zs_exec.get("data", []))
        if zs_match: zs_correct += 1
        
        total_cost_saved += calculate_cost(sys_prompt + question, zs_res.content)

        # --- 2. Multi-Agent Hive ---
        hive_start = time.time()
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
        
        hive_latency = time.time() - hive_start
        hive_lat_total += hive_latency
        hive_ret_total += hive_res.get("retries", 0)
        
        hive_exec = hive_res.get("sandbox_result", {})
        hive_match = hive_exec.get("success") and compare_results(gt_data, hive_exec.get("data", []))
        if hive_match: hive_correct += 1
        
        # Approximate Swarm Cost 
        peek_estimate = get_table_peek(current_db_path)
        swarm_in_chars = (len(sys_prompt) + len(raw_schema) + len(peek_estimate) + len(question)) * (hive_res.get("retries", 0) + 1)
        swarm_out_chars = len(hive_res.get("sql_query", "")) * (hive_res.get("retries", 0) + 1)
        total_cost_saved += calculate_cost("a"*swarm_in_chars, "a"*swarm_out_chars)

        # --- Log & Update UI ---
        sys.stdout.write("\033[7A") # Move up above HUD
        sys.stdout.write("\033[K")  # Clear line
        # log_msg = f"[{idx+1:03d}] DB: {db_id:<15} | ZS: {'✅' if zs_match else '❌'} | Swarm: {'✅' if hive_match else '❌'}"
        # print(log_msg)
        print("\n\n\n\n\n\n") # Push down to make room for HUD again
        render_hud(idx + 1, total_questions, zs_correct, hive_correct, total_cost_saved, eval_start_time, zs_lat_total, hive_lat_total, hive_ret_total)

if __name__ == "__main__":
    evaluate(sample_size=500, batch_size=50, cooldown_seconds=70)