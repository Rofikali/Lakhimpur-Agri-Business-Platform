# Stage 6 · Code · Part 1 — Auth + Products modules
## Lakhimpur Agri-Business Platform · Industry Grade

---

## STEP 0 — STUBS (run before anything else)

Create these files so `make up` doesn't crash on import.

```bash
# Run from repo root
for mod in auth products inventory orders payments pl_engine farm petha notify; do
  mkdir -p backend/modules/$mod
  touch backend/modules/$mod/__init__.py
  echo "from fastapi import APIRouter\nrouter = APIRouter()" > backend/modules/$mod/router.py
done
touch backend/modules/__init__.py
touch backend/shared/__init__.py
touch backend/shared/utils.py
```

Verify: `make up && curl http://localhost:8000/health` → `{"status":"ok"}`

---

## MODULE 1 — AUTH

### modules/auth/models.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped
from shared.models.base import Base


class Owner(Base):
    __tablename__ = "owners"

    id            : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username      : Mapped[str]       = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash : Mapped[str]       = mapped_column(String(255), nullable=False)
    phone         : Mapped[str | None]= mapped_column(String(15), nullable=True)
    created_at    : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                      default=lambda: datetime.now(timezone.utc))
    updated_at    : Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True),
                                                      default=lambda: datetime.now(timezone.utc),
                                                      onupdate=lambda: datetime.now(timezone.utc))
```

### modules/auth/schemas.py
```python
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class LoginRequest(BaseModel):
    username : str = Field(min_length=1, max_length=100)
    password : str = Field(min_length=1)


class TokenResponse(BaseModel):
    owner_id   : str
    username   : str
    expires_at : datetime


class RefreshResponse(BaseModel):
    expires_at : datetime
```

### modules/auth/repository.py
```python
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.auth.models import Owner


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_username(self, username: str) -> Owner | None:
        result = await self.db.execute(
            select(Owner).where(Owner.username == username)
        )
        return result.scalar_one_or_none()

    async def find_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        result = await self.db.execute(
            select(Owner).where(Owner.id == owner_id)
        )
        return result.scalar_one_or_none()
```

### modules/auth/service.py
```python
from datetime import datetime, timezone, timedelta
from modules.auth.repository import AuthRepository
from modules.auth.schemas import LoginRequest, TokenResponse
from core.security import verify_password, create_access_token
from core.redis import blocklist_token
from core.config import settings
from shared.exceptions import InvalidCredentialsError


class AuthService:
    def __init__(self, repo: AuthRepository):
        self.repo = repo

    async def login(self, data: LoginRequest) -> tuple[str, str, TokenResponse]:
        """Verify credentials → issue JWT. Returns (token, jti, response)."""
        owner = await self.repo.find_by_username(data.username)

        # Use same error for wrong username AND wrong password
        # Prevents username enumeration
        if not owner or not verify_password(data.password, owner.password_hash):
            raise InvalidCredentialsError()

        token, jti = create_access_token(str(owner.id))
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)

        return token, jti, TokenResponse(
            owner_id=str(owner.id),
            username=owner.username,
            expires_at=expires_at,
        )

    async def logout(self, jti: str) -> None:
        """Add token jti to Redis blocklist so it can't be reused."""
        ttl = settings.JWT_EXPIRY_HOURS * 3600
        await blocklist_token(jti, ttl_secs=ttl)

    async def refresh(self, current_payload: dict) -> tuple[str, str, datetime]:
        """Issue a fresh token for the same owner."""
        token, jti = create_access_token(current_payload["sub"])
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
        return token, jti, expires_at
```

### modules/auth/router.py
```python
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from modules.auth.schemas import LoginRequest, TokenResponse
from modules.auth.service import AuthService
from modules.auth.repository import AuthRepository
from core.security import set_auth_cookie, clear_auth_cookie
from core.dependencies import require_owner, get_db_session
from core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> AuthService:
    return AuthService(repo=AuthRepository(db))


@router.post("/login", response_model=TokenResponse)
async def login(
    body     : LoginRequest,
    response : Response,
    service  : AuthService = Depends(_svc),
):
    """Owner login. Sets httpOnly JWT cookie."""
    token, jti, data = await service.login(body)
    set_auth_cookie(response, token)
    return data


@router.post("/logout", status_code=200)
async def logout(
    response : Response,
    owner    : dict = Depends(require_owner),
    service  : AuthService = Depends(_svc),
):
    """Invalidate JWT and clear cookie."""
    jti = owner.get("jti", "")
    if jti:
        await service.logout(jti)
    clear_auth_cookie(response)
    return {"message": "logged out"}


@router.post("/refresh")
async def refresh(
    response : Response,
    owner    : dict = Depends(require_owner),
    service  : AuthService = Depends(_svc),
):
    """Silent token refresh. Called automatically 15 min before expiry."""
    token, jti, expires_at = await service.refresh(owner)
    set_auth_cookie(response, token)
    return {"expires_at": expires_at}
