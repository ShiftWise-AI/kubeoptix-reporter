{{- define "kubeoptix-reporter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kubeoptix-reporter.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "kubeoptix-reporter.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "kubeoptix-reporter.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
app.kubernetes.io/name: {{ include "kubeoptix-reporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "kubeoptix-reporter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeoptix-reporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "kubeoptix-reporter.image" -}}
{{- printf "image-registry.openshift-image-registry.svc:5000/%s/%s:%s" .Release.Namespace (include "kubeoptix-reporter.fullname" .) .Values.image.tag }}
{{- end }}
