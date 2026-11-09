"""Apply outstanding numbered migrations without resetting application data."""
from cart_recovery.repository import initialize

initialize()
print('Database migrations applied; existing business data retained.')
