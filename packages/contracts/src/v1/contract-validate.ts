import {
  FORBIDDEN_ADAPTER_METADATA_KEY_PATTERN,
  FORBIDDEN_CONTENT_FIELD_NAMES,
  SCHEMA_VERSION_V1,
} from "./enums.js";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const TIMESTAMP_PATTERN = /.*(Z|[+-]\d{2}:\d{2})$/;

const SENSITIVE_KEY_PATTERN = FORBIDDEN_ADAPTER_METADATA_KEY_PATTERN;

export type ValidationIssue = {
  path: string;
  message: string;
};

export type JsonSchemaDocument = {
  type?: string;
  additionalProperties?: boolean;
  required?: string[];
  properties?: Record<string, JsonSchemaProperty>;
  $defs?: Record<string, JsonSchemaProperty>;
};

export type JsonSchemaProperty = {
  type?: string;
  const?: string;
  enum?: string[];
  format?: string;
  pattern?: string;
  minLength?: number;
  maxLength?: number;
  maxProperties?: number;
  oneOf?: JsonSchemaProperty[];
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  additionalProperties?: boolean | JsonSchemaProperty;
  propertyNames?: JsonSchemaProperty;
  not?: JsonSchemaProperty;
};

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

export function isTimezoneAwareTimestamp(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }

  if (!TIMESTAMP_PATTERN.test(value)) {
    return false;
  }

  return !Number.isNaN(Date.parse(value));
}

export function validateAdapterMetadata(
  value: unknown,
  path = "adapter_metadata",
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    issues.push({ path, message: "must be an object" });
    return issues;
  }

  const entries = Object.entries(value as Record<string, unknown>);

  if (entries.length > 32) {
    issues.push({ path, message: "must contain at most 32 entries" });
  }

  for (const [key, entryValue] of entries) {
    const keyPath = `${path}.${key}`;

    if (key.trim().length === 0) {
      issues.push({ path: keyPath, message: "key must not be empty" });
    }

    if (key.length > 64) {
      issues.push({ path: keyPath, message: "key exceeds 64 characters" });
    }

    if (SENSITIVE_KEY_PATTERN.test(key)) {
      issues.push({ path: keyPath, message: "key is not allowed" });
    }

    if (
      entryValue !== null &&
      typeof entryValue !== "string" &&
      typeof entryValue !== "number" &&
      typeof entryValue !== "boolean"
    ) {
      issues.push({ path: keyPath, message: "value must be a JSON scalar" });
      continue;
    }

    if (typeof entryValue === "string") {
      if (entryValue.length === 0) {
        issues.push({
          path: keyPath,
          message: "string value must not be empty",
        });
      }

      if (entryValue.length > 512) {
        issues.push({
          path: keyPath,
          message: "string value exceeds 512 characters",
        });
      }
    }
  }

  return issues;
}

export function validateAgainstSchema(
  schema: JsonSchemaDocument,
  value: unknown,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return [{ path: "", message: "document must be an object" }];
  }

  const document = value as Record<string, unknown>;

  for (const fieldName of FORBIDDEN_CONTENT_FIELD_NAMES) {
    if (fieldName in document) {
      issues.push({
        path: fieldName,
        message:
          "forbidden content field is not allowed in canonical contracts",
      });
    }
  }

  if (schema.additionalProperties === false && schema.properties) {
    for (const key of Object.keys(document)) {
      if (!(key in schema.properties)) {
        issues.push({
          path: key,
          message: "additional property is not allowed",
        });
      }
    }
  }

  for (const requiredField of schema.required ?? []) {
    if (!(requiredField in document)) {
      issues.push({
        path: requiredField,
        message: "required field is missing",
      });
    }
  }

  for (const [fieldName, fieldSchema] of Object.entries(
    schema.properties ?? {},
  )) {
    if (!(fieldName in document)) {
      continue;
    }

    issues.push(
      ...validateProperty(fieldName, document[fieldName], fieldSchema, schema),
    );
  }

  issues.push(...validateEntityRules(document));

  return issues;
}

