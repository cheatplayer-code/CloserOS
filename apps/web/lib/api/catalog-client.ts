/** Catalog UI API helpers and types. */

import { apiRequest } from "./http";
import { buildQueryString } from "./product-client";

export interface CatalogProductV1 {
  id: string;
  sku: string;
  name: string;
  category_code: string;
  description: string;
  status: string;
  version: number;
  updated_at: string;
}

export interface CatalogVariantV1 {
  id: string;
  product_id: string;
  sku: string;
  display_name: string;
  attributes: Record<string, string>;
  status: string;
  version: number;
}

export interface CatalogProductDetailV1 {
  product: CatalogProductV1;
  variants: CatalogVariantV1[];
}

export interface CatalogProductListV1 {
  items: CatalogProductV1[];
}

export interface CatalogImportRunV1 {
  id?: string | null;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  created_count?: number;
  updated_count?: number;
  dry_run?: boolean;
  rows?: Array<{
    row_number: number;
    is_valid: boolean;
    error_code?: string | null;
  }>;
}

const API_PREFIX = "/api/v1";

function tenantPath(tenantId: string, suffix: string): string {
  return `${API_PREFIX}/tenants/${tenantId}${suffix}`;
}

export function createCatalogApiClient() {
  return {
    listProducts(
      tenantId: string,
      query: { status?: string; category_code?: string; q?: string } = {},
    ) {
      return apiRequest<CatalogProductListV1>(
        tenantPath(tenantId, `/catalog/products${buildQueryString(query)}`),
      );
    },
    getProduct(tenantId: string, productId: string) {
      return apiRequest<CatalogProductDetailV1>(
        tenantPath(tenantId, `/catalog/products/${productId}`),
      );
    },
    createProduct(
      tenantId: string,
      body: {
        sku: string;
        name: string;
        category_code: string;
        description?: string;
      },
      csrfToken: string,
    ) {
      return apiRequest<CatalogProductV1>(
        tenantPath(tenantId, "/catalog/products"),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },
    publishProduct(
      tenantId: string,
      productId: string,
      expectedVersion: number,
      csrfToken: string,
    ) {
      return apiRequest<CatalogProductV1>(
        tenantPath(tenantId, `/catalog/products/${productId}/publish`),
        {
          method: "POST",
          body: { expected_version: expectedVersion },
          csrfToken,
        },
      );
    },
    addVariant(
      tenantId: string,
      productId: string,
      body: {
        sku: string;
        display_name: string;
        attributes?: Record<string, string>;
      },
      csrfToken: string,
    ) {
      return apiRequest<CatalogVariantV1>(
        tenantPath(tenantId, `/catalog/products/${productId}/variants`),
        { method: "POST", body, csrfToken },
      );
    },
    setPrice(
      tenantId: string,
      variantId: string,
      body: { amount_minor: number; currency: string },
      csrfToken: string,
    ) {
      return apiRequest<Record<string, unknown>>(
        tenantPath(tenantId, `/catalog/variants/${variantId}/price`),
        { method: "POST", body, csrfToken },
      );
    },
    setInventory(
      tenantId: string,
      variantId: string,
      body: {
        location_code: string;
        available_quantity: number;
        reserved_quantity?: number;
      },
      csrfToken: string,
    ) {
      return apiRequest<Record<string, unknown>>(
        tenantPath(tenantId, `/catalog/variants/${variantId}/inventory`),
        { method: "POST", body, csrfToken },
      );
    },
    uploadImport(
      tenantId: string,
      body: {
        csv_text: string;
        delimiter?: string;
        mapping: Record<string, string>;
        dry_run?: boolean;
      },
      csrfToken: string,
    ) {
      return apiRequest<CatalogImportRunV1>(
        tenantPath(tenantId, "/catalog/imports"),
        {
          method: "POST",
          body,
          csrfToken,
        },
      );
    },
    publishImport(tenantId: string, runId: string, csrfToken: string) {
      return apiRequest<CatalogImportRunV1>(
        tenantPath(tenantId, `/catalog/imports/${runId}/publish`),
        { method: "POST", body: {}, csrfToken },
      );
    },
  };
}

export const catalogApiClient = createCatalogApiClient();
