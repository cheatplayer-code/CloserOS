import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "../..");
const composeFile = resolve(scriptDirectory, "compose.yaml");
const composePrefix = ["compose", "-f", composeFile];

function runDocker(args, failureMessage) {
  const result = spawnSync("docker", args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  });

  if (result.status !== 0) {
    console.error(failureMessage);
    if (result.stderr.trim()) {
      console.error(result.stderr.trim());
    }
    process.exit(result.status ?? 1);
  }

  return result.stdout.trim();
}

function serviceContainerId(serviceName) {
  const containerId = runDocker(
    [...composePrefix, "ps", "--quiet", serviceName],
    `${serviceName} is not available through Docker Compose.`,
  );
  if (!containerId) {
    console.error(`${serviceName} is not running.`);
    process.exit(1);
  }
  return containerId;
}

for (const serviceName of ["postgres", "redis"]) {
  const containerId = serviceContainerId(serviceName);
  const state = runDocker(
    [
      "inspect",
      "--format",
      "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}",
      containerId,
    ],
    `Could not inspect ${serviceName}.`,
  );

  if (state !== "true healthy") {
    console.error(
      `${serviceName} must be running and healthy; state: ${state}`,
    );
    process.exit(1);
  }
}

runDocker(
  [
    ...composePrefix,
    "exec",
    "--no-TTY",
    "postgres",
    "sh",
    "-ec",
    `test "$(PGPASSWORD="$POSTGRES_PASSWORD" psql --no-password --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only --no-align --command 'SELECT current_database()')" = "$POSTGRES_DB"`,
  ],
  "Authenticated PostgreSQL database verification failed.",
);

runDocker(
  [
    ...composePrefix,
    "exec",
    "--no-TTY",
    "redis",
    "sh",
    "-ec",
    `test "$(REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --no-auth-warning ping)" = PONG`,
  ],
  "Authenticated Redis PING failed.",
);

runDocker(
  [
    ...composePrefix,
    "exec",
    "--no-TTY",
    "redis",
    "sh",
    "-ec",
    `response="$(env -u REDISCLI_AUTH redis-cli ping 2>&1 || true)"; case "$response" in *NOAUTH*) exit 0 ;; *) exit 1 ;; esac`,
  ],
  "Redis unexpectedly accepted an unauthenticated PING.",
);

console.log(
  "PostgreSQL: running, healthy, authenticated, configured database exists.",
);
console.log("Redis: running, healthy, authenticated PING returned PONG.");
console.log("Redis: unauthenticated PING was rejected.");
