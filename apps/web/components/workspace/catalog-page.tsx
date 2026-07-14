"use client";
/* eslint-disable react-hooks/set-state-in-effect -- workspace pages reset fetch state when tenant context changes */

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  catalogApiClient,
  type CatalogProductV1,
} from "../../lib/api/catalog-client";
import type { ApiFailure } from "../../lib/auth/types";
import { useTenant } from "../../lib/tenant/use-tenant";
import { AppShell } from "../app/app-shell";
import { ProtectedRoute } from "../app/protected-route";
import { TenantGate } from "../app/tenant-gate";
import { Spinner } from "../auth/spinner";
import { WorkspaceEmptyState, WorkspaceStatusBanner } from "./workspace-status";
import {
  useWorkspaceLogoutHandlers,
  useWorkspaceRoleDenied,
  useWorkspaceSession,
} from "./workspace-utils";

const CATALOG_ROLES = ["owner", "sales_head"];

export function CatalogPage() {
  return (
    <ProtectedRoute returnTo="/app/catalog">
      <TenantGate>
        <CatalogContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function CatalogContent() {
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [products, setProducts] = useState<CatalogProductV1[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("corner_sofa");
  const permissionDenied = useWorkspaceRoleDenied(CATALOG_ROLES);
  const showLoading = Boolean(tenant.tenantId) && !permissionDenied && loading;

  useEffect(() => {
    if (!tenant.tenantId || permissionDenied) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailure(null);
    void catalogApiClient
      .listProducts(tenant.tenantId, {
        status: statusFilter || undefined,
        q: query || undefined,
      })
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (!result.ok) {
          setProducts([]);
          setFailure(result);
          return;
        }
        setProducts(result.data.items);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tenant.tenantId, permissionDenied, statusFilter, query]);

  if (!session) {
    return null;
  }
  const activeSession = session;

  async function onCreate() {
    if (!tenant.tenantId || !activeSession.csrfToken) {
      return;
    }
    const result = await catalogApiClient.createProduct(
      tenant.tenantId,
      { sku, name, category_code: category },
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    setProducts((current) => [result.data, ...current]);
    setSku("");
    setName("");
  }

  return (
    <AppShell
      session={activeSession}
      onLogout={onLogout}
      onLogoutAll={onLogoutAll}
    >
      <section className="workspace-page" aria-labelledby="catalog-title">
        <header className="workspace-page__header">
          <div>
            <p className="workspace-page__eyebrow">Catalog</p>
            <h1 id="catalog-title">Products</h1>
            <p>
              Structured SKU source of truth for grounded AI replies. Managers
              cannot edit catalog facts.
            </p>
          </div>
          <Link href="/app/catalog/imports">CSV imports</Link>
        </header>

        {permissionDenied ? (
          <WorkspaceEmptyState
            title="Catalog management requires owner or sales head"
            description="Read-only roles cannot mutate product facts in V1."
          />
        ) : null}

        <WorkspaceStatusBanner failure={failure} />

        {!permissionDenied ? (
          <>
            <form
              className="workspace-filters"
              onSubmit={(event) => {
                event.preventDefault();
                void onCreate();
              }}
              aria-label="Create product draft"
            >
              <label>
                SKU
                <input
                  value={sku}
                  onChange={(event) => setSku(event.target.value)}
                  required
                />
              </label>
              <label>
                Name
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                />
              </label>
              <label>
                Category
                <input
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  required
                />
              </label>
              <button type="submit">Create draft</button>
            </form>

            <div className="workspace-filters" aria-label="Product filters">
              <label>
                Status
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="">All</option>
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
              <label>
                Search
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="SKU or name"
                />
              </label>
            </div>

            {showLoading ? <Spinner label="Loading catalog" /> : null}

            {!showLoading && products.length === 0 ? (
              <WorkspaceEmptyState
                title="No products yet"
                description="Create a draft or import a CSV to populate the catalog."
              />
            ) : null}

            {products.length > 0 ? (
              <table className="workspace-table">
                <caption>Tenant product catalog</caption>
                <thead>
                  <tr>
                    <th scope="col">SKU</th>
                    <th scope="col">Name</th>
                    <th scope="col">Category</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.id}>
                      <td>
                        <Link href={`/app/catalog/products/${product.id}`}>
                          {product.sku}
                        </Link>
                      </td>
                      <td>{product.name}</td>
                      <td>{product.category_code}</td>
                      <td>
                        {product.status}
                        {product.status !== "active" ? (
                          <span className="workspace-inline-warning">
                            {" "}
                            Not customer-visible
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
