# Changelog

## [0.1.1](https://github.com/DeontewattsV1/Ethos-Aegis-/compare/v0.1.0...v0.1.1) (2026-05-22)


### Features

* add make upgrade + powerful interactive REPL modes ([29d9d07](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/29d9d078742d5a659f499dd01e6cf1bbd8d2f962))
* add release-please changelog automation + StackBlitz quick-start badge ([935a317](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/935a3173925904acdd93f0b443564196db1f753a))
* **brand:** integrate Ethos Aegis identity kit (9 SVG marks + styleguide) ([01a62fe](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/01a62feb0ea32cffc1b977802872b73838f081d1))
* **celestial:** add Celestial Language + Agent Spec Pack package ([7c0ec56](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/7c0ec56a4636da6a9da4bad21dd2036ff3ec8fa5))
* **python:** integrate Ethos-Aegis Python subtree under python/ ([00bb89a](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/00bb89afe730c6729b560f96e61f518a5e370f6e))
* scaffold living-docs-template (typed observable + region-marker docs) ([9cbc1e5](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/9cbc1e584aec912af6dab63824bd7049c7225f87))
* scaffold living-docs-template (typed observable + region-marker docs) ([dec3ba1](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/dec3ba1fd51234177b18d5db43f54ce98480b27a))


### Bug Fixes

* address Devin Review findings from PR [#1](https://github.com/DeontewattsV1/Ethos-Aegis-/issues/1) ([4f204e3](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/4f204e312ad0d1f6cb9ca45caddffd56cfadd68d))
* address Devin Review findings from PR [#1](https://github.com/DeontewattsV1/Ethos-Aegis-/issues/1) (npm run docs, off-after-once, workflow_dispatch, stderr ordering) ([2da1abc](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/2da1abced2d904af3d2d07d8d0ca7dc3ace48f4b))
* **brand:** include ethos-aegis-preview.png in manifest assets list ([c368186](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/c36818612d628bde6482a10d5c09827a22ac04a1))
* **docs.yml:** drop branches:main on push so feature-branch pushes trigger live-docs regeneration ([41ec021](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/41ec02176aef88dc87f2c0c8326052fe288acec7))
* **docs.yml:** only bump last-verified stamp on push to main, not on PR ([94e6aac](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/94e6aacd0bc85a2fc0a1eb064e04316362f85453))
* **docs.yml:** quote if: expression and remove colon from commit msg trigger to fix YAML parse ([502b28c](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/502b28c833a1e19729e6240e43b0f5b0a7288acc))
* **gemini:** de-duplicate system instructions; flush trailing system ([ee0124b](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/ee0124bd57870c412e635b3b03e0d7f1c3fd60ed))
* **gemini:** preserve real assistant content after prelude (PR [#33](https://github.com/DeontewattsV1/Ethos-Aegis-/issues/33) \xf0\x9f\x93\x9d follow-up) ([de0c601](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/de0c601b2af745cb79813d977fda93e083e56983))
* **gemini:** preserve user/model role alternation in _to_gemini_contents ([6a9aa15](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/6a9aa155df00f229c5978a4999c07ed3612d54a2))
* **gemini:** synthesize user prelude for leading-assistant input (PR [#33](https://github.com/DeontewattsV1/Ethos-Aegis-/issues/33) \xf0\x9f\x9a\xa9 follow-up) ([79683da](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/79683dabddcc9b4b9e6950cbc6e60271dd878d85))
* **python:** align adapter signatures with BaseAdapter + fix stress-buffer invariant ([20a2849](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/20a2849b772e6481a8668805c75d57ee5bc2daae))
* **python:** NutrientPlex idempotency + CI cache key + dead code cleanup ([b73e05b](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/b73e05bf8e017851224a425ca268fc7f9a99dfdd))
* **repl:** defensive scenario error handling + cleaner upgrade:dry script ([1882a42](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/1882a42ae0184f93f94df99a21e95ec373c9ee99))
* **repl:** resolve SonarCloud findings + correct error scenario API usage ([35d36ba](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/35d36ba1b837c2d67cc229d8af8632dfcac0e8ce))


### Documentation

* **brand:** rename palette token 'Smoke Gray' to 'Smoke' for consistency ([7c32d00](https://github.com/DeontewattsV1/Ethos-Aegis-/commit/7c32d007226a11370808ab887ce772e715156d94))

## Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases are automated by [release-please](https://github.com/googleapis/release-please)
based on [Conventional Commits](https://www.conventionalcommits.org/) in the
default branch. **Don't edit this file by hand** — push conventional commits to
`main` and release-please will open / update a release PR that rewrites this
file with the curated changelog for the next release.

<!-- release-please-managed-content-begin -->
<!-- release-please will overwrite the content below on the first release PR.
     Anything between the begin/end markers is bootstrap-only. -->

The first release PR cut by release-please will replace this notice with the
real `## [0.1.0]` section, populated from the Conventional Commits in the
default branch up to that point.

<!-- release-please-managed-content-end -->
