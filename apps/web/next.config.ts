import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const appsWebDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.join(appsWebDirectory, "../..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: repositoryRoot,
  transpilePackages: ["@closeros/ui"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
