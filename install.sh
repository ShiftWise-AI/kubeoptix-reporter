#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="${CHART_DIR:-${SCRIPT_DIR}/helm/kubeoptix-reporter}"
NAMESPACE="${NAMESPACE:-shiftwise-ai}"
RELEASE_NAME="${RELEASE_NAME:-kubeoptix-reporter}"
TIMEOUT="${TIMEOUT:-10m}"
CLEANUP_ORPHANS="${CLEANUP_ORPHANS:-true}"
PRUNE_HELM_RELEASE_SECRETS="${PRUNE_HELM_RELEASE_SECRETS:-true}"
PRUNE_BUILD_HISTORY="${PRUNE_BUILD_HISTORY:-true}"
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

is_true() {
    case "${1,,}" in
        true|1|yes|y|on)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

is_managed_or_legacy_name() {
    local resource_name="$1"
    local instance_label="$2"

    if [[ "$instance_label" == "$RELEASE_NAME" ]]; then
        return 0
    fi

    [[ "$resource_name" == "$RELEASE_NAME"* ]] && return 0
    [[ "$resource_name" == *kubeoptix-reporter* ]] && return 0
    [[ "$resource_name" == reporter* ]] && return 0

    return 1
}

cleanup_post_install_residue() {
    if ! is_true "$CLEANUP_ORPHANS"; then
        log "Limpeza pós-instalação desabilitada (CLEANUP_ORPHANS=$CLEANUP_ORPHANS)"
        return 0
    fi

    log "Limpando recursos órfãos e não utilizados do release"

    declare -A used_secrets=()
    declare -A used_configmaps=()
    local line=""
    local kind=""
    local name=""

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        kind="${line%%:*}"
        name="${line#*:}"
        [[ -n "$name" && "$name" != "<no value>" ]] || continue

        if [[ "$kind" == "secret" ]]; then
            used_secrets["$name"]=1
        elif [[ "$kind" == "configmap" ]]; then
            used_configmaps["$name"]=1
        fi
    done < <(
        oc get statefulset "$STATEFULSET" -n "$NAMESPACE" -o jsonpath='{range .spec.template.spec.imagePullSecrets[*]}secret:{.name}{"\n"}{end}{range .spec.template.spec.volumes[*]}secret:{.secret.secretName}{"\n"}configmap:{.configMap.name}{"\n"}{range .projected.sources[*]}secret:{.secret.name}{"\n"}configmap:{.configMap.name}{"\n"}{end}{end}{range .spec.template.spec.containers[*].env[*]}secret:{.valueFrom.secretKeyRef.name}{"\n"}configmap:{.valueFrom.configMapKeyRef.name}{"\n"}{end}{range .spec.template.spec.containers[*].envFrom[*]}secret:{.secretRef.name}{"\n"}configmap:{.configMapRef.name}{"\n"}{end}' 2>/dev/null
    )

    if [[ -n "$GITHUB_SECRET" ]]; then
        used_secrets["$GITHUB_SECRET"]=1
    fi

    while IFS= read -r name; do
        [[ -n "$name" ]] || continue
        if [[ -z "${used_secrets[$name]+x}" ]]; then
            log "Removendo Secret não utilizado: $name"
            oc delete secret "$name" -n "$NAMESPACE" --ignore-not-found >/dev/null
        fi
    done < <(
        oc get secret -n "$NAMESPACE" \
            -l "app.kubernetes.io/instance=${RELEASE_NAME},app.kubernetes.io/name=kubeoptix-reporter" \
            -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
    )

    while IFS= read -r name; do
        [[ -n "$name" ]] || continue
        if [[ -z "${used_configmaps[$name]+x}" ]]; then
            log "Removendo ConfigMap não utilizado: $name"
            oc delete configmap "$name" -n "$NAMESPACE" --ignore-not-found >/dev/null
        fi
    done < <(
        oc get configmap -n "$NAMESPACE" \
            -l "app.kubernetes.io/instance=${RELEASE_NAME},app.kubernetes.io/name=kubeoptix-reporter" \
            -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
    )

    local instance_label=""
    local origin_alpha=""
    local origin_beta=""
    local origin_service=""
    local is_used="false"

    for kind in secret configmap; do
        while IFS=$'\t' read -r name instance_label origin_alpha origin_beta; do
            [[ -n "$name" ]] || continue
            origin_service="${origin_alpha:-$origin_beta}"
            [[ -n "$origin_service" && "$origin_service" != "<no value>" ]] || continue

            if ! is_managed_or_legacy_name "$name" "$instance_label"; then
                continue
            fi

            is_used="false"
            if [[ "$kind" == "secret" ]]; then
                [[ -n "${used_secrets[$name]+x}" ]] && is_used="true"
            else
                [[ -n "${used_configmaps[$name]+x}" ]] && is_used="true"
            fi

            if [[ "$is_used" == "true" ]]; then
                continue
            fi

            if ! oc get service "$origin_service" -n "$NAMESPACE" >/dev/null 2>&1; then
                log "Removendo $kind órfão vinculado a serviço inexistente ($origin_service): $name"
                oc delete "$kind" "$name" -n "$NAMESPACE" --ignore-not-found >/dev/null
            else
                log "Removendo $kind de certificado não utilizado na aplicação ($origin_service): $name"
                oc delete "$kind" "$name" -n "$NAMESPACE" --ignore-not-found >/dev/null
            fi
        done < <(
            oc get "$kind" -n "$NAMESPACE" \
                -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.app\.kubernetes\.io/instance}{"\t"}{.metadata.annotations.service\.alpha\.openshift\.io/originating-service-name}{"\t"}{.metadata.annotations.service\.beta\.openshift\.io/originating-service-name}{"\n"}{end}'
        )
    done
}

