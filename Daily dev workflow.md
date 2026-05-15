aily dev workflow

# Morning — start working

make up             # start all services
make logs           # check everything is healthy

# During development

# Edit backend files → uvicorn auto-reloads

# Edit frontend files → Nuxt HMR updates browser

# Before committing

make lint           # must pass
make test-unit      # fast — run often
git add . && git commit -m "feat: add petha batch expiry alert"

# pre-commit hooks run automatically

# Adding a new DB column (never drop columns)

make generate-migration MSG="add product description field"

# Review the generated file in migrations/versions/

make migrate

# Full test before pushing to main

make test-cov

# End of day

make down           # stop all services (data persists in ./data/)
