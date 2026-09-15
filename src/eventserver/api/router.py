from fastapi import APIRouter

from eventserver.api import deliveries, pairing, public_events, subscriptions, users

api_router = APIRouter()
api_router.include_router(public_events.router)
api_router.include_router(users.router)
api_router.include_router(subscriptions.router)
api_router.include_router(pairing.router)
api_router.include_router(deliveries.router)
