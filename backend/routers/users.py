from fastapi import APIRouter, Depends, Body, HTTPException, Response
from typing import List, Optional
from pydantic import BaseModel
from auth.clerk import is_clerk_user
from entities.user import User
from gateways.activities import ActivitiesGateway
from gateways.moodreports import MoodsGateway
from gateways.users import UsersGateway
from constants import VAPID_PRIVATE_KEY, VAPID_CLAIMS
from pywebpush import webpush, WebPushException
from services.conversation_service import initiate_user_recurrent_checkin
import json
import traceback
from gateways.scheduled_notifications import ScheduledNotificationController
from fastapi import Request
router = APIRouter(prefix="/api")

activities_gateway = ActivitiesGateway()
moods_gateway = MoodsGateway()
users_gateway = UsersGateway()

class ActivityResponse(BaseModel):
    id: str
    title: str
    measure: str

class ActivityEntryResponse(BaseModel):
    id: str
    activity_id: str
    quantity: int
    date: str

class MoodReportResponse(BaseModel):
    id: str
    user_id: str
    date: str
    score: str

class PushNotificationPayload(BaseModel):
    title: str
    body: str
    icon: Optional[str] = None
    url: Optional[str] = None

@router.get("/activities", response_model=List[ActivityResponse])
async def get_activities(user: User = Depends(is_clerk_user)):
    activities = activities_gateway.get_all_activities_by_user_id(user.id)
    return [
        ActivityResponse(id=a.id, title=a.title, measure=a.measure) for a in activities
    ]

@router.get("/activity-entries", response_model=List[ActivityEntryResponse])
async def get_activity_entries(user: User = Depends(is_clerk_user)):
    activities = activities_gateway.get_all_activities_by_user_id(user.id)
    all_entries = []
    for activity in activities:
        entries = activities_gateway.get_all_activity_entries_by_activity_id(
            activity.id
        )
        all_entries.extend(entries)
    return [
        ActivityEntryResponse(
            id=e.id, activity_id=e.activity_id, quantity=e.quantity, date=e.date
        )
        for e in all_entries
    ]

@router.get("/mood-reports", response_model=List[MoodReportResponse])
async def get_mood_reports(user: User = Depends(is_clerk_user)):
    mood_reports = moods_gateway.get_all_mood_reports_by_user_id(user.id)
    return [
        MoodReportResponse(id=m.id, user_id=m.user_id, date=m.date, score=m.score)
        for m in mood_reports
    ]

@router.get("/user-health")
async def health():
    return {"status": "ok"}

class PwaStatusUpdate(BaseModel):
    is_pwa_installed: Optional[bool] = None
    is_pwa_notifications_enabled: Optional[bool] = None
    pwa_subscription_endpoint: Optional[str] = None
    pwa_subscription_key: Optional[str] = None
    pwa_subscription_auth_token: Optional[str] = None

@router.post("/update-pwa-status")
async def update_pwa_status(
    status_update: PwaStatusUpdate = Body(...),
    user: User = Depends(is_clerk_user)
):
    update_fields = {k: v for k, v in status_update.dict().items() if v is not None}
    updated_user = users_gateway.update_fields(user.id, update_fields)
    return {"message": "PWA status updated successfully", "user": updated_user}

async def send_push_notification(
    payload: PushNotificationPayload,
    user: User
):
    subscription_info = users_gateway.get_subscription_info(user.id)
    if not subscription_info:
        raise HTTPException(status_code=404, detail="Subscription not found")

    print(f"Sending push notification to: {subscription_info}")
    print(f"Payload: {payload}")

    try:
        response = webpush(
            subscription_info,
            data=json.dumps({
                "title": payload.title,
                "body": payload.body,
                "icon": payload.icon,
                "url": payload.url
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        print(f"WebPush response: {response.text}")
        return {"message": "Push notification sent successfully"}
    except WebPushException as ex:
        print(f"WebPush error: {ex}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to send push notification: {ex}")

@router.post("/trigger-push-notification")
async def trigger_push_notification(
    payload: PushNotificationPayload = Body(...),
    user: User = Depends(is_clerk_user)
):
    return await send_push_notification(payload, user)

@router.post("/process-scheduled-notification")
async def process_scheduled_notification(request: Request):
    body = await request.json()
    notification_id = body.get("notification_id", None)

    if not notification_id:
        raise HTTPException(status_code=400, detail="Notification ID is required")

    notification_controller = ScheduledNotificationController()
    message = notification_controller.process_notification(notification_id)
    
    if message:
        notification = notification_controller.get(notification_id)
        user = users_gateway.get_user_by_id(notification.user_id)
        
        # Send push notification
        await send_push_notification(
            PushNotificationPayload(title=f"hey {user.name}", body=message.lower(), url="/log"),
            user
        )

        # Recreate the notification for changing time of the day its processed
        notification_controller.recreate(notification_id)

        return {"message": "Notification processed, sent successfully, and recreated for next occurrence"}
    else:
        return Response(status_code=204, content={"message": "No notification processed"})

@router.post("/initiate-user-recurrent-checkin/{user_id}")
async def initiate_recurrent_checkin(user_id: str):
    initiate_user_recurrent_checkin(user_id)
    return {"message": "Recurrent check-in initiated successfully"}