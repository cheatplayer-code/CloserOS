import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { delimiter, dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "../..");
const temporaryRoot = mkdtempSync(join(tmpdir(), "closeros-cls002-"));
const temporaryCacheRoot = mkdtempSync(
  join(tmpdir(), "closeros-cls002-cache-"),
);
const projectName = `closeros_cls002_clean_${process.pid}_${Date.now()}`;

function run(command, args, options = {}) {
  console.log(`> ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? temporaryRoot,
    env: options.env ?? process.env,
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
    maxBuffer: 20 * 1024 * 1024,
  });

  if (result.error) {
    throw new Error(`${command} could not start: ${result.error.message}`);
  }

  if (result.status !== 0) {
    throw new Error(`${command} failed with exit code ${result.status ?? 1}`);
  }

  return options.capture ? result.stdout.trim() : "";
}

function runCorepack(args, options) {
  if (process.platform === "win32") {
    const commandInterpreter = process.env.ComSpec ?? "cmd.exe";
    return run(
      commandInterpreter,
      ["/d", "/s", "/c", `corepack ${args.join(" ")}`],
      options,
    );
  }
  return run("corepack", args, options);
}

async function availablePort() {
  const server = createServer();
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    server.close();
    throw new Error("Could not allocate an isolated host port");
  }
  const { port } = address;
  await new Promise((resolveClose) => server.close(resolveClose));
  return port;
}

const repositoryFiles = run(
  "git",
  ["ls-files", "--cached", "--others", "--exclude-standard"],
  { cwd: repositoryRoot, capture: true },
)
  .split(/\r?\n/u)
  .filter(Boolean);

for (const relativePath of repositoryFiles) {
  const destination = resolve(temporaryRoot, relativePath);
  mkdirSync(dirname(destination), { recursive: true });
  copyFileSync(resolve(repositoryRoot, relativePath), destination);
}

const postgresPort = await availablePort();
const redisPort = await availablePort();
const corepackBin = join(temporaryCacheRoot, "corepack-bin");
mkdirSync(corepackBin, { recursive: true });
const isolatedEnvironment = {
  ...process.env,
  COMPOSE_PROJECT_NAME: projectName,
  npm_config_fetch_retries: "5",
  npm_config_fetch_retry_maxtimeout: "120000",
  npm_config_fetch_timeout: "300000",
  npm_config_store_dir: join(temporaryCacheRoot, "pnpm"),
  PATH: `${corepackBin}${delimiter}${process.env.PATH ?? ""}`,
  pnpm_config_store_dir: join(temporaryCacheRoot, "pnpm"),
  POSTGRES_HOST_PORT: String(postgresPort),
  REDIS_HOST_PORT: String(redisPort),
  UV_CACHE_DIR: join(temporaryCacheRoot, "uv"),
};

let verificationError;
try {
  runCorepack(["enable", "pnpm", "--install-directory", corepackBin], {
    env: isolatedEnvironment,
  });
  let setupComplete = false;
  for (let attempt = 1; attempt <= 3 && !setupComplete; attempt += 1) {
    try {
      runCorepack(["pnpm", "run", "setup"], {
        env: isolatedEnvironment,
      });
      setupComplete = true;
    } catch (error) {
      if (attempt === 3) {
        throw error;
      }
      console.warn(
        `Frozen setup attempt ${attempt} failed; retrying with the same initially empty temporary cache.`,
      );
    }
  }
  runCorepack(["pnpm", "run", "infra:config"], {
    env: isolatedEnvironment,
  });
  runCorepack(["pnpm", "run", "infra:up"], {
    env: isolatedEnvironment,
  });
  runCorepack(["pnpm", "run", "infra:check"], {
    env: isolatedEnvironment,
  });
  runCorepack(["pnpm", "run", "quality"], {
    env: isolatedEnvironment,
  });
} catch (error) {
  verificationError = error;
} finally {
  try {
    run(
      "docker",
      [
        "compose",
        "-f",
        "infra/docker/compose.yaml",
        "down",
        "--volumes",
        "--remove-orphans",
      ],
      { env: isolatedEnvironment },
    );

    const remainingResources = [
      run(
        "docker",
        [
          "container",
          "ls",
          "--all",
          "--quiet",
          "--filter",
          `label=com.docker.compose.project=${projectName}`,
        ],
        { env: isolatedEnvironment, capture: true },
      ),
      run(
        "docker",
        [
          "volume",
          "ls",
          "--quiet",
          "--filter",
          `label=com.docker.compose.project=${projectName}`,
        ],
        { env: isolatedEnvironment, capture: true },
      ),
      run(
        "docker",
        [
          "network",
          "ls",
          "--quiet",
          "--filter",
          `label=com.docker.compose.project=${projectName}`,
        ],
        { env: isolatedEnvironment, capture: true },
      ),
    ].filter(Boolean);

    if (remainingResources.length > 0) {
      throw new Error("Temporary Docker resources remain after cleanup");
    }
  } catch (cleanupError) {
    verificationError ??= cleanupError;
  }

  rmSync(temporaryRoot, { recursive: true, force: true });
  rmSync(temporaryCacheRoot, { recursive: true, force: true });
}

if (verificationError) {
  console.error(
    `Clean-checkout verification failed: ${verificationError.message}`,
  );
  process.exit(1);
}

console.log(
  `Clean-checkout verification passed and project ${projectName} was removed.`,
);
