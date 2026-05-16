# hared / exceptions.py

from fastapi import status


class AppException(Exception):
    """Base — all app errors inherit from this."""

    def __init__(
        self,
        error_code: str,
        message: str,
        http_status: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
        field: str | None = None,
        detail: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = http_status
        self.field = field
        self.detail = detail
        super().__init__(message)


# ── Auth ──────────────────────────────────────────────────────────────────────
class InvalidCredentialsError(AppException):
    def __init__(self):
        super().__init__("INVALID_CREDENTIALS", "Invalid credentials", status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppException):
    def __init__(self):
        super().__init__("FORBIDDEN", "Access denied", status.HTTP_403_FORBIDDEN)


# ── Products ──────────────────────────────────────────────────────────────────
class ProductNotFoundError(AppException):
    def __init__(self, product_id: str = ""):
        super().__init__(
            "PRODUCT_NOT_FOUND",
            "Product not found",
            status.HTTP_404_NOT_FOUND,
            detail={"product_id": product_id},
        )


class ProductInactiveError(AppException):
    def __init__(self, name: str = ""):
        super().__init__("PRODUCT_INACTIVE", f"{name} is currently unavailable")


# ── Inventory ────────────────────────────────────────────────────────────────
class StockInsufficientError(AppException):
    def __init__(self, product: str, available, requested):
        super().__init__(
            "STOCK_INSUFFICIENT",
            f"Only {available} available for {product}",
            field="quantity",
            detail={"available_qty": str(available), "requested_qty": str(requested)},
        )


class StockNegativeError(AppException):
    def __init__(self, current_qty):
        super().__init__(
            "STOCK_NEGATIVE",
            f"Cannot reduce below zero. Current: {current_qty}",
            field="qty",
            detail={"current_qty": str(current_qty)},
        )


class ClosingStockExceedsMaxError(AppException):
    def __init__(self, provided, max_allowed):
        super().__init__(
            "CLOSING_STOCK_EXCEEDS_MAX",
            f"Closing stock exceeds maximum possible ({max_allowed})",
            field="qty",
            detail={"provided": str(provided), "max_allowed": str(max_allowed)},
        )


# ── Orders ────────────────────────────────────────────────────────────────────
class OrderNotFoundError(AppException):
    def __init__(self, order_id: str = ""):
        super().__init__(
            "ORDER_NOT_FOUND",
            "Order not found",
            status.HTTP_404_NOT_FOUND,
            detail={"order_id": order_id},
        )


class OrderAlreadyCancelledError(AppException):
    def __init__(self):
        super().__init__("ORDER_ALREADY_CANCELLED", "Order is already cancelled")


class InvalidStatusTransitionError(AppException):
    def __init__(self, current: str, requested: str):
        super().__init__(
            "ORDER_INVALID_STATUS_TRANSITION",
            f"Cannot transition from '{current}' to '{requested}'",
            detail={"current": current, "requested": requested},
        )


# ── Payments ─────────────────────────────────────────────────────────────────
class WebhookSignatureInvalidError(AppException):
    def __init__(self):
        super().__init__(
            "WEBHOOK_SIGNATURE_INVALID", "Invalid webhook signature", status.HTTP_400_BAD_REQUEST
        )


class RazorpayOrderCreateFailedError(AppException):
    def __init__(self):
        super().__init__(
            "RAZORPAY_ORDER_CREATE_FAILED",
            "Payment service unavailable. Try again shortly.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ── Farm ─────────────────────────────────────────────────────────────────────
class SeasonNotFoundError(AppException):
    def __init__(self):
        super().__init__("SEASON_NOT_FOUND", "Farm season not found", status.HTTP_404_NOT_FOUND)


class InvalidSeasonTransitionError(AppException):
    def __init__(self, current: str, action: str):
        super().__init__(
            "INVALID_SEASON_TRANSITION",
            f"Cannot '{action}' when season is '{current}'",
            detail={"current_status": current},
        )


# ── Petha ─────────────────────────────────────────────────────────────────────
class BatchNotFoundError(AppException):
    def __init__(self):
        super().__init__("BATCH_NOT_FOUND", "Petha batch not found", status.HTTP_404_NOT_FOUND)


class BatchAlreadyCompletedError(AppException):
    def __init__(self):
        super().__init__("BATCH_ALREADY_COMPLETED", "Batch outcome already recorded")


class BatchExpiredError(AppException):
    def __init__(self, expiry_date: str):
        super().__init__(
            "BATCH_EXPIRED", f"Batch expired on {expiry_date}", detail={"expiry_date": expiry_date}
        )
