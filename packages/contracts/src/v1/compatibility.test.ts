import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  ChannelConnectionStatus,
  CrmOutcomeType,
  DeliveryStatus,
  LeadStatus,
  MessageDirection,
  ParticipantSenderType,
  ProviderKind,
  SalesCaseStatus,
  SCHEMA_VERSION_V1,
  WebhookProcessingStatus,
} from "./enums.js";
import {
  type JsonSchemaDocument,
  validateAgainstSchema,
} from "./contract-validate.js";
import { V1_SCHEMA_FILES } from "./schema-manifest.js";

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const schemasDir = join(packageRoot, "schemas/v1");
const validFixturesDir = join(packageRoot, "fixtures/v1/valid");
const invalidFixturesDir = join(packageRoot, "fixtures/v1/invalid");

const REQUIRED_FIELDS_BY_SCHEMA: Record<string, string[]> = {
  "channel-connection.json": [
    "schema_version",
    "id",
    "tenant_id",
    "provider",
    "external_connection_id",
    "status",
    "adapter_metadata",
    "created_at",
    "updated_at",
  ],
  "lead.json": [
    "schema_version",
    "id",
    "tenant_id",
    "external_identity_id",
    "status",
    "adapter_metadata",
    "created_at",
    "updated_at",
  ],
  "sales-case.json": [
    "schema_version",
    "id",
    "tenant_id",
    "status",
    "created_at",
    "updated_at",
  ],
  "conversation-thread.json": [
    "schema_version",
    "id",
    "tenant_id",
    "channel_connection_id",
    "external_conversation_id",
    "adapter_metadata",
    "created_at",
    "updated_at",
  ],
  "message.json": [
    "schema_version",
    "id",
    "tenant_id",
    "conversation_thread_id",
    "external_message_id",
    "sender_type",
    "direction",
    "sent_at",
    "received_at",
    "adapter_metadata",
  ],
  "message-edit-event.json": [
    "schema_version",
    "id",
    "tenant_id",
    "message_id",
    "external_event_id",
    "occurred_at",
    "adapter_metadata",
  ],
  "message-deletion-event.json": [
    "schema_version",
    "id",
    "tenant_id",
    "message_id",
    "external_event_id",
    "occurred_at",
    "adapter_metadata",
  ],
  "message-delivery-status-event.json": [
    "schema_version",
    "id",
    "tenant_id",
    "message_id",
    "external_event_id",
    "occurred_at",
    "delivery_status",
    "adapter_metadata",
  ],
  "manager-assignment.json": [
    "schema_version",
    "id",
    "tenant_id",
    "manager_user_id",
    "assigned_at",
  ],
  "crm-outcome.json": [
    "schema_version",
    "id",
    "tenant_id",
    "sales_case_id",
    "external_deal_id",
    "outcome_type",
    "occurred_at",
    "adapter_metadata",
  ],
  "webhook-event.json": [
    "schema_version",
    "id",
    "tenant_id",
    "channel_connection_id",
    "external_event_id",
    "processing_status",
    "received_at",
    "adapter_metadata",
  ],
};

const ENUM_PARITY: Record<string, string[]> = {
  providerKind: Object.values(ProviderKind),
  channelConnectionStatus: Object.values(ChannelConnectionStatus),
  leadStatus: Object.values(LeadStatus),
  salesCaseStatus: Object.values(SalesCaseStatus),
  participantSenderType: Object.values(ParticipantSenderType),
  messageDirection: Object.values(MessageDirection),
  deliveryStatus: Object.values(DeliveryStatus),
  crmOutcomeType: Object.values(CrmOutcomeType),
  webhookProcessingStatus: Object.values(WebhookProcessingStatus),
};

const INVALID_FIXTURE_TARGETS: Record<string, string> = {
  "missing-tenant-id.json": "channel-connection.json",
  "wrong-schema-version.json": "lead.json",
  "forbidden-body-field.json": "message.json",
  "naive-timestamp.json": "sales-case.json",
  "invalid-provider-enum.json": "channel-connection.json",
  "both-assignment-targets.json": "manager-assignment.json",
  "sales-case-with-lifecycle.json": "conversation-thread.json",
  "sensitive-adapter-key.json": "webhook-event.json",
  "invalid-uuid.json": "sales-case.json",
};

function loadJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

function loadSchema(fileName: string): JsonSchemaDocument {
  return loadJson(join(schemasDir, fileName)) as JsonSchemaDocument;
}

function enumValuesFromSchema(
  schema: JsonSchemaDocument,
  defName: string,
): string[] {
  const definition = schema.$defs?.[defName];

  if (!definition?.enum) {
    throw new Error(`Missing enum definition ${defName}`);
  }

  return [...definition.enum].sort();
}

