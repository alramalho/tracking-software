from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import base64
import json
from typing import Tuple, List
from loguru import logger
import traceback
from datetime import datetime
from ai import stt, tts
from ai.llm import ask_schema, ask_text
from ai.assistant.assistant import Assistant
from ai.assistant.memory import DatabaseMemory
from gateways.database.mongodb import MongoDBGateway
from gateways.activities import ActivitiesGateway
from gateways.users import UsersGateway
from entities.activity import Activity, ActivityEntry
from pydantic import BaseModel, Field

app = FastAPI()
users_gateway = UsersGateway()
activities_gateway = ActivitiesGateway()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

def talk_with_assistant(user_id:str, user_input:str,) -> str:
    user = users_gateway.get_user_by_id(user_id)
    memory = DatabaseMemory(MongoDBGateway("messages"), user_id=user.id)

    assistant = Assistant(memory=memory, user=user)
    return assistant.get_response(user_input)

def get_activities_from_conversation(user_id: str) -> List[Activity]:
    memory = DatabaseMemory(MongoDBGateway("messages"), user_id=user_id)
    activities = activities_gateway.get_all_activities_by_user_id(user_id)
    prompt = f"""
    Given the conversation history, extract any present high level (examples include work, exercise, reading, meditation, be with friends, etc. counter examples include low level tasks like fixing a specific bug or reading first chapter of a book) activities.
    Try to match activities with existent ones, if not, create new ones.
    Don't infer anything that is not explicitly included. 
    If you don't have enough information to create complete activities (e.g. missing measure), do not create them. This is of utmost importance.

    Existent Activities:
    {", ".join([str(a) for a in activities])}
    
    Conversation history:
    {memory.read_all_as_str(max_messages=6)}
    """

    class ResponseModel(BaseModel):
        reasonings: str = Field(description="Your reasoning justifying each activity against the conversation history, specifically the message from the user must be included.")
        activities: list[Activity]

    response = ask_schema("Go!", prompt, ResponseModel)
    activities = [Activity.new(user_id=user_id, measure=a.measure, title=a.title) for a in response.activities]
    return activities

def get_activity_entries_from_conversation(user_id: str) -> List[ActivityEntry]:
    memory = DatabaseMemory(MongoDBGateway("messages"), user_id=user_id)
    activities_gateway = ActivitiesGateway()
    activities = activities_gateway.get_all_activities_by_user_id(user_id)
    prompt = f"""
    Given the conversation history extract any activity entries that are mentioned & matched against existent activities.
    Try to match activities with existent ones, if not, create new ones.
    Don't infer anything that is not explicitly included.
    If you don't have enough information to create complete activity entries (e.g. missing quantity from the dialogue), do not create them. This is of utmost importance.

    Existent Activities:
    {", ".join([f"{str(a)} (id: '{a.id}')" for a in activities])}
    
    Conversation history:
    {memory.read_all_as_str(max_messages=6)}
    """
    class ResponseModel(BaseModel):
        reasonings: str = Field(description="Your reasoning justifying each activity entry against the conversation history, specifically the message from the user must be included.")
        activity_entries: list[ActivityEntry]

    response = ask_schema("Go!", prompt, ResponseModel)
    activity_entries = [ActivityEntry.new(activity_id=a.activity_id, quantity=a.quantity, date=a.date) for a in response.activity_entries]

    return activity_entries


def store_activities_from_conversation(user_id: str) -> Tuple[List[Activity], List[ActivityEntry], str]:
    activities_gateway = ActivitiesGateway()
    
    activities = get_activities_from_conversation(user_id)
    logger.info(f"Activities: {activities}")

    for activity in activities:
        try:
            activities_gateway.create_activity(activity)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error creating activity: {e}")

    activity_entries = get_activity_entries_from_conversation(user_id)
    logger.info(f"Activity entries: {activity_entries}")

    for activity_entry in activity_entries:
        try:
            activities_gateway.create_activity_entry(activity_entry)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error creating activity entry: {e}")

    # Generate notification text
    notification_text = generate_notification_text(activities, activity_entries)

    return activities, activity_entries, notification_text.strip('"')

