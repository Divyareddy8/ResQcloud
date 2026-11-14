pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    triggers {
        githubPush()
        pollSCM('H/5 * * * *')
    }

    environment {
        BACKEND = 'divya995/resqcloud'
        FRONTEND = 'divya995/resqcloud-frontend'
        NAMESPACE = 'resqcloud'
        KUBECONFIG = '/var/lib/jenkins/.kube/config'
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('Build Backend') {
            steps {
                sh '''
                    docker build \
                    -t "$BACKEND:$BUILD_NUMBER" \
                    -t "$BACKEND:latest" .
                '''
            }
        }

        stage('Automated Tests') {
            steps {
                sh '''
                    docker run --rm \
                    "$BACKEND:$BUILD_NUMBER" \
                    python -m pytest -q tests
                '''
            }
        }

        stage('Build Frontend') {
            steps {
                sh '''
                    docker build \
                    -t "$FRONTEND:$BUILD_NUMBER" \
                    -t "$FRONTEND:latest" \
                    ./frontend
                '''
            }
        }

        stage('Publish Docker Images') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'dockerhub',
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PASS'
                    )
                ]) {
                    sh '''
                        set +x

                        export DOCKER_CONFIG="$(mktemp -d)"
                        trap 'rm -rf "$DOCKER_CONFIG"' EXIT

                        printf '%s' "$DOCKER_PASS" | \
                        docker login \
                        -u "$DOCKER_USER" \
                        --password-stdin

                        docker push "$BACKEND:$BUILD_NUMBER"
                        docker push "$BACKEND:latest"

                        docker push "$FRONTEND:$BUILD_NUMBER"
                        docker push "$FRONTEND:latest"
                    '''
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                sh '''
                    kubectl get namespace "$NAMESPACE"

                    for service in shard0 shard1 shard2 replica0 replica1 replica2
                    do
                        kubectl set image \
                        statefulset/"$service" \
                        "*=$BACKEND:$BUILD_NUMBER" \
                        -n "$NAMESPACE"

                        kubectl rollout status \
                        statefulset/"$service" \
                        -n "$NAMESPACE" \
                        --timeout=300s
                    done

                    for service in coordinator matcher api
                    do
                        kubectl set image \
                        deployment/"$service" \
                        "*=$BACKEND:$BUILD_NUMBER" \
                        -n "$NAMESPACE"

                        kubectl rollout status \
                        deployment/"$service" \
                        -n "$NAMESPACE" \
                        --timeout=300s
                    done

                    kubectl set image deployment/frontend \
                    "*=$FRONTEND:$BUILD_NUMBER" \
                    -n "$NAMESPACE"

                    kubectl rollout status deployment/frontend \
                    -n "$NAMESPACE" \
                    --timeout=300s
                '''
            }
        }

        stage('Deployment Verification') {
            steps {
                sh '''
                    kubectl get pods -n "$NAMESPACE"
                    kubectl get deployments -n "$NAMESPACE"
                    kubectl get statefulsets -n "$NAMESPACE"
                    kubectl get pvc -n "$NAMESPACE"
                    kubectl get hpa -n "$NAMESPACE"

                    kubectl exec -n "$NAMESPACE" \
                    deployment/coordinator -- \
                    python -c "import httpx; r=httpx.get('http://api:8000/health'); r.raise_for_status(); print(r.json())"
                '''
            }
        }
    }

    post {
        success {
            echo 'ResQCloud CI/CD pipeline completed successfully.'
        }

        failure {
            echo 'Pipeline failed. Inspect the console output.'
        }

        always {
            deleteDir()
        }
    }
}
