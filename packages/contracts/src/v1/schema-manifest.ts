export const V1_SCHEMA_FILES = [
  "channel-connection.json",
  "lead.json",
  "sales-case.json",
  "conversation-thread.json",
  "message.json",
  "message-edit-event.json",
  "message-deletion-event.json",
  "message-delivery-status-event.json",
  "manager-assignment.json",
  "crm-outcome.json",
  "webhook-event.json",
] as const;

export type V1SchemaFile = (typeof V1_SCHEMA_FILES)[number];

export const V1_SCHEMA_BASE_PATH = "schemas/v1";