def generate_notification_text(activities: List[Activity], activity_entries: List[ActivityEntry]) -> str:
    if not activities and not activity_entries:
        return ""
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    system_prompt = f"""
    You are an AI assistant that generates friendly and encouraging notifications about a user's activities.
    Given a list of activities and activity entries, create a brief, engaging notification that summarizes what the user has done.
    Use a conversational tone and combine information from both activities and entries when possible.

    Example:
       Activity: {{title: 'meditate', measure: 'hours'}}, Entry: {{quantity: 2, date: '{current_date}'}}
       Notification: "I've registered that you meditated for 2 hours today. Keep up the good work!"

    Keep it minimal and merely informative. Only a minimal encouragement is allowed at the end, as the above example shows.
    """

    activities_str = "\n".join([f"Activity: {{title: '{a.title}', measure: '{a.measure}'}}" for a in activities])
    entries_str = "\n".join([f"Entry: {{quantity: {e.quantity}, date: '{e.date}'}}" for e in activity_entries])

    user_prompt = f"""
    Please generate a notification based on these activities and entries:

    {activities_str}
    {entries_str}
    """

    return ask_text(user_prompt, system_prompt)

@app.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = bytearray()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            user_id = "66b29679de73d9a05e77a247"
            
            if message['action'] == 'start_recording':
                audio_buffer.clear()
            
            elif message['action'] == 'stop_recording':
                # Process the audio (assuming it's sent with this message)
                audio_data = message.get('audio_data', '')
                audio_bytes = base64.b64decode(audio_data)
                
                transcription = stt.speech_to_text(audio_bytes)
                
                # Send transcription to the client
                await websocket.send_json({
                    "type": "transcription",
                    "text": transcription
                })

                text_response = talk_with_assistant(user_id=user_id, user_input=transcription)
                activities, activity_entries, notification_text = store_activities_from_conversation(user_id=user_id)
                audio_response = tts.text_to_speech(text_response)
                
                # Send audio response back to the client
                await websocket.send_json({
                    "type": "audio",
                    "transcription": text_response,
                    "audio": base64.b64encode(audio_response).decode('utf-8'),
                    "new_activities": [a.model_dump() for a in activities],
                    "new_activity_entries": [a.model_dump() for a in activity_entries],
                    "new_activities_notification": notification_text
                })

                audio_buffer.clear()
            
            elif message['action'] == 'update_transcription':
                updated_transcription = message.get('text', '')
                text_response = talk_with_assistant(user_id=user_id, user_input=updated_transcription)
                activities, activity_entries, notification_text = store_activities_from_conversation(user_id=user_id)
                audio_response = tts.text_to_speech(text_response)
                
                await websocket.send_json({
                    "type": "audio",
                    "transcription": text_response,
                    "audio": base64.b64encode(audio_response).decode('utf-8'),
                    "new_activities": [a.model_dump() for a in activities],
                    "new_activity_entries": [a.model_dump() for a in activity_entries],
                    "new_activities_notification": notification_text
                })
    
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error: {e}")
    finally:
        await websocket.close()

class ActivityResponse(BaseModel):
    id: str
    title: str
    measure: str

class ActivityEntryResponse(BaseModel):
    id: str
    activity_id: str
    quantity: int
    date: str

@app.get("/api/activities", response_model=List[ActivityResponse])
async def get_activities():
    user_id = "66b29679de73d9a05e77a247"  # Replace with actual user authentication
    activities = activities_gateway.get_all_activities_by_user_id(user_id)
    return [ActivityResponse(id=a.id, title=a.title, measure=a.measure) for a in activities]

@app.get("/api/activity-entries", response_model=List[ActivityEntryResponse])
async def get_activity_entries():
    user_id = "66b29679de73d9a05e77a247"  # Replace with actual user authentication
    activities = activities_gateway.get_all_activities_by_user_id(user_id)
    all_entries = []
    for activity in activities:
        entries = activities_gateway.get_all_activity_entries_by_activity_id(activity.id)
        all_entries.extend(entries)
    return [ActivityEntryResponse(id=e.id, activity_id=e.activity_id, quantity=e.quantity, date=e.date) for e in all_entries]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)