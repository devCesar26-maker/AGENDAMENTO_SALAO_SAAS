import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { applyAccentColor } from "../lib/theme";
import {
  cacheTenantPublicProfile,
  readTenantPublicProfile,
  slugToDisplayName,
  type TenantPublicProfile,
} from "../lib/tenant-public-cache";

export function usePublicTenantBranding(slug: string | null | undefined) {
  const cached = useMemo(() => (slug ? readTenantPublicProfile(slug) : null), [slug]);

  const catalogProbe = useQuery({
    queryKey: ["public-catalog-probe", slug],
    enabled: !!slug,
    queryFn: async () => {
      await api.get("/public/catalog/", { headers: { "X-Tenant-Slug": slug ?? "" } });
      return true;
    },
    retry: false,
  });

  const profile: TenantPublicProfile | null = useMemo(() => {
    if (!slug) return null;
    if (cached) return cached;
    return {
      slug,
      name: slugToDisplayName(slug),
      phone: "",
      address: "",
      tema_cor: "#6366f1",
    };
  }, [cached, slug]);

  useEffect(() => {
    if (profile?.tema_cor) applyAccentColor(profile.tema_cor);
  }, [profile?.tema_cor]);

  return {
    profile,
    catalogReady: catalogProbe.isSuccess,
    catalogLoading: catalogProbe.isLoading,
    catalogError: catalogProbe.isError,
  };
}

export function syncTenantPublicCacheFromOrg(org: {
  slug: string;
  name: string;
  phone: string;
  address: string;
  tema_cor: string;
}) {
  cacheTenantPublicProfile({
    slug: org.slug,
    name: org.name,
    phone: org.phone,
    address: org.address,
    tema_cor: org.tema_cor,
  });
}
