FROM maven:3.9-eclipse-temurin-17 AS build

WORKDIR /workspace

# Resolve dependencies before copying source to keep rebuilds quick.
COPY pom.xml ./
RUN mvn --batch-mode --no-transfer-progress dependency:go-offline

COPY src ./src
RUN mvn --batch-mode --no-transfer-progress -DskipTests package

FROM eclipse-temurin:17-jre-alpine

RUN apk add --no-cache curl \
    && addgroup -S careercompass \
    && adduser -S -G careercompass -h /app careercompass

WORKDIR /app

COPY --from=build /workspace/target/careercompass-backend-*.jar ./app.jar

# Docker initializes the named volumes from these directories, including their
# ownership, so the non-root process can persist H2 metadata and uploads.
RUN mkdir -p /app/data /app/uploads/learning-outcomes \
    && chown -R careercompass:careercompass /app

USER careercompass

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
