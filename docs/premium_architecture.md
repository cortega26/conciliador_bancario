# Premium Architecture (Diseñado, No Implementado)

Objetivo: permitir que capacidades premium vivan como plugins privados (wheel/zip/repo privado) sin que el core:

- dependa de implementaciones premium,
- falle si no hay premium,
- exponga IP (heurísticas por banco, automatizaciones, presentación ejecutiva).

## 1) Descubrimiento de plugins (propuesta)

Usar entry points de Python (packaging), por ejemplo:

- Grupo: `conciliador_bancario.premium`
- Cada entry point retorna un objeto que implementa `PremiumPlugin` (ver `src/conciliador_bancario/core/premium_contracts/`).

Ejemplo (diseño):

```toml
[project.entry-points."conciliador_bancario.premium"]
"vendor_pack" = "vendor_pkg.plugin:plugin"
```

Nota: este repo no implementa el loader. Solo define el contrato.

## 2) Activación (propuesta)

- Flags CLI (diseño): `--enable-premium`, `--premium-plugin vendor_pack`
- Config por cliente (diseño): `premium: { enabled: true, plugins: ["vendor_pack"] }`

Regla: si premium no está habilitado, el core no debe intentar cargar nada.

## 3) Aislamiento y manejo de errores (propuesta)

El core debe tratar premium como opcional y potencialmente fallido:

- Fallas al cargar plugin:
  - no deben romper el core por defecto,
  - deben registrarse como hallazgos/auditoría técnica (tipo "sistema").
- Fallas dentro de plugin:
  - no deben ocultarse,
  - deben quedar auditadas,
  - deben degradar a comportamiento core (fail-closed).

## 4) Versionado y compatibilidad (propuesta)

Cada plugin declara:

- `name`, `version`, `vendor`
- `min_core_version` (o rango)

El core valida compatibilidad antes de activar capacidades premium.

## 5) Superficie de extension (propuesta)

Capacidades premium posibles, todas opcionales:

- `BankRuleProvider`: reglas por banco y normalización específica.
- `ExecutiveReportRenderer`: reportes ejecutivos.
- `OperationalBatchRunner`: batch operativo multi-cliente.

El core solo consume estas interfaces si:

1. premium esta habilitado,
2. un plugin compatible fue cargado,
3. la capacidad existe.
