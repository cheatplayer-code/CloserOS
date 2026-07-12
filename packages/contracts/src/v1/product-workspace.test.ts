import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  validateAgainstSchema,
  type JsonSchemaDocument,
} from "./contract-validate.js";
import { PRODUCT_WORKSPACE_SCHEMA_FILES } from "./schema-manifest.js";

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");

const PRODUCT_SCHEMAS = PRODUCT_WORKSPACE_SCHEMA_FILES;

const PRODUCT_FIXTURES: Record<(typeof PRODUCT_SCHEMAS)[number], string> = {
  "dashboard-response.json": "dashboard-response.json",
  "follow-up-task.json": "follow-up-task.json",
  "manager-scorecard.json": "manager-scorecard.json",
};

describe("RSTU product workspace contract fixtures", () => {
  for (const schemaFile of PRODUCT_SCHEMAS) {
    it(`validates ${schemaFile} fixture`, () => {
      const schema = JSON.parse(
        readFileSync(join(packageRoot, "schemas/v1", schemaFile), "utf8"),
      ) as JsonSchemaDocument;
      const fixture = JSON.parse(
        readFileSync(
          join(packageRoot, "fixtures/v1/valid", PRODUCT_FIXTURES[schemaFile]),
          "utf8",
        ),
      );
      const result = validateAgainstSchema(schema, fixture);
      expect(result).toEqual([]);
    });
  }
});
