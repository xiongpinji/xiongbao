import { api } from "./client";

export interface SkillPackageManifestFile {
  path: string;
  size: number;
  sha256: string;
}

export interface SkillPackageView {
  package_id: string;
  skill_id: string;
  name: string;
  version: string;
  content_hash: string;
  manifest: { files: SkillPackageManifestFile[] };
  source: string;
  file_count: number;
  total_size: number;
  imported_at: string;
}

export const listSkillPackages = () =>
  api
    .get<{ packages: SkillPackageView[]; total: number }>("/skill-packages")
    .then((response) => response.data.packages);

export const importSkillPackage = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api
    .post<{ imported: boolean; package: SkillPackageView }>(
      "/skill-packages/import",
      form,
    )
    .then((response) => response.data);
};

export const shortSkillPackageHash = (contentHash: string) =>
  contentHash.length > 16 ? `${contentHash.slice(0, 16)}…` : contentHash;

export const skillPackageFilePaths = (manifest: SkillPackageView["manifest"]) =>
  manifest.files.map((file) => file.path);
