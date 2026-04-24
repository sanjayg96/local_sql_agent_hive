# Local Multi-Agent Text-to-SQL Architecture (SLM Hive)

## Overview
This repository contains a privacy-first, fully local framework designed to translate natural language questions into executable SQL queries. Instead of relying on a single, massive cloud-based language model, this system orchestrates a "swarm" of specialized Small Language Models (SLMs) working collaboratively to understand schemas, write code, execute queries, and self-correct errors.

## The Core Philosophy: Why Build This?
For non-technical readers, a good analogy for the current state of Artificial Intelligence is the era of giant mainframe computers. Today, nearly every AI task is routed through massive, generalized cloud models. While powerful, this approach poses significant risks regarding data privacy, high recurring API costs, and environmental sustainability. 

If we look at the historical evolution of Machine Learning, a clear pattern emerges. We moved from single massive decision trees to "Random Forests" (ensembles of smaller trees). In computer vision, we moved to networks of multiple specialized filters. In language processing, architectures evolved to use "Mixture of Experts," where tasks are routed to specialized sub-networks. 

The underlying principle is consistent: A coordinated ensemble of smaller, specialized units consistently outperforms a monolithic giant. 

This project applies that exact philosophy to generative AI. By breaking down the complex task of database querying into specialized roles, we can achieve high accuracy using models small enough to run entirely on local consumer hardware. This guarantees absolute data privacy, eliminates cloud API costs, and significantly reduces the compute footprint. This "swarm" architecture is not limited to SQL; the same underlying thinking can be applied to autonomous coding, legal document analysis, or complex data extraction.

## Architecture & Solution
The system uses LangGraph to manage the workflow between several distinct agents:

* **The Analyst:** Rather than blindly passing the entire database schema to the code generator, the Analyst performs a "Peek" operation. It executes a lightweight query to sample a few rows of actual data, helping the system understand specific data formats and categorical values.
* **The Architect:** A model specialized in code generation (Qwen 2.5 Coder 7B) takes the user's question, the schema, and the sample data to write the raw SQLite query.
* **The Sandbox:** A secure, local execution environment that runs the generated SQL against the target database and captures the results or errors.
* **The Auditor:** An evaluation model (Llama 3.1 8B Instruct) that reviews the sandbox output. It features a "Classified Feedback Loop." If the query fails, the Auditor categorizes the failure as either a Syntax Error or an Empty Logic Error, providing targeted instructions back to the Architect to rewrite the query.

## Benchmark Results
The architecture was evaluated against 500 randomized samples from the Spider dataset (a challenging, multi-domain Text-to-SQL benchmark). All tests were executed completely locally on an Apple Silicon M5 with 24GB of Unified Memory.

* **Single SLM (Zero-Shot Baseline):** 53.4% Accuracy | Average Latency: 5.5s
* **Swarm of SLMs (Hive Architecture):** 77.4% Accuracy | Average Latency: 11.2s | Average Retries: 0.4
* **Estimated Cloud API Cost Saved:** $2.70 (Calculated based on equivalent frontier model pricing for this single test batch)

The swarm approach yielded a 24% absolute improvement in accuracy over the zero-shot baseline. The targeted self-correction mechanism successfully recovered nearly a quarter of all queries that a single model would have failed.

## Project Structure
* `app.py`: Streamlit application providing a conversational user interface and a trace viewer to see the agents "thinking" in real-time.
* `hive.py`: The LangGraph state definition, agent logic, and routing rules.
* `evaluate.py`: The benchmarking script featuring thermal control, automated batching, and real-time accuracy and cost tracking.
* `sandbox_sql.py`: The local SQLite execution module.
* `config.json`: Configuration file mapping agent roles to specific local models.

## Reproduction Guide

### Prerequisites
1.  Python 3.11 or higher.
2.  The `uv` package manager.
3.  Ollama installed and running locally.

### 1. Model Setup
Pull the required models via Ollama:
```bash
ollama pull qwen2.5-coder:7b
ollama pull llama3.1:8b-instruct-q4_K_M
```
### 2. Environment Setup

Clone the repository and install the dependencies using [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

---

### 3. Downloading the Spider Dataset

To run the evaluation, you'll need to download the Spider dataset from the official source:

1. Navigate to the [Yale Spider Dataset website](https://yale-lily.github.io/spider).
2. Download the dataset zip file.
3. Extract the contents of the zip file.
4. Create a folder called `data` in the root directory of this project.
5. Move the following items from the extracted Spider folder into your new `data` folder:
    - The `database` directory (contains all the `.sqlite` files)
    - The `dev.json` file
    - The `tables.json` file

Your directory structure should look like this:

```
project_root/
├── data/
│   ├── database/
│   ├── dev.json
│   └── tables.json
├── app.py
├── hive.py
...
```

---

### 4. Running the Project

**To run the benchmark evaluation:**

```bash
uv run evaluate.py
```

**To launch the interactive chat interface:**

```bash
uv run streamlit run app.py
```