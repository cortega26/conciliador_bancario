# Premium Roadmap (Diseñado, No Implementado)

Este documento define funcionalidades **premium (pago)** que quedan fuera del core freemium por las reglas del producto.
No hay implementación en este repo; solo se describen objetivos, riesgos y dependencias.

## Principio de frontera

- Core: reduce riesgo contable y mejora confiabilidad/auditabilidad.
- Premium: ahorra tiempo humano recurrente, automatiza agresivamente, mejora presentación ejecutiva o consolida clientes.

## Features Premium (Clasificadas)

### 1) Reglas bancarias especificas

- Nombre: `BankSpecificRulePacks`
- Problema: cartolas heterogéneas por banco, columnas/formatos no estandarizados, referencias no canónicas.
- Por qué NO core: requiere conocimiento por banco y mantenimiento continuo (IP y ahorro de tiempo).
- Valor percibido: configuración rápida por banco + menor fricción operacional.
- Riesgos: falsos positivos por reglas mal calibradas; dependencia de layouts; regresiones por cambios de formato.
- Dependencias core: ingestion/normalización (modelos y auditoría), motor de matching explicable.

### 2) Heuristicas agresivas de auto-match

- Nombre: `AggressiveAutoMatchRules`
- Problema: reducir pendientes y acelerar cierre de mes con reglas adicionales.
- Por qué NO core: optimiza % de autoconciliación (ahorro de tiempo) y eleva riesgo de falsos positivos.
- Valor percibido: menos revisión humana repetitiva.
- Riesgos: conciliaciones incorrectas, pérdida de trazabilidad defendible si no se controla.
- Dependencias core: matching engine, umbrales y políticas de confianza, auditoría.

### 3) Batch operativo multi-cliente

- Nombre: `OperationalBatchRunner`
- Problema: ejecutar conciliaciones para múltiples empresas/meses en modo operativo.
- Por qué NO core: ahorro de tiempo operativo recurrente + riesgo de automatización masiva.
- Valor percibido: pipeline de ejecución repetible y rápido para estudios.
- Riesgos: errores a escala; gestión de credenciales/rutas; aislamiento de fallas.
- Dependencias core: CLI/pipeline; configuraciones por cliente; logs/auditoría.

### 4) Reportes ejecutivos listos para cliente

- Nombre: `ExecutiveReportRenderer`
- Problema: presentación final, resúmenes, PDFs/HTML y "insights" para entregar a cliente.
- Por qué NO core: presentación y "bonito" es premium (no reduce riesgo per se).
- Valor percibido: deliverables profesionales.
- Riesgos: mezclar narrativa con evidencia; ocultar incertidumbre; inconsistencia de números.
- Dependencias core: run.json/audit.jsonl; reporte técnico; modelos.

### 5) Metricas comparativas entre clientes

- Nombre: `CrossClientAnalytics`
- Problema: comparar desempeño/pendientes entre empresas (benchmark).
- Por qué NO core: consolidación multi-cliente y analítica es premium.
- Valor percibido: gestión interna del estudio.
- Riesgos: privacidad; interpretaciones incorrectas; normalización inconsistente.
- Dependencias core: formato de outputs, identificadores estables.

### 6) Diff mes-a-mes consolidado

- Nombre: `MonthOverMonthDiff`
- Problema: detectar cambios/reincidencias y explicar variaciones entre meses.
- Por qué NO core: ahorro de tiempo de análisis recurrente.
- Valor percibido: control de calidad y rapidez en cierres.
- Riesgos: falsos hallazgos por cambios de layout o reglas; requiere buena identidad de entidades.
- Dependencias core: run_id/fingerprint determinista; auditoría.

### 7) Resolución asistida de split/merge (pagos parciales y agrupados)

- Nombre: `SplitMergeResolutionAssistant`
- Problema: la realidad operacional genera casos N↔1 (una factura pagada en múltiples transferencias; múltiples facturas pagadas en una sola transferencia), además de neteos por comisiones/retenciones.
- Por qué NO core: es ahorro de tiempo recurrente y tiende a requerir heurísticas por banco/ERP y flujos de revisión (zona premium).
- Valor percibido: reduce pendientes repetitivos sin "adivinar"; propone agrupaciones y requiere confirmación humana.
- Riesgos: false positives si se automatiza; complejidad de UX; requiere trazabilidad de por qué se sugiere un grupo/split.
- Dependencias core: run.json/audit.jsonl explicables; identidad estable de transacciones; políticas fail-closed.
