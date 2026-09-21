import asyncio, json
from eval.runner import evaluate_all
async def run():
    report = await evaluate_all(use_mock=True)
    s=report['summary']
    print(f"Routing accuracy {s['routing_accuracy']} ({s['correct']}/{s['total']})")
    print(f"Relevance mean {s['relevance_mean']} completeness {s['completeness_pass']}/{s['total']}")
    print(f"Latency mean {s['latency']['mean_ms']} median {s['latency']['median_ms']} p95 {s['latency']['p95_ms']}")
    print(f"Hallucination {s['hallucination_flags']} Error {s['error_flags']}")
    with open('eval_after.json','w') as f: json.dump(report,f,indent=2)
asyncio.run(run())
