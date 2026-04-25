import requests
import statistics
from collections import Counter

API_URL = "http://localhost:8001/ask"

QUERIES = [
    "What is retrieval augmented generation?",
    "Explain vector databases",
    "How does BM25 work?",
    "What is LightRAG?",
    "Explain multi-hop QA",
]

results = []

def call_api(question):
    try:
        res = requests.post(API_URL, json={"question": question})
        data = res.json()

        return {
            "latency": data.get("latency_ms", 0),
            "confidence": data.get("confidence", 0),
            "sources": len(data.get("sources", [])),
            "cache": data.get("from_cache", False),
            "intent": data.get("routing", {}).get("intent", "unknown"),
            "model": data.get("model_used", "unknown"),
            "reranker": data.get("reranker_used", "unknown"),
            "guardrails": data.get("guardrail_flags", []),
            "fetch_latency": sum(
                f.get("latency_ms", 0)
                for f in data.get("retrieval_trace", [])
            )
        }

    except Exception as e:
        print(f"Error: {e}")
        return None


print("🚀 Running metrics collection...\n")

for q in QUERIES:
    r = call_api(q)
    if r:
        results.append(r)
        print(f"✔ {q}")

# -------------------------
# 📊 Aggregation
# -------------------------

lat = [r["latency"] for r in results]
conf = [r["confidence"] for r in results]
src = [r["sources"] for r in results]

cache_hits = sum(r["cache"] for r in results)

intent_dist = Counter(r["intent"] for r in results)
model_dist = Counter(r["model"] for r in results)
reranker_dist = Counter(r["reranker"] for r in results)

print("\n📊 ===== METRICS =====\n")

print(f"Total Queries: {len(results)}")

print("\n⏱ Latency")
print(f"  Avg: {statistics.mean(lat):.2f} ms")
print(f"  Min: {min(lat):.2f} ms")
print(f"  Max: {max(lat):.2f} ms")

print("\n🎯 Confidence")
print(f"  Avg: {statistics.mean(conf):.4f}")

print("\n📚 Sources")
print(f"  Avg: {statistics.mean(src):.2f}")

print("\n⚡ Cache Hit Rate")
print(f"  {cache_hits}/{len(results)} = {(cache_hits/len(results))*100:.2f}%")

print("\n🧠 Intent Distribution")
for k, v in intent_dist.items():
    print(f"  {k}: {v}")

print("\n🤖 Model Usage")
for k, v in model_dist.items():
    print(f"  {k}: {v}")

print("\n🔁 Reranker Usage")
for k, v in reranker_dist.items():
    print(f"  {k}: {v}")

print("\n🛡 Guardrail Flags")
flags = [f for r in results for f in r["guardrails"]]
for k, v in Counter(flags).items():
    print(f"  {k}: {v}")
