import time
import requests
import json
import statistics
from typing import List

VLLM_URL = "http://localhost:8000/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/api/generate"

PROMPT = "Explain the importance of the Socratic method in education."
NUM_REQUESTS = 5

def benchmark_ollama(num_requests: int = NUM_REQUESTS):
    print(f"\n--- Benchmarking Ollama (Model: llama3.1:latest) ---")
    payload = {
        "model": "llama3.1:latest",
        "prompt": PROMPT,
        "stream": False,
        "options": {"temperature": 0.0}
    }
    
    latencies = []
    tokens_per_second = []
    
    # Warmup
    try:
        requests.post(OLLAMA_URL, json=payload, timeout=60)
    except Exception as e:
        print(f"Failed to connect to Ollama. Make sure it is running. Error: {e}")
        return
        
    for i in range(num_requests):
        print(f"Request {i+1}/{num_requests}...")
        start_time = time.time()
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        end_time = time.time()
        
        if response.status_code == 200:
            data = response.json()
            latency = end_time - start_time
            latencies.append(latency)
            
            # Ollama sometimes provides eval_count and eval_duration
            if "eval_count" in data and "eval_duration" in data:
                # eval_duration is in nanoseconds typically
                tps = data["eval_count"] / (data["eval_duration"] / 1e9)
                tokens_per_second.append(tps)
            else:
                # Rough estimate based on words
                words = len(data.get("response", "").split())
                tokens_per_second.append((words * 1.3) / latency)
        else:
            print(f"Error: {response.status_code}")
            
    if latencies:
        print(f"Average Latency: {statistics.mean(latencies):.2f} seconds")
        print(f"Average Throughput: {statistics.mean(tokens_per_second):.2f} tokens/second")

def benchmark_vllm(num_requests: int = NUM_REQUESTS):
    print(f"\n--- Benchmarking vLLM (Model: meta-llama/Meta-Llama-3.1-8B-Instruct) ---")
    payload = {
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "temperature": 0.0
    }
    
    headers = {"Authorization": "Bearer EMPTY"}
    latencies = []
    tokens_per_second = []
    
    # Warmup
    try:
        requests.post(VLLM_URL, json=payload, headers=headers, timeout=60)
    except Exception as e:
        print(f"Failed to connect to vLLM. Make sure it is running. Error: {e}")
        return
        
    for i in range(num_requests):
        print(f"Request {i+1}/{num_requests}...")
        start_time = time.time()
        response = requests.post(VLLM_URL, json=payload, headers=headers, timeout=120)
        end_time = time.time()
        
        if response.status_code == 200:
            data = response.json()
            latency = end_time - start_time
            latencies.append(latency)
            
            usage = data.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            if completion_tokens > 0:
                tps = completion_tokens / latency
                tokens_per_second.append(tps)
        else:
            print(f"Error: {response.status_code} - {response.text}")

    if latencies:
        print(f"Average Latency: {statistics.mean(latencies):.2f} seconds")
        print(f"Average Throughput: {statistics.mean(tokens_per_second):.2f} tokens/second")

if __name__ == "__main__":
    print("Starting Benchmarks - This may take a few minutes...")
    print("Ensure BOTH Ollama and vLLM servers are running sequentially to test them.")
    benchmark_ollama()
    benchmark_vllm()
    print("\nBenchmarking Complete.")
