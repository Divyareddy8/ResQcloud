import os, json, logging, time
import httpx
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'),format='%(message)s')
log=logging.getLogger('resqcloud')
def event(action,**kwargs):
 log.info(json.dumps({'time':time.time(),'service':os.getenv('SERVICE','unknown'),'event':action,**kwargs},default=str))
def url(name):return os.getenv(name,'')
def client():return httpx.Client(timeout=4)
