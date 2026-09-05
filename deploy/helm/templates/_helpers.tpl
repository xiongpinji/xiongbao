{{/*
Expand the name of the chart.
*/}}
{{- define "xagent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Render an immutable digest when supplied, otherwise the explicit release tag.
*/}}
{{- define "xagent.image" -}}
{{- if .digest -}}
{{ printf "%s@%s" .repository .digest }}
{{- else -}}
{{ printf "%s:%s" .repository .tag }}
{{- end -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "xagent.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "xagent.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "xagent.labels" -}}
helm.sh/chart: {{ include "xagent.chart" . }}
{{ include "xagent.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "xagent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "xagent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API selector labels
*/}}
{{- define "xagent.apiSelectorLabels" -}}
app.kubernetes.io/name: {{ include "xagent.name" . }}-api
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "xagent.workerSelectorLabels" -}}
app.kubernetes.io/name: {{ include "xagent.name" . }}-worker
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Web selector labels
*/}}
{{- define "xagent.webSelectorLabels" -}}
app.kubernetes.io/name: {{ include "xagent.name" . }}-web
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "xagent.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "xagent.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Namespace to use
*/}}
{{- define "xagent.namespace" -}}
{{- if .Values.namespace.create }}
{{- default (include "xagent.fullname" .) .Values.namespace.name }}
{{- else }}
{{- .Release.Namespace }}
{{- end }}
{{- end }}

{{/*
Chart 管理的 Secret 名称（非 ESO、非 existingSecretRef 时用于承载 values 注入的 secret）
*/}}
{{- define "xagent.secretName" -}}
{{- printf "%s-secret" (include "xagent.fullname" .) }}
{{- end }}

{{/*
持密环境变量注入（api / worker 共用）。
每项优先级：ESO ExternalSecret > existingSecretRef > chart 管理 Secret（values 有值时）> 省略。
省略时应用回退到自身默认值（仅 lite/dev 可接受）；prod 必须走前三种之一。
*/}}
{{- define "xagent.secretEnvVars" -}}
{{- $esoName := printf "%s-eso" (include "xagent.fullname" .) -}}
{{- if .Values.secrets.eso.enabled }}
- name: XAGENT_SECURITY__JWT_SECRET
  valueFrom:
    secretKeyRef: { name: {{ $esoName | quote }}, key: jwt-secret }
- name: XAGENT_LLM__PROXY_API_KEY
  valueFrom:
    secretKeyRef: { name: {{ $esoName | quote }}, key: proxy-api-key }
- name: LANGFUSE_PUBLIC_KEY
  valueFrom:
    secretKeyRef: { name: {{ $esoName | quote }}, key: langfuse-public-key }
- name: LANGFUSE_SECRET_KEY
  valueFrom:
    secretKeyRef: { name: {{ $esoName | quote }}, key: langfuse-secret-key }
{{- else }}
{{- if .Values.security.existingJwtSecretRef.name }}
- name: XAGENT_SECURITY__JWT_SECRET
  valueFrom:
    secretKeyRef: { name: {{ .Values.security.existingJwtSecretRef.name | quote }}, key: {{ .Values.security.existingJwtSecretRef.key | quote }} }
{{- else if .Values.security.jwtSecret }}
- name: XAGENT_SECURITY__JWT_SECRET
  valueFrom:
    secretKeyRef: { name: {{ include "xagent.secretName" . | quote }}, key: jwt-secret }
{{- end }}
{{- if .Values.llm.existingProxyApiKeySecretRef.name }}
- name: XAGENT_LLM__PROXY_API_KEY
  valueFrom:
    secretKeyRef: { name: {{ .Values.llm.existingProxyApiKeySecretRef.name | quote }}, key: {{ .Values.llm.existingProxyApiKeySecretRef.key | quote }} }
{{- else if .Values.llm.proxyApiKey }}
- name: XAGENT_LLM__PROXY_API_KEY
  valueFrom:
    secretKeyRef: { name: {{ include "xagent.secretName" . | quote }}, key: proxy-api-key }
{{- end }}
{{- if .Values.observability.existingLangfuseSecretRef.name }}
- name: LANGFUSE_PUBLIC_KEY
  valueFrom:
    secretKeyRef: { name: {{ .Values.observability.existingLangfuseSecretRef.name | quote }}, key: {{ .Values.observability.existingLangfuseSecretRef.publicKeyKey | quote }} }
- name: LANGFUSE_SECRET_KEY
  valueFrom:
    secretKeyRef: { name: {{ .Values.observability.existingLangfuseSecretRef.name | quote }}, key: {{ .Values.observability.existingLangfuseSecretRef.secretKeyKey | quote }} }
{{- else if or .Values.observability.langfusePublicKey .Values.observability.langfuseSecretKey }}
- name: LANGFUSE_PUBLIC_KEY
  valueFrom:
    secretKeyRef: { name: {{ include "xagent.secretName" . | quote }}, key: langfuse-public-key }
- name: LANGFUSE_SECRET_KEY
  valueFrom:
    secretKeyRef: { name: {{ include "xagent.secretName" . | quote }}, key: langfuse-secret-key }
{{- end }}
{{- end }}
{{- end }}

{{/*
postgres 密码的 secretKeyRef（三处一致）：ESO > existingSecretRef > chart 管理 Secret。
*/}}
{{- define "xagent.postgresPasswordSecretRef" -}}
{{- if .Values.secrets.eso.enabled }}
name: {{ printf "%s-eso" (include "xagent.fullname" .) | quote }}
key: db-password
{{- else if .Values.postgres.existingSecretRef.name }}
name: {{ .Values.postgres.existingSecretRef.name | quote }}
key: {{ .Values.postgres.existingSecretRef.key | quote }}
{{- else }}
name: {{ include "xagent.secretName" . | quote }}
key: postgres-password
{{- end }}
{{- end }}

{{/*
内置依赖（postgres / redis / qdrant）启用且未给外部 url 时，注入指向内置 Service 的连接串。
postgres 密码经 $(XAGENT_POSTGRES_PASSWORD) 延迟展开，明文不进入 ConfigMap / Deployment。
*/}}
{{- define "xagent.dependencyEnvVars" -}}
{{- if and .Values.postgres.enabled (not .Values.postgres.url) }}
- name: XAGENT_POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      {{- include "xagent.postgresPasswordSecretRef" . | nindent 6 }}
- name: XAGENT_DB__URL
  value: "postgresql+asyncpg://xagent:$(XAGENT_POSTGRES_PASSWORD)@{{ include "xagent.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}"
{{- end }}
{{- if and .Values.redis.enabled (not .Values.redis.url) }}
- name: XAGENT_CACHE__REDIS_URL
  value: "redis://{{ include "xagent.fullname" . }}-redis:6379/0"
{{- end }}
{{- if and .Values.qdrant.enabled (not .Values.qdrant.url) }}
- name: XAGENT_MEMORY__QDRANT_URL
  value: "http://{{ include "xagent.fullname" . }}-qdrant:6333"
{{- end }}
{{- end }}
