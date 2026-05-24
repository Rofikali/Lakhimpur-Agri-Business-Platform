from decimal import Decimal


class TestProductCreate:
    async def test_create_product_returns_201(self, auth_client):
        resp = await auth_client.post(
            "/api/products/",
            json={
                "name": "Test Rice",
                "category": "rice",
                "unit": "kg",
                "sell_price": "100",
                "farm_cost": "50",
                "labor_cost": "5",
                "overhead_cost": "3",
                "packaging_cost": "7",
                "normal_loss_percent": "0",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Rice"
        assert data["slug"] == "test-rice"
        assert data["sell_price"] == "100.00000"
        assert data["true_cost"] == "65.00000"
        assert data["current_qty"] == "0.000"  # new product has 0 stock

    async def test_create_product_calculates_true_cost_with_loss(self, auth_client):
        resp = await auth_client.post(
            "/api/products/",
            json={
                "name": "Joha Rice 2",
                "category": "rice",
                "unit": "kg",
                "sell_price": "105",
                "farm_cost": "50",
                "normal_loss_percent": "33",
            },
        )
        assert resp.status_code == 201
        cost = Decimal(resp.json()["true_cost"])
        # With 33% loss absorption, true_cost > farm_cost
        assert cost > Decimal("50")

    async def test_float_price_rejected(self, auth_client):
        resp = await auth_client.post(
            "/api/products/",
            json={
                "name": "Bad Product",
                "category": "rice",
                "unit": "kg",
                "sell_price": 105.5,  # ← float — must be rejected
            },
        )
        assert resp.status_code == 422

    async def test_gross_margin_calculated_in_response(self, auth_client):
        resp = await auth_client.post(
            "/api/products/",
            json={
                "name": "Margin Test",
                "category": "petha",
                "unit": "pc",
                "sell_price": "70",
                "farm_cost": "20",
                "labor_cost": "5",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        sell = Decimal(data["sell_price"])
        cost = Decimal(data["true_cost"])
        margin = Decimal(data["gross_margin"])
        assert margin == sell - cost


class TestProductList:
    async def test_owner_sees_all_products(self, auth_client, joha_product):
        resp = await auth_client.get("/api/products/")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_public_sees_only_active(self, client, joha_product):
        resp = await client.get("/api/products/")
        assert resp.status_code == 200
        for p in resp.json():
            assert p["is_active"] is True


class TestProductUpdate:
    async def test_update_price_recalculates_margin(self, auth_client, joha_product):
        product, _ = joha_product
        resp = await auth_client.patch(
            f"/api/products/{product.id}",
            json={
                "sell_price": "120",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["sell_price"] == "120.00000"

    async def test_soft_delete_hides_from_public(self, auth_client, client, joha_product):
        product, _ = joha_product
        # Delete
        resp = await auth_client.delete(f"/api/products/{product.id}")
        assert resp.status_code == 204
        # Not visible to public
        pub = await client.get("/api/products/")
        ids = [p["id"] for p in pub.json()]
        assert str(product.id) not in ids

    async def test_deleted_product_still_visible_to_owner(self, auth_client, joha_product):
        product, _ = joha_product
        await auth_client.delete(f"/api/products/{product.id}")
        resp = await auth_client.get("/api/products/")
        ids = [p["id"] for p in resp.json()]
        assert str(product.id) in ids
