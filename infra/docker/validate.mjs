import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "../..");
const composeFile = resolve(scriptDirectory, "compose.yaml");

function fail(message) {
  console.error(`Infrastructure configuration invalid: ${message}`);
  process.exit(1);
}

const rendered = spawnSync(
  "docker",
  ["compose", "-f", composeFile, "config", "--format", "json"],
  {
    cwd: repositoryRoot,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  },
);

if (rendered.status !== 0) {
  console.error(rendered.stderr.trim() || "docker compose config failed");
  process.exit(rendered.status ?? 1);
}

let config;
try {
  config = JSON.parse(rendered.stdout);
} catch {
  fail("docker compose config did not return valid JSON");
}

const requiredImages = {
  postgres: "postgres:18.4-bookworm",
  redis: "redis:8.8.0-trixie",
};

const serviceNames = Object.keys(config.services ?? {}).sort();
if (serviceNames.join(",") !== "postgres,redis") {
  fail("exactly the postgres and redis services are required");
}

for (const [serviceName, expectedImage] of Object.entries(requiredImages)) {
  const service = config.services[serviceName];
  if (service.image !== expectedImage || service.image.endsWith(":latest")) {
    fail(`${serviceName} must use the exact reviewed image ${expectedImage}`);
  }

  if (!Array.isArray(service.healthcheck?.test)) {
    fail(`${serviceName} must define a container health check`);
  }

  const ports = service.ports ?? [];
  if (
    ports.length !== 1 ||
    ports[0].host_ip !== "127.0.0.1" ||
    ports[0].protocol !== "tcp"
  ) {
    fail(`${serviceName} must expose one TCP port on 127.0.0.1 only`);
  }

  const mounts = service.volumes ?? [];
  if (mounts.length !== 1 || mounts[0].type !== "volume" || !mounts[0].source) {
    fail(`${serviceName} must use one named persistent volume`);
  }

  if (service.privileged === true) {
    fail(`${serviceName} must not be privileged`);
  }

  if (JSON.stringify(service).toLowerCase().includes("/var/run/docker.sock")) {
    fail(`${serviceName} must not mount the Docker socket`);
  }
}

for (const volumeName of ["postgres_data", "redis_data"]) {
  if (!Object.hasOwn(config.volumes ?? {}, volumeName)) {
    fail(`named volume ${volumeName} is missing`);
  }
}

const postgresEnvironment = config.services.postgres.environment ?? {};
if (
  !postgresEnvironment.POSTGRES_PASSWORD ||
  postgresEnvironment.POSTGRES_HOST_AUTH_METHOD === "trust"
) {
  fail("PostgreSQL password authentication must remain enabled");
}

const redisEnvironment = config.services.redis.environment ?? {};
const redisCommand = (config.services.redis.command ?? []).join(" ");
if (
  !redisEnvironment.REDIS_PASSWORD ||
  !redisCommand.includes("--requirepass")
) {
  fail("Redis authentication must remain enabled");
}

const requiredVariables = [
  "POSTGRES_DB",
  "POSTGRES_USER",
  "POSTGRES_PASSWORD",
  "POSTGRES_HOST_PORT",
  "REDIS_PASSWORD",
  "REDIS_HOST_PORT",
  "DATABASE_URL",
  "REDIS_URL",
];
const exampleEnvironment = readFileSync(
  resolve(repositoryRoot, ".env.example"),
  "utf8",
);

for (const variableName of requiredVariables) {
  if (!new RegExp(`^${variableName}=.+$`, "m").test(exampleEnvironment)) {
    fail(`${variableName} must be documented with a local example value`);
  }
}

console.log(
  "Compose configuration valid: PostgreSQL and Redis are pinned, authenticated, health-checked, persistent, and loopback-only.",
);
