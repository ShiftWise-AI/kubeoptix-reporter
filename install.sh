#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="${CHART_DIR:-${SCRIPT_DIR}/helm/kubeoptix-reporter}"
NAMESPACE="${NAMESPACE:-shiftwise-ai}"
RELEASE_NAME="${RELEASE_NAME:-kubeoptix-reporter}"
TIMEOUT="${TIMEOUT:-10m}"
VALUES_FILE=""
HELM_ARGS=()

log() {
    printf '[install] %s\n' "$*"
}

fail() {
    printf '[install] ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Comando obrigatório não encontrado: $1"
}

usage() {
    cat <<EOF
Uso: $(basename "$0") -f <values.yaml> [-- <argumentos adicionais do Helm>]

Opções:
  -f, --values ARQUIVO  Arquivo de valores usado no lint e na instalação
  -h, --help            Exibe esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--values)
            [[ $# -ge 2 ]] || fail "A opção '$1' exige um arquivo"
            VALUES_FILE="$2"
            shift 2
            ;;
        --)
            shift
            HELM_ARGS=("$@")
            break
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Opção desconhecida: $1. Use -- antes de argumentos adicionais do Helm"
            ;;
    esac
done

[[ -n "$VALUES_FILE" ]] || fail "Informe o arquivo de valores com -f <values.yaml>"
[[ -f "$VALUES_FILE" ]] || fail "Arquivo de valores não encontrado: $VALUES_FILE"

require_command oc
require_command helm

[[ -d "$CHART_DIR" ]] || fail "Chart Helm não encontrado: $CHART_DIR"

log "Validando acesso ao OpenShift"
oc whoami >/dev/null 2>&1 || fail "Faça login no OpenShift com 'oc login' antes de instalar"

if ! oc get namespace "$NAMESPACE" >/dev/null 2>&1; then
    log "Criando namespace $NAMESPACE"
    oc create namespace "$NAMESPACE" >/dev/null
fi

log "Validando chart Helm com $VALUES_FILE"
helm lint "$CHART_DIR" -f "$VALUES_FILE"

IS_UPDATE=false
if helm status "$RELEASE_NAME" --namespace "$NAMESPACE" >/dev/null 2>&1; then
    IS_UPDATE=true
    log "Atualizando release $RELEASE_NAME no namespace $NAMESPACE"
    HELM_UPGRADE_ARGS=()
    if helm upgrade --help | grep -q -- '--force-conflicts'; then
        HELM_UPGRADE_ARGS+=(--force-conflicts)
    fi
    helm upgrade "$RELEASE_NAME" "$CHART_DIR" \
        --namespace "$NAMESPACE" \
        -f "$VALUES_FILE" \
        "${HELM_UPGRADE_ARGS[@]}" \
        "${HELM_ARGS[@]}"
else
    log "Instalando release $RELEASE_NAME no namespace $NAMESPACE"
    helm install "$RELEASE_NAME" "$CHART_DIR" \
        --namespace "$NAMESPACE" \
        -f "$VALUES_FILE" \
        "${HELM_ARGS[@]}"
fi

BUILD_CONFIG="kubeoptix-reporter"

oc get buildconfig "$BUILD_CONFIG" -n "$NAMESPACE" >/dev/null 2>&1 \
    || fail "BuildConfig '$BUILD_CONFIG' não encontrado"

STATEFULSET="$(oc get statefulset \
    -n "$NAMESPACE" \
    -l "app.kubernetes.io/instance=${RELEASE_NAME},app.kubernetes.io/name=kubeoptix-reporter" \
    -o jsonpath='{.items[0].metadata.name}')"

[[ -n "$STATEFULSET" ]] || fail "StatefulSet do release não encontrado"

PVC_NAME="$(oc get statefulset "$STATEFULSET" \
    -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.volumes[?(@.persistentVolumeClaim)].persistentVolumeClaim.claimName}')"
GITHUB_SECRET="$(oc get buildconfig "$BUILD_CONFIG" \
    -n "$NAMESPACE" \
    -o jsonpath='{.spec.source.sourceSecret.name}')"

if [[ -n "$PVC_NAME" ]]; then
    oc get persistentvolumeclaim "$PVC_NAME" -n "$NAMESPACE" >/dev/null 2>&1 \
        || fail "PVC '$PVC_NAME' definido em '$VALUES_FILE' não encontrado no namespace '$NAMESPACE'"
else
    log "Persistência desabilitada; validação de PVC ignorada"
fi

oc get secret "$GITHUB_SECRET" -n "$NAMESPACE" >/dev/null 2>&1 \
    || fail "Secret '$GITHUB_SECRET' definido em '$VALUES_FILE' não encontrado no namespace '$NAMESPACE'"

if [[ "$IS_UPDATE" == true ]]; then
    log "Iniciando novo build $BUILD_CONFIG para a atualização"
    BUILD_NAME="$(oc start-build "$BUILD_CONFIG" -n "$NAMESPACE" -o name)"
else
    BUILD_NAME="$(oc get builds \
        -n "$NAMESPACE" \
        -l "buildconfig=${BUILD_CONFIG}" \
        --sort-by=.metadata.creationTimestamp \
        -o name | tail -n 1)"

    if [[ -z "$BUILD_NAME" ]]; then
        log "Iniciando build $BUILD_CONFIG"
        BUILD_NAME="$(oc start-build "$BUILD_CONFIG" -n "$NAMESPACE" -o name)"
    else
        log "Acompanhando build disparado pelo BuildConfig: $BUILD_NAME"
    fi
fi

oc logs -n "$NAMESPACE" -f "$BUILD_NAME"

log "Aguardando conclusão do build $BUILD_NAME"
oc wait -n "$NAMESPACE" \
    --for=jsonpath='{.status.phase}'=Complete \
    "$BUILD_NAME" \
    --timeout="$TIMEOUT" \
    || true

BUILD_PHASE="$(oc get "$BUILD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.phase}')"
[[ "$BUILD_PHASE" == "Complete" ]] \
    || fail "Build '$BUILD_NAME' terminou com status '$BUILD_PHASE'"

log "Reiniciando StatefulSet $STATEFULSET com a imagem atualizada"
oc rollout restart "statefulset/$STATEFULSET" -n "$NAMESPACE"

log "Aguardando StatefulSet $STATEFULSET"
oc rollout status "statefulset/$STATEFULSET" -n "$NAMESPACE" --timeout="$TIMEOUT"

SERVICE="$(oc get service \
    -n "$NAMESPACE" \
    -l "app.kubernetes.io/instance=${RELEASE_NAME},app.kubernetes.io/name=kubeoptix-reporter" \
    -o jsonpath='{.items[?(@.spec.clusterIP!="None")].metadata.name}')"

log "Instalação concluída"
printf 'Release:   %s\nNamespace: %s\nService:   %s:8000\nHealth:    /health\n' \
    "$RELEASE_NAME" "$NAMESPACE" "$SERVICE"