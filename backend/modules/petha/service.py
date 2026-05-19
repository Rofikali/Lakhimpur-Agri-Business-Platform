import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from modules.petha.repository import PethaRepository
from modules.petha.schemas import BatchCreate, BatchOutcome
from modules.petha.models import PethaBatch
from modules.inventory.service import InventoryService
from modules.inventory.schemas import StockEntryCreate
from shared.exceptions import BatchNotFoundError, BatchAlreadyCompletedError, BatchExpiredError

DP5 = Decimal("0.00001")


class PethaService:
    def __init__(self, repo: PethaRepository, inventory: InventoryService | None = None):
        self.repo = repo
        self.inventory = inventory

    async def create_batch(self, data: BatchCreate) -> dict:
        # Sum costs by type
        ingredient = sum(
            (c.total_amount for c in data.costs if c.cost_type == "ingredient"), Decimal("0")
        )
        labor = sum((c.total_amount for c in data.costs if c.cost_type == "labor"), Decimal("0"))
        overhead = sum(
            (c.total_amount for c in data.costs if c.cost_type in ("fuel", "overhead")),
            Decimal("0"),
        )
        total = ingredient + labor + overhead
        expiry = data.batch_date + timedelta(days=data.shelf_life_days)

        batch = await self.repo.create_batch(
            variety=data.variety,
            status="in_production",
            batch_date=data.batch_date,
            planned_pieces=data.planned_pieces,
            shelf_life_days=data.shelf_life_days,
            recipe_snapshot=data.recipe_snapshot,
            total_ingredient_cost=ingredient,
            total_labor_cost=labor,
            total_overhead_cost=overhead,
            total_batch_cost=total,
            expiry_date=expiry,
        )
        for c in data.costs:
            await self.repo.add_cost(
                batch_id=batch.id,
                cost_type=c.cost_type,
                description=c.description,
                qty=c.qty,
                unit_cost=c.unit_cost,
                total_amount=c.total_amount,
            )

        return self._batch_dict(batch)

    async def record_outcome(self, batch_id: uuid.UUID, data: BatchOutcome) -> dict:
        batch = await self.repo.get_batch(batch_id)
        if not batch:
            raise BatchNotFoundError()
        if batch.status != "in_production":
            if batch.status == "expired":
                raise BatchExpiredError(str(batch.expiry_date))
            raise BatchAlreadyCompletedError()

        good = data.good_pieces
        total_cost = batch.total_batch_cost

        # Absorption costing: rejected pieces' cost absorbed by good pieces
        cost_per_piece = total_cost / Decimal(str(good)) if good > 0 else Decimal("0")
        rejection_pct = (
            (Decimal(str(data.rejected_pieces)) / Decimal(str(batch.planned_pieces)) * 100)
            if batch.planned_pieces > 0
            else Decimal("0")
        )

        batch.good_pieces = good
        batch.rejected_pieces = data.rejected_pieces
        batch.cost_per_piece = cost_per_piece
        batch.status = "completed"

        # Add to inventory
        if self.inventory and good > 0:
            slug = "narikal-petha" if batch.variety == "narikal" else "septa-petha"
            from modules.products.repository import ProductRepository

            prod_repo = ProductRepository(self.repo.db)
            product = await prod_repo.get_by_slug(slug)
            if product:
                await self.inventory.add_stock_entry(
                    StockEntryCreate(
                        idempotency_key=__import__("uuid").uuid4(),
                        product_id=product.id,
                        entry_type="production",
                        qty=Decimal(str(good)),
                        unit_cost=cost_per_piece,
                        total_amount=cost_per_piece * Decimal(str(good)),
                        source="own",
                        reference_id=batch_id,
                        reference_type="petha_batch",
                        date=batch.batch_date,
                        note=f"{batch.variety} petha batch",
                    )
                )

        await self.repo.save(batch)
        d = self._batch_dict(batch)
        d["rejection_pct"] = str(rejection_pct.quantize(DP5))
        return d

    async def mark_expired(self, batch_id: uuid.UUID) -> dict:
        """
        Called when shelf life passes with unsold pieces.
        Remaining inventory × cost_per_piece = abnormal loss.
        """
        batch = await self.repo.get_batch(batch_id)
        if not batch:
            raise BatchNotFoundError()
        if batch.status != "completed":
            raise BatchAlreadyCompletedError()

        # Calculate unsold quantity from inventory
        unsold_qty = Decimal("0")
        if self.inventory and batch.cost_per_piece:
            slug = "narikal-petha" if batch.variety == "narikal" else "septa-petha"
            from modules.products.repository import ProductRepository

            prod_repo = ProductRepository(self.repo.db)
            product = await prod_repo.get_by_slug(slug)
            if product:
                stock = await self.inventory.get_current_stock(product.id)
                unsold_qty = stock.current_qty

        abnormal_loss = unsold_qty * batch.cost_per_piece if batch.cost_per_piece else Decimal("0")
        batch.abnormal_loss_amount = abnormal_loss
        batch.status = "expired"
        await self.repo.save(batch)

        # Record abnormal loss as stock entry
        if self.inventory and unsold_qty > 0 and batch.cost_per_piece:
            slug = "narikal-petha" if batch.variety == "narikal" else "septa-petha"
            from modules.products.repository import ProductRepository

            product = await ProductRepository(self.repo.db).get_by_slug(slug)
            if product:
                await self.inventory.add_stock_entry(
                    StockEntryCreate(
                        idempotency_key=__import__("uuid").uuid4(),
                        product_id=product.id,
                        entry_type="wastage_abnormal",
                        qty=unsold_qty,
                        unit_cost=batch.cost_per_piece,
                        total_amount=abnormal_loss,
                        source="own",
                        reference_id=batch_id,
                        reference_type="petha_batch",
                        date=date.today(),
                        note=f"Expired {batch.variety} petha batch",
                    )
                )

        d = self._batch_dict(batch)
        d["abnormal_loss_amount"] = str(abnormal_loss)
        return d

    async def list_batches(self, include_expired: bool = False) -> list[dict]:
        batches = await self.repo.list_batches(include_expired)
        return [self._batch_dict(b) for b in batches]

    async def get_expiring_soon(self, days: int = 3) -> list[dict]:
        batches = await self.repo.get_expiring_soon(days)
        return [self._batch_dict(b) for b in batches]

    @staticmethod
    def _batch_dict(b: PethaBatch) -> dict:
        from datetime import date as dt

        days_left = (b.expiry_date - dt.today()).days if b.expiry_date else 0
        return {
            "id": str(b.id),
            "variety": b.variety,
            "status": b.status,
            "batch_date": b.batch_date.isoformat(),
            "planned_pieces": b.planned_pieces,
            "good_pieces": b.good_pieces,
            "rejected_pieces": b.rejected_pieces,
            "total_batch_cost": str(b.total_batch_cost),
            "cost_per_piece": str(b.cost_per_piece) if b.cost_per_piece else None,
            "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
            "days_to_expiry": days_left,
        }