describe("v1 contract compatibility", () => {
  for (const schemaFile of V1_SCHEMA_FILES) {
    describe(schemaFile, () => {
      const schema = loadSchema(schemaFile);

      it("pins schema_version to 1.0", () => {
        const schemaVersion = schema.$defs?.schemaVersion;
        expect(schemaVersion?.const).toBe(SCHEMA_VERSION_V1);
        expect(schema.additionalProperties).toBe(false);
      });

      it("requires tenant_id on every tenant-owned record", () => {
        expect(schema.required).toContain("tenant_id");
        expect(REQUIRED_FIELDS_BY_SCHEMA[schemaFile]).toContain("tenant_id");
      });

      it("keeps the required field contract stable", () => {
        expect([...(schema.required ?? [])].sort()).toEqual(
          [...REQUIRED_FIELDS_BY_SCHEMA[schemaFile]].sort(),
        );
      });

      it("does not allow provider content fields in core properties", () => {
        const propertyNames = Object.keys(schema.properties ?? {});
        expect(propertyNames).not.toContain("body");
        expect(propertyNames).not.toContain("text");
        expect(propertyNames).not.toContain("content");
      });
    });
  }

  it("keeps TypeScript enums aligned with JSON Schema enums", () => {
    const channelConnection = loadSchema("channel-connection.json");
    expect(enumValuesFromSchema(channelConnection, "providerKind")).toEqual(
      [...ENUM_PARITY.providerKind].sort(),
    );
    expect(
      enumValuesFromSchema(channelConnection, "channelConnectionStatus"),
    ).toEqual([...ENUM_PARITY.channelConnectionStatus].sort());

    const lead = loadSchema("lead.json");
    expect(enumValuesFromSchema(lead, "leadStatus")).toEqual(
      [...ENUM_PARITY.leadStatus].sort(),
    );

    const salesCase = loadSchema("sales-case.json");
    expect(enumValuesFromSchema(salesCase, "salesCaseStatus")).toEqual(
      [...ENUM_PARITY.salesCaseStatus].sort(),
    );

    const message = loadSchema("message.json");
    expect(enumValuesFromSchema(message, "participantSenderType")).toEqual(
      [...ENUM_PARITY.participantSenderType].sort(),
    );
    expect(enumValuesFromSchema(message, "messageDirection")).toEqual(
      [...ENUM_PARITY.messageDirection].sort(),
    );

    const delivery = loadSchema("message-delivery-status-event.json");
    expect(enumValuesFromSchema(delivery, "deliveryStatus")).toEqual(
      [...ENUM_PARITY.deliveryStatus].sort(),
    );

    const crmOutcome = loadSchema("crm-outcome.json");
    expect(enumValuesFromSchema(crmOutcome, "crmOutcomeType")).toEqual(
      [...ENUM_PARITY.crmOutcomeType].sort(),
    );

    const webhook = loadSchema("webhook-event.json");
    expect(enumValuesFromSchema(webhook, "webhookProcessingStatus")).toEqual(
      [...ENUM_PARITY.webhookProcessingStatus].sort(),
    );
  });

  it("accepts all valid synthetic fixtures", () => {
    for (const fixtureName of readdirSync(validFixturesDir).sort()) {
      const schemaFile = fixtureName;
      const schema = loadSchema(schemaFile);
      const fixture = loadJson(join(validFixturesDir, fixtureName));
      const issues = validateAgainstSchema(schema, fixture);

      expect(issues, fixtureName).toEqual([]);
    }
  });

  it("rejects invalid synthetic fixtures", () => {
    for (const fixtureName of readdirSync(invalidFixturesDir).sort()) {
      const schemaFile = INVALID_FIXTURE_TARGETS[fixtureName];

      if (!schemaFile) {
        throw new Error(
          `Missing schema mapping for invalid fixture ${fixtureName}`,
        );
      }

      const schema = loadSchema(schemaFile);
      const fixture = loadJson(join(invalidFixturesDir, fixtureName));
      const issues = validateAgainstSchema(schema, fixture);

      expect(issues.length, fixtureName).toBeGreaterThan(0);
    }
  });

  it("fails when tenant_id is removed from a valid fixture", () => {
    const schema = loadSchema("channel-connection.json");
    const fixture = loadJson(
      join(validFixturesDir, "channel-connection.json"),
    ) as Record<string, unknown>;
    delete fixture.tenant_id;

    const issues = validateAgainstSchema(schema, fixture);
    expect(issues.some((issue) => issue.path === "tenant_id")).toBe(true);
  });

  it("fails when a required enum value is removed from the schema", () => {
    const schema = loadSchema("channel-connection.json");
    const providerEnum = schema.$defs?.providerKind?.enum;

    expect(providerEnum).toContain(ProviderKind.Whatsapp);

    const trimmedEnum = providerEnum?.filter(
      (value) => value !== ProviderKind.Whatsapp,
    );
    const mutatedSchema: JsonSchemaDocument = {
      ...schema,
      $defs: {
        ...schema.$defs,
        providerKind: {
          ...schema.$defs?.providerKind,
          enum: trimmedEnum,
        },
      },
    };

    const fixture = loadJson(join(validFixturesDir, "channel-connection.json"));
    const issues = validateAgainstSchema(mutatedSchema, fixture);

    expect(issues.some((issue) => issue.path === "provider")).toBe(true);
  });
});
