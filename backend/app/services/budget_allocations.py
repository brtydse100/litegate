"""Conserve integer micro-dollars across direct users and immediate children."""

from decimal import Decimal, DecimalException, localcontext

from fastapi import HTTPException

from app.organization import OrganizationHierarchy

SCALE = 1_000_000
MAX_UNITS = 9_000_000_000_000_000
ALLOCATION_ERROR = "Assigned envelope cannot cover child budgets, manual allocations, and consumed spend"


def units(value) -> int:
    try:
        text = str(value)
        if len(text) > 80:
            raise ValueError
        amount = Decimal(text)
        with localcontext() as context:
            context.prec = 50
            # Check bounds before scaling: huge exponents must not overflow, and
            # tiny nonzero values must not underflow into a zero allocation.
            if not amount.is_finite() or amount < 0 or amount > Decimal(MAX_UNITS) / SCALE:
                raise ValueError
            rounded = amount.quantize(Decimal("0.000001"))
            if rounded != amount:
                raise ValueError
            return int(rounded * SCALE)
    except (DecimalException, ValueError, TypeError):
        raise HTTPException(422, "Budget must be nonnegative, finite, and have at most six decimal places") from None


def dollars(value: int) -> float:
    return float(Decimal(value) / SCALE)


def allocate(
    tree: OrganizationHierarchy,
    envelopes: dict,
    overrides: dict,
    memberships: dict,
    reservations: dict | None = None,
    spent: dict | None = None,
    *,
    strict: bool = True,
) -> dict:
    reservations, spent = reservations or {}, spent or {}
    result = {}
    for node in tree.nodes.values():
        assigned = envelopes.get(node.id, 0)
        children = sum(envelopes.get(child.id, 0) for child in tree.nodes.values() if child.parent_id == node.id)
        direct = sorted(user for user, group in memberships.items() if group == node.id)
        manual = {user: overrides[user] for user in direct if overrides.get(user) is not None}
        reserved = reservations.get(node.id, 0)
        available = assigned - children - sum(manual.values()) - reserved
        automatic = [user for user in direct if user not in manual]
        shortfall = max(0, sum(spent.get(user, 0) for user in automatic) - available) + sum(
            max(0, spent.get(user, 0) - value) for user, value in manual.items()
        )
        if shortfall:
            if strict:
                raise HTTPException(409, ALLOCATION_ERROR)
            result[node.id] = {
                "assigned": assigned,
                "allocated": None,
                "reserved": reserved,
                "remainder": None,
                "users": {user: manual.get(user) for user in direct},
                "shortfall": shortfall,
                "allocation_error": ALLOCATION_ERROR,
            }
            continue
        amounts = dict(manual)
        # Equal shares subject to consumed-spend floors; never reclaim consumed dollars.
        while automatic:
            share = available // len(automatic)
            above = [user for user in automatic if spent.get(user, 0) > share]
            if not above:
                amounts.update({user: share for user in automatic})
                available -= share * len(automatic)
                break
            for user in above:
                amounts[user] = spent[user]
                available -= spent[user]
                automatic.remove(user)
        result[node.id] = {
            "assigned": assigned,
            "allocated": assigned - available,
            "reserved": reserved,
            "remainder": available,
            "users": dict(sorted(amounts.items())),
            "shortfall": 0,
            "allocation_error": None,
        }
    return result
