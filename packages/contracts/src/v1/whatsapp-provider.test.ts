import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  validateAgainstSchema,
  type JsonSchemaDocument,
} from "./contract-validate.js";
import { WHATSAPP_PROVIDER_SCHEMA_FILES } from "./schema-manifest.js";

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");

const WHATSAPP_FIXTURES: Record<
  (typeof WHATSAPP_PROVIDER_SCHEMA_FILES)[number],
  string
> = {
  "whatsapp-connection.json": "whatsapp-connection.json",
  "outbound-message.json": "outbound-message.json",
  "provider-template.json": "provider-template.json",
};

describe("VW WhatsApp provider contract fixtures", () => {
  for (const schemaFile of WHATSAPP_PROVIDER_SCHEMA_FILES) {
    it(`validates ${schemaFile} fixture`, () => {
      const schema = JSON.parse(
        readFileSync(join(packageRoot, "schemas/v1", schemaFile), "utf8"),
      ) as JsonSchemaDocument;
      const fixture = JSON.parse(
        readFileSync(
          join(packageRoot, "fixtures/v1/valid", WHATSAPP_FIXTURES[schemaFile]),
          "utf8",
        ),
      );
      const result = validateAgainstSchema(schema, fixture);
      expect(result).toEqual([]);
    });
  }
});