function validateProperty(
  path: string,
  value: unknown,
  propertySchema: JsonSchemaProperty,
  rootSchema: JsonSchemaDocument,
): ValidationIssue[] {
  if (path === "adapter_metadata" || path.endsWith(".adapter_metadata")) {
    return validateAdapterMetadata(value, path);
  }

  if ("$ref" in propertySchema) {
    const ref = (propertySchema as { $ref: string }).$ref;
    const resolved = resolveRef(ref, rootSchema);

    if (resolved) {
      return validateProperty(path, value, resolved, rootSchema);
    }
  }

  if (propertySchema.const !== undefined && value !== propertySchema.const) {
    return [{ path, message: `must equal ${propertySchema.const}` }];
  }

  if (
    propertySchema.enum &&
    (typeof value !== "string" || !propertySchema.enum.includes(value))
  ) {
    return [
      { path, message: `must be one of: ${propertySchema.enum.join(", ")}` },
    ];
  }

  if (propertySchema.oneOf) {
    const branchIssues = propertySchema.oneOf.map((branch) =>
      validateProperty(path, value, branch, rootSchema),
    );
    const passingBranch = branchIssues.find(
      (candidate) => candidate.length === 0,
    );

    if (!passingBranch) {
      return [{ path, message: "must satisfy oneOf constraint" }];
    }

    return [];
  }

  if (propertySchema.type === "string") {
    if (typeof value !== "string") {
      return [{ path, message: "must be a string" }];
    }

    if (propertySchema.format === "uuid" && !isUuid(value)) {
      return [{ path, message: "must be a UUID" }];
    }

    if (
      propertySchema.pattern &&
      !new RegExp(propertySchema.pattern).test(value)
    ) {
      return [{ path, message: "must match required pattern" }];
    }

    if (
      propertySchema.minLength !== undefined &&
      value.length < propertySchema.minLength
    ) {
      return [
        {
          path,
          message: `must be at least ${propertySchema.minLength} characters`,
        },
      ];
    }

    if (
      propertySchema.maxLength !== undefined &&
      value.length > propertySchema.maxLength
    ) {
      return [
        {
          path,
          message: `must be at most ${propertySchema.maxLength} characters`,
        },
      ];
    }

    if (
      propertySchema.format === "date-time" &&
      !isTimezoneAwareTimestamp(value)
    ) {
      return [{ path, message: "must be a timezone-aware ISO 8601 timestamp" }];
    }
  }

  if (propertySchema.type === "null" && value !== null) {
    return [{ path, message: "must be null" }];
  }

  if (propertySchema.type === "object") {
    if (path.endsWith("adapter_metadata") || path === "adapter_metadata") {
      return validateAdapterMetadata(value, path);
    }
  }

  return [];
}

function resolveRef(
  ref: string,
  schema: JsonSchemaDocument,
): JsonSchemaProperty | undefined {
  const match = ref.match(/^#\/\$defs\/(.+)$/);

  if (!match) {
    return undefined;
  }

  return schema.$defs?.[match[1]];
}

function validateEntityRules(
  document: Record<string, unknown>,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (
    document.schema_version !== undefined &&
    document.schema_version !== SCHEMA_VERSION_V1
  ) {
    issues.push({
      path: "schema_version",
      message: `must equal ${SCHEMA_VERSION_V1}`,
    });
  }

  if ("tenant_id" in document && !isUuid(document.tenant_id)) {
    issues.push({ path: "tenant_id", message: "must be a UUID" });
  }

  if ("conversation_thread_id" in document && "sales_case_id" in document) {
    const hasThread =
      document.conversation_thread_id !== null &&
      document.conversation_thread_id !== undefined;
    const hasSalesCase =
      document.sales_case_id !== null && document.sales_case_id !== undefined;

    if (hasThread === hasSalesCase) {
      issues.push({
        path: "conversation_thread_id",
        message:
          "exactly one of conversation_thread_id or sales_case_id must be set",
      });
    }
  }

  if (
    document.sales_case_id !== null &&
    document.sales_case_id !== undefined &&
    document.lifecycle_status !== null &&
    document.lifecycle_status !== undefined
  ) {
    issues.push({
      path: "lifecycle_status",
      message: "must be omitted or null when sales_case_id is set",
    });
  }

  if ("updated_at" in document && "created_at" in document) {
    const createdAt = document.created_at;
    const updatedAt = document.updated_at;

    if (
      typeof createdAt === "string" &&
      typeof updatedAt === "string" &&
      Date.parse(updatedAt) < Date.parse(createdAt)
    ) {
      issues.push({
        path: "updated_at",
        message: "must not be earlier than created_at",
      });
    }
  }

  if ("received_at" in document && "sent_at" in document) {
    const sentAt = document.sent_at;
    const receivedAt = document.received_at;

    if (
      typeof sentAt === "string" &&
      typeof receivedAt === "string" &&
      Date.parse(receivedAt) < Date.parse(sentAt)
    ) {
      issues.push({
        path: "received_at",
        message: "must not be earlier than sent_at",
      });
    }
  }

  if ("processed_at" in document && document.processed_at !== null) {
    const receivedAt = document.received_at;
    const processedAt = document.processed_at;

    if (
      typeof receivedAt === "string" &&
      typeof processedAt === "string" &&
      Date.parse(processedAt) < Date.parse(receivedAt)
    ) {
      issues.push({
        path: "processed_at",
        message: "must not be earlier than received_at",
      });
    }
  }

  return issues;
}

export function assertValid(schema: JsonSchemaDocument, value: unknown): void {
  const issues = validateAgainstSchema(schema, value);

  if (issues.length > 0) {
    const summary = issues
      .map((issue) => `${issue.path}: ${issue.message}`)
      .join("; ");
    throw new Error(`Contract validation failed: ${summary}`);
  }
}
