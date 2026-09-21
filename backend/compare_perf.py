import json
with open('phase8_perf_before.json') as f: before=json.load(f)
with open('phase8_perf_after.json') as f: after=json.load(f)

def pct(delta, base):
    return delta/base*100 if base else 0

print("Metric | Before median | After median | Delta | % change")
for key in ['routing','retrieval','validation']:
    b=before[key]
    a=after[key]
    delta=a['median']-b['median']
    print(f"{key:20s} {b['median']:.3f} -> {a['median']:.3f} delta {delta:+.3f} ({pct(delta,b['median']):+.1f}%)")

b=before['health']['combined']; a=after['health']['combined']
print(f"health combined     {b:.1f} -> {a:.1f} delta {a-b:+.1f} ({pct(a-b,b):+.1f}%)")

b=before['llm_generation']['median']; a=after['llm_generation']['median']
print(f"llm_generation      {b:.1f} -> {a:.1f} delta {a-b:+.1f} ({pct(a-b,b):+.1f}%)")

b=before['orchestrator_mock']['median']; a=after['orchestrator_mock']['median']
print(f"orchestrator_mock   {b:.2f} -> {a:.2f} delta {a-b:+.2f} ({pct(a-b,b):+.1f}%)")

b=before['orchestrator_live']['median']; a=after['orchestrator_live']['median']
print(f"orchestrator_live   {b:.1f} -> {a:.1f} delta {a-b:+.1f} ({pct(a-b,b):+.1f}%)")

b=before['stream']['ttft']['median']; a=after['stream']['ttft']['median']
print(f"stream TTFT         {b:.1f} -> {a:.1f} delta {a-b:+.1f} ({pct(a-b,b):+.1f}%)")

b=before['stream']['total']['median']; a=after['stream']['total']['median']
print(f"stream total        {b:.1f} -> {a:.1f} delta {a-b:+.1f} ({pct(a-b,b):+.1f}%)")

b=before['orchestrator_stream_live']['ttft']['median']; a=after['orchestrator_stream_live']['ttft']['median']
print(f"orch_stream TTFT    {b:.1f} -> {a:.1f} delta {a-b:+.1f} ({pct(a-b,b):+.1f}%)")

# Also show detailed health
print("\nHealth detail before:", before['health'])
print("Health detail after:", after['health'])
print("\nRetrieval cache benefit: median", before['retrieval']['median'], "->", after['retrieval']['median'])
