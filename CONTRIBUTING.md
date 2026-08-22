# Contributing to LiteGate

Thank you for helping make LiteGate simpler and safer. Start with an issue for a
new feature or user-visible behavior so the scope can be agreed before a large
change is written.

## Development checks

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=75

cd ../frontend
npm install
npm test
npm run test:e2e
npm run build
```

Behavior changes should begin with a failing public contract. Keep pull requests
focused, do not commit credentials or runtime databases, and update the relevant
guide and changelog entry when behavior changes.

By contributing, you agree that your contribution is licensed under the
[MIT License](LICENSE).
