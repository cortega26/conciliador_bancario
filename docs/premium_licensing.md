# Premium Licensing & Distribution (Diseñado, No Implementado)

## Estado actual

- Este repo (core) esta bajo licencia MIT (ver `LICENSE`).

## Objetivo

- Mantener el core OSS (MIT) completo y usable.
- Distribuir premium bajo licencia comercial propietaria, sin exponer IP.

## Opciones de distribucion premium (propuesta)

1) Wheel privado (recomendado)
- Distribucion: Artifactory, GitHub Packages, feed privado, etc.
- Ventajas: integracion limpia con entry points; versionado semver; instalacion reproducible.
- Riesgos: gestion de credenciales y supply chain.

2) ZIP firmado
- Distribucion: canal controlado (entrega directa).
- Ventajas: control fuerte de artefactos.
- Riesgos: instalacion menos estandar; actualizaciones manuales.

3) Repo privado (monorepo o submodulo)
- Distribucion: git + CI/CD.
- Ventajas: desarrollo controlado.
- Riesgos: operaciones mas complejas en ambientes de clientes.

## Separacion legal/tecnica (propuesta)

- Premium depende del core.
- El core no depende de premium.
- El core no incluye:
  - reglas por banco,
  - heuristicas agresivas,
  - presentacion ejecutiva,
  - batch operativo.

## Compliance (propuesta)

- Versionar plugins con metadatos claros (vendor, version, compatibilidad).
- Registrar en auditoria tecnica cuando premium este activo (sin exponer secretos).

