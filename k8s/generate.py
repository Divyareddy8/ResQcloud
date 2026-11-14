
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
NS = "resqcloud"

# Local images by default.
# A Docker Hub username can be supplied later for CI/CD.
registry = sys.argv[1] if len(sys.argv) > 1 else None

BACKEND = (
    f"{registry}/resqcloud:latest"
    if registry else "resqcloud-backend:v1"
)

FRONTEND = (
    f"{registry}/resqcloud-frontend:latest"
    if registry else "resqcloud-frontend:v1"
)

PULL_POLICY = "Always" if registry else "IfNotPresent"

objects = []


def add(kind, name, spec=None, version="v1", **extra):
    metadata = {"name": name}

    if kind != "Namespace":
        metadata["namespace"] = NS

    obj = {
        "apiVersion": version,
        "kind": kind,
        "metadata": metadata
    }

    if spec is not None:
        obj["spec"] = spec

    obj.update(extra)
    objects.append(obj)


def resources(cpu="50m", memory="64Mi",
              cpu_limit="500m", memory_limit="192Mi"):
    return {
        "requests": {
            "cpu": cpu,
            "memory": memory
        },
        "limits": {
            "cpu": cpu_limit,
            "memory": memory_limit
        }
    }


def http_probe(port=8000, path="/health"):
    return {
        "httpGet": {
            "path": path,
            "port": port
        },
        "periodSeconds": 10,
        "timeoutSeconds": 3,
        "failureThreshold": 3
    }


def health_probes(port=8000, path="/health"):
    return {
        "startupProbe": {
            **http_probe(port, path),
            "failureThreshold": 30
        },
        "readinessProbe": http_probe(port, path),
        "livenessProbe": http_probe(port, path)
    }


def service(name, ports, headless=False, selector=None):
    spec = {
        "selector": {"app": selector or name},
        "ports": ports
    }

    if headless:
        spec["clusterIP"] = "None"

    add("Service", name, spec)


def deployment(name, container, replicas=1):
    add(
        "Deployment",
        name,
        {
            "replicas": replicas,
            "selector": {
                "matchLabels": {"app": name}
            },
            "template": {
                "metadata": {
                    "labels": {"app": name}
                },
                "spec": {
                    "containers": [container]
                }
            }
        },
        version="apps/v1"
    )


def statefulset(name, container, size="1Gi", volumes=None):
    pod_spec = {
        "containers": [container]
    }

    if volumes:
        pod_spec["volumes"] = volumes

    add(
        "StatefulSet",
        name,
        {
            "serviceName": f"{name}-headless",
            "replicas": 1,
            "selector": {
                "matchLabels": {"app": name}
            },
            "template": {
                "metadata": {
                    "labels": {"app": name}
                },
                "spec": pod_spec
            },
            "volumeClaimTemplates": [
                {
                    "metadata": {"name": "data"},
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "storageClassName": "standard",
                        "resources": {
                            "requests": {
                                "storage": size
                            }
                        }
                    }
                }
            ]
        },
        version="apps/v1"
    )


def backend_container(name, module):
    return {
        "name": name,
        "image": BACKEND,
        "imagePullPolicy": PULL_POLICY,
        "command": [
            "uvicorn",
            module,
            "--host", "0.0.0.0",
            "--port", "8000"
        ],
        "ports": [{"containerPort": 8000}],
        "envFrom": [
            {"configMapRef": {"name": "resqcloud-config"}}
        ],
        "env": [
            {"name": "SERVICE", "value": name}
        ],
        "resources": resources(),
        **health_probes()
    }


# ==========================================
# 1. Namespace
# ==========================================

add("Namespace", NS)


# ==========================================
# 2. Application configuration
# ==========================================

shards = ";".join(
    f"http://shard{i}:8000,http://replica{i}:8000"
    for i in range(3)
)

add(
    "ConfigMap",
    "resqcloud-config",
    data={
        "COORDINATOR_URL": "http://coordinator:8000",
        "RABBITMQ_HOST": "rabbitmq",
        "SHARDS": shards,
        "PYTHONUNBUFFERED": "1"
    }
)

# Local demonstration configuration.
# Production deployments should use a dedicated
# RabbitMQ user and Secret-backed credentials.

add(
    "ConfigMap",
    "rabbitmq-config",
    data={
        "rabbitmq.conf": (
            "loopback_users.guest = false\n"
            "vm_memory_high_watermark.absolute = 256MiB\n"
            "disk_free_limit.absolute = 100MB\n"
        )
    }
)


# ==========================================
# 3. Distributed storage
# ==========================================

for i in range(3):
    for role in ("shard", "replica"):
        name = f"{role}{i}"

        container = backend_container(
            name, "backend.storage:app"
        )

        container["env"].extend([
            {
                "name": "NODE_ID",
                "value": name
            },
            {
                "name": "DB_PATH",
                "value": "/data/db.sqlite"
            }
        ])

        container["volumeMounts"] = [
            {
                "name": "data",
                "mountPath": "/data"
            }
        ]

        ports = [{"port": 8000, "targetPort": 8000}]

        service(name, ports)

        service(
            f"{name}-headless",
            ports,
            headless=True,
            selector=name
        )

        statefulset(name, container)


