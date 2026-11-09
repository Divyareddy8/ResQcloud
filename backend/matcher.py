import os,time,pika
from backend.api import get_record,save,scan
from backend.common import event
RABBIT=os.getenv('RABBITMQ_HOST','rabbitmq')
def score(request,resource):
 if request['type']!=resource['type'] or not resource['availability']:return -1
 # Exact locality outranks other locations; deterministic tie-break by resource ID.
 return 100 if request['location'].strip().lower()==resource['location'].strip().lower() else 20
def match_one(request_id):
 request=get_record('request/'+request_id)
 if request['status']!='pending':return
 candidates=[(score(request,r),r) for r in scan('resource/')]
 candidates=[(s,r) for s,r in candidates if s>=0]
 if not candidates:event('no_match',request_id=request_id);return
 candidates.sort(key=lambda x:(-x[0],x[1]['id']))
 best=candidates[0][1]
 # Single matcher replica is intentional: coordinator lacks atomic compare-and-swap.
 best['availability']=False;best['status']='assigned';save('resource/'+best['id'],best)
 request['status']='matched';request['assigned_resource']=best['id'];request['match_score']=candidates[0][0]
 save('request/'+request_id,request)
 event('request_matched',request_id=request_id,resource_id=best['id'],score=candidates[0][0])
def main():
 while True:
  try:
   conn=pika.BlockingConnection(pika.ConnectionParameters(RABBIT,heartbeat=60))
   ch=conn.channel();ch.queue_declare(queue='emergency.requests',durable=True);ch.basic_qos(prefetch_count=1)
   def callback(channel,method,properties,body):
    try:match_one(body.decode());channel.basic_ack(method.delivery_tag)
    except Exception as exc:event('match_error',error=str(exc));channel.basic_nack(method.delivery_tag,requeue=False)
   ch.basic_consume(queue='emergency.requests',on_message_callback=callback)
   event('matcher_ready');ch.start_consuming()
  except Exception as exc:event('matcher_reconnecting',error=str(exc));time.sleep(4)
if __name__=='__main__':main()
