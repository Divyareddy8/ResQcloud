pipeline {
  agent any
  options { timestamps() }
  environment { IMAGE = 'YOUR_DOCKERHUB_USERNAME/resqcloud'; TAG = "${BUILD_NUMBER}" }
  stages {
    stage('Checkout') { steps { checkout scm } }
    stage('Tests') { steps { sh 'python3 -m pip install -r requirements.txt && python3 -m pytest -q tests' } }
    stage('Build') { steps { sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest .' } }
    stage('Push') { steps { withCredentials([usernamePassword(credentialsId: 'dockerhub',usernameVariable:'DOCKER_USER',passwordVariable:'DOCKER_PASS')]) { sh 'echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin && docker push $IMAGE:$TAG && docker push $IMAGE:latest' } } }
    stage('Deploy') { steps { sh 'kubectl set image deployment/api api=$IMAGE:$TAG -n resqcloud && kubectl rollout status deployment/api -n resqcloud --timeout=180s' } }
  }
  post { always { cleanWs() } }
}
