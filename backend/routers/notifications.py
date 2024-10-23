from fastapi import APIRouter, Depends, Body, HTTPException, Query
from typing import Dict
from auth.clerk import is_clerk_user
from entities.user import User
from services.notification_manager import NotificationManager
from gateways.users import UsersGateway
from entities.message import Message
from gateways.database.mongodb import MongoDBGateway
from ai.assistant.memory import DatabaseMemory
from pywebpush import webpush, WebPushException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi import Request
from typing import Optional
from constants import (
    VAPID_PRIVATE_KEY,
    VAPID_CLAIMS,
    SCHEDULED_NOTIFICATION_TIME_DEVIATION_IN_HOURS,
)
import json
import traceback
from loguru import logger

router = APIRouter()

notification_manager = NotificationManager()
users_gateway = UsersGateway()


class PwaStatusUpdate(BaseModel):
    is_pwa_installed: Optional[bool] = None
    is_pwa_notifications_enabled: Optional[bool] = None
    pwa_subscription_endpoint: Optional[str] = None
    pwa_subscription_key: Optional[str] = None
    pwa_subscription_auth_token: Optional[str] = None


@router.post("/update-pwa-status")
async def update_pwa_status(
    status_update: PwaStatusUpdate = Body(...), user: User = Depends(is_clerk_user)
):
    update_fields = {k: v for k, v in status_update.dict().items() if v is not None}
    updated_user = users_gateway.update_fields(user.id, update_fields)
    return {"message": "PWA status updated successfully", "user": updated_user}


@router.post("/process-scheduled-notification")
async def process_scheduled_notification(request: Request):
    body = await request.json()
    notification_id = body.get("notification_id", None)

    if not notification_id:
        raise HTTPException(status_code=400, detail="Notification ID is required")

    processed_notification = notification_manager.process_notification(notification_id)

    if processed_notification:
        user = users_gateway.get_user_by_id(processed_notification.user_id)

        # Send push notification
        try:
            notification_manager.send_push_notification(
                user,
                title=f"hey {user.name}",
                body=processed_notification.message.lower(),
                url=f"/log?notification_id={processed_notification.id}",
            )
            logger.info(f"Sent push notification to {user.id}")
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            raise Exception(f"Failed to send push notification: {e}")

        memory = DatabaseMemory(MongoDBGateway("messages"), user.id)
        memory.write(
            Message.new(
                text=processed_notification.message,
                sender_name="Jarvis",
                sender_id="0",
                recipient_name=user.name,
                recipient_id=user.id,
            )
        )

        return {"message": "Notification processed and sent successfully"}
    else:
        return JSONResponse(
            status_code=204, content={"message": "No notification processed"}
        )


@router.post("/mark-notification-opened")
async def mark_notification_opened(
    notification_id: str = Query(...), user: User = Depends(is_clerk_user)
):
    notification = notification_manager.get_notification(notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to mark this notification as opened"
        )

    updated_notification = notification_manager.mark_as_opened(notification_id)

    return {
        "message": "Notification marked as opened",
        "notification": updated_notification,
    }


@router.post("/initiate-recurrent-checkin")
async def route_initiate_recurrent_checkin(user: User = Depends(is_clerk_user)):
    notification = notification_manager.create_notification(
        user_id=user.id,
        message="",  # This will be filled when processed
        notification_type="engagement",
        prompt_tag="user-recurrent-checkin",
        recurrence="daily",
        time_deviation_in_hours=SCHEDULED_NOTIFICATION_TIME_DEVIATION_IN_HOURS,
    )
    return {
        "message": "Recurrent check-in initiated successfully",
        "notification": notification,
    }


@router.get("/load-notifications")
async def load_notifications(user: User = Depends(is_clerk_user)):
    notifications = [n for n in notification_manager.get_all_for_user(user.id) if n.status != "concluded"]
    for notification in notifications:
        if notification.status == "processed":
            notification_manager.mark_as_opened(notification.id)
    return {"notifications": notifications}


@router.post("/conclude-notification/{notification_id}")
async def conclude_notification(
    notification_id: str, user: User = Depends(is_clerk_user)
):
    notification = notification_manager.get_notification(notification_id)
    if not notification or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    concluded_notification = notification_manager.conclude_notification(notification_id)
    return {
        "message": "Notification concluded",
        "notification_id": concluded_notification.id,
    }


@router.post("/trigger-push-notification")
async def trigger_push_notification(
    request: Request, user: User = Depends(is_clerk_user)
):
    try:
        body = await request.json()

        title = body.get("title", None)
        body = body.get("body", None)
        url = body.get("url", None)
        icon = body.get("icon", None)

        return await notification_manager.send_push_notification(
            user, title, body, url, icon
        )
    except Exception as e:
        logger.error(f"Failed to send push notification: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))