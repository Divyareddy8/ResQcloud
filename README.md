# ResQCloud AI — Distributed Emergency Response Platform

One codebase for **Cloud Computing** and **Software Production Engineering (DevOps)**.

## Features
- Responsive React incident command dashboard with automatic 5-second refresh.
- FastAPI REST API for emergency requests and volunteer resources.
- RabbitMQ durable queue and asynchronous matching worker.
- SHA-256 deterministic routing across **three shards**, with **one independent persistent replica per shard**.
- Coordinator heartbeat status, degraded writes, read fallback, and manual anti-entropy reconciliation.
- Docker Compose local environment, Kubernetes StatefulSets/Deployments/Services/HPA.
- Jenkins test → image build → Docker Hub → Kubernetes rolling update pipeline.
- Ansible Docker-host provisioning role; optional ELK local logging integration.

## Quick start (Docker Desktop / Ubuntu with Docker Compose)
```bash
docker compose up -d --build
docker compose ps
```
Open **http://localhost:3000** (dashboard), **http://localhost:8000/docs** (Swagger), **http://localhost:15672** (RabbitMQ, guest/guest for local development).

### Sample data
```bash
bash scripts/demo.sh
```
Create a resource first, then a matching request. Refresh the dashboard or wait 5 seconds for automatic updates.

### Test shard placement
```bash
curl http://localhost:8001/internal/nodes
curl http://localhost:8001/internal/shard/request%2Fdemo
curl http://localhost:8001/internal/scan/request
```

### Demonstrate failure and recovery
```bash
docker compose stop shard0
curl http://localhost:8001/internal/nodes
curl http://localhost:8000/requests
docker compose start shard0
bash scripts/recover.sh
curl http://localhost:8001/internal/nodes
```
The read fallback works for records located in shard0; other shards are unaffected. For a stronger demonstration, create multiple requests and verify their placements before stopping a node. The recovery endpoint copies the newest record version back to all available nodes in each pair. This is **manual recovery**, not automatic background repair.

### Automated tests
```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -q tests
```

## Kubernetes
1. Build/push the backend image to Docker Hub (replace `YOUR_DOCKERHUB_USERNAME`):
```bash
docker build -t YOUR_DOCKERHUB_USERNAME/resqcloud:latest .
docker login
docker push YOUR_DOCKERHUB_USERNAME/resqcloud:latest
python3 k8s/generate.py YOUR_DOCKERHUB_USERNAME
kubectl apply -f k8s/all.yaml
kubectl get pods -n resqcloud
kubectl port-forward -n resqcloud svc/api 8000:8000
```
2. Ensure the cluster has a default StorageClass and metrics-server (for HPA).
3. Delete an API pod to demonstrate automatic Kubernetes recovery. Scale `api` with `kubectl scale deployment/api --replicas=3 -n resqcloud`.
4. Frontend runs via Docker Compose; for a fully in-cluster frontend, add its image and Deployment/Service. Kubernetes manifest here deploys backend only.

## Jenkins
- Install Jenkins with Docker CLI, Kubernetes CLI, Git, Pipeline, and Credentials Binding plugins.
- Configure a Pipeline from SCM pointing to this repository, `Jenkinsfile`.
- Configure GitHub webhook `http://PUBLIC_JENKINS_URL/github-webhook/` and select **GitHub hook trigger for GITScm polling** in Jenkins.
- Add a Jenkins username/password credential with ID `dockerhub`.
- Replace `YOUR_DOCKERHUB_USERNAME` in `Jenkinsfile` with your Docker Hub namespace.
- Ensure the Jenkins agent can build Docker images and access Kubernetes via a restricted kubeconfig/service account.
- Push a backend code change, watch the pipeline, and verify rollout. **Frontend image publishing and frontend deployment are not automated in this starter pipeline.**

## Ansible
```bash
ansible-playbook -i ansible/inventory.ini ansible/site.yml --ask-become-pass
```
Target is Ubuntu/Debian. Review package availability on your distro.

## ELK
Start main stack, then:
```bash
docker compose -f observability/docker-compose.elk.yml up -d
bash observability/ship_logs.sh
```
Visit http://localhost:5601, create a Kibana data view `resqcloud-*`, and inspect the events. Install `nc`/netcat on the host. This is an **optional development log shipper**; a production system should use Filebeat or Fluent Bit with TLS/authentication.

## Architecture / tradeoffs
- **Coordinator** hashes record key (request/resource + UUID) to a shard; two SQLite-backed HTTP storage nodes hold the same data.
- **Write semantics:** succeeds when at least one node accepts a write; `degraded=true` warns about insufficient replication.
- **Reads:** primary-first with replica fallback. There is no quorum or linearizability guarantee.
- **Reconciliation:** manual newest-version-wins repair. Concurrent writes and clock skew can cause conflicts.
- **Matching:** deterministic resource type and exact-location preference. Run **one matcher worker only**: this starter does not implement atomic reservation and cannot safely run multiple matching consumers.
- **RabbitMQ:** durable messages, but request persistence and message publishing are not transactional. If broker is unavailable, creation returns `queued=false`; retry using `/match/{request_id}`. Dead-letter queue and retries are future work.
- **Security:** sample local environment is not hardened; RabbitMQ defaults and unauthenticated APIs are **not suitable for public deployment**. Add identity, authorization, TLS, Vault and network policies before exposing it.
- **AI:** the project name is a product concept. Current matching uses explainable rule-based scoring, **not a trained ML model**.

## Evidence checklist
Cloud: request create/read/update; resource register/status; RabbitMQ event; 3 shard placements; 6 storage nodes; failure and replica read; manual recovery; Kubernetes pod recovery and scaling.
SPE: GitHub commits; webhook; Jenkins stages; pytest; Docker Hub tags; Kubernetes rollout; Docker Compose; Ansible role; Kibana events; HPA metrics.

## Remaining work for a complete top-marks submission
- Automated periodic reconciliation with recovery tests.
- Atomic reservation / concurrency safety and idempotent message processing.
- Authentication, Vault integration, hardened secrets, TLS and RBAC.
- Frontend Kubernetes deployment and frontend CI/CD stages.
- Real AI model with evaluation, or rename the project to **ResQCloud**.
- Broader integration/load/fault-injection tests and alerting dashboards.
- Production ELK shipping with Filebeat/Fluent Bit and persistent volumes.

This repository is a substantial **runnable starter implementation**, not a verified full-production solution or a guarantee of marks.
