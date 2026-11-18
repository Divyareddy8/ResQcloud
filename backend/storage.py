import os, sqlite3, threading, json, time
import httpx
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from backend.common import event
app=FastAPI(title='ResQCloud Storage Node')
NODE=os.getenv('NODE_ID','shard0');DB=os.getenv('DB_PATH','/data/storage.sqlite')
lock=threading.RLock()
def connect():
 os.makedirs(os.path.dirname(DB) or '.',exist_ok=True)
 c=sqlite3.connect(DB,timeout=15)
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL, version INTEGER NOT NULL)')
 c.commit();return c
class Record(BaseModel):
 value:dict
 version:int
@app.on_event('startup')
def startup():
 with connect() as c:pass
 event('node_started',node=NODE)
 def heartbeat():
  coordinator=os.getenv('COORDINATOR_URL','http://coordinator:8000')
  registered=False
  while True:
   try:
    endpoint='heartbeat' if registered else 'register'
    r=httpx.post(coordinator+'/internal/nodes/'+endpoint,json={'node':NODE},timeout=3)
    r.raise_for_status();registered=True
   except httpx.HTTPError:registered=False
   time.sleep(3)
 threading.Thread(target=heartbeat,daemon=True).start()
@app.get('/health')
def health():return {'status':'ok','node':NODE}
@app.put('/internal/data/{key:path}')
def put(key:str,record:Record):
 with lock,connect() as c:
  old=c.execute('SELECT version FROM records WHERE key=?',(key,)).fetchone()
  if old and old[0]>record.version:return {'stored':False,'version':old[0]}
  c.execute('INSERT INTO records VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,version=excluded.version',(key,json.dumps(record.value),record.version))
  c.commit()
 event('record_written',node=NODE,key=key)
 return {'stored':True,'version':record.version}
@app.get('/internal/data/{key:path}')
def get(key:str):
 with connect() as c:r=c.execute('SELECT value,version FROM records WHERE key=?',(key,)).fetchone()
 if not r:raise HTTPException(404,'Record missing')
 return {'value':json.loads(r[0]),'version':r[1]}
@app.get('/internal/records')
def records():
 with connect() as c:rows=c.execute('SELECT key,value,version FROM records').fetchall()
 return {'node':NODE,'records':[{'key':k,'value':json.loads(v),'version':ver} for k,v,ver in rows]}
@app.get('/internal/stats')
def stats():
 with connect() as c:n=c.execute('SELECT count(*) FROM records').fetchone()[0]
 return {'node':NODE,'count':n}
