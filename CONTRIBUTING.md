# Contributing to Ethos-Aegis-

Thank you for your interest in contributing to Ethos-Aegis-!

## Development Setup

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/Ethos-Aegis-.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`

## Project Structure

```
Ethos-Aegis-/
├── python/           # Python package with celestial tools
├── examples/         # Code examples (basic, advanced, interactive)
├── docs/            # Documentation and guides
├── assets/          # Brand assets
├── tests/           # TypeScript tests
└── .github/workflows/ # CI/CD workflows
```

## Making Changes

1. Make your changes in your feature branch
2. Test locally if applicable
3. Run linting: `make lint` (or equivalent)
4. Run tests: `make test` (or equivalent)
5. Commit your changes with clear, descriptive messages
6. Push to your fork
7. Open a Pull Request against `main`

## Code Standards

### Python
- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Include docstrings for public functions

### TypeScript
- Follow existing patterns in the codebase
- Use consistent naming conventions
- Include tests for new functionality

## Documentation

- Update relevant docs when adding features
- Use Markdown formatting
- Include code examples where applicable

## Testing

- Write tests for new functionality
- Ensure all tests pass before submitting PR
- Follow existing test patterns

## Workflow Guidelines

When adding GitHub Actions workflows:
- Use kebab-case for workflow filenames
- Include `name:` at the top
- Use `permissions:` block for security
- Include `workflow_dispatch` for manual testing

## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- Include reproduction steps for bugs
- Check existing issues before creating new ones

## Questions?

Feel free to open a Discussion if you have questions about contributing.