cleanup_helm_release_secrets() {
    if ! is_true "$PRUNE_HELM_RELEASE_SECRETS"; then
        log "Remoção de secrets do Helm desabilitada (PRUNE_HELM_RELEASE_SECRETS=$PRUNE_HELM_RELEASE_SECRETS)"
        return 0
    fi

    log "Removendo secrets internos do Helm do release"

    local secret_name=""
    while IFS= read -r secret_name; do
        [[ -n "$secret_name" ]] || continue
        log "Removendo secret do Helm: $secret_name"
        oc delete secret "$secret_name" -n "$NAMESPACE" --ignore-not-found >/dev/null
    done < <(
        oc get secret -n "$NAMESPACE" -o jsonpath='{range .items[?(@.type=="helm.sh/release.v1")]}{.metadata.name}{"\n"}{end}' \
            | grep -E "^sh\.helm\.release\.v1\.${RELEASE_NAME}\.v[0-9]+$" || true
    )
}

cleanup_build_history() {
    if ! is_true "$PRUNE_BUILD_HISTORY"; then
        log "Remoção de histórico de builds desabilitada (PRUNE_BUILD_HISTORY=$PRUNE_BUILD_HISTORY)"
        return 0
    fi

    log "Removendo histórico de builds do BuildConfig $BUILD_CONFIG"

    local build_name=""
    while IFS= read -r build_name; do
        [[ -n "$build_name" ]] || continue
        if [[ "$build_name" == "$BUILD_NAME" || "$build_name" == "build/$BUILD_NAME" ]]; then
            continue
        fi
        log "Removendo build antigo: $build_name"
        oc delete "$build_name" -n "$NAMESPACE" --ignore-not-found >/dev/null
    done < <(
        oc get builds -n "$NAMESPACE" -l "buildconfig=${BUILD_CONFIG}" -o name 2>/dev/null || true
    )
}

cleanup_explicit_unused_configmaps() {
    local cm_name="kubeoptix-reporter-1-sys-config"

    if ! oc get configmap "$cm_name" -n "$NAMESPACE" >/dev/null 2>&1; then
        return 0
    fi

    local cm_in_use=""
    cm_in_use="$(oc get statefulset "$STATEFULSET" -n "$NAMESPACE" -o jsonpath='{range .spec.template.spec.volumes[*]}{.configMap.name}{"\n"}{range .projected.sources[*]}{.configMap.name}{"\n"}{end}{end}{range .spec.template.spec.containers[*].env[*]}{.valueFrom.configMapKeyRef.name}{"\n"}{end}{range .spec.template.spec.containers[*].envFrom[*]}{.configMapRef.name}{"\n"}{end}' 2>/dev/null | grep -Fx "$cm_name" || true)"

    if [[ -n "$cm_in_use" ]]; then
        log "ConfigMap $cm_name ainda está em uso pelo StatefulSet; remoção ignorada"
        return 0
    fi

    log "Removendo ConfigMap não utilizado: $cm_name"
    oc delete configmap "$cm_name" -n "$NAMESPACE" --ignore-not-found >/dev/null
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

cleanup_post_install_residue
cleanup_explicit_unused_configmaps
cleanup_build_history
cleanup_helm_release_secrets

SERVICE="$(oc get service \
    -n "$NAMESPACE" \
    -l "app.kubernetes.io/instance=${RELEASE_NAME},app.kubernetes.io/name=kubeoptix-reporter" \
    -o jsonpath='{.items[?(@.spec.clusterIP!="None")].metadata.name}')"

log "Instalação concluída"
printf 'Release:   %s\nNamespace: %s\nService:   %s:8000\nHealth:    /health\n' \
    "$RELEASE_NAME" "$NAMESPACE" "$SERVICE"