# ==========================================
# 4. Coordinator
# ==========================================

coordinator = backend_container(
    "coordinator",
    "backend.coordinator:app"
)

coordinator["resources"] = resources(
    cpu="100m",
    memory="96Mi",
    memory_limit="256Mi"
)

service(
    "coordinator",
    [{"port": 8000, "targetPort": 8000}]
)

deployment("coordinator", coordinator)


# ==========================================
# 5. RabbitMQ
# ==========================================

rabbit_ports = [
    {
        "name": "amqp",
        "port": 5672,
        "targetPort": 5672
    },
    {
        "name": "management",
        "port": 15672,
        "targetPort": 15672
    }
]

service("rabbitmq", rabbit_ports)

service(
    "rabbitmq-headless",
    rabbit_ports,
    headless=True,
    selector="rabbitmq"
)

rabbit_probe = {
    "exec": {
        "command": [
            "rabbitmq-diagnostics", "-q", "ping"
        ]
    },
    "periodSeconds": 15,
    "timeoutSeconds": 10,
    "failureThreshold": 5
}

rabbitmq = {
    "name": "rabbitmq",
    "image": "rabbitmq:3.13-management-alpine",
    "imagePullPolicy": "IfNotPresent",
    "ports": [
        {"containerPort": 5672},
        {"containerPort": 15672}
    ],
    "env": [
        {
            "name": "RABBITMQ_NODENAME",
            "value": "rabbit@rabbitmq-0"
        }
    ],
    "resources": resources(
        cpu="100m",
        memory="256Mi",
        cpu_limit="750m",
        memory_limit="512Mi"
    ),
    "volumeMounts": [
        {
            "name": "data",
            "mountPath": "/var/lib/rabbitmq"
        },
        {
            "name": "rabbit-config",
            "mountPath": "/etc/rabbitmq/conf.d/90-resqcloud.conf",
            "subPath": "rabbitmq.conf"
        }
    ],
    "startupProbe": {
        **rabbit_probe,
        "failureThreshold": 30
    },
    "readinessProbe": rabbit_probe,
    "livenessProbe": rabbit_probe
}

statefulset(
    "rabbitmq",
    rabbitmq,
    volumes=[
        {
            "name": "rabbit-config",
            "configMap": {
                "name": "rabbitmq-config"
            }
        }
    ]
)


# ==========================================
# 6. FastAPI
# ==========================================

api = backend_container(
    "api",
    "backend.api:app"
)

api["resources"] = resources(
    cpu="100m",
    memory="96Mi",
    memory_limit="192Mi"
)

service(
    "api",
    [{"port": 8000, "targetPort": 8000}]
)

deployment("api", api, replicas=2)


# ==========================================
# 7. Matcher worker
# ==========================================

matcher = {
    "name": "matcher",
    "image": BACKEND,
    "imagePullPolicy": PULL_POLICY,
    "command": [
        "python", "-m", "backend.matcher"
    ],
    "envFrom": [
        {"configMapRef": {"name": "resqcloud-config"}}
    ],
    "env": [
        {"name": "SERVICE", "value": "matcher"}
    ],
    "resources": resources()
}

deployment("matcher", matcher, replicas=1)

# Prevent two matcher workers during rolling updates.
# The current matching algorithm does not support
# atomic concurrent resource assignment.

objects[-1]["spec"]["strategy"] = {
    "type": "Recreate"
}


# ==========================================
# 8. Frontend
# ==========================================

frontend = {
    "name": "frontend",
    "image": FRONTEND,
    "imagePullPolicy": PULL_POLICY,
    "ports": [{"containerPort": 80}],
    "resources": resources(
        cpu="25m",
        memory="32Mi",
        cpu_limit="200m",
        memory_limit="64Mi"
    ),
    **health_probes(port=80, path="/")
}

service(
    "frontend",
    [{"port": 80, "targetPort": 80}]
)

deployment("frontend", frontend)


# ==========================================
# 9. Horizontal Pod Autoscaler
# ==========================================

add(
    "HorizontalPodAutoscaler",
    "api-hpa",
    {
        "scaleTargetRef": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": "api"
        },
        "minReplicas": 2,
        "maxReplicas": 5,
        "metrics": [
            {
                "type": "Resource",
                "resource": {
                    "name": "cpu",
                    "target": {
                        "type": "Utilization",
                        "averageUtilization": 70
                    }
                }
            }
        ]
    },
    version="autoscaling/v2"
)


# ==========================================
# 10. Generate Kubernetes manifest
# ==========================================

output = ROOT / "all.yaml"

output.write_text(
    "\n---\n".join(
        json.dumps(obj, indent=2)
        for obj in objects
    ) + "\n"
)

print(f"Generated {len(objects)} Kubernetes objects")
print(f"Manifest: {output}")
print(f"Backend image: {BACKEND}")
print(f"Frontend image: {FRONTEND}")