```

---

## MODULE 2 — PRODUCTS

### modules/products/schemas.py
```python
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, ConfigDict, computed_field
from typing import Any
import uuid


class ProductCreate(BaseModel):
    name                : str     = Field(min_length=2, max_length=200)
    category            : str     = Field(pattern=r"^(rice|petha)$")
    unit                : str     = Field(pattern=r"^(kg|pc|cup)$")
    sell_price          : Decimal
    farm_cost           : Decimal = Decimal("0")
    labor_cost          : Decimal = Decimal("0")
    overhead_cost       : Decimal = Decimal("0")
    packaging_cost      : Decimal = Decimal("0")
    normal_loss_percent : Decimal = Decimal("0")
    is_own_farm         : bool    = True
    low_stock_threshold : Decimal = Decimal("5")
    description         : str | None = None

    @field_validator("sell_price","farm_cost","labor_cost",
                     "overhead_cost","packaging_cost","normal_loss_percent", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal:
        if isinstance(v, float):
            raise ValueError("Use string or Decimal for money — never float")
        return Decimal(str(v))


class ProductUpdate(BaseModel):
    name                : str | None     = Field(None, min_length=2, max_length=200)
    sell_price          : Decimal | None = None
    farm_cost           : Decimal | None = None
    labor_cost          : Decimal | None = None
    overhead_cost       : Decimal | None = None
    packaging_cost      : Decimal | None = None
    normal_loss_percent : Decimal | None = None
    is_active           : bool | None    = None
    low_stock_threshold : Decimal | None = None

    @field_validator("sell_price","farm_cost","labor_cost",
                     "overhead_cost","packaging_cost","normal_loss_percent", mode="before")
    @classmethod
    def no_float(cls, v: Any) -> Decimal | None:
        if v is None: return None
        if isinstance(v, float):
            raise ValueError("Use string or Decimal for money — never float")
        return Decimal(str(v))


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id                  : uuid.UUID
    name                : str
    slug                : str
    category            : str
    unit                : str
    sell_price          : str
    farm_cost           : str
    labor_cost          : str
    overhead_cost       : str
    packaging_cost      : str
    normal_loss_percent : str
    true_cost           : str
    gross_margin        : str
    margin_pct          : str
    is_own_farm         : bool
    is_active           : bool
    low_stock_threshold : str
    current_qty         : str  # from inventory_stock join
    image_url           : str | None

    @field_validator("sell_price","farm_cost","labor_cost","overhead_cost",
                     "packaging_cost","normal_loss_percent","true_cost",
                     "gross_margin","margin_pct","low_stock_threshold",
                     "current_qty", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else "0"
```

### modules/products/repository.py
```python
import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from modules.products.models import Product
from modules.inventory.models import InventoryStock


class ProductRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_active(self) -> list[Product]:
        result = await self.db.execute(
            select(Product)
            .where(Product.is_active == True, Product.deleted_at.is_(None))
            .order_by(Product.category, Product.name)
        )
        return list(result.scalars().all())

    async def get_all(self) -> list[Product]:
        """Owner sees all including inactive."""
        result = await self.db.execute(
            select(Product)
            .where(Product.deleted_at.is_(None))
            .order_by(Product.category, Product.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Product | None:
        result = await self.db.execute(
            select(Product).where(Product.slug == slug, Product.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Product:
        product = Product(**kwargs)
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def update(self, product: Product) -> Product:
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def get_stock(self, product_id: uuid.UUID) -> InventoryStock | None:
        result = await self.db.execute(
            select(InventoryStock).where(InventoryStock.product_id == product_id)
        )
        return result.scalar_one_or_none()
```

### modules/products/service.py
```python
import uuid
import re
from decimal import Decimal
from datetime import datetime, timezone
from modules.products.repository import ProductRepository
from modules.products.schemas import ProductCreate, ProductUpdate
from modules.products.models import Product
from modules.inventory.models import InventoryStock
from shared.exceptions import ProductNotFoundError, ProductInactiveError
from core.redis import cache_delete


def _calculate_true_cost(
    farm_cost: Decimal,
    labor_cost: Decimal,
    overhead_cost: Decimal,
    packaging_cost: Decimal,
    normal_loss_percent: Decimal,
) -> Decimal:
    """
    True cost per unit including normal loss absorption.
    Normal loss is absorbed: if 33% loss, 1kg chawl needs 1.49kg dhan.
    loss_absorb = farm_cost * (loss% / (1 - loss%))
    """
    ZERO = Decimal("0")
    if normal_loss_percent >= Decimal("100"):
        return Decimal("99999.99999")  # invalid — protect against div/0
    loss_pct = normal_loss_percent / Decimal("100")
    loss_absorb = farm_cost * loss_pct / (Decimal("1") - loss_pct) if loss_pct > ZERO else ZERO
    return farm_cost + loss_absorb + labor_cost + overhead_cost + packaging_cost


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    async def list_products(self, owner: bool = False) -> list[dict]:
        products = await (self.repo.get_all() if owner else self.repo.get_all_active())
        result = []
        for p in products:
            stock = await self.repo.get_stock(p.id)
            result.append(self._to_response_dict(p, stock))
        return result

    async def get_product(self, product_id: uuid.UUID) -> dict:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))
        stock = await self.repo.get_stock(product.id)
        return self._to_response_dict(product, stock)

    async def get_active(self, product_id: uuid.UUID) -> Product:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))
        if not product.is_active:
            raise ProductInactiveError(product.name)
        return product

    async def create_product(self, data: ProductCreate) -> dict:
        true_cost = _calculate_true_cost(
            data.farm_cost, data.labor_cost,
            data.overhead_cost, data.packaging_cost,
            data.normal_loss_percent,
        )
        slug = _slugify(data.name)

        product = await self.repo.create(
            name=data.name, slug=slug,
            category=data.category, unit=data.unit,
            sell_price=data.sell_price, farm_cost=data.farm_cost,
            labor_cost=data.labor_cost, overhead_cost=data.overhead_cost,
            packaging_cost=data.packaging_cost,
            normal_loss_percent=data.normal_loss_percent,
            true_cost=true_cost, is_own_farm=data.is_own_farm,
            low_stock_threshold=data.low_stock_threshold,
        )
        # Create inventory_stock row
        stock = InventoryStock(product_id=product.id, current_qty=Decimal("0"))
        self.repo.db.add(stock)
        await self.repo.db.flush()

        await cache_delete("products:list:active")
        return self._to_response_dict(product, stock)

    async def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> dict:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))

        for field, val in data.model_dump(exclude_none=True).items():
            setattr(product, field, val)

        # Recalculate true_cost if any cost field changed
        product.true_cost = _calculate_true_cost(
            product.farm_cost, product.labor_cost,
            product.overhead_cost, product.packaging_cost,
            product.normal_loss_percent,
        )

        await self.repo.update(product)
        await cache_delete("products:list:active")
        await cache_delete(f"products:detail:{product.slug}")

        stock = await self.repo.get_stock(product.id)
        return self._to_response_dict(product, stock)

    async def soft_delete(self, product_id: uuid.UUID) -> None:
        product = await self.repo.get_by_id(product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))
        product.deleted_at = datetime.now(timezone.utc)
        product.is_active = False
        await self.repo.update(product)
        await cache_delete("products:list:active")

    def _to_response_dict(self, p: Product, stock: InventoryStock | None) -> dict:
        margin = p.sell_price - p.true_cost
        margin_pct = (margin / p.sell_price * 100) if p.sell_price else Decimal("0")
        return {
            "id": p.id, "name": p.name, "slug": p.slug,
            "category": p.category, "unit": p.unit,
            "sell_price": str(p.sell_price),
            "farm_cost": str(p.farm_cost),
            "labor_cost": str(p.labor_cost),
            "overhead_cost": str(p.overhead_cost),
            "packaging_cost": str(p.packaging_cost),
            "normal_loss_percent": str(p.normal_loss_percent),
            "true_cost": str(p.true_cost),
            "gross_margin": str(margin),
            "margin_pct": str(margin_pct.quantize(Decimal("0.00001"))),
            "is_own_farm": p.is_own_farm, "is_active": p.is_active,
            "low_stock_threshold": str(p.low_stock_threshold),
            "current_qty": str(stock.current_qty) if stock else "0.000",
            "image_url": p.image_url,
        }
