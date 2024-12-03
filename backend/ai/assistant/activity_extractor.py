from pydantic import BaseModel, Field
from typing import List, Tuple, Dict, Any
from ai.assistant.memory import Memory
from entities.message import Message, Emotion
from entities.user import User
from entities.activity import Activity
from datetime import datetime
import re
from loguru import logger
from .flowchart_framework import FlowchartLLMFramework
from gateways.activities import ActivitiesGateway

activities_gateway = ActivitiesGateway()

class ExtractedActivityEntry(BaseModel):
    activity_id: str = Field(..., description="The id of the activity that was logged")
    date: str = Field(
        ..., description="The date of when the activity was done. YYYY-MM-DD"
    )
    measure: str = Field(
        ..., description="The measure of the activity (minutes, kilometers, pages, etc)"
    )
    quantity: int = Field(
        ...,
        description="The quantity of the activity (how many minutes were spent reading / how many kilometers were ran / etc)",
    )


class ExtractedActivityEntryList(BaseModel):
    activities: List[ExtractedActivityEntry] = Field(
        ..., description="A list of activities that were logged"
    )


first_message_flowchart = {
    "FirstTimeEver": {
        "text": "Based on the conversation history, is this the first time ever talking to the user?",
        "connections": {"Yes": "Introduce", "No": "FirstTimeToday"},
    },
    "Introduce": {
        "text": "Introduce yourself, say that you're Jarvis, you're happy to meet the user and you're here to talk to them about their recent activities and automatically track them. Then ask what they've been up to recently or how they're doing.",
    },
    "FirstTimeToday": {
        "text": "Based on the conversation history, is this the first time talking today?",
        "connections": {"Yes": "Greet", "No": "End"},
    },
    "Greet": {
        "text": "Greet the user, asking what's he has been up to since you last talked X days ago (use the conversation history to determine how many days)",
    },
    "End": {  # this should never be reached
        "text": "Conclude the conversation appropriately based on the entire interaction. "
    },
}


every_message_flowchart = {
    "ActivityScanner": {
        "text": "Did the user recently mentioned in the conversation history any activity that has not been extracted by you yet?",
        "connections": {"Yes": "CheckActivityQualifies", "No": "Converse"},
        "temperature": 0.7,
    },
    "CheckActivityQualifies": {
        "text": "Does the activity exist in the user's activities list?",
        "connections": {"Yes": "CheckActivityMeasurement", "No": "InformTheUserOnlyExistingActivitiesAreSupported"},
        "temperature": 0.7,
    },
    "CheckActivityMeasurement": {
        "text": "Did the user mention the date of when the activity was done and the measure (for how long, how much pages, etc) in his exchanged messages with you?",
        "connections": {
            "No": "AskForMoreInformation",
            "Yes": "ExtractActivity",
        },
    },
    "AskForMoreInformation": {
        "text": "Ask the user for the missing information about the activity (either date and / or measure, whatever is missing)",
    },
    "ExtractActivity": {
        "text": f"Extract new activities from the user's message. New activites are activites that are not on the recent activities list. Today is {datetime.now().strftime('%b %d, %Y')}",
        "schema": ExtractedActivityEntryList,
        "connections": {"default": "InformTheUserAboutTheActivity"},
    },
    "InformTheUserAboutTheActivity": {
        "text": "Inform the user that you've extracted the activity, which he needs to accept or reject.",
    },
    "InformTheUserOnlyExistingActivitiesAreSupported": {
        "text": "Inform the user that you only support activities that are on his activities list.",
    },
    "Converse": {
        "text": "Let the user lead an engaging and challenging conversation with you, given your goal and recent conversation history.",
        "temperature": 1,
        "connections": {},
    },
}


class ActivityExtractorAssistant(object):
    def __init__(
        self,
        user: User,
        user_activities: List[Activity],
        memory: Memory,
    ):
        self.name = "Jarvis"
        self.memory = memory
        self.user = user
        self.user_activities = user_activities

    def get_response(
        self, user_input: str, message_id: str, emotions: List[Emotion] = []
    ) -> Tuple[str, List[ExtractedActivityEntry]]:
        is_first_message_in_more_than_a_day = (
            len(self.memory.read_all(max_words=1000, max_age_in_minutes=1440)) == 0
        )

        self.memory.write(
            Message.new(
                id=message_id,
                text=user_input,
                sender_name=self.user.name,
                sender_id=self.user.id,
                recipient_name=self.name,
                recipient_id="0",
                emotions=emotions,
            )
        )

        system_prompt = f"""You are {self.name}, an AI assistant helping the user track their activities. 
        Follow the instruction wrapped in <focus> tags carefully and provide appropriate responses, while always keeping your friendly personality and a connection to the conversastion thread.
        Just like a human would do.
        That instruction does not come from the user, but you must address it.
        Always consider the entire conversation history when making decisions or responses.
        Respond in the same language as the initial input.
        """

        if is_first_message_in_more_than_a_day:
            flowchart = first_message_flowchart
        else:
            flowchart = every_message_flowchart

        framework = FlowchartLLMFramework(flowchart, system_prompt)

        result, extracted = framework.run(
            f"""
        
        Here's the user's all the existent activities user is trying to track:
        {"\n- ".join([str(a) for a in self.user_activities])}

        Here's user's most recently logged activities:
        {activities_gateway.get_readable_recent_activity_entries(self.user.id)}
                               
        Now here's your actual conversation history with the user:
        {self.memory.read_all_as_str(max_words=1000, max_age_in_minutes=3*60)}

        {f"<system note>The detected user's emotions on HIS LAST MESSAGE are: {[f'{e.emotion} ({e.score * 100:.2f}%)' for e in emotions]}</system note>" if emotions else ""}
        
        Only output message to be sent to the user.
        """
        )

        jarvis_prefix = re.match(r"^Jarvis\s*\([^)]*\)\s*:\s*", result)
        if jarvis_prefix:
            result = result[len(jarvis_prefix.group(0)) :]
        elif result.startswith(f"{self.name}:"):
            result = result[len(f"{self.name}:") :]

        self.memory.write(
            Message.new(
                result,
                sender_name=self.name,
                sender_id="0",
                recipient_name=self.user.name,
                recipient_id=self.user.id,
            )
        )

        logger.info(f"FRAMEWORK RESULT: {result}")
        logger.info(f"EXTRACTED: {extracted}")

        return result, (
            extracted["ExtractActivity"].activities
            if "ExtractActivity" in extracted
            else []
        )