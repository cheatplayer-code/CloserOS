import type {
  CreateOutboundDraftRequestV1,
  CreateWhatsAppConnectionRequestV1,
  OutboundMessageActionRequestV1,
  OutboundMessageV1,
  UpdateWhatsAppConnectionRequestV1,
  WhatsAppConnectionActionRequestV1,
  WhatsAppConnectionListResponseV1,
  WhatsAppConnectionV1,
} from "@closeros/contracts";

import { apiRequest } from "./http";

const API_PREFIX = "/api/v1";

function tenantPath(tenantId: string, suffix: string): string {
  return `${API_PREFIX}/tenants/${tenantId}${suffix}`;
}

export function createWhatsAppApiClient() {
  return {
    listWhatsAppConnections(tenantId: string) {
      return apiRequest<WhatsAppConnectionListResponseV1>(
        tenantPath(tenantId, "/integrations/whatsapp"),
      );
    },

    createWhatsAppConnection(
      tenantId: string,
      body: CreateWhatsAppConnectionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<WhatsAppConnectionV1>(
        tenantPath(tenantId, "/integrations/whatsapp"),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },

    updateWhatsAppConnection(
      tenantId: string,
      connectionId: string,
      body: UpdateWhatsAppConnectionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<WhatsAppConnectionV1>(
        tenantPath(tenantId, `/integrations/whatsapp/${connectionId}`),
        {
          method: "PATCH",
          body,
          csrfToken,
        },
      );
    },

    verifyWhatsAppConnection(
      tenantId: string,
      connectionId: string,
      body: WhatsAppConnectionActionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<WhatsAppConnectionV1>(
        tenantPath(tenantId, `/integrations/whatsapp/${connectionId}/verify`),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },

    disableWhatsAppConnection(
      tenantId: string,
      connectionId: string,
      body: WhatsAppConnectionActionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<WhatsAppConnectionV1>(
        tenantPath(tenantId, `/integrations/whatsapp/${connectionId}/disable`),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },

    createOutboundDraft(
      tenantId: string,
      threadId: string,
      body: CreateOutboundDraftRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<OutboundMessageV1>(
        tenantPath(tenantId, `/conversations/${threadId}/outbound-drafts`),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },

    approveOutboundMessage(
      tenantId: string,
      messageId: string,
      body: OutboundMessageActionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<OutboundMessageV1>(
        tenantPath(tenantId, `/outbound-messages/${messageId}/approve`),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },

    cancelOutboundMessage(
      tenantId: string,
      messageId: string,
      body: OutboundMessageActionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<OutboundMessageV1>(
        tenantPath(tenantId, `/outbound-messages/${messageId}/cancel`),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },

    getOutboundMessage(tenantId: string, messageId: string) {
      return apiRequest<OutboundMessageV1>(
        tenantPath(tenantId, `/outbound-messages/${messageId}`),
      );
    },
  };
}

export type WhatsAppApiClient = ReturnType<typeof createWhatsAppApiClient>;

export const whatsappApiClient = createWhatsAppApiClient();
