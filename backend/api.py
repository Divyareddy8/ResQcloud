import os,uuid,datetime,threading,time
from contextlib import asynccontextmanager
import httpx,pika
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from backend.common import event
COORD=os.getenv('COORDINATOR_URL','http://coordinator:8000')
RABBIT=os.getenv('RABBITMQ_HOST','rabbitmq')
TYPES={'water','food','medicine','transportation','shelter'}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def get_record(key):
 try:
  r=httpx.get(COORD+'/internal/data/'+key,timeout=5)
  if r.status_code!=200:raise HTTPException(404,'Record not found or unavailable')
  return r.json()['value']
 except httpx.HTTPError:raise HTTPException(503,'Storage coordinator unavailable')
def save(key,data):
 try:
  r=httpx.put(COORD+'/internal/data/'+key,json={'value':data},timeout=8)
  if not r.is_success:raise HTTPException(503,'Storage write unavailable')
 except httpx.HTTPError:raise HTTPException(503,'Storage coordinator unavailable')

def scan(prefix):
    try:
        response = httpx.get(
            COORD + '/internal/scan/' + prefix,
            timeout=12,
            follow_redirects=True
        )

        response.raise_for_status()

        return [
            record['value']
            for record in response.json()['records']
        ]

    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail='Storage scan unavailable'
        )

def publish(request_id):
 try:
  conn=pika.BlockingConnection(pika.ConnectionParameters(RABBIT,heartbeat=30,blocked_connection_timeout=3))
  ch=conn.channel();ch.queue_declare(queue='emergency.requests',durable=True)
  ch.basic_publish(exchange='',routing_key='emergency.requests',body=request_id.encode(),properties=pika.BasicProperties(delivery_mode=2));conn.close()
  return True
 except Exception as exc:event('broker_unavailable',error=str(exc));return False
class RequestIn(BaseModel):
 type:str;location:str=Field(min_length=2);details:str=Field(min_length=3);priority:int=Field(default=3,ge=1,le=5)
class ResourceIn(BaseModel):
 type:str;location:str=Field(min_length=2);availability:bool=True;provider:str='Community volunteer'
class StatusIn(BaseModel):status:str
app=FastAPI(title='ResQCloud AI Emergency API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','*').split(','),allow_methods=['*'],allow_headers=['*'])
@app.get('/health')
def health():return {'status':'ok','service':'api'}
@app.post('/requests',status_code=201)
def create_request(data:RequestIn):
 if data.type not in TYPES:raise HTTPException(400,'Unsupported resource type')
 item={'id':str(uuid.uuid4()),**data.model_dump(),'status':'pending','assigned_resource':None,'created_at':now()}
 save('request/'+item['id'],item)
 queued=publish(item['id']);event('request_created',request_id=item['id'],queued=queued)
 return {**item,'queued':queued}
@app.get('/requests')
def requests():return sorted(scan('request/'),key=lambda r:r['created_at'],reverse=True)
@app.get('/requests/{request_id}')
def request(request_id:str):return get_record('request/'+request_id)
@app.put('/requests/{request_id}/status')
def request_status(request_id:str,data:StatusIn):
 if data.status not in {'pending','matched','in_progress','completed','cancelled'}:raise HTTPException(400,'Invalid status')
 item=get_record('request/'+request_id);item['status']=data.status;save('request/'+request_id,item);return item
@app.post('/resources',status_code=201)
def create_resource(data:ResourceIn):
 if data.type not in TYPES:raise HTTPException(400,'Unsupported resource type')
 item={'id':str(uuid.uuid4()),**data.model_dump(),'status':'available' if data.availability else 'unavailable','created_at':now()}
 save('resource/'+item['id'],item);event('resource_registered',resource_id=item['id']);return item
@app.get('/resources')
def resources():return scan('resource/')
@app.put('/resources/{resource_id}/status')
def resource_status(resource_id:str,data:StatusIn):
 if data.status not in {'available','assigned','unavailable'}:raise HTTPException(400,'Invalid status')
 item=get_record('resource/'+resource_id);item['status']=data.status;item['availability']=data.status=='available';save('resource/'+resource_id,item);return item
@app.post('/match/{request_id}')
def match(request_id:str):
 queued=publish(request_id)
 if not queued:raise HTTPException(503,'Message broker unavailable')
 return {'queued':True,'request_id':request_id}
@app.get('/stats')
def stats():
 rs=scan('request/');resources=scan('resource/')
 return {'requests':len(rs),'pending':sum(x['status']=='pending' for x in rs),'matched':sum(x['status']=='matched' for x in rs),'available_resources':sum(x['availability'] for x in resources)}
