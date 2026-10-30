# syntax=docker/dockerfile:1.7
FROM maven:3.9.9-eclipse-temurin-17 AS runner-build
WORKDIR /src
COPY runner/pom.xml runner/pom.xml
COPY runner/src runner/src
RUN --mount=type=secret,id=maven_settings,target=/run/secrets/maven_settings,required=true \
    mvn --settings /run/secrets/maven_settings -f runner/pom.xml \
      --batch-mode --no-transfer-progress --update-snapshots -Pframework clean test package

FROM eclipse-temurin:17-jre-jammy
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt
COPY --from=runner-build /src/runner/target/benchmark-runner.jar /app/benchmark-runner.jar
COPY controller /app/controller
COPY scripts /app/scripts
COPY configs /app/configs
RUN mkdir -p /data/results
EXPOSE 8080
ENTRYPOINT ["python3", "-m", "uvicorn", "controller.app:app", "--host", "0.0.0.0", "--port", "8080"]
