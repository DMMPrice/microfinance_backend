pipeline {
    agent any

    environment {
        REGISTRY        = "dmmprice/microfinance_backend"
        CONTAINER_NAME  = "microfinance_backend"
        HOST_PORT       = "5050"
        CONTAINER_PORT  = "5050"
        GIT_URL         = "https://github.com/DMMPrice/microfinance_backend.git"
        GIT_BRANCH      = "main"

        // ✅ host-visible path (must exist on host AND mounted into Jenkins container)
        HOST_ENV_FILE   = "/data/jenkins/envs/.env"
    }

    triggers {
        githubPush()
    }

    stages {

        stage('Checkout (Private Repo)') {
            steps {
                git branch: "${GIT_BRANCH}",
                    url: "${GIT_URL}"
            }
        }

        stage('Prepare env file (from Jenkins secret file)') {
            steps {
                withCredentials([file(credentialsId: 'microfinance-backend-env-file', variable: 'ENV_FILE')]) {
                    sh '''
                      set -e
                      echo "Saving env file to host-visible path..."
                      mkdir -p /data/jenkins/envs
                      install -m 600 "$ENV_FILE" /data/jenkins/envs/.env
                      echo "✅ Saved env file:"
                      ls -la /data/jenkins/envs
                    '''
                }
            }
        }

        stage('Build Docker image') {
            steps {
                sh '''
                  set -e
                  docker build \
                    -t ${REGISTRY}:${BUILD_NUMBER} \
                    -t ${REGISTRY}:latest \
                    .
                '''
            }
        }

        stage('Push Docker image') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-dmmprice',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                      set -e
                      echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                      docker push ${REGISTRY}:${BUILD_NUMBER}
                      docker push ${REGISTRY}:latest
                      docker logout
                    '''
                }
            }
        }

        stage('Deploy (pull & restart container)') {
            steps {
                sh '''
                  set -e
                  docker pull ${REGISTRY}:latest

                  docker stop ${CONTAINER_NAME} || true
                  docker rm ${CONTAINER_NAME} || true

                  echo "Deploying with env file: ${HOST_ENV_FILE}"
                  docker run -d \
                    --name ${CONTAINER_NAME} \
                    --restart always \
                    -p ${HOST_PORT}:${CONTAINER_PORT} \
                    --env-file ${HOST_ENV_FILE} \
                    ${REGISTRY}:latest

                  echo "✅ Deployed container:"
                  docker ps --filter "name=${CONTAINER_NAME}"
                '''
            }
        }
    }

    post {
        always {
            sh 'docker image prune -f || true'
        }
    }
}
