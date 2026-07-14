"use client";
/* eslint-disable react-hooks/set-state-in-effect -- detail pages load when route/tenant change */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  catalogApiClient,
  type CatalogProductDetailV1,
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

export function CatalogProductDetailPage() {
  return (
    <ProtectedRoute returnTo="/app/catalog">
      <TenantGate>
        <CatalogProductDetailContent />
      </TenantGate>
    </ProtectedRoute>
  );
}

function CatalogProductDetailContent() {
  const params = useParams<{ id: string }>();
  const productId = params.id;
  const session = useWorkspaceSession();
  const { onLogout, onLogoutAll } = useWorkspaceLogoutHandlers();
  const tenant = useTenant();
  const [detail, setDetail] = useState<CatalogProductDetailV1 | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [variantSku, setVariantSku] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [amountMinor, setAmountMinor] = useState("45000000");
  const [location, setLocation] = useState("almaty");
  const [quantity, setQuantity] = useState("1");
  const permissionDenied = useWorkspaceRoleDenied(CATALOG_ROLES);

  useEffect(() => {
    if (!tenant.tenantId || !productId || permissionDenied) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    void catalogApiClient
      .getProduct(tenant.tenantId, productId)
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (!result.ok) {
          setDetail(null);
          setFailure(result);
          return;
        }
        setDetail(result.data);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tenant.tenantId, productId, permissionDenied]);

  if (!session) {
    return null;
  }
  const activeSession = session;

  async function refresh() {
    if (!tenant.tenantId || !productId) {
      return;
    }
    const result = await catalogApiClient.getProduct(
      tenant.tenantId,
      productId,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    setDetail(result.data);
  }

  async function onAddVariant() {
    if (!tenant.tenantId || !activeSession.csrfToken || !productId) {
      return;
    }
    const result = await catalogApiClient.addVariant(
      tenant.tenantId,
      productId,
      { sku: variantSku, display_name: displayName || variantSku },
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    await refresh();
  }

  async function onSetPrice(variantId: string) {
    if (!tenant.tenantId || !activeSession.csrfToken) {
      return;
    }
    const result = await catalogApiClient.setPrice(
      tenant.tenantId,
      variantId,
      { amount_minor: Number(amountMinor), currency: "KZT" },
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
    }
  }

  async function onSetInventory(variantId: string) {
    if (!tenant.tenantId || !activeSession.csrfToken) {
      return;
    }
    const result = await catalogApiClient.setInventory(
      tenant.tenantId,
      variantId,
      {
        location_code: location,
        available_quantity: Number(quantity),
      },
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
    }
  }

  async function onPublish() {
    if (!tenant.tenantId || !activeSession.csrfToken || !detail) {
      return;
    }
    const result = await catalogApiClient.publishProduct(
      tenant.tenantId,
      detail.product.id,
      detail.product.version,
      activeSession.csrfToken,
    );
    if (!result.ok) {
      setFailure(result);
      return;
    }
    await refresh();
  }

  return (
    <AppShell
      session={activeSession}
      onLogout={onLogout}
      onLogoutAll={onLogoutAll}
    >
      <section
        className="workspace-page"
        aria-labelledby="catalog-product-title"
      >
        <header className="workspace-page__header">
          <div>
            <p className="workspace-page__eyebrow">Catalog</p>
            <h1 id="catalog-product-title">
              {detail?.product.name ?? "Product"}
            </h1>
            <p>SKU {detail?.product.sku ?? "…"}</p>
          </div>
          <Link href="/app/catalog">Back</Link>
        </header>

        {permissionDenied ? (
          <WorkspaceEmptyState
            title="Catalog detail requires owner or sales head"
            description="Use dashboard analytics if you need read-only commercial summaries."
          />
        ) : null}

        <WorkspaceStatusBanner failure={failure} />
        {loading ? <Spinner label="Loading product" /> : null}

        {detail && !permissionDenied ? (
          <>
            <p>
              Status: <strong>{detail.product.status}</strong>
              {detail.product.status !== "active" ? (
                <span className="workspace-inline-warning">
                  {" "}
                  Freshness: not customer-visible until published with usable
                  price and inventory.
                </span>
              ) : null}
            </p>
            <button type="button" onClick={() => void onPublish()}>
              Publish
            </button>

            <h2>Variants</h2>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void onAddVariant();
              }}
              aria-label="Add variant"
            >
              <label>
                Variant SKU
                <input
                  value={variantSku}
                  onChange={(event) => setVariantSku(event.target.value)}
                  required
                />
              </label>
              <label>
                Display name
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </label>
              <button type="submit">Add variant</button>
            </form>

            <label>
              Price (minor units)
              <input
                value={amountMinor}
                onChange={(event) => setAmountMinor(event.target.value)}
              />
            </label>
            <label>
              Location
              <input
                value={location}
                onChange={(event) => setLocation(event.target.value)}
              />
            </label>
            <label>
              Available quantity
              <input
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
            </label>

            <ul>
              {detail.variants.map((variant) => (
                <li key={variant.id}>
                  <strong>{variant.sku}</strong> — {variant.display_name} (
                  {variant.status})
                  <button
                    type="button"
                    onClick={() => void onSetPrice(variant.id)}
                  >
                    Set price
                  </button>
                  <button
                    type="button"
                    onClick={() => void onSetInventory(variant.id)}
                  >
                    Set inventory
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
