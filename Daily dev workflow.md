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

### Add New Package Production Only Dependency

    uv sync --no-dev ( Production Only )
    uv add fastapi-users

### Add New Package Dev Only Dependency

    uv add --dev pytest-xdist

### Update Packages

    uv lock --upgrade

    or:

    uv sync --upgrade

## Install packeges 
    pacman -Syu --noconfirm

    pacman -S --noconfirm \
    python \
    python-pip \
    nodejs \
    npm \
    postgresql \
    redis \
    git \
    base-devel \
    curl

sudo pacman -S less
sudo pacman -S git-lfs
git lfs install

### install Docker
    pacman -Syu --noconfirm
    pacman -S --noconfirm docker docker-compose

## Install redis 
    pacman -S redis

    
## Run FastApi
    uv run uvicorn main:app --reload


GitHub repository secrets — set in repo Settings → Secrets → Actions
Secret name	Value	Used by
JWT_PRIVATE_KEY_TEST	Test RSA private key (different from prod)	Backend CI tests
JWT_PUBLIC_KEY_TEST	Test RSA public key	Backend CI tests
RAILWAY_TOKEN	From railway.app → Account → Tokens	Deploy backend
VERCEL_TOKEN	From vercel.com → Settings → Tokens	Deploy frontend
VERCEL_ORG_ID	From vercel.com → Team settings	Deploy frontend
VERCEL_PROJECT_ID	From vercel.com → Project settings	Deploy frontend
CODECOV_TOKEN	From codecov.io (optional)	Coverage reports
