import {
  shortSkillPackageHash,
  skillPackageFilePaths,
} from "../api/skillPackages";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("skill package presentation", () => {
  it("shows a stable short SHA-256 without changing the stored hash", () => {
    const hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    assert(shortSkillPackageHash(hash) === "0123456789abcdef…", "Hash preview drifted");
    assert(hash.length === 64, "Source hash must remain complete");
  });

  it("preserves every manifest path including scripts and references", () => {
    const paths = skillPackageFilePaths({
      files: [
        { path: "SKILL.md", size: 10, sha256: "a" },
        { path: "references/guide.md", size: 20, sha256: "b" },
        { path: "scripts/check.py", size: 30, sha256: "c" },
        { path: "assets/template.txt", size: 40, sha256: "d" },
      ],
    });
    assert(
      paths.join(",") ===
        "SKILL.md,references/guide.md,scripts/check.py,assets/template.txt",
      "Manifest paths were not preserved",
    );
  });
});
