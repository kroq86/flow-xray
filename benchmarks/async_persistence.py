"""Bounded ASGI persistence experiment: N=8, three repetitions, 2ms ticker.
Synthetic support request; no LLM/network. Same input and PII transform in
both variants; no latency thresholds tuned after measurement.
"""
import asyncio, json, platform, re, statistics, sys, tempfile, time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from flow_xray import TraceStore, trace
from flow_xray.asgi import TraceMiddleware

trace.configure(max_value_chars=100_000)
EMAIL=re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
PHONE=re.compile(r'(?<!\w)(?:\+?\d[\d\s()\-]{7,}\d)(?!\w)')

def redact(text):
    return PHONE.sub('[REDACTED:phone]',EMAIL.sub('[REDACTED:email]',text))

DOCUMENTS=[{'doc_id':f'doc_{i}','text':('The support policy covers billing, login and returns. Contact service@example.com. '*8)} for i in range(20)]

@trace
async def retrieve(question):
    await asyncio.sleep(0)
    return DOCUMENTS

@trace
async def generate(question,documents):
    trace.meta(model='fixture',prompt_tokens=2300,completion_tokens=60)
    await asyncio.sleep(0)
    return {'answer':'Returns take five business days. Contact service@example.com.','citations':['doc_0']}

@trace
async def app(scope,receive,send):
    question='How do returns work?'
    result=await generate(question,await retrieve(question))
    await send({'type':'http.response.start','status':200,'headers':[]})
    await send({'type':'http.response.body','body':json.dumps(result).encode(),'more_body':False})

async def once(root):
    store=TraceStore(root,redact=redact,retention_days=7)
    middleware=TraceMiddleware(app,store)
    n=8; period=.002; lags=[]; stop=False
    async def ticker():
        previous=asyncio.get_running_loop().time()
        while not stop:
            await asyncio.sleep(period)
            now=asyncio.get_running_loop().time()
            lags.append(max(0,now-previous-period)*1000)
            previous=now
    async def receive(): return {'type':'http.request','body':b'','more_body':False}
    async def send(message): pass
    ticker_task=asyncio.create_task(ticker())
    await asyncio.sleep(.01)
    started=time.perf_counter()
    await asyncio.gather(*(middleware({'type':'http','method':'POST','path':'/chat','headers':[(b'x-request-id',f'bench-{i:08d}'.encode())]},receive,send) for i in range(n)))
    elapsed=(time.perf_counter()-started)*1000
    await asyncio.sleep(.01); stop=True; await ticker_task
    rows=store.entries(limit=n+1)
    sizes={'json':sum(p.stat().st_size for p in root.rglob('*.json')),'html':sum(p.stat().st_size for p in root.rglob('*.html'))}
    return {'requests':n,'saved':len(rows),'elapsed_ms':round(elapsed,3),'max_loop_lag_ms':round(max(lags),3),'p95_loop_lag_ms':round(sorted(lags)[min(len(lags)-1,int(len(lags)*.95))],3),'mean_trace_bytes':{k:v//n for k,v in sizes.items()}}

async def main():
    with tempfile.TemporaryDirectory(prefix='flow-async-measure-') as tmp:
        warm=TraceStore(Path(tmp)/'warm',redact=redact)
        @trace
        def seed(): return 'warm'
        warm.save(trace.run(seed),kind='warm',name='warm')
        results=[await once(Path(tmp)/str(i)) for i in range(3)]
    print(json.dumps({'python':platform.python_version(),'source':sys.argv[1],'fixture_documents':20,'document_chars':len(DOCUMENTS[0]['text']),'ticker_ms':2,'series':results},indent=2))
asyncio.run(main())
