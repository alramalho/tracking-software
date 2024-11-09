from fastapi import FastAPI, WebSocket, Request
from shared.logger import create_logger

create_logger(level="DEBUG")

from fastapi.middleware.cors import CORSMiddleware
import base64
import json
from loguru import logger
import traceback
import asyncio
from routers.evaluation import evaluation_router
from routers.clerk import router as clerk_router
from routers.users import router as users_router
from routers.activities import router as activities_router
from routers.plans import router as plans_router
from routers.notifications import router as notifications_router
from routers.ai import router as ai_router
from starlette.middleware.base import BaseHTTPMiddleware
from constants import POSTHOG_API_KEY, POSTHOG_HOST
from fastapi.responses import Response
from auth.clerk import get_token_from_request, validate_token
from gateways.users import UsersGateway
from entities.user import User
from typing import Optional
app = FastAPI()


from posthog import Posthog

posthog = Posthog(
    project_api_key=POSTHOG_API_KEY,
    host=POSTHOG_HOST,
)


async def get_user_from_request(request: Request) -> Optional[User]:
    try:
        # Try to get the user ID from the token
        token = get_token_from_request(request)
        validated, clerk_id = await validate_token(token)
        if validated:
            user_clerk_id = clerk_id

        if user_clerk_id:
            return UsersGateway().get_user_by_safely("clerk_id", user_clerk_id)
    except:
        pass


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):

        response = await call_next(request)

        # Get the response body
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        # Log the response body and traceback for errors
        if response.status_code >= 400:
            error_message = f"Error response body: {response_body.decode()}"
            user = await get_user_from_request(request)
            user_id = user.id if user else "unknown"

            
            posthog.capture(
                distinct_id=user_id,
                event='error',
                properties={
                    "error": error_message,
                    "user_id": user_id,
                    "user_username": user.username if user else "unknown",
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                },
            )
            logger.error(error_message)

        # Re-create the response with the consumed body
        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


app.add_middleware(LoggingMiddleware)

app.include_router(clerk_router)
app.include_router(evaluation_router)

app.include_router(users_router)
app.include_router(activities_router)
app.include_router(plans_router)
app.include_router(notifications_router)
app.include_router(ai_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import HTTPException

@app.get("/exception")
def read_root():
    raise HTTPException(status_code=500, detail="test")
    return {"status": "ok"}
