export type TenantPublicProfile = {
  name: string;
  phone: string;
  address: string;
  tema_cor: string;
  slug: string;
};

const prefix = "eclat:tenant-public:";

export function cacheTenantPublicProfile(profile: TenantPublicProfile) {
  try {
    localStorage.setItem(`${prefix}${profile.slug}`, JSON.stringify(profile));
  } catch {
    /* ignore quota */
  }
}

export function readTenantPublicProfile(slug: string): TenantPublicProfile | null {
  try {
    const raw = localStorage.getItem(`${prefix}${slug}`);
    if (!raw) return null;
    return JSON.parse(raw) as TenantPublicProfile;
  } catch {
    return null;
  }
}

export function slugToDisplayName(slug: string) {
  return slug
    .split("-")
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
