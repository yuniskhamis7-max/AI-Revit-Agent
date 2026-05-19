# Contributing

Thanks for helping improve this project.

## Local Guidelines

- Test Revit-writing commands on a copied model.
- Keep Revit API mutations inside explicit transactions.
- Prefer adding reusable behavior to `lib/` and keeping pyRevit button scripts
  thin.
- Keep payload-driven execution deterministic: generated data should be
  validated before any document changes are made.

## Pull Request Checklist

- The README still matches the current repository structure.
- New user-facing behavior is documented.
- Revit commands fail clearly when required levels, grids, links, families, or
  types are missing.
- Temporary model files, logs, and local `.addin` files are not committed.

## Style

This codebase currently targets pyRevit compatibility, so use conservative
Python syntax and avoid adding dependencies unless they are clearly needed.
