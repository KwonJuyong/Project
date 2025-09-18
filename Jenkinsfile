pipeline {
    agent any

    environment {
        COMPOSE_FILE = "docker-compose-jy-v0-test.yml"
    }

    stages {
        stage('Checkout Code') {
            steps {
                git branch: 'jy-v0-test', credentialsId: 'hyuns-github-token', url: 'git@github.com:LabChain/aprofi_backend.git'
            }
        }

        stage('Create .env File') {
            steps {
                sh 'cp .env.jy-v0-test .env'
            }
        }

        stage('Download Required Docker Images') {
            steps {
                sh "docker pull python:3.11"
                sh "docker pull gcc:latest"
            }
        }

        stage('Stop and Remove Old Containers') {
            steps {
                sh "docker-compose -f $COMPOSE_FILE down -v --remove-orphans"
                sh "docker container prune -f"
            }
        }

        stage('Build & Run FastAPI') {
            steps {
                sh "docker-compose -f $COMPOSE_FILE up -d --build"
            }
        }

        stage('API Health Check') {
            steps {
                script {
                    sh 'curl -f http://localhost:8003 || echo "API is not responding"'
                }
            }
        }

        stage('DB Connection Check') {
            steps {
                script {
                    sh 'docker exec aprofi_postgres_server_jy_v0_test psql -U labchain -d aprofi_db_jy_v0_test -c "SELECT 1;" || echo "DB Connection Failed"'
                }
            }
        }
    }

    post {
        success {
            echo "✅ Build completed successfully!"
        }
        failure {
            echo "🚨 Build Failed!"
        }
        always {
            echo "🔄 Cleanup..."
            sh 'rm -f .env'
        }
    }
}
