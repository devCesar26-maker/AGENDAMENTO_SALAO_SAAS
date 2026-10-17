import { useParams } from "react-router-dom";

const APP_SUBDOMAINS = new Set(["app", "www"]);

export function tenantSlugForHostname(hostname: string): string | null {
  const host = hostname.toLowerCase().split(":")[0];
  const parts = host.split(".");
  if (parts.length < 3 || parts[0] === "localhost") return null;
  const subdomain = parts[0];
  return APP_SUBDOMAINS.has(subdomain) ? null : subdomain;
}

export function useTenantSlug(): string | undefined {
  const { slug } = useParams<{ slug: string }>();
  return slug ?? tenantSlugForHostname(window.location.hostname) ?? undefined;
}
