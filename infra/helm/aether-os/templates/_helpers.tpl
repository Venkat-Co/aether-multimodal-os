{{- define "aether.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aether.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "aether.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aether.labels" -}}
app.kubernetes.io/name: {{ include "aether.name" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "aether.serviceAccountName" -}}
{{- printf "%s-sa" (include "aether.fullname" .) -}}
{{- end -}}