```

### modules/products/router.py
```python
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from modules.products.schemas import ProductCreate, ProductUpdate
from modules.products.service import ProductService
from modules.products.repository import ProductRepository
from core.dependencies import require_owner, get_db_session

router = APIRouter(prefix="/api/products", tags=["products"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> ProductService:
    return ProductService(repo=ProductRepository(db))


@router.get("/")
async def list_products(
    service : ProductService = Depends(_svc),
    owner   : dict | None   = Depends(require_owner),
):
    """Owner sees all (inc inactive). Public sees active only."""
    return await service.list_products(owner=owner is not None)


@router.get("/{product_id}")
async def get_product(
    product_id : uuid.UUID,
    service    : ProductService = Depends(_svc),
):
    return await service.get_product(product_id)


@router.post("/", status_code=201)
async def create_product(
    body    : ProductCreate,
    owner   : dict = Depends(require_owner),
    service : ProductService = Depends(_svc),
):
    return await service.create_product(body)


@router.patch("/{product_id}")
async def update_product(
    product_id : uuid.UUID,
    body       : ProductUpdate,
    owner      : dict = Depends(require_owner),
    service    : ProductService = Depends(_svc),
):
    return await service.update_product(product_id, body)


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id : uuid.UUID,
    owner      : dict = Depends(require_owner),
    service    : ProductService = Depends(_svc),
):
    await service.soft_delete(product_id)
```
