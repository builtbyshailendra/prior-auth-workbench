#!/usr/bin/env bash
# Deploy one release to the cluster kubectl points at. A release is an image tag.
# If the new pods aren't ready in time, every Deployment the release changed is rolled
# back to the version before it, and the script exits with an error.
#
#   deploy/scripts/deploy.sh <tag>
#
# Optional: REGISTRY (default ghcr.io/builtbyshailendra), TIMEOUT (default 120s).
set -euo pipefail

tag=${1:?usage: deploy/scripts/deploy.sh <image tag>}
registry=${REGISTRY:-ghcr.io/builtbyshailendra}
timeout=${TIMEOUT:-120s}
ns=priorauth
deployments=(workflow worker web)
root=$(cd "$(dirname "$0")/.." && pwd)

revision() {
  kubectl -n "$ns" get deployment "$1" \
    -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}' 2>/dev/null || true
}

random() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

# 1. The namespace, and secrets generated on the first deploy. They live only in a
#    Kubernetes Secret, never in a file or this repo.
kubectl apply -f "$root/k8s/base/namespace.yaml"
if ! kubectl -n "$ns" get secret priorauth-secrets >/dev/null 2>&1; then
  password=$(random)
  kubectl -n "$ns" create secret generic priorauth-secrets \
    --from-literal=password="$password" \
    --from-literal=database-url="postgresql+psycopg://postgres:$password@postgres:5432/priorauth" \
    --from-literal=session-secret="$(random)$(random)" \
    --from-literal=connector-token="$(random)" \
    --from-literal=extractor-token="$(random)" \
    --from-literal=demo-password="$(random)"
fi

# 2. Point the manifests at this release's images, and apply them.
declare -A before
for d in "${deployments[@]}"; do before[$d]=$(revision "$d"); done

release="$root/k8s/.release"
rm -rf "$release"
mkdir -p "$release"
trap 'rm -rf "$release"' EXIT
cat > "$release/kustomization.yaml" <<YAML
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../kind
images:
  - name: priorauth-workflow
    newName: $registry/priorauth-workflow
    newTag: "$tag"
  - name: priorauth-web
    newName: $registry/priorauth-web
    newTag: "$tag"
patches:
  # Shows up as CHANGE-CAUSE in "kubectl rollout history".
  - target:
      kind: Deployment
    patch: |
      - op: add
        path: /metadata/annotations
        value:
          kubernetes.io/change-cause: release $tag
YAML
kubectl apply -k "$release"

# 3. Wait. Old pods keep serving until new ones are ready (maxUnavailable: 0).
kubectl -n "$ns" rollout status statefulset/postgres --timeout="$timeout"
failed=()
for d in "${deployments[@]}"; do
  kubectl -n "$ns" rollout status "deployment/$d" --timeout="$timeout" || failed+=("$d")
done
if [ ${#failed[@]} -eq 0 ]; then
  echo "Release $tag is live."
  exit 0
fi

# 4. Roll back the whole release, not just the part that failed, so every part stays
#    on the same version.
echo "Release $tag didn't become ready (${failed[*]}). Rolling back." >&2
kubectl -n "$ns" get pods >&2
for d in "${deployments[@]}"; do
  if [ -n "${before[$d]}" ] && [ "${before[$d]}" != "$(revision "$d")" ]; then
    kubectl -n "$ns" rollout undo "deployment/$d"
  fi
done
for d in "${deployments[@]}"; do
  kubectl -n "$ns" rollout status "deployment/$d" --timeout="$timeout"
done
echo "Rolled back. The release before $tag is still serving." >&2
exit 1
