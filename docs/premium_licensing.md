# Premium Licensing & Distribution (Diseñado, No Implementado)

## Estado actual

- Este repo (core) está bajo licencia MIT (ver `LICENSE`).

## Objetivo

- Mantener el core OSS (MIT) completo y usable.
- Distribuir premium bajo licencia comercial propietaria, sin exponer IP.

## Opciones de distribución premium (propuesta)

1) Wheel privado (recomendado)
- Distribución: Artifactory, GitHub Packages, feed privado, etc.
- Ventajas: integración limpia con entry points; versionado semver; instalación reproducible.
- Riesgos: gestión de credenciales y supply chain.

2) ZIP firmado
- Distribución: canal controlado (entrega directa).
- Ventajas: control fuerte de artefactos.
- Riesgos: instalación menos estándar; actualizaciones manuales.

3) Repo privado (monorepo o submódulo)
- Distribución: git + CI/CD.
- Ventajas: desarrollo controlado.
- Riesgos: operaciones más complejas en ambientes de clientes.

## Separación legal/técnica (propuesta)

- Premium depende del core.
- El core no depende de premium.
- El core no incluye:
  - reglas por banco,
  - heurísticas agresivas,
  - presentación ejecutiva,
  - batch operativo.

## Compliance (propuesta)

- Versionar plugins con metadatos claros (vendor, version, compatibilidad).
- Registrar en auditoría técnica cuando premium esté activo (sin exponer secretos).
