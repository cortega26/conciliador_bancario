# Changelog

Este proyecto sigue (en lo posible) **Keep a Changelog** y **SemVer**.

## [0.5.0](https://github.com/cortega26/conciliador_bancario/compare/v0.4.0...v0.5.0) (2026-10-01)


### Features

* Add boundary checks and secret scanning tools for repository safety ([2f1c640](https://github.com/cortega26/conciliador_bancario/commit/2f1c6405620db4f211c8f23b041f544bb568438b))
* **cli:** bajar el umbral de confianza ya no es un acto invisible ([3f9a743](https://github.com/cortega26/conciliador_bancario/commit/3f9a743f512cdab2367277c4ad30827343a2185a))
* **cli:** la salida en uso tiene codigo propio, pero solo si se pide ([79cdcba](https://github.com/cortega26/conciliador_bancario/commit/79cdcba61399e3df97722843113da8bb02a0f692))
* **cli:** los hallazgos criticos ya no son invisibles desde el exit code ([a267301](https://github.com/cortega26/conciliador_bancario/commit/a267301a448d4f15b184de5eb881d9c2962d80c7))
* Enhance CI/CD workflows, versioning, and changelog management ([58333b9](https://github.com/cortega26/conciliador_bancario/commit/58333b9655f92deb96d08984f138613c564259d1))
* Implement core banking reconciliation models and pipeline ([5ae8621](https://github.com/cortega26/conciliador_bancario/commit/5ae86212cf4c120e777151d55018f17d67b3d99e))
* implement supply chain vulnerability checks with pip-audit ([896bc1e](https://github.com/cortega26/conciliador_bancario/commit/896bc1eec2bf5dbfc4d388bb77ace5cee7622ee2))
* **matching:** la diferencia de sumas, que no se reportaba en ninguna parte ([1eb7028](https://github.com/cortega26/conciliador_bancario/commit/1eb702802269f0539533e6c7b839a225d63111b4))
* **reporting:** la diferencia de sumas aparece en la hoja Resumen ([5b2fbca](https://github.com/cortega26/conciliador_bancario/commit/5b2fbca8ebf646107fd45b79ae07da1eae0ea97c))
* Update version to 0.2.0 and enhance run.json contract validation ([c26fbc8](https://github.com/cortega26/conciliador_bancario/commit/c26fbc8e4f245b64e0983af551ec0ff4490fa1f5))


### Bug Fixes

* **audit:** dos corridas al mismo --out no se pisan mas ([d32e646](https://github.com/cortega26/conciliador_bancario/commit/d32e646e7f9391d642f28e81324325c4fec066e2))
* **audit:** el aviso de criticos iba a stdout, y una decision fail-closed sin traza ([bf0d34f](https://github.com/cortega26/conciliador_bancario/commit/bf0d34fc4f23683cd4fa165aabb634b9d40d49aa))
* **audit:** la escritura atomica estaba en el codigo y no en el producto ([402acc6](https://github.com/cortega26/conciliador_bancario/commit/402acc64693efee19c0cc4cb5768060f38816ba5))
* **audit:** permisos, cerrojos huerfanos y lecturas parciales ([e399da9](https://github.com/cortega26/conciliador_bancario/commit/e399da9096dd7c4367d6f5fc2f392a5b3dc30b89))
* **audit:** scope audit.jsonl to a single run ([5a22b68](https://github.com/cortega26/conciliador_bancario/commit/5a22b680994e56992da8975800b547fe5e78f0d1))
* **audit:** una carrera en el cerrojo dejaba pasar dos corridas a la vez ([47d2d8f](https://github.com/cortega26/conciliador_bancario/commit/47d2d8fa640a9f9636c9a1055b21a42ac293293c))
* **ci:** build in publish and smoke with the project's own toolchain ([31524a8](https://github.com/cortega26/conciliador_bancario/commit/31524a8e356b768b870adc22575b11659a67a8a7))
* **ci:** build in publish and smoke with the project's own toolchain ([cd1b79f](https://github.com/cortega26/conciliador_bancario/commit/cd1b79fc209b12b151ea11e315e82d1e4c7bd234))
* **ci:** make the OCR anti-skip guard exit 0 on success ([955b30c](https://github.com/cortega26/conciliador_bancario/commit/955b30c618e94aae34497c12acc48e82314b067c))
* **cli:** make --no-mask usable ([5577397](https://github.com/cortega26/conciliador_bancario/commit/5577397ab647e01beadb1580048467debbc5d6dc))
* **cli:** run aceptaba un archivo vacio, y un flag de limite era muerto ([efb521c](https://github.com/cortega26/conciliador_bancario/commit/efb521c246fc9666bf073410cf55ddc1ff773ece))
* **deps:** clear the pip-audit supply-chain gate ([2cbf79f](https://github.com/cortega26/conciliador_bancario/commit/2cbf79f9049307c89820a4078c755df54aba9fa6))
* **deps:** clear the pip-audit supply-chain gate ([837a4ee](https://github.com/cortega26/conciliador_bancario/commit/837a4eedcc8a3b187a703a18744cf45b1b2ae43f))
* **deps:** Pillow 10.4.0 -&gt; 12.3.0, 33 vulnerabilidades conocidas ([4ea3d04](https://github.com/cortega26/conciliador_bancario/commit/4ea3d046f61394177f4b546b9d6c3abfd5080482))
* **docs:** el guard que impedia las contradicciones era ciego a como se escriben ([2ff2848](https://github.com/cortega26/conciliador_bancario/commit/2ff284866f49afdb5192215c4f8b6a4885c42323))
* **errors:** ErrorIngestion cumple el contrato de la taxonomia; mypy a cero y en CI ([07d252f](https://github.com/cortega26/conciliador_bancario/commit/07d252f968bbf690dd8bf1c3956c43975512bd94))
* **errors:** give ErrorIngestion the taxonomy's details/hint contract ([6962215](https://github.com/cortega26/conciliador_bancario/commit/6962215ceae7dff82b9904e61165c3b47abd3b0f))
* format echo command in release workflow for consistency ([1c4f49e](https://github.com/cortega26/conciliador_bancario/commit/1c4f49e04c6791ab6b50d6af98d3fd0304612331))
* **gates:** el gate de entorno era unidireccional y decia OK en falso ([ae00436](https://github.com/cortega26/conciliador_bancario/commit/ae004366eed36b35e2f22d37bd856e876e79e184))
* **ingestion:** classify schema violations as ingestion errors ([e691c11](https://github.com/cortega26/conciliador_bancario/commit/e691c114be51be7388e3ecefb77084ee15aa48ad))
* **ingestion:** classify schema violations as ingestion errors ([636b020](https://github.com/cortega26/conciliador_bancario/commit/636b020a5ee699b346c60903dc448b74ead5435a))
* **ingestion:** surface duplicate expected ids as a finding ([88f3846](https://github.com/cortega26/conciliador_bancario/commit/88f3846e03296944a006ef8d964998dfec9c801f))
* **ingestion:** una fecha_contable ilegible ya no se pierde en silencio ([988469b](https://github.com/cortega26/conciliador_bancario/commit/988469bf8e95711e3da01bd4a818ade5f6833c6c))
* **matching:** 1000 USD no es 1000 CLP ([a3dccc8](https://github.com/cortega26/conciliador_bancario/commit/a3dccc83e5bacd78c100a3e5d68b38f1d8fa2077))
* **matching:** bound ref_exacta by a date window ([8d34248](https://github.com/cortega26/conciliador_bancario/commit/8d342486e7bafae2f3821c8af0e9daeb284165ae))
* **matching:** el invariante 1:1 daba exit 10 en vez de exit 4; docs al dia ([9e025b6](https://github.com/cortega26/conciliador_bancario/commit/9e025b62558cee8dc620920c9f4c45ee1c5e9314))
* **matching:** el run_id ahora distingue corridas que difieren en un override ([bd93460](https://github.com/cortega26/conciliador_bancario/commit/bd93460fd3296b93b89111e434ed24300add1ac7))
* **matching:** la conciliacion no puede apoyarse en una moneda que nadie escribio ([3898ef4](https://github.com/cortega26/conciliador_bancario/commit/3898ef444be6a7a3bdd8f718577135b1e6a3b83d))
* **matching:** la diferencia de sumas agrupa por moneda y solo cuenta lo conciliado ([17238ca](https://github.com/cortega26/conciliador_bancario/commit/17238caf09be3bf2efbb734d39d4278c43e34d3b))
* **matching:** la divisa de un total tambien puede ser inventada, y decirlo ([ce205df](https://github.com/cortega26/conciliador_bancario/commit/ce205df1f426dd252145c62268f30db9a3a00e34))
* **matching:** O(n^2) en el total conciliado, y hallazgos con el mismo id ([47fccf2](https://github.com/cortega26/conciliador_bancario/commit/47fccf2fe7603ac8c8658c93ee753f0fa1e0dcda))
* **mypy:** el veredicto del gate de tipos dependia de quien lo corrio ultimo ([66922fd](https://github.com/cortega26/conciliador_bancario/commit/66922fdfe8416f8e0e0896eadee2750c7f9abd9f))
* **ocr:** el monto de una columna ya no se atribuye a la fecha de otra ([65720ae](https://github.com/cortega26/conciliador_bancario/commit/65720ae34fb325b9629af76087a2152364bd5436))
* **parsing:** rechazar notacion cientrica, hex y el signo minus unicode ([483536c](https://github.com/cortega26/conciliador_bancario/commit/483536c9ea0e12c80c45b7e70be7efbcaccc90e9))
* **parsing:** resolve single-separator amounts deterministically ([abb6a7c](https://github.com/cortega26/conciliador_bancario/commit/abb6a7c09b13c7b053beecae114f0b938eb3c264))
* **parsing:** un monto con centavos se rechaza, no se redondea ([4835fd1](https://github.com/cortega26/conciliador_bancario/commit/4835fd1775e14ed1c8e53dc0126d668165b88a9e))
* **pdf:** un PDF vacio o corrupto es error de ingesta, no internal error ([34ae53a](https://github.com/cortega26/conciliador_bancario/commit/34ae53ac55e281ffa269eb9cd347cd58d79be2b3))
* **preflight:** dos gates que no podían pasar nunca, y el orden de `twine` ([dd3736a](https://github.com/cortega26/conciliador_bancario/commit/dd3736a1bddeb3498902e8950357a470358f41ad))
* **release:** esperar a que GitHub calcule mergeable, y no mergear con el arbol sucio ([03a56b0](https://github.com/cortega26/conciliador_bancario/commit/03a56b02feb64ab633d0b80455ce64e1c37273f9))
* **release:** handle merge-tag file detection in verify_release_tag ([53910d2](https://github.com/cortega26/conciliador_bancario/commit/53910d28eca975dff08a71ae371e924c43c2d40a))
* **release:** mergear origin/&lt;rama&gt;, no el nombre local de la rama ([e4f77f4](https://github.com/cortega26/conciliador_bancario/commit/e4f77f4687bcf78d45409a7b47234b527a5558df))
* **release:** un titulo de release-please avisa, no bloquea el merge ([9b31f1f](https://github.com/cortega26/conciliador_bancario/commit/9b31f1f197b7dfbb28d92d1fd4852549ac40d553))
* **reporting:** sanitize user-controlled id cells ([c390948](https://github.com/cortega26/conciliador_bancario/commit/c39094888d3c98f59f32b761e87bfab38271ce28))
* **supply-chain:** el gate afirmaba vulnerabilidades que no habia medido ([387867e](https://github.com/cortega26/conciliador_bancario/commit/387867eb4496e23a8af566a78dc86a076a5ae5ad))
* **tools:** await_ci no exigia el job de volumen, y por eso no lo requeria ([643af59](https://github.com/cortega26/conciliador_bancario/commit/643af595b742687bf159b815e50228dea218c31f))
* **tools:** await_ci reventaba con KeyError justo en el caso que dice vigilar ([f2c82d1](https://github.com/cortega26/conciliador_bancario/commit/f2c82d1fc68d136106f4223da427a432667182c2))
* **tools:** el gate de entorno media el interprete equivocado ([cd5beaf](https://github.com/cortega26/conciliador_bancario/commit/cd5beaf8f1181a79fadd2a06d090c57766c3b44d))
* **tools:** requiere_red estaba declarado y no lo consultaba nadie ([bb90df7](https://github.com/cortega26/conciliador_bancario/commit/bb90df7318575fc5398419d65708934091bf4847))
* trigger release please after migration ([8211401](https://github.com/cortega26/conciliador_bancario/commit/8211401da83ff9f14098cd19814ea47bcb5d910d))
* **xlsx:** un limite de tamano que no mire el lado descomprimido no protege ([4b40993](https://github.com/cortega26/conciliador_bancario/commit/4b409933137f145e7395dced3b4451a5a23a9f9b))
* **xlsx:** un XLSX ilegible es error de ingesta, no internal error ([8376129](https://github.com/cortega26/conciliador_bancario/commit/83761295e73a896d1efec37d1a00b3b2c3651607))
* **xlsx:** un XLSX ilegible es error de ingesta, no internal error ([3fff161](https://github.com/cortega26/conciliador_bancario/commit/3fff161d98836580f027b3b104aec4804d4e50b0))
* **xml:** un DTD hostil es error de ingesta, no internal error ([d294784](https://github.com/cortega26/conciliador_bancario/commit/d294784e62ee624d0c29354750d45f2dd10e4f9a))


### Build and toolchain

* **ci:** el gate de supply-chain audita tambien los extras opcionales ([17659bd](https://github.com/cortega26/conciliador_bancario/commit/17659bde8255abfbaba9782f214dadf279c06895))
* **deps:** Bump pypdf from 4.2.0 to 6.6.2 in the pip group across 1 directory ([2f21f45](https://github.com/cortega26/conciliador_bancario/commit/2f21f451a92cbe3019c0ee5f8e2ff58a831c8f52))
* **deps:** Bump pypdf from 6.6.2 to 6.7.1 in the pip group across 1 directory ([d797214](https://github.com/cortega26/conciliador_bancario/commit/d7972141dfd28a48be281f0a4c2d6a9bddf57f94))
* **deps:** Bump pypdf from 6.7.1 to 6.7.2 in the pip group across 1 directory ([5d162a7](https://github.com/cortega26/conciliador_bancario/commit/5d162a71756edca39700a31ae8665eb498880390))
* **deps:** Bump pypdf in the pip group across 1 directory ([c5f55a6](https://github.com/cortega26/conciliador_bancario/commit/c5f55a6c87b1beb0f6fb8db43ee93e21ac2fd51c))
* **deps:** Bump pypdf in the pip group across 1 directory ([6e96fbb](https://github.com/cortega26/conciliador_bancario/commit/6e96fbbaad7112f91b257b4f18a7a69e1007a14f))
* **deps:** Bump pypdf in the pip group across 1 directory ([9c8ee3a](https://github.com/cortega26/conciliador_bancario/commit/9c8ee3ad94328f50e419fbb11a702c910d365519))
* embebir SBOM CycloneDX en el wheel (PEP 770) ([04ac1c3](https://github.com/cortega26/conciliador_bancario/commit/04ac1c3887bbe5a27f72cdee909c862720876914))
* embebir un SBOM CycloneDX en el wheel (PEP 770) ([4bc904b](https://github.com/cortega26/conciliador_bancario/commit/4bc904ba628696b84398b2c5d91d115f1125103b))
* exclude .pypi_smoke from the sdist ([25bcde2](https://github.com/cortega26/conciliador_bancario/commit/25bcde21408b68c76e19d0d2d8ddd3f14596ccff))
* **ingesta:** frontera que clasifica la excepcion en vez de tragarsela ([cb86905](https://github.com/cortega26/conciliador_bancario/commit/cb86905fec6862dec6a8f8f544c76865c85ed7c5))
* los tests de volumen existen pero no se ejecutaban nunca ([9f31da2](https://github.com/cortega26/conciliador_bancario/commit/9f31da2954fb3a014d333745a81261d338261809))
* no importar la stdlib xml solo para tipar, y evitar B405 ([488a98e](https://github.com/cortega26/conciliador_bancario/commit/488a98e620c847c141547527e5b03a6876dc8515))
* point PyPI Homepage to tooltician.com ([0704075](https://github.com/cortega26/conciliador_bancario/commit/0704075f4a0fad3fa40408105e986c38266d449a))
* protocolo de iteracion, con la maquinaria que lo hace cumplible ([d2bb8f0](https://github.com/cortega26/conciliador_bancario/commit/d2bb8f06d56029b6358610be524ab256215462f6))
* **release:** guard que falla si un merge commit duplica el changelog ([c7dbc9c](https://github.com/cortega26/conciliador_bancario/commit/c7dbc9ccd770b297ba02e63864fe7ca3f882bbbe))
* **release:** merge_pr.py, para que el numero del PR no se escriba a mano ([c96f496](https://github.com/cortega26/conciliador_bancario/commit/c96f496ac9c421b1bd5e18659cdf8c99f8b363b5))
* **release:** verificar el paquete publicado, no solo que el job pasara ([157a8d4](https://github.com/cortega26/conciliador_bancario/commit/157a8d4a4ce3c20fb455fd52f319ccf5ca50501e))
* take mypy from 21 errors to zero and put it in CI ([7242c71](https://github.com/cortega26/conciliador_bancario/commit/7242c71379159b47c133c5f374ab04accb036cc1))


### Tests

* **audit:** el test de concurrencia era flaky y no fallaba en CI ([d7e730f](https://github.com/cortega26/conciliador_bancario/commit/d7e730f73e2e2cbe353c90bac75d2ac45917373c))
* **audit:** el test del cerrojo no podia fallar, y su propio comentario lo defendia ([79e5050](https://github.com/cortega26/conciliador_bancario/commit/79e505024a9d9d845e03c35c860824ce69847d2a))
* close coverage gaps on untested paths and add a coverage ratchet ([50f4579](https://github.com/cortega26/conciliador_bancario/commit/50f4579f33c2822ca00a6a514e3a81b34682386b))
* close coverage gaps on untested paths and add a coverage ratchet ([4087627](https://github.com/cortega26/conciliador_bancario/commit/408762705ea9859f1e5689e8b1c8a15d101fbf47))
* **e2e:** pruebas end-to-end del producto, mas spec y todo ([82171f3](https://github.com/cortega26/conciliador_bancario/commit/82171f32b681ec7bc775e71d08c361efdfe5e919))
* enhance JSON validation and normalization in golden dataset tests ([4a35c2a](https://github.com/cortega26/conciliador_bancario/commit/4a35c2a8d6be3f474959e5d769c5211787fe2992))
* **fuzz-ocr:** generador de PDFs escaneados con degradaciones ([1aa4545](https://github.com/cortega26/conciliador_bancario/commit/1aa454506efa446fb699b18fc26ffbc38d5b12ce))
* **fuzz:** generador de datos hostiles; encuentra 4 bugs de parsing ([31cadd9](https://github.com/cortega26/conciliador_bancario/commit/31cadd9eccd3ccb9c0e0dd1d8f6e08da596c4d75))
* fuzzing de los adaptadores de ingesta (encuentra un DTD que se reportaba como internal error) ([d7d9d50](https://github.com/cortega26/conciliador_bancario/commit/d7d9d50d35a722d1e7ee9310e050bc43deec7058))
* fuzzing de los adaptadores de ingesta con Hypothesis ([38768ba](https://github.com/cortega26/conciliador_bancario/commit/38768ba9c8c084d6201b02223b26a907ef1469ee))
* **ingesta:** contrato de frontera con discovery automatico ([dec13a1](https://github.com/cortega26/conciliador_bancario/commit/dec13a1345014bc94e4588f138ff6b3fa12f7c67))
* **ingesta:** el determinismo se mide sobre un archivo que se parsea de verdad ([93fa50e](https://github.com/cortega26/conciliador_bancario/commit/93fa50ec2448100a85796745c36ac9c4eaf4ae89))
* **matching:** characterize fail-closed branches ([ab9367c](https://github.com/cortega26/conciliador_bancario/commit/ab9367cd1124586a7e205bae324360f8c9f661ba))
* **meta:** borrar un job de CI pasaba desatendido y hacia mentir al informe ([5b82cde](https://github.com/cortega26/conciliador_bancario/commit/5b82cde0db9f61b3108b061c98f85e78916058c3))
* **meta:** el guard de alfabetos no podia ver el fallo que se proponia cazar ([a702791](https://github.com/cortega26/conciliador_bancario/commit/a7027917c8ca9b22b76015cd3c29701a24efba2c))
* **meta:** el guard de preflight&lt;-&gt;CI se saltaba gates y ignoraba `en_ci` ([db04173](https://github.com/cortega26/conciliador_bancario/commit/db041739e2b3d7ae417826784c7c189b985a5152))
* **meta:** la contraprueba no cubria una version de matriz inexistente ([6276ca5](https://github.com/cortega26/conciliador_bancario/commit/6276ca585a4170c417bbcb0facfc7b4c0031f79a))
* **ocr:** exercise the real OCR path in CI ([1b99c71](https://github.com/cortega26/conciliador_bancario/commit/1b99c713f73b31c6144f8a84c01cb1b862ded1b4))
* **ocr:** exercise the real OCR path in CI ([724d208](https://github.com/cortega26/conciliador_bancario/commit/724d20869666cb7c17ab6d4039b3a77157a1a6a1))
* **parsing:** cover ambiguous separators and accounting negatives ([0a247c4](https://github.com/cortega26/conciliador_bancario/commit/0a247c47bc9cc06c1ff851086d22787e2bbccd2c))
* **reporte:** el determinismo del reporte, comparado donde se puede comparar ([11295b3](https://github.com/cortega26/conciliador_bancario/commit/11295b31f37109458a22544b18a71b3383ff2d2c))
* **volumen:** el gate de memoria media la mitad de lo que prometia proteger ([336a4a5](https://github.com/cortega26/conciliador_bancario/commit/336a4a5a1f9dd462167bba1a9278232f238d1d67))
* **volumen:** los limites probados en el borde, y el default medido ([9b96f57](https://github.com/cortega26/conciliador_bancario/commit/9b96f5744a56492c6357bd3bcbd75afd779ce9e1))
* **volumen:** medir el default real, y un test de concurrencia que no era tautologia ([36e563e](https://github.com/cortega26/conciliador_bancario/commit/36e563e8f81389f1ebe67365031613296f51ea1d))
* **xlsx:** fija que una formula de Excel no viaja como texto ejecutable ([a70b047](https://github.com/cortega26/conciliador_bancario/commit/a70b0477975dcb84ad80ab269119f695442d21b4))
* **xlsx:** una guarda que detecta un parametrize con cero casos ([70c0e95](https://github.com/cortega26/conciliador_bancario/commit/70c0e95e131269bc6ab25b8ad208a2479dbc51be))
* **xml:** prueba de que no hay red, no de que no hay transacciones ([5ae2656](https://github.com/cortega26/conciliador_bancario/commit/5ae26563865f24d9598f5570d1fabd3a20f0faab))


### Documentation

* add author and portfolio link ([f3c1848](https://github.com/cortega26/conciliador_bancario/commit/f3c1848df2f010367885db8d0968847e21829cc8))
* add migration report for core subpackage move ([1ab216a](https://github.com/cortega26/conciliador_bancario/commit/1ab216a68b6184b3710f11f4465ea2810316d6ef))
* changelog and plans index for 008 and 009 ([bb21e4e](https://github.com/cortega26/conciliador_bancario/commit/bb21e4e6f97adf942961f25a136d96c22aa98c17))
* **changelog:** add [Unreleased] notes and move the section to the top ([661fa3e](https://github.com/cortega26/conciliador_bancario/commit/661fa3e0ed7afa8a062fef8f505ae1f58d6363ab))
* **changelog:** document core subpackage move ([60dbec8](https://github.com/cortega26/conciliador_bancario/commit/60dbec85ac4faeb52c193a7081f5138352381a33))
* **changelog:** fold 0.2.15 into a single 0.2.16 entry ([90a9d79](https://github.com/cortega26/conciliador_bancario/commit/90a9d79a7b111b3a234f8e09d32f84aba2de657d))
* **changelog:** notas de 0.2.19 para quien actualiza desde 0.2.18 ([db23be3](https://github.com/cortega26/conciliador_bancario/commit/db23be383189bde3fc189706de86a4d4c4f6ed61))
* **changelog:** reescribir las notas de 0.2.17 para un usuario ([81844b7](https://github.com/cortega26/conciliador_bancario/commit/81844b76a2546cf2f6a1734ea1bce9f46250ba44))
* **changelog:** write the real 0.2.15 release notes ([cda0edc](https://github.com/cortega26/conciliador_bancario/commit/cda0edc4e1adef392369351e9d76626f815acc94))
* **cli:** el contrato de exit codes decia `3` = "no implementado", y `3` es config invalida ([57f443d](https://github.com/cortega26/conciliador_bancario/commit/57f443d5a207cc66014de4b5ae911c8223ee5db4))
* diez lineas con CJK pegado en prosa, y una nota de plan que ya no era cierta ([4ce1bc4](https://github.com/cortega26/conciliador_bancario/commit/4ce1bc48ca49205e85cab470caa4fccffcf3e6df))
* enhance README with additional flowcharts and PyPI badge ([581f679](https://github.com/cortega26/conciliador_bancario/commit/581f679cc15226fa42e66328e406a35847303cdd))
* Enhance README with detailed usage instructions and project overview ([3d95236](https://github.com/cortega26/conciliador_bancario/commit/3d9523657787d5b895b0c40bd3b9f58ee87f8d82))
* informe de stress test 2026-09-29 (4 hallazgos, 2 criticos) ([e905850](https://github.com/cortega26/conciliador_bancario/commit/e905850656250a6994e8aafeab3c1361b01ecc69))
* los limites que un operador no puede deducir, por fin escritos ([22cf0d1](https://github.com/cortega26/conciliador_bancario/commit/22cf0d10748b5d5d773f38401a8a8208b884b2e8))
* **plans:** add execution backlog for fail-closed, parsing, audit and packaging findings ([aadd8e7](https://github.com/cortega26/conciliador_bancario/commit/aadd8e72545bcb13b792d0db17fd1dd0ec0bc11a))
* **plans:** mark 002 DONE ([c9faf3a](https://github.com/cortega26/conciliador_bancario/commit/c9faf3ad1fe6d5344a8fc93d9bded151392e8da5))
* **release:** como mergear sin duplicar el changelog ([c1982d9](https://github.com/cortega26/conciliador_bancario/commit/c1982d9fb1cb7276af05aeed4948b73dfcabb76b))
* **spec:** A8 marcado como hecho, para que spec y todo coincidan ([22aa014](https://github.com/cortega26/conciliador_bancario/commit/22aa0143a5606537691d5aded268cb33cb540238))
* **spec:** la seccion de fuera de alcance afirmaba que no hay test de concurrencia ([4f23385](https://github.com/cortega26/conciliador_bancario/commit/4f2338510841fdd89788f28d84a5e95154b286d7))
* **todo:** A8 re-verificado; el unico commit sin PR esta verificado ([884f91b](https://github.com/cortega26/conciliador_bancario/commit/884f91b105dd4d0739ec5156a1102cf40c80c4e0))
* **todo:** A9 hecho, con evidencia de la publicacion verificada ([b312502](https://github.com/cortega26/conciliador_bancario/commit/b3125026135f4797f544930e2882aae9f6b2aa51))
* **todo:** cerrar el backlog, con la evidencia de como se cerro ([2b21ea1](https://github.com/cortega26/conciliador_bancario/commit/2b21ea13224771a59b8f665568e2d877d4164161))
* **todo:** el checklist de A3 y A4 seguia marcando tareas hechas como [ ] ([a21d38c](https://github.com/cortega26/conciliador_bancario/commit/a21d38cd7a968bf5fbc222df18e81688acce505c))
* **todo:** slots=True se midio y no sirve, queda escrito para no repetirlo ([c94f1f2](https://github.com/cortega26/conciliador_bancario/commit/c94f1f2741c6b23cb33dc68bbc8f71c1c97f10c7))
* Update README and RUNBOOK for improved clarity and added references ([51eeac5](https://github.com/cortega26/conciliador_bancario/commit/51eeac5a98e8a045095db315787031d712b11fb6))
* update README to improve output formatting in flowchart ([bf81e9d](https://github.com/cortega26/conciliador_bancario/commit/bf81e9d86a9a845130f97b87de9932dc98a03033))
* update references after core move ([923aecc](https://github.com/cortega26/conciliador_bancario/commit/923aeccb5f9dbba21bb532af994ab89c05fdcf2d))


### Performance

* **matching:** index the amount+date candidate scan ([7fe436c](https://github.com/cortega26/conciliador_bancario/commit/7fe436c62fd01d6a1ef93158ac3aa12dc4f5dce7))


### Refactoring

* **matching:** las reglas son clases, para que agregar una sea verifiable ([d86ce60](https://github.com/cortega26/conciliador_bancario/commit/d86ce60f21c2769448f709db001457feb60618ba))
* **matching:** las reglas son clases, para que agregar una sea verificable ([7eb6873](https://github.com/cortega26/conciliador_bancario/commit/7eb687344d7a8f9a73b6191b178bcbdcef288d2b))
* **matching:** las reglas son clases, para que agregar una sea verificable ([80e21c8](https://github.com/cortega26/conciliador_bancario/commit/80e21c8b146f951026793d34ed4add94386f43ed))
* **packaging:** move conciliador_core under conciliador_bancario/core ([e0f9063](https://github.com/cortega26/conciliador_bancario/commit/e0f90634f93de8955873764dcc00933d70ef8867))


### Miscellaneous chores

* add .code-workspace to .gitignore ([7b9f211](https://github.com/cortega26/conciliador_bancario/commit/7b9f21132e0befcfeab741c133de5c6d4ed1b45f))
* add release-please workflow and configuration ([186c614](https://github.com/cortega26/conciliador_bancario/commit/186c614f9cf0b88b96dde056c32f748e602a264d))
* bump version to 0.2.2 and update CHANGELOG; enhance CI/CD workflows for automated releases ([63c982d](https://github.com/cortega26/conciliador_bancario/commit/63c982d412b3c16510c2cf9e7512537035e3a9ab))
* **deps:** update dependencies to latest stable ([2767dc2](https://github.com/cortega26/conciliador_bancario/commit/2767dc23b632d1ed809940b325765f7c26905e16))
* **deps:** update dependencies to latest stable ([b128461](https://github.com/cortega26/conciliador_bancario/commit/b1284613ef20c313731a73d2191c7cc1d2cdd36e))
* fix deps pins and stabilize ingestion limits ([28da3ac](https://github.com/cortega26/conciliador_bancario/commit/28da3ac5a368158241d8143bdf1823c63eaad2c7))
* fix pins and stabilize ingestion limits ([76fe1ce](https://github.com/cortega26/conciliador_bancario/commit/76fe1ceddf93995860cf921a783e0b6bcdd601fa))
* ignore the local codegraph index ([9f8c028](https://github.com/cortega26/conciliador_bancario/commit/9f8c028525ca79ec935564e0a2343ce6a33badd1))
* refactor package structure and update documentation for bankrecon integration ([ae8eca0](https://github.com/cortega26/conciliador_bancario/commit/ae8eca04035daf5c38f6df0fbc54a43274c760a7))
* **release:** declarar las secciones del changelog ([d7e7ab0](https://github.com/cortega26/conciliador_bancario/commit/d7e7ab020a69f1f9cca62b3991b8b36206308f2a))
* **release:** declarar las secciones del changelog (build/test se descartaban en silencio) ([d43648a](https://github.com/cortega26/conciliador_bancario/commit/d43648a1426a7d8a628fb1c06c841eb6f785f6ab))
* **release:** los commits de CI no son bug fixes ([a251869](https://github.com/cortega26/conciliador_bancario/commit/a25186969ed86ce77681c40dc6ba4898c2c22022))
* **release:** v0.2.1 [skip release] ([2d1e13c](https://github.com/cortega26/conciliador_bancario/commit/2d1e13ce0d08a7728b3d9d50120de2b29fd8345c))
* **release:** v0.2.10 [skip release] ([e200284](https://github.com/cortega26/conciliador_bancario/commit/e200284bacc549dd18fe0f36f823d10c4d86e75e))
* **release:** v0.2.11 [skip release] ([370ba8f](https://github.com/cortega26/conciliador_bancario/commit/370ba8f864d7f5465e66f92e4308163048491426))
* **release:** v0.2.12 [skip release] ([adf1dd0](https://github.com/cortega26/conciliador_bancario/commit/adf1dd09e6ca4ae4088160dfaa99f4ffb94fed93))
* **release:** v0.2.13 ([e62c35f](https://github.com/cortega26/conciliador_bancario/commit/e62c35fc7705bd986152c78054fa1bc20a7396a8))
* **release:** v0.2.13 ([9ddb108](https://github.com/cortega26/conciliador_bancario/commit/9ddb10893420be12f11e3eda95d0849ed88195fe))
* **release:** v0.2.14 ([f5e1063](https://github.com/cortega26/conciliador_bancario/commit/f5e1063bec4aa4d6d19e850a418861605a03629c))
* **release:** v0.2.14 ([a228269](https://github.com/cortega26/conciliador_bancario/commit/a228269d7e621c4598d21ffd45bd9685d474d5ae))
* **release:** v0.2.15 ([0d65d20](https://github.com/cortega26/conciliador_bancario/commit/0d65d203ad4dfdf27509d33af7df92b7204ee3a2))
* **release:** v0.2.15 ([6111062](https://github.com/cortega26/conciliador_bancario/commit/611106206d48fb2636bb9d9c565b537991adfc18))
* **release:** v0.2.16 ([56124cc](https://github.com/cortega26/conciliador_bancario/commit/56124cc9386b2d6e36d0d63b4a200d40a57a45b5))
* **release:** v0.2.16 ([d8d849f](https://github.com/cortega26/conciliador_bancario/commit/d8d849f62e23ae53d8977808f964e1bdbdcff38e))
* **release:** v0.2.17 ([53a828b](https://github.com/cortega26/conciliador_bancario/commit/53a828be67b658b308b5c71b2746e3df48a58ea2))
* **release:** v0.2.17 ([717bfcb](https://github.com/cortega26/conciliador_bancario/commit/717bfcbd729268d0908f224d5e2905434b3ea5ce))
* **release:** v0.2.18 ([c7d89d2](https://github.com/cortega26/conciliador_bancario/commit/c7d89d29a8a9ca8f75630374ffcff1522a93bb57))
* **release:** v0.2.18 ([741e715](https://github.com/cortega26/conciliador_bancario/commit/741e715b487dcd590009b756dee56712e0ad59c9))
* **release:** v0.2.19 ([b652135](https://github.com/cortega26/conciliador_bancario/commit/b65213501a6c9a24dc61cb3ae3b56d26bf7d4155))
* **release:** v0.2.20 ([aa9faac](https://github.com/cortega26/conciliador_bancario/commit/aa9faacc1e646e09ad8406e7e6f052df857de048))
* **release:** v0.2.21 ([8661ea5](https://github.com/cortega26/conciliador_bancario/commit/8661ea5292816f0b07671246eb066134b0340084))
* **release:** v0.2.3 [skip release] ([d31c7b3](https://github.com/cortega26/conciliador_bancario/commit/d31c7b3c162fd4dc76eeae91f2b24211f720f002))
* **release:** v0.2.4 [skip release] ([7d3648e](https://github.com/cortega26/conciliador_bancario/commit/7d3648e8f9ad56592f52022f73d008a199cb2ea0))
* **release:** v0.2.5 [skip release] ([b1289e8](https://github.com/cortega26/conciliador_bancario/commit/b1289e8b551bbbef4a90fbc7101887b088c109a5))
* **release:** v0.2.6 [skip release] ([2024a1f](https://github.com/cortega26/conciliador_bancario/commit/2024a1ff022a5c3db1a66b56094bb8401a0cec17))
* **release:** v0.2.7 [skip release] ([355a9f5](https://github.com/cortega26/conciliador_bancario/commit/355a9f550524c5e86686af9c64ebe4c3c6bc3cbe))
* **release:** v0.2.8 [skip release] ([84f0959](https://github.com/cortega26/conciliador_bancario/commit/84f0959b5dfde38738ef6410fd51d3fe7d7b18b7))
* **release:** v0.2.9 [skip release] ([5974275](https://github.com/cortega26/conciliador_bancario/commit/5974275e26869060370ef041e5a24fa80f02f80a))
* **release:** v0.3.0 ([cf8130f](https://github.com/cortega26/conciliador_bancario/commit/cf8130f192bd74384518b055838ad0dd1af2c888))
* **release:** v0.3.1 ([375aa4a](https://github.com/cortega26/conciliador_bancario/commit/375aa4a9a12bd64cc1be2f5524ef761ae56fbbbf))
* **release:** v0.3.2 ([4f661ae](https://github.com/cortega26/conciliador_bancario/commit/4f661aed8ce2b6659d9025811e9a52025b0ce900))
* **release:** v0.4.0 ([34068b9](https://github.com/cortega26/conciliador_bancario/commit/34068b9a8c2c3be52d5c4a4171f0116c60d3da59))
* remove unnecessary newline in bankrecon __init__.py ([2b9c151](https://github.com/cortega26/conciliador_bancario/commit/2b9c151563ce8d081bcd5dde01a2dde2a27fbaf8))
* update build process and enhance documentation for maintainers ([fabb735](https://github.com/cortega26/conciliador_bancario/commit/fabb7351fd7fe744903a69bb755cae778698cea0))
* update version retrieval in release workflow for improved accuracy ([e649f44](https://github.com/cortega26/conciliador_bancario/commit/e649f44ae108eb40e1eddb55d2289586a3ca826d))

## [0.4.0](https://github.com/cortega26/conciliador_bancario/compare/v0.3.2...v0.4.0) (2026-10-01)


### Features

* **cli:** la salida en uso tiene codigo propio, pero solo si se pide ([79cdcba](https://github.com/cortega26/conciliador_bancario/commit/79cdcba61399e3df97722843113da8bb02a0f692))

## [0.3.2](https://github.com/cortega26/conciliador_bancario/compare/v0.3.1...v0.3.2) (2026-10-01)


### Bug Fixes

* **tools:** await_ci reventaba con KeyError justo en el caso que dice vigilar ([f2c82d1](https://github.com/cortega26/conciliador_bancario/commit/f2c82d1fc68d136106f4223da427a432667182c2))


### Tests

* **audit:** el test del cerrojo no podia fallar, y su propio comentario lo defendia ([79e5050](https://github.com/cortega26/conciliador_bancario/commit/79e505024a9d9d845e03c35c860824ce69847d2a))


### Documentation

* **cli:** el contrato de exit codes decia `3` = "no implementado", y `3` es config invalida ([57f443d](https://github.com/cortega26/conciliador_bancario/commit/57f443d5a207cc66014de4b5ae911c8223ee5db4))


### Refactoring

* **matching:** las reglas son clases, para que agregar una sea verifiable ([d86ce60](https://github.com/cortega26/conciliador_bancario/commit/d86ce60f21c2769448f709db001457feb60618ba))
* **matching:** las reglas son clases, para que agregar una sea verificable ([7eb6873](https://github.com/cortega26/conciliador_bancario/commit/7eb687344d7a8f9a73b6191b178bcbdcef288d2b))
* **matching:** las reglas son clases, para que agregar una sea verificable ([80e21c8](https://github.com/cortega26/conciliador_bancario/commit/80e21c8b146f951026793d34ed4add94386f43ed))

## [0.3.1](https://github.com/cortega26/conciliador_bancario/compare/v0.3.0...v0.3.1) (2026-09-30)


### Tests

* **volumen:** el gate de memoria media la mitad de lo que prometia proteger ([336a4a5](https://github.com/cortega26/conciliador_bancario/commit/336a4a5a1f9dd462167bba1a9278232f238d1d67))


### Documentation

* **todo:** slots=True se midio y no sirve, queda escrito para no repetirlo ([c94f1f2](https://github.com/cortega26/conciliador_bancario/commit/c94f1f2741c6b23cb33dc68bbc8f71c1c97f10c7))

## [0.3.0](https://github.com/cortega26/conciliador_bancario/compare/v0.2.21...v0.3.0) (2026-09-30)


### Features

* **cli:** bajar el umbral de confianza ya no es un acto invisible ([3f9a743](https://github.com/cortega26/conciliador_bancario/commit/3f9a743f512cdab2367277c4ad30827343a2185a))
* **cli:** los hallazgos criticos ya no son invisibles desde el exit code ([a267301](https://github.com/cortega26/conciliador_bancario/commit/a267301a448d4f15b184de5eb881d9c2962d80c7))
* **matching:** la diferencia de sumas, que no se reportaba en ninguna parte ([1eb7028](https://github.com/cortega26/conciliador_bancario/commit/1eb702802269f0539533e6c7b839a225d63111b4))
* **reporting:** la diferencia de sumas aparece en la hoja Resumen ([5b2fbca](https://github.com/cortega26/conciliador_bancario/commit/5b2fbca8ebf646107fd45b79ae07da1eae0ea97c))


### Bug Fixes

* **audit:** dos corridas al mismo --out no se pisan mas ([d32e646](https://github.com/cortega26/conciliador_bancario/commit/d32e646e7f9391d642f28e81324325c4fec066e2))
* **audit:** el aviso de criticos iba a stdout, y una decision fail-closed sin traza ([bf0d34f](https://github.com/cortega26/conciliador_bancario/commit/bf0d34fc4f23683cd4fa165aabb634b9d40d49aa))
* **audit:** la escritura atomica estaba en el codigo y no en el producto ([402acc6](https://github.com/cortega26/conciliador_bancario/commit/402acc64693efee19c0cc4cb5768060f38816ba5))
* **audit:** permisos, cerrojos huerfanos y lecturas parciales ([e399da9](https://github.com/cortega26/conciliador_bancario/commit/e399da9096dd7c4367d6f5fc2f392a5b3dc30b89))
* **audit:** una carrera en el cerrojo dejaba pasar dos corridas a la vez ([47d2d8f](https://github.com/cortega26/conciliador_bancario/commit/47d2d8fa640a9f9636c9a1055b21a42ac293293c))
* **cli:** run aceptaba un archivo vacio, y un flag de limite era muerto ([efb521c](https://github.com/cortega26/conciliador_bancario/commit/efb521c246fc9666bf073410cf55ddc1ff773ece))
* **docs:** el guard que impedia las contradicciones era ciego a como se escriben ([2ff2848](https://github.com/cortega26/conciliador_bancario/commit/2ff284866f49afdb5192215c4f8b6a4885c42323))
* **ingestion:** una fecha_contable ilegible ya no se pierde en silencio ([988469b](https://github.com/cortega26/conciliador_bancario/commit/988469bf8e95711e3da01bd4a818ade5f6833c6c))
* **matching:** el invariante 1:1 daba exit 10 en vez de exit 4; docs al dia ([9e025b6](https://github.com/cortega26/conciliador_bancario/commit/9e025b62558cee8dc620920c9f4c45ee1c5e9314))
* **matching:** el run_id ahora distingue corridas que difieren en un override ([bd93460](https://github.com/cortega26/conciliador_bancario/commit/bd93460fd3296b93b89111e434ed24300add1ac7))
* **matching:** la conciliacion no puede apoyarse en una moneda que nadie escribio ([3898ef4](https://github.com/cortega26/conciliador_bancario/commit/3898ef444be6a7a3bdd8f718577135b1e6a3b83d))
* **matching:** la diferencia de sumas agrupa por moneda y solo cuenta lo conciliado ([17238ca](https://github.com/cortega26/conciliador_bancario/commit/17238caf09be3bf2efbb734d39d4278c43e34d3b))
* **matching:** la divisa de un total tambien puede ser inventada, y decirlo ([ce205df](https://github.com/cortega26/conciliador_bancario/commit/ce205df1f426dd252145c62268f30db9a3a00e34))
* **matching:** O(n^2) en el total conciliado, y hallazgos con el mismo id ([47fccf2](https://github.com/cortega26/conciliador_bancario/commit/47fccf2fe7603ac8c8658c93ee753f0fa1e0dcda))
* **tools:** await_ci no exigia el job de volumen, y por eso no lo requeria ([643af59](https://github.com/cortega26/conciliador_bancario/commit/643af595b742687bf159b815e50228dea218c31f))


### Build and toolchain

* los tests de volumen existen pero no se ejecutaban nunca ([9f31da2](https://github.com/cortega26/conciliador_bancario/commit/9f31da2954fb3a014d333745a81261d338261809))


### Tests

* **audit:** el test de concurrencia era flaky y no fallaba en CI ([d7e730f](https://github.com/cortega26/conciliador_bancario/commit/d7e730f73e2e2cbe353c90bac75d2ac45917373c))
* **reporte:** el determinismo del reporte, comparado donde se puede comparar ([11295b3](https://github.com/cortega26/conciliador_bancario/commit/11295b31f37109458a22544b18a71b3383ff2d2c))
* **volumen:** los limites probados en el borde, y el default medido ([9b96f57](https://github.com/cortega26/conciliador_bancario/commit/9b96f5744a56492c6357bd3bcbd75afd779ce9e1))
* **volumen:** medir el default real, y un test de concurrencia que no era tautologia ([36e563e](https://github.com/cortega26/conciliador_bancario/commit/36e563e8f81389f1ebe67365031613296f51ea1d))
* **xml:** prueba de que no hay red, no de que no hay transacciones ([5ae2656](https://github.com/cortega26/conciliador_bancario/commit/5ae26563865f24d9598f5570d1fabd3a20f0faab))


### Documentation

* los limites que un operador no puede deducir, por fin escritos ([22cf0d1](https://github.com/cortega26/conciliador_bancario/commit/22cf0d10748b5d5d773f38401a8a8208b884b2e8))
* **spec:** A8 marcado como hecho, para que spec y todo coincidan ([22aa014](https://github.com/cortega26/conciliador_bancario/commit/22aa0143a5606537691d5aded268cb33cb540238))
* **spec:** la seccion de fuera de alcance afirmaba que no hay test de concurrencia ([4f23385](https://github.com/cortega26/conciliador_bancario/commit/4f2338510841fdd89788f28d84a5e95154b286d7))
* **todo:** A8 re-verificado; el unico commit sin PR esta verificado ([884f91b](https://github.com/cortega26/conciliador_bancario/commit/884f91b105dd4d0739ec5156a1102cf40c80c4e0))
* **todo:** A9 hecho, con evidencia de la publicacion verificada ([b312502](https://github.com/cortega26/conciliador_bancario/commit/b3125026135f4797f544930e2882aae9f6b2aa51))
* **todo:** cerrar el backlog, con la evidencia de como se cerro ([2b21ea1](https://github.com/cortega26/conciliador_bancario/commit/2b21ea13224771a59b8f665568e2d877d4164161))
* **todo:** el checklist de A3 y A4 seguia marcando tareas hechas como [ ] ([a21d38c](https://github.com/cortega26/conciliador_bancario/commit/a21d38cd7a968bf5fbc222df18e81688acce505c))

## [0.2.21](https://github.com/cortega26/conciliador_bancario/compare/v0.2.20...v0.2.21) (2026-09-29)


### Bug Fixes

* **matching:** 1000 USD no es 1000 CLP ([a3dccc8](https://github.com/cortega26/conciliador_bancario/commit/a3dccc83e5bacd78c100a3e5d68b38f1d8fa2077))


### Tests

* **e2e:** pruebas end-to-end del producto, mas spec y todo ([82171f3](https://github.com/cortega26/conciliador_bancario/commit/82171f32b681ec7bc775e71d08c361efdfe5e919))
* **xlsx:** fija que una formula de Excel no viaja como texto ejecutable ([a70b047](https://github.com/cortega26/conciliador_bancario/commit/a70b0477975dcb84ad80ab269119f695442d21b4))
* **xlsx:** una guarda que detecta un parametrize con cero casos ([70c0e95](https://github.com/cortega26/conciliador_bancario/commit/70c0e95e131269bc6ab25b8ad208a2479dbc51be))

## [0.2.20](https://github.com/cortega26/conciliador_bancario/compare/v0.2.19...v0.2.20) (2026-09-29)


### Bug Fixes

* **gates:** el gate de entorno era unidireccional y decia OK en falso ([ae00436](https://github.com/cortega26/conciliador_bancario/commit/ae004366eed36b35e2f22d37bd856e876e79e184))
* **ocr:** el monto de una columna ya no se atribuye a la fecha de otra ([65720ae](https://github.com/cortega26/conciliador_bancario/commit/65720ae34fb325b9629af76087a2152364bd5436))
* **parsing:** rechazar notacion cientrica, hex y el signo minus unicode ([483536c](https://github.com/cortega26/conciliador_bancario/commit/483536c9ea0e12c80c45b7e70be7efbcaccc90e9))
* **parsing:** un monto con centavos se rechaza, no se redondea ([4835fd1](https://github.com/cortega26/conciliador_bancario/commit/4835fd1775e14ed1c8e53dc0126d668165b88a9e))
* **preflight:** dos gates que no podían pasar nunca, y el orden de `twine` ([dd3736a](https://github.com/cortega26/conciliador_bancario/commit/dd3736a1bddeb3498902e8950357a470358f41ad))
* **xlsx:** un limite de tamano que no mire el lado descomprimido no protege ([4b40993](https://github.com/cortega26/conciliador_bancario/commit/4b409933137f145e7395dced3b4451a5a23a9f9b))


### Build and toolchain

* **release:** verificar el paquete publicado, no solo que el job pasara ([157a8d4](https://github.com/cortega26/conciliador_bancario/commit/157a8d4a4ce3c20fb455fd52f319ccf5ca50501e))


### Tests

* **fuzz-ocr:** generador de PDFs escaneados con degradaciones ([1aa4545](https://github.com/cortega26/conciliador_bancario/commit/1aa454506efa446fb699b18fc26ffbc38d5b12ce))
* **fuzz:** generador de datos hostiles; encuentra 4 bugs de parsing ([31cadd9](https://github.com/cortega26/conciliador_bancario/commit/31cadd9eccd3ccb9c0e0dd1d8f6e08da596c4d75))


### Documentation

* **changelog:** notas de 0.2.19 para quien actualiza desde 0.2.18 ([db23be3](https://github.com/cortega26/conciliador_bancario/commit/db23be383189bde3fc189706de86a4d4c4f6ed61))
* informe de stress test 2026-09-29 (4 hallazgos, 2 criticos) ([e905850](https://github.com/cortega26/conciliador_bancario/commit/e905850656250a6994e8aafeab3c1361b01ecc69))

## [0.2.19](https://github.com/cortega26/conciliador_bancario/compare/v0.2.18...v0.2.19) (2026-09-29)

### Impacto para el usuario

- **Actualiza Pillow si usas OCR.** `pip install bankrecon[pdf-ocr]` instalaba
  Pillow 10.4.0, con **33 vulnerabilidades conocidas** (seis `high` segun
  Dependabot), corregidas en 12.1.1 / 12.2.0 / 12.3.0. Ahora el extra declara
  `Pillow==12.3.0`. No hay nada que hacer en el codigo: es una dependencia que se
  reinstala sola al actualizar el paquete.
  El salto de version mayor (10 -> 12) no cambio el comportamiento de OCR: el
  job `pdf_ocr` de CI corre OCR real con tesseract sobre un PDF escaneado y pasa
  con Pillow 12.3.0. Si tu plataforma no tiene binarios para Pillow 12, el
  `pip install` va a fallar al compilar, y la causa sera visible en el error.

- **El escaneo de dependencias ahora cubre los extras opcionales.** El gate de
  supply-chain audita el entorno instalado y, por separado, cada extra
  declarado en `pyproject.toml`. Antes no cubria los extras: por eso el punto
  anterior pudo publicarse con el gate en verde. No cambia el comportamiento
  del CLI; cambia que un extra nuevo con una vulnerabilidad conocida falle la
  build en vez de aparecer semanas despues en Dependabot.

- **Sin cambios de comportamiento en la conciliacion.** Los fixes de exit code
  (`internal error` -> error de ingesta) salieron en 0.2.17. Los cambios de
  matching, normalizacion y OCR no se tocaron en esta version.

### Bug Fixes

* **deps:** Pillow 10.4.0 -&gt; 12.3.0, 33 vulnerabilidades conocidas ([4ea3d04](https://github.com/cortega26/conciliador_bancario/commit/4ea3d046f61394177f4b546b9d6c3abfd5080482))
* **release:** un titulo de release-please avisa, no bloquea el merge ([9b31f1f](https://github.com/cortega26/conciliador_bancario/commit/9b31f1f197b7dfbb28d92d1fd4852549ac40d553))


### Build and toolchain

* **ci:** el gate de supply-chain audita tambien los extras opcionales ([17659bd](https://github.com/cortega26/conciliador_bancario/commit/17659bde8255abfbaba9782f214dadf279c06895))
* protocolo de iteracion, con la maquinaria que lo hace cumplible ([d2bb8f0](https://github.com/cortega26/conciliador_bancario/commit/d2bb8f06d56029b6358610be524ab256215462f6))
* **release:** merge_pr.py, para que el numero del PR no se escriba a mano ([c96f496](https://github.com/cortega26/conciliador_bancario/commit/c96f496ac9c421b1bd5e18659cdf8c99f8b363b5))


### Tests

* **ingesta:** el determinismo se mide sobre un archivo que se parsea de verdad ([93fa50e](https://github.com/cortega26/conciliador_bancario/commit/93fa50ec2448100a85796745c36ac9c4eaf4ae89))

## [0.2.18](https://github.com/cortega26/conciliador_bancario/compare/v0.2.17...v0.2.18) (2026-09-29)


### Build and toolchain

* **ingesta:** frontera que clasifica la excepcion en vez de tragarsela ([cb86905](https://github.com/cortega26/conciliador_bancario/commit/cb86905fec6862dec6a8f8f544c76865c85ed7c5))
* **release:** guard que falla si un merge commit duplica el changelog ([c7dbc9c](https://github.com/cortega26/conciliador_bancario/commit/c7dbc9ccd770b297ba02e63864fe7ca3f882bbbe))


### Tests

* **ingesta:** contrato de frontera con discovery automatico ([dec13a1](https://github.com/cortega26/conciliador_bancario/commit/dec13a1345014bc94e4588f138ff6b3fa12f7c67))


### Documentation

* **changelog:** reescribir las notas de 0.2.17 para un usuario ([81844b7](https://github.com/cortega26/conciliador_bancario/commit/81844b76a2546cf2f6a1734ea1bce9f46250ba44))


### Miscellaneous chores

* **release:** los commits de CI no son bug fixes ([a251869](https://github.com/cortega26/conciliador_bancario/commit/a25186969ed86ce77681c40dc6ba4898c2c22022))

## [0.2.17](https://github.com/cortega26/conciliador_bancario/compare/v0.2.16...v0.2.17) (2026-09-29)

### Impacto para el usuario

- **Un archivo invalido ahora se reporta como error de ingesta (exit 4), no como
  falla del programa (exit 10).** En 0.2.16, un PDF vacio, corrupto o truncado, un
  XLSX ilegible (incluido un `.csv` renombrado a `.xlsx`) y un XML con DTD o
  entidades terminaban en `internal error` con traceback. El reporte senalaba a la
  herramienta cuando el problema era el archivo que entrego el cliente. Ahora cada
  caso sale con exit 4, mensaje que nombra el motivo y `hint` con el remedio
  concreto, distinguiendo "vacio" de "corrupto", y "no es un XLSX" de "esta
  protegido con contrasena".
  **Afecta a cualquier automatizacion que discrimine por exit code:** un input
  malo se confundia con un bug de la herramienta. La proteccion anti-entidades ya
  funcionaba (no habia expansion, no habia DoS); lo que estaba mal era el codigo
  de salida y el mensaje.
- **El wheel incluye un SBOM CycloneDX** en
  `bankrecon-*.dist-info/sboms/bankrecon.cdx.json`, segun PEP 770, para obtener
  el inventario de dependencias sin instalar ni resolver. Cubre las dependencias
  runtime directas; el arbol transitivo completo lo cubre `pip-audit` en CI. No
  cambia la resolucion de dependencias.
- **OCR:** el guard anti-skip de CI sale 0 cuando las dependencias si estan
  instaladas, en vez de fallar el job. Sin efecto en el comportamiento del CLI.


### Bug Fixes

* **errors:** give ErrorIngestion the taxonomy's details/hint contract ([6962215](https://github.com/cortega26/conciliador_bancario/commit/6962215ceae7dff82b9904e61165c3b47abd3b0f))
* **pdf:** un PDF vacio o corrupto es error de ingesta, no internal error ([34ae53a](https://github.com/cortega26/conciliador_bancario/commit/34ae53ac55e281ffa269eb9cd347cd58d79be2b3))
* **xlsx:** un XLSX ilegible es error de ingesta, no internal error ([3fff161](https://github.com/cortega26/conciliador_bancario/commit/3fff161d98836580f027b3b104aec4804d4e50b0))
* **xml:** un DTD hostil es error de ingesta, no internal error ([d294784](https://github.com/cortega26/conciliador_bancario/commit/d294784e62ee624d0c29354750d45f2dd10e4f9a))
* **ci:** make the OCR anti-skip guard exit 0 on success ([955b30c](https://github.com/cortega26/conciliador_bancario/commit/955b30c618e94aae34497c12acc48e82314b067c))


### Build and toolchain

* embebir un SBOM CycloneDX en el wheel (PEP 770) ([4bc904b](https://github.com/cortega26/conciliador_bancario/commit/4bc904ba628696b84398b2c5d91d115f1125103b))
* take mypy from 21 errors to zero and put it in CI ([7242c71](https://github.com/cortega26/conciliador_bancario/commit/7242c71379159b47c133c5f374ab04accb036cc1))
* no importar la stdlib xml solo para tipar, y evitar B405 ([488a98e](https://github.com/cortega26/conciliador_bancario/commit/488a98e620c847c141547527e5b03a6876dc8515))


### Tests

* close coverage gaps on untested paths and add a coverage ratchet ([4087627](https://github.com/cortega26/conciliador_bancario/commit/408762705ea9859f1e5689e8b1c8a15d101fbf47))
* fuzzing de los adaptadores de ingesta con Hypothesis ([38768ba](https://github.com/cortega26/conciliador_bancario/commit/38768ba9c8c084d6201b02223b26a907ef1469ee))
* **ocr:** exercise the real OCR path in CI ([724d208](https://github.com/cortega26/conciliador_bancario/commit/724d20869666cb7c17ab6d4039b3a77157a1a6a1))


### Documentation

* **release:** como mergear sin duplicar el changelog ([c1982d9](https://github.com/cortega26/conciliador_bancario/commit/c1982d9fb1cb7276af05aeed4948b73dfcabb76b))
* **release:** declarar las secciones del changelog ([d7e7ab0](https://github.com/cortega26/conciliador_bancario/commit/d7e7ab020a69f1f9cca62b3991b8b36206308f2a))

## [0.2.16](https://github.com/cortega26/conciliador_bancario/compare/v0.2.14...v0.2.16) (2026-09-29)

### Breaking changes

- **Parseo de montos.** Un separador decimal aislado ya no se elimina: `0,50` se
  ingeria como `50` (error de 100x) y `(1.234,56)` como `+1235`, es decir un
  credito contabilizado como debito. Ambos pasaban en silencio, con exit 0 y
  reporte aparentemente correcto. Ahora `0,50`, `12,5`, `1.5` y `12.50` se
  rechazan con `ErrorParseo` nombrando el valor, porque CLP no tiene centimos y
  adivinar seria conciliar mal. El redondeo sigue siendo el default de `Decimal`
  (half-even). **Afecta a cualquier cliente que hoy envie centimos.**
- **`audit.jsonl` pasa a estar acotado a una corrida.** Repetir el comando
  identico en el mismo `--out` ya no duplica la traza ni reinicia `seq`, que antes
  no era clave unica y hacia que dos corridas identicas fueran indistinguibles en
  el artefacto durable. Conservar la traza de una corrida anterior es
  responsabilidad de quien ejecuta (copiar el `run_dir`).
- **La regla `ref_exacta` ahora exige ventana temporal** (nuevo knob
  `ventana_dias_ref_exacta`, por defecto `7` dias). Antes no miraba las fechas:
  referencia y monto exactos con **892 dias** de diferencia se conciltaban con
  score 1.0 y estado `conciliado`, sin que nadie revisara el reporte. Una
  referencia reciclada de otro periodo (un proveedor que repite un numero de
  factura) conciliaba contra el movimiento equivocado. Fuera de la ventana no hay
  match y la fila queda `pendiente`; dentro de la ventana pero con desfase, el
  score baja a 0.80 y el match queda `sugerido`, con el mismo conservatism que ya
  aplicaba `monto_fecha`. La rama referencia-coincide-pero-monto-difiere sigue
  siendo `critica`: ahi la evidencia es un problema de datos, no un desfase de
  liquidacion.

### Security

- `.pypi_smoke/` (477 archivos, 11 binarios `.exe`, copia de pip 26.0.1) se
  publicaba dentro del sdist de `bankrecon`, una herramienta de conciliacion
  financiera. El target `sdist` ahora lo excluye y `RELEASING.md` indica crear ese
  venv fuera del repositorio. Los archivos siguen versionados: purparlos o
  reescribir la historia es una decision del mantenedor.
- Cuatro celdas de `reporte_conciliacion.xlsx` se escribian sin sanear,
  saltandose el helper `_mask_cell` del propio archivo. Un `id` de
  `=cmd|'/c calc'!A1` producia una celda de formula viva. Ahora se sanean en el
  renderizado y `MovimientoEsperado.id` rechaza en la frontera valores que
  empiezan por `=`, `+`, `-`, `@` o contienen caracteres de control.
- `prevenir_csv_injection` solo inspeccionaba el primer caracter; un espacio
  inicial bastaba para bypassear la guarda, ya que Excel lo descarta antes de
  evaluar. Ahora ignora espacios y caracteres de control iniciales.

### Fixed

- Un `id` repetido en el archivo de movimientos esperados hacia desaparecer una
  fila de la conciliacion sin generar hallazgo alguno (exit 0, reporte
  aparentemente completo). Se descarta la repeticion y se reporta como
  `id_duplicado_esperado` / `id_duplicado_banco`, con el id, los ordinales de
  fila y los montos descartados. Aplica igual para CSV y XLSX.
- `--no-mask` fallaba con exit 2 y `Flags incompatibles: --mask y --no-mask`,
  culpando al usuario por un defecto de cableado. Las tres invocaciones (sin
  flag, `--mask`, `--no-mask`) ahora terminan en 0 y `--no-mask` produce un
  reporte genuinamente sin enmascarar. El default sigue siendo enmascarar.
- Un dato del cliente que viola el esquema (una `moneda` que no es ISO-3, un `id`
  con prefijo de formula) se reportaba como `Error interno no esperado` (exit 10),
  con un volcado de pydantic en ingles y sin numero de fila. Ahora se reporta como
  error de ingestion (exit 4) en los cuatro formatos, nombrando la fila y el
  campo: `Fila 2: dato invalido segun esquema: moneda='CLPPE'`.

### Changed

- Los fallos de CLI se registran en `audit_fallo.jsonl` en vez de `audit.jsonl`,
  para que toda linea del artefacto durable sea atribuible a un `run_id`.
- Dependencias actualizadas a sus ultimas versiones estables y gate de supply
  chain reparado: el `pip-audit` de CI llevaba rojo desde el 2026-05-30. Se
  corrigio subiendo en vez de silenciando (`.pip-audit-ignore.txt` sigue sin
  entradas) y se elimino el pin directo de `click`, que era una dependencia
  declarada pero nunca importada que mantenia una version vulnerable en el
  entorno. Notables: `pydantic` 2.7.4 -> 2.13.5, `hatchling` 1.25.0 -> 1.32.4
  (lista de archivos del sdist verificada identica), `pytest` -> 9.1.1,
  `hypothesis` -> 6.168.3, `twine` -> 7.0.0. Se mantienen `ruff` 0.4.10 y `mypy`
  1.10.0: ruff 0.16.9 exige una migracion de estilo en 65 archivos y mypy ya
  reporta 18 errores sin estar en CI.

- **Publicacion a PyPI.** El pipeline de release construia y verificaba los
  artefactos con un toolchain propio (`build==1.2.2`, `twine==5.1.1`) mientras CI
  usaba el del proyecto, asi que no se publicaba exactamente lo que CI habia
  validado. Con `hatchling` 1.32.4 (que emite `Metadata-Version: 2.5`) el chequeo
  del release caia y la subida se caia con el. Ambos workflows ahora instalan
  `.[dev]`, que es lo que ya hacia el job de test, y no queda ningun pin suelto
  de `build`/`twine` en `.github/workflows/`.

### Performance

- La busqueda de candidatos por monto+fecha recorria todos los movimientos
  esperados por cada transaccion bancaria: el matching era O(n*m) y crecia de
  forma cuadratica (320 ms con n=2000, con el costo por fila duplicandose en cada
  aumento de tamano). Ahora indexa por monto y es lineal (~18 us por fila).
  Sin cambio de resultados: verificado sobre 1080 casos generados (2501 matches,
  46577 hallazgos), cero diferencias.

## [0.2.14](https://github.com/cortega26/conciliador_bancario/compare/v0.2.13...v0.2.14) (2026-02-11)


### Bug Fixes

* **release:** handle merge-tag file detection in verify_release_tag ([53910d2](https://github.com/cortega26/conciliador_bancario/commit/53910d28eca975dff08a71ae371e924c43c2d40a))

## [0.2.13](https://github.com/cortega26/conciliador_bancario/compare/v0.2.12...v0.2.13) (2026-02-11)


### Bug Fixes

* trigger release please after migration ([8211401](https://github.com/cortega26/conciliador_bancario/commit/8211401da83ff9f14098cd19814ea47bcb5d910d))

## [0.2.12] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.11] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.10] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.9] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.8] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.7] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.6] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.5] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.4] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.3] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.2] - 2026-02-10
### Changed
- Tests: hardening de normalización/validación en golden datasets (menos brittle ante cambios no contractuales).
- Docs: mejoras de README (diagramas Mermaid y aclaraciones de flujo).
- Repo hygiene: se incluyó `pyvenv.cfg` en el historial (no afecta el runtime del paquete).

## [0.2.1] - 2026-02-10
### Changed
- Packaging/namespace: el código interno de contratos dejó de existir como paquete top-level separado; ahora vive en `conciliador_bancario.core` (impacta integraciones Premium).
- Hardening: comando `concilia explain` ahora valida `run.json` (fail-closed) antes de procesarlo.
- Hardening: límites defensivos de ingesta (size/rows/cells/pages/text) configurables vía `limites_ingesta` o flags `--max-*` (fail-closed).
- CI: agrega gate SCA con `pip-audit` y smoke test de instalación desde wheel.
- Security: actualiza `pypdf` a `6.6.2` (fix CVEs reportadas por `pip-audit`).

## [0.2.0] - 2026-02-09
### Changed
- Contrato Core -> Premium: `run.json` ahora incluye `schema_version` y el Core valida el payload (fail-closed) antes de persistir.

## [0.1.0] - 2026-02-07
### Added
- MVP: CLI, ingestión (CSV/XLSX/XML/PDF texto + OCR opcional), normalización, matching explicable, reporte Excel, auditoría y tests.
