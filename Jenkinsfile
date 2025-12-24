pipeline {
    agent any

    environment {
        REGISTRY        = "dmmprice/microfinance_backend"
        CONTAINER_NAME  = "microfinance_backend"
        HOST_PORT       = "5050"
        CONTAINER_PORT  = "5050"
        GIT_URL         = "https://github.com/AppynittyCommunication/pmsproject_backend.git"
        GIT_BRANCH      = "main"
    }

    triggers {
        githubPush()
    }

    stages {
        stage('Checkout (Private Repo)') {
            steps {
                git branch: "${GIT_BRANCH}",
                    credentialsId: 'github-dmmprice-pat',
                    url: "${GIT_URL}"
            }
        }

        stage('Prepare .env (from Jenkins secret file)') {
            steps {
                withCredentials([file(credentialsId: 'microfinance-backend-env-file', variable: 'ENV_FILE')]) {
                    sh '''
                      echo "Copying env file from Jenkins credential..."
                      cp "$ENV_FILE" .env
                    '''
                }
            }
        }

        stage('Build Docker image') {
            steps {
                sh '''
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
                withCredentials([file(credentialsId: 'microfinance-backend-env-file', variable: 'ENV_FILE')]) {
                    sh '''
                      docker pull ${REGISTRY}:latest

                      docker stop ${CONTAINER_NAME} || true
                      docker rm ${CONTAINER_NAME} || true

                      docker run -d \
                        --name ${CONTAINER_NAME} \
                        --restart always \
                        -p ${HOST_PORT}:${CONTAINER_PORT} \
                        --env-file "$ENV_FILE" \
                        ${REGISTRY}:latest
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker image prune -f || true'
        }
    }
}
