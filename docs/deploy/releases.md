# Releases & supply chain

Roadmap **E01-04**, ADR-0014, MASTER_PROMPT §19. Companion:
`docs/deploy/environments.md` (image refs per environment),
`docs/runbooks/rolling-update.md` (how a digest reaches the nodes).

## What a release is

A release is a **git tag** `vMAJOR.MINOR.PATCH`. Pushing it runs
`.github/workflows/release.yml`, which for every production image:

1. builds it from the pinned Dockerfile, tagged **by semver and by the full git
   SHA** — never `latest`;
2. pushes it to `ghcr.io/itsh-neumeier/<image>`;
3. generates an SBOM (Syft, SPDX JSON);
4. **signs** the image and **attests** the SBOM with cosign, keyless — the
   signing identity is this workflow running on this tag (GitHub OIDC, no
   long-lived key);
5. scans the built image (Trivy, CRITICAL/HIGH, fail on a fixable finding);
6. publishes a GitHub Release carrying the SBOM and the digest to deploy.

Images in scope today: **`bbz-api`**. `bbz-web` joins the matrix once `apps/web`
ships a Dockerfile + committed lockfile (E01-06 / Epic 07); `cucm-cti-gateway`
is E24-01. Adding one is a new `matrix.include` entry.

## Cutting a release

```sh
git switch main && git pull --ff-only
git tag -a v1.4.0 -m "v1.4.0"
git push origin v1.4.0
```

Watch the **Release** workflow. Its job summary prints, per image:

| field | example |
|---|---|
| semver | `1.4.0` |
| sha tag | `9f8e7d6…` |
| digest | `sha256:…` |
| deploy ref | `ghcr.io/itsh-neumeier/bbz-api@sha256:…` |

A bad tag (`v1.4`, `1.4.0`, `v1.4.0-rc1`) fails the first step on purpose — the
version must be exactly `vMAJOR.MINOR.PATCH`, no pre-release suffix.

**Dry run** (the E01-04 acceptance step): push a real low version tag such as
`v0.1.0` from a scratch branch, let the workflow run, then
`cosign verify` the published digest by hand. Clean up afterwards — delete the
GitHub Release, the git tag, and the GHCR package version.

## Verifying before deploy

Deployments consume the **digest** only — `tools/rolling-update.sh` refuses any
ref that is not `…@sha256:…`. Verify it first:

```sh
REF=ghcr.io/itsh-neumeier/bbz-api@sha256:<digest>
IDENTITY='^https://github\.com/itsh-neumeier/bbz-platform/\.github/workflows/release\.yml@refs/tags/v'
ISSUER=https://token.actions.githubusercontent.com

cosign verify "$REF" \
  --certificate-oidc-issuer "$ISSUER" \
  --certificate-identity-regexp "$IDENTITY"

cosign verify-attestation "$REF" --type spdxjson \
  --certificate-oidc-issuer "$ISSUER" \
  --certificate-identity-regexp "$IDENTITY"
```

Both must succeed. The workflow runs exactly these two checks after signing, so a
release that publishes has already proven it verifies. Enforcing the check **at
deploy time** on the nodes is E23-12 / E24-01.

## Rotation & revocation

Keyless signatures are logged in the public Rekor transparency log; there is no
key to rotate. To pull a bad release: delete the GHCR package version and the
GitHub Release, and make sure no node's `.env` pins that digest
(`docs/runbooks/rollback.md`).
