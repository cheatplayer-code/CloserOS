"use client";

import Link from "next/link";
import { useState } from "react";

import {
  catalogApiClient,
  type CatalogImportRunV1,
} from "../../lib/api/catalog-client";
import type { ApiFailure } from "../../lib/auth/types";
import { useTenant } from "../../lib/tenant/use-tenant";
import { AppShell } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { TenantGate } from "../app/tenant-gate";
import { WorkspaceEmptyState, WorkspaceStatusBanner } from "./workspace-status";
import {
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "./workspace-utils";

const CATALOG_ROLES = ["owner", "sales_head"];

const DEFAULT_MAPPING = {
  product_sku: "product_sku",
  variant_sku: "variant_sku",
  product_name: "product_name",
  category_code: "category_code",
  amount_minor_or_decimal: "amount_minor_or_decimal",
  currency: "currency",
  available_quantity: "available_quantity",
  location_code: "location_code",
};

export function CatalogImportsPage() {
  return (
    <ProtectedRoute returnTo="/app/catalog/imports">
      <TenantGate>
        <CatalogImportsContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function CatalogImportsContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [csvText, setCsvText] = useState(
    "product_sku,variant_sku,product_name,category_code,amount_minor_or_decimal,currency,available_quantity,location_code\nSOFA-1,SOFA-1-GY,Угловой диван,corner_sofa,45000000,KZT,3,almaty\n",
  );
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [preview, setPreview] = useState<CatalogImportRunV1 | null>(null);
  const [lastRun, setLastRun] = useState<CatalogImportRunV1 | null>(null);
  const permissionDenied = useWorkspaceRoleDenied(CATALOG_ROLES);

  if (!session) {
    return null;
  }
  const activeSession = session;

  async function runDryRun() {
    if (!tenant.tenantId || !activeSession.csrfToken) {
      return;
    }
    const result = await catalogApiClient.uploadImport(
      tenant.tenantId,
      {
        csv_text: csvText,
        delimiter: ",",
        mapping: DEFAULT_MAPPING,
        dry_run: true,
      },
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    setFailure(null);
    setPreview(result.data);
  }

  async function uploadAndKeep() {
    if (!tenant.tenantId || !activeSession.csrfToken) {
      return;
    }
    const result = await catalogApiClient.uploadImport(
      tenant.tenantId,
      {
        csv_text: csvText,
        delimiter: ",",
        mapping: DEFAULT_MAPPING,
        dry_run: false,
      },
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    setFailure(null);
    setLastRun(result.data);
  }

  async function publish() {
    if (!tenant.tenantId || !activeSession.csrfToken || !lastRun?.id) {
      return;
    }
    const result = await catalogApiClient.publishImport(
      tenant.tenantId,
      lastRun.id,
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    setFailure(null);
    setLastRun(result.data);
  }

  return (
    <AppShell
      session={activeSession}
      onLogout={onLogout}
      onLogoutAll={onLogoutAll}
    >
      <section
        className="workspace-page"
        aria-labelledby="catalog-imports-title"
      >
        <header className="workspace-page__header">
          <div>
            <p className="workspace-page__eyebrow">Catalog</p>
            <h1 id="catalog-imports-title">CSV imports</h1>
            <p>
              Upload validates only. Publish is a separate explicit step. XLSX
              is not implemented in this block.
            </p>
          </div>
          <Link href="/app/catalog">Back to products</Link>
        </header>

        {permissionDenied ? (
          <WorkspaceEmptyState
            title="Import requires owner or sales head"
            description="Catalog administrators must confirm publish after preview."
          />
        ) : (
          <>
            <WorkspaceStatusBanner failure={failure} />
            <label>
              CSV content (UTF-8)
              <textarea
                value={csvText}
                onChange={(event) => setCsvText(event.target.value)}
                rows={10}
                aria-describedby="csv-help"
              />
            </label>
            <p id="csv-help">
              Column mapping uses canonical field names. Formula-leading cells
              are rejected.
            </p>
            <div className="workspace-actions">
              <button type="button" onClick={() => void runDryRun()}>
                Preview (dry run)
              </button>
              <button type="button" onClick={() => void uploadAndKeep()}>
                Upload for publish
              </button>
              <button
                type="button"
                onClick={() => void publish()}
                disabled={!lastRun?.id || lastRun.status !== "ready_to_publish"}
              >
                Confirm publish
              </button>
            </div>
            {preview ? (
              <p>
                Preview: {preview.valid_rows} valid / {preview.invalid_rows}{" "}
                invalid of {preview.total_rows}
              </p>
            ) : null}
            {lastRun ? (
              <p>
                Run {lastRun.id ?? "dry-run"} status {lastRun.status}; created{" "}
                {lastRun.created_count ?? 0}, updated{" "}
                {lastRun.updated_count ?? 0}
              </p>
            ) : null}
            {preview?.rows && preview.rows.length > 0 ? (
              <table className="workspace-table">
                <caption>Validation row results</caption>
                <thead>
                  <tr>
                    <th scope="col">Row</th>
                    <th scope="col">Valid</th>
                    <th scope="col">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr key={row.row_number}>
                      <td>{row.row_number}</td>
                      <td>{row.is_valid ? "yes" : "no"}</td>
                      <td>{row.error_code ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </>
        )}
      </section>
    </AppShell>
  );
}
