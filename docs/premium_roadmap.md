# Premium Roadmap (Diseñado, No Implementado)

Este documento define funcionalidades **premium (pago)** que quedan fuera del core freemium por las reglas del producto.
No hay implementacion en este repo; solo se describen objetivos, riesgos y dependencias.

## Principio de frontera

- Core: reduce riesgo contable y mejora confiabilidad/auditabilidad.
- Premium: ahorra tiempo humano recurrente, automatiza agresivamente, mejora presentacion ejecutiva o consolida clientes.

## Features Premium (Clasificadas)

### 1) Reglas bancarias especificas

- Nombre: `BankSpecificRulePacks`
- Problema: cartolas heterogeneas por banco, columnas/formatos no estandarizados, referencias no canonicas.
- Por que NO core: requiere conocimiento por banco y mantenimiento continuo (IP y ahorro de tiempo).
- Valor percibido: configuracion rapida por banco + menor friccion operacional.
- Riesgos: falsos positivos por reglas mal calibradas; dependencia de layouts; regresiones por cambios de formato.
- Dependencias core: ingestion/normalizacion (modelos y auditoria), motor de matching explicable.

### 2) Heuristicas agresivas de auto-match

- Nombre: `AggressiveAutoMatchRules`
- Problema: reducir pendientes y acelerar cierre de mes con reglas adicionales.
- Por que NO core: optimiza % de autoconciliacion (ahorro de tiempo) y eleva riesgo de falsos positivos.
- Valor percibido: menos revision humana repetitiva.
- Riesgos: conciliaciones incorrectas, perdida de trazabilidad defendible si no se controla.
- Dependencias core: matching engine, umbrales y politicas de confianza, auditoria.

### 3) Batch operativo multi-cliente

- Nombre: `OperationalBatchRunner`
- Problema: ejecutar conciliaciones para multiples empresas/meses en modo operativo.
- Por que NO core: ahorro de tiempo operativo recurrente + riesgo de automatizacion masiva.
- Valor percibido: pipeline de ejecucion repetible y rapido para estudios.
- Riesgos: errores a escala; gestion de credenciales/rutas; aislamiento de fallas.
- Dependencias core: CLI/pipeline; configuraciones por cliente; logs/auditoria.

### 4) Reportes ejecutivos listos para cliente

- Nombre: `ExecutiveReportRenderer`
- Problema: presentacion final, resumenes, PDFs/HTML y "insights" para entregar a cliente.
- Por que NO core: presentacion y "bonito" es premium (no reduce riesgo per se).
- Valor percibido: deliverables profesionales.
- Riesgos: mezclar narrativa con evidencia; ocultar incertidumbre; inconsistencia de numeros.
- Dependencias core: run.json/audit.jsonl; reporte tecnico; modelos.

### 5) Metricas comparativas entre clientes

- Nombre: `CrossClientAnalytics`
- Problema: comparar desempeno/pendientes entre empresas (benchmark).
- Por que NO core: consolidacion multi-cliente y analitica es premium.
- Valor percibido: gestion interna del estudio.
- Riesgos: privacidad; interpretaciones incorrectas; normalizacion inconsistente.
- Dependencias core: formato de outputs, identificadores estables.

### 6) Diff mes-a-mes consolidado

- Nombre: `MonthOverMonthDiff`
- Problema: detectar cambios/reincidencias y explicar variaciones entre meses.
- Por que NO core: ahorro de tiempo de analisis recurrente.
- Valor percibido: control de calidad y rapidez en cierres.
- Riesgos: falsos hallazgos por cambios de layout o reglas; requiere buena identidad de entidades.
- Dependencias core: run_id/fingerprint determinista; auditoria.

