import type {
  CreateCrmConnectionRequestV1,
  CrmConnectionActionRequestV1,
  CrmConnectionListResponseV1,
  CrmConnectionV1,
  CrmSyncStatusResponseV1,
  UpdateCrmConnectionRequestV1,
} from "@closeros/contracts";

import { apiRequest } from "./http";

const API_PREFIX = "/api/v1";

function tenantPath(tenantId: string, suffix: string): string {
  return `${API_PREFIX}/tenants/${tenantId}${suffix}`;
}

export function createCrmApiClient() {
  return {
    listCrmConnections(tenantId: string) {
      return apiRequest<CrmConnectionListResponseV1>(
        tenantPath(tenantId, "/integrations/crm"),
      );
    },

    createCrmConnection(
      tenantId: string,
      body: CreateCrmConnectionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<CrmConnectionV1>(
        tenantPath(tenantId, "/integrations/crm"),
        { method: "POST", body, csrfToken },
      );
    },

    updateCrmConnection(
      tenantId: string,
      connectionId: string,
      body: UpdateCrmConnectionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<CrmConnectionV1>(
        tenantPath(tenantId, `/integrations/crm/${connectionId}`),
        { method: "PATCH", body, csrfToken },
      );
    },

    verifyCrmConnection(
      tenantId: string,
      connectionId: string,
      body: CrmConnectionActionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<CrmConnectionV1>(
        tenantPath(tenantId, `/integrations/crm/${connectionId}/verify`),
        { method: "POST", body, csrfToken },
      );
    },

    disableCrmConnection(
      tenantId: string,
      connectionId: string,
      body: CrmConnectionActionRequestV1,
      csrfToken: string,
    ) {
      return apiRequest<CrmConnectionV1>(
        tenantPath(tenantId, `/integrations/crm/${connectionId}/disable`),
        { method: "POST", body, csrfToken },
      );
    },

    getCrmSyncStatus(tenantId: string, connectionId: string) {
      return apiRequest<CrmSyncStatusResponseV1>(
        tenantPath(tenantId, `/integrations/crm/${connectionId}/sync-status`),
      );
    },
  };
}

export type CrmApiClient = ReturnType<typeof createCrmApiClient>;

export const crmApiClient = createCrmApiClient();
