# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases are automated by [release-please](https://github.com/googleapis/release-please)
based on [Conventional Commits](https://www.conventionalcommits.org/) in the
default branch. Don't edit this file by hand — push conventional commits to `main`
and release-please will open / update a release PR.

## [Unreleased]

### Features
- Region-marker driven README sync (`scripts/sync-readme.ts`)
- Output snapshot capture pipeline (`scripts/run-examples.ts`)
- Drift detection in CI (`scripts/validate-docs.ts`)
- Typed `EventEmitter` seed library with `on` / `once` / `off` / `emit` / `onError`
- 7 examples (basic / advanced / interactive)
- Devcontainer, Gitpod, and CodeSandbox/Stackblitz quick-start environments
- Three CI workflows: `docs.yml`, `examples.yml`, `readme.yml`

### Continuous Integration
- Added `release-please` automation for changelog and version management
