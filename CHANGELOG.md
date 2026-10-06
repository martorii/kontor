# Changelog

## [1.0.0](https://github.com/martorii/kontor/compare/kontor-v0.1.2...kontor-v1.0.0) (2026-10-06)


### Features

* add categorization rerun endpoint ([ccf78bb](https://github.com/martorii/kontor/commit/ccf78bbb76460402aa3b452b92b737e2f6bee90f))
* add categorization rerun endpoint ([d10b44a](https://github.com/martorii/kontor/commit/d10b44a8984f231af08b801ad0dde68a84fff946))
* add category tree, rules YAML loader and category sync ([178539b](https://github.com/martorii/kontor/commit/178539b457a005ea9f64b93a0739bd6dbb8e83e9))
* add category tree, rules YAML loader and category sync ([a43e79b](https://github.com/martorii/kontor/commit/a43e79b981ad6717cb5e0fa67aef964caeb238e0))
* add domain core (transaction model, normalization, fingerprinting) ([eca1b76](https://github.com/martorii/kontor/commit/eca1b7620e88769ebd625350d45f1d3f3b74f7e4))
* add domain core with transaction model, normalization and fingerprinting ([fa832b1](https://github.com/martorii/kontor/commit/fa832b19184d2decb7c4f9a21c5065bb0a389749))
* add evaluation harness with labeled-set export and make eval ([e3ac129](https://github.com/martorii/kontor/commit/e3ac1291bec4bcec7504055a7b84caa7aaac546e))
* add import service and accounts API ([e998a88](https://github.com/martorii/kontor/commit/e998a887d7a21034d50c914f101f5b34da849c39))
* add import service, accounts API and python-multipart ([d29a790](https://github.com/martorii/kontor/commit/d29a790f41d182e6669ab957f23c7190fe1eaa08))
* add LLM port, LM Studio adapter and fake adapter ([b88dd42](https://github.com/martorii/kontor/commit/b88dd42ead6dfcb2ff4c1ad9f142fb151f058ff4))
* add LLM port, LM Studio adapter and fake adapter (step 13) ([6cb5502](https://github.com/martorii/kontor/commit/6cb5502c8d74ebc2d534eac2be12217404d75710))
* add manual categorization API ([24f5f05](https://github.com/martorii/kontor/commit/24f5f05d0f53af670747241cad874e3576550e18))
* add manual categorization API (step 15) ([f2a1282](https://github.com/martorii/kontor/commit/f2a12824df20f46667f27028f4cc6786279f308b))
* add parser port, registry and DKB checking-account parser ([86f1993](https://github.com/martorii/kontor/commit/86f19933b8a3d152a88f0e0fef469da3336935a8))
* add parser port, registry and DKB checking-account parser ([cdf7bd3](https://github.com/martorii/kontor/commit/cdf7bd3a867f6686be560327acfbae934d642f02))
* add reporting views, report endpoints and transaction explorer ([b7e29f4](https://github.com/martorii/kontor/commit/b7e29f49ed40ff8528f8660e7549cb3eb7cc0c35))
* add reporting views, report endpoints and transaction explorer (step 16) ([10113c1](https://github.com/martorii/kontor/commit/10113c1cf516b6d4e22e0f5e117f4b0d3df62e9e))
* add rule engine and apply it during import ([da623a8](https://github.com/martorii/kontor/commit/da623a8554698b1912d16862fafb22d329fd46cb))
* add rule engine and apply it during import ([6aa0e6b](https://github.com/martorii/kontor/commit/6aa0e6b6c67735c6a1270eee7304b9bb90d9f265))
* add Streamlit report views for monthly, year, income vs. expenses and merchants ([9983549](https://github.com/martorii/kontor/commit/99835492e73bdeac0b26efb586e49d15bc1c4e35))
* add Streamlit review tab and transaction explorer with in-place relabelling ([3fa2887](https://github.com/martorii/kontor/commit/3fa2887b4695d1c17accf3c7804f7498e2ea8d82))
* add Streamlit UI shell with upload, import history and accounts ([3369b5d](https://github.com/martorii/kontor/commit/3369b5d96938f761f091b63a6393e892d7099464))
* add Streamlit UI shell with upload, import history and accounts (step 17) ([eb2d876](https://github.com/martorii/kontor/commit/eb2d8769618b6b67d54e78d145b424a9f20f84ed))
* change a transaction's category from the monthly overview and sort income vs. expenses by month ([fb101ec](https://github.com/martorii/kontor/commit/fb101ec3744d9baa62685d1af59dccaf8cd96550))
* evaluation harness with labeled-set export and make eval (step 20) ([45b8c5e](https://github.com/martorii/kontor/commit/45b8c5ec0747d60e8cc779ad77f454f6033ea8aa))
* list a category's transactions in the monthly overview drill-down ([2857f00](https://github.com/martorii/kontor/commit/2857f002dab29cf0f3f0e52a384d0b5659f0f29e))
* run the LLM step after import and on demand ([f36802f](https://github.com/martorii/kontor/commit/f36802f7314b66d5173129e1369fc632ac231571))
* run the LLM step after import and on demand (step 14) ([7979b18](https://github.com/martorii/kontor/commit/7979b18edf00e3c24870a223e75d65d87530e6ab))
* show the LLM step's progress as a progress bar during an upload ([f9059f1](https://github.com/martorii/kontor/commit/f9059f1c23540b2cbc3bf5c09f5accc1e02c796b))
* Streamlit report views (step 18) ([3112230](https://github.com/martorii/kontor/commit/311223079ff8da014e48ec994ff8eb6ec0646dc9))
* Streamlit review tab and transaction explorer (step 19) ([c43103a](https://github.com/martorii/kontor/commit/c43103ad6d320eaa3838163d72aaeb3949107fba))
* upload progress bar and longer upload timeout ([e1d629a](https://github.com/martorii/kontor/commit/e1d629a74706ee7ebbdfa1e5be1e979fa1a900ce))


### Bug Fixes

* default the API container's LLM_BASE_URL to the host's LM Studio ([0eb2d5c](https://github.com/martorii/kontor/commit/0eb2d5c3a5e244c290f8a243052d5e00b909fefa))
* give uploads a 30 minute timeout and report a timeout as such ([af7eb42](https://github.com/martorii/kontor/commit/af7eb422591f9f6a806ebb8538d08cb7a88bfd14))
* list the allowed categories in the LLM prompt ([d8bccf9](https://github.com/martorii/kontor/commit/d8bccf99149ca0ff0b394b763568e291e15e8042))
* offer only subcategories to the LLM, like the rules ([a4ec8c8](https://github.com/martorii/kontor/commit/a4ec8c8b5c0e0ebdedea91d33085e8d0862639f6))


### Documentation

* v1 README and CONTRACT cleanup (step 21) ([e9ad188](https://github.com/martorii/kontor/commit/e9ad18813077749590b40ccd1ee498fc97003f98))
* write the v1 README and close the CONTRACT open items ([6c247e0](https://github.com/martorii/kontor/commit/6c247e0570d55089054cd9814a6fd59e82e59349))

## [0.1.2](https://github.com/martorii/kontor/compare/kontor-v0.1.1...kontor-v0.1.2) (2026-10-04)


### Bug Fixes

* publish multi-arch (amd64, arm64) release image ([464f41b](https://github.com/martorii/kontor/commit/464f41be19cdf5d5b3a8acfbce4795859a639030))
* publish multi-arch (amd64, arm64) release image ([f46d816](https://github.com/martorii/kontor/commit/f46d8168ae939eab64af435bfaec521f27f8c276))

## [0.1.1](https://github.com/martorii/kontor/compare/kontor-v0.1.0...kontor-v0.1.1) (2026-10-04)


### Bug Fixes

* tag release images as v&lt;version&gt; ([47c443b](https://github.com/martorii/kontor/commit/47c443bc9681432ba73b77e5930fc78a4cfb31d5))
* tag release images as v&lt;version&gt; ([8436cef](https://github.com/martorii/kontor/commit/8436cef26cb9cd192b25bdc800f11ea27570ca34))

## 0.1.0 (2026-10-03)


### Features

* add API skeleton, settings and structlog setup ([9c9f81e](https://github.com/martorii/kontor/commit/9c9f81eabff0727de5e2df5f5736fc7d416910c6))
* add database schema, initial migration and migrate service ([bb42d69](https://github.com/martorii/kontor/commit/bb42d69276eb089a3c1b26d1e8a383bc4b9a723e))
* add Dockerfile, compose stack and CI image build ([42abcae](https://github.com/martorii/kontor/commit/42abcae36ce3ca30e8c401343952be06db5a3c43))
* add release-please workflow, GHCR publish and deploy targets ([1ec4d34](https://github.com/martorii/kontor/commit/1ec4d348a1e8ca1036d53c5154394dda8fbb12f9))
* API skeleton, configuration, logging (step 03) ([d7981ce](https://github.com/martorii/kontor/commit/d7981cec34613d4b3535e190aaaf3f9058f67d7b))
* Docker Compose and Postgres (step 04) ([34ccb6b](https://github.com/martorii/kontor/commit/34ccb6bf61b94fb5786c50580adab5cadc1b67f5))
* release-please workflow, GHCR publish and deploy targets (step 06) ([dc4bf09](https://github.com/martorii/kontor/commit/dc4bf094522521bf7842e564db2b125b2b3d9c7a))


### Bug Fixes

* keep uv.lock version in sync on release ([e30e96f](https://github.com/martorii/kontor/commit/e30e96fa33e108d7574205294f058fa80a006c65))
* keep uv.lock version in sync on release ([91beaed](https://github.com/martorii/kontor/commit/91beaed2749e4b18440b8c288f3a4248e2366814))
* use release-please toml value path for uv.lock ([a5a429b](https://github.com/martorii/kontor/commit/a5a429bb72621f905924f6f1c5ada7f9e26e9518))
* use release-please toml value path for uv.lock ([7abb031](https://github.com/martorii/kontor/commit/7abb03166faf6eaa3d768b6db41b42e595b5e4fd))


### Documentation

* add CLAUDE.md, CONTRACT.md and PLAN.md ([7f39797](https://github.com/martorii/kontor/commit/7f39797de3c7c26ca134b30d60946a540ffbd9bd))
* mark plan step 05 done ([cc1a3f6](https://github.com/martorii/kontor/commit/cc1a3f6d763ab9202f090bdbbafb9489f7f55076))
* mark plan step 06 done ([eb5f205](https://github.com/martorii/kontor/commit/eb5f2052c282d063433b8e8871a03defefd545f7))
* tick step 02 in plan ([804c580](https://github.com/martorii/kontor/commit/804c580000ec94a0c03c997a1984184cf9d6ee9e))
* tick step 02 in plan ([3dc33e9](https://github.com/martorii/kontor/commit/3dc33e9855c178da8d7da3a1f97b5f4d8d06e68b))
