import pathlib,sys
name=sys.argv[1] if len(sys.argv)>1 else 'YOUR_DOCKERHUB_USERNAME'
root=pathlib.Path(__file__).parent
items=['''apiVersion: v1
kind: Namespace
metadata: {name: resqcloud}''']
for i in range(3):
 for role in ('shard','replica'):
  node=f'{role}{i}'
  items.append(f'''apiVersion: apps/v1
kind: StatefulSet
metadata: {{name: {node}, namespace: resqcloud}}
spec:
  serviceName: {node}
  replicas: 1
  selector:
    matchLabels: {{app: {node}}}
  template:
    metadata:
      labels: {{app: {node}}}
    spec:
      containers:
      - name: storage
        image: {name}/resqcloud:latest
        command: ["uvicorn", "backend.storage:app", "--host", "0.0.0.0", "--port", "8000"]
        env:
        - {{name: NODE_ID, value: "{node}"}}
        - {{name: DB_PATH, value: "/data/db.sqlite"}}
        volumeMounts:
        - {{name: data, mountPath: /data}}
  volumeClaimTemplates:
  - metadata: {{name: data}}
    spec:
      accessModes: [ReadWriteOnce]
      resources:
        requests: {{storage: 1Gi}}''')
  items.append(f'''apiVersion: v1
kind: Service
metadata: {{name: {node}, namespace: resqcloud}}
spec:
  selector: {{app: {node}}}
  ports: [{{port: 8000}}]''')
for svc,cmd,n in [('api','backend.api:app',2),('coordinator','backend.coordinator:app',1)]:
 items.append(f'''apiVersion: apps/v1
kind: Deployment
metadata: {{name: {svc}, namespace: resqcloud}}
spec:
  replicas: {n}
  selector:
    matchLabels: {{app: {svc}}}
  template:
    metadata:
      labels: {{app: {svc}}}
    spec:
      containers:
      - name: {svc}
        image: {name}/resqcloud:latest
        command: ["uvicorn", "{cmd}", "--host", "0.0.0.0", "--port", "8000"]
        resources:
          requests: {{cpu: 100m, memory: 128Mi}}''')
 items.append(f'''apiVersion: v1
kind: Service
metadata: {{name: {svc}, namespace: resqcloud}}
spec:
  selector: {{app: {svc}}}
  ports: [{{port: 8000}}]''')
items.append(f'''apiVersion: apps/v1
kind: Deployment
metadata: {{name: matcher, namespace: resqcloud}}
spec:
  replicas: 1
  selector:
    matchLabels: {{app: matcher}}
  template:
    metadata:
      labels: {{app: matcher}}
    spec:
      containers:
      - name: matcher
        image: {name}/resqcloud:latest
        command: ["python", "-m", "backend.matcher"]''')
items.append('''apiVersion: apps/v1
kind: Deployment
metadata: {name: rabbitmq, namespace: resqcloud}
spec:
  replicas: 1
  selector:
    matchLabels: {app: rabbitmq}
  template:
    metadata:
      labels: {app: rabbitmq}
    spec:
      containers:
      - name: rabbitmq
        image: rabbitmq:3.13-management-alpine''')
items.append('''apiVersion: v1
kind: Service
metadata: {name: rabbitmq, namespace: resqcloud}
spec:
  selector: {app: rabbitmq}
  ports: [{port: 5672, name: amqp}, {port: 15672, name: management}]''')
items.append('''apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: api-hpa, namespace: resqcloud}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: api}
  minReplicas: 2
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target: {type: Utilization, averageUtilization: 70}''')
(root/'all.yaml').write_text('\n---\n'.join(items)+'\n')
print('Generated',len(items),'objects')
