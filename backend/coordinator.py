import os,hashlib,threading,time
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from backend.common import event
app=FastAPI(title='ResQCloud Distributed Storage Coordinator')
SHARDS=[[x.strip() for x in group.split(',')] for group in os.getenv('SHARDS','http://shard0:8000,http://replica0:8000;http://shard1:8000,http://replica1:8000;http://shard2:8000,http://replica2:8000').split(';')]
status={u:False for group in SHARDS for u in group}
class Record(BaseModel):value:dict;version:int|None=None
def shard(key):return int(hashlib.sha256(key.encode()).hexdigest(),16)%len(SHARDS)
def ping(u):
 try:return httpx.get(u+'/health',timeout=1).status_code==200
 except httpx.HTTPError:return False
def check():
 for u in status:status[u]=ping(u)
@app.on_event('startup')
def startup():
 def heartbeat():
  while True:
   check();time.sleep(3)
 threading.Thread(target=heartbeat,daemon=True).start()
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/internal/nodes')
def nodes():return {'nodes':status,'shards':SHARDS}
@app.get('/internal/shard/{key:path}')
def placement(key:str):return {'shard':shard(key),'nodes':SHARDS[shard(key)]}
@app.put('/internal/data/{key:path}')
def put(key:str,record:Record):
 group=SHARDS[shard(key)]
 version=record.version or time.time_ns()
 results=[]
 for u in group:
  try:
   r=httpx.put(u+'/internal/data/'+key,json={'value':record.value,'version':version},timeout=3)
   if r.is_success:results.append(u);status[u]=True
  except httpx.HTTPError:status[u]=False
 if not results:raise HTTPException(503,'All storage replicas unavailable')
 event('write',key=key,shard=shard(key),replicas=len(results))
 return {'key':key,'shard':shard(key),'written_to':results,'degraded':len(results)<len(group),'version':version}
@app.get('/internal/data/{key:path}')
def get(key:str):
 for u in SHARDS[shard(key)]:
  try:
   r=httpx.get(u+'/internal/data/'+key,timeout=3)
   if r.status_code==200:return r.json()
  except httpx.HTTPError:status[u]=False
 raise HTTPException(503,'Record unavailable on all replicas')
@app.get('/internal/scan/{prefix}')
def scan(prefix:str):
 found={}
 for group in SHARDS:
  for u in group:
   try:
    r=httpx.get(u+'/internal/records',timeout=3);r.raise_for_status()
    for item in r.json()['records']:
     if item['key'].startswith(prefix) and (item['key'] not in found or item['version']>found[item['key']]['version']):found[item['key']]=item
   except httpx.HTTPError:continue
 return {'records':list(found.values())}
@app.post('/internal/reconcile')
def reconcile():
 repaired=0;unavailable=[]
 for group in SHARDS:
  merged={}
  for u in group:
   try:
    r=httpx.get(u+'/internal/records',timeout=3);r.raise_for_status()
    for item in r.json()['records']:
     if item['key'] not in merged or item['version']>merged[item['key']]['version']:merged[item['key']]=item
   except httpx.HTTPError:unavailable.append(u)
  for u in group:
   if u in unavailable:continue
   for item in merged.values():
    try:
     r=httpx.put(u+'/internal/data/'+item['key'],json={'value':item['value'],'version':item['version']},timeout=3)
     if r.is_success:repaired+=1
    except httpx.HTTPError:unavailable.append(u);break
 event('reconcile',writes=repaired)
 return {'replication_writes':repaired,'unavailable':list(set(unavailable))}
