from backend.coordinator import shard,SHARDS
from backend.matcher import score

def test_deterministic_sharding():
 assert shard('request/123')==shard('request/123')
 assert 0<=shard('request/123')<3

def test_locality_priority():
 r={'type':'water','location':'Bengaluru'}
 assert score(r,{'type':'water','location':'Bengaluru','availability':True})==100
 assert score(r,{'type':'water','location':'Mysuru','availability':True})==20
 assert score(r,{'type':'food','location':'Bengaluru','availability':True})==-1
 assert score(r,{'type':'water','location':'Bengaluru','availability':False})==-1
