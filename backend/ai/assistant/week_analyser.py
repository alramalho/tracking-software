from pydantic import BaseModel, Field
from typing import List, Tuple, Dict, Any
from ai.assistant.memory import Memory
from entities.message import Message, Emotion
from entities.user import User
from entities.activity import Activity
from datetime import datetime
import re
from loguru import logger
from entities.plan import Plan
from .flowchart_framework import FlowchartLLMFramework
from gateways.activities import ActivitiesGateway
from controllers.plan_controller import PlanController, PlanSession

activities_gateway = ActivitiesGateway()
plan_controller = PlanController()


class OptionalPlanNameSchema(BaseModel):
    plan_name: str | None = Field(None, description="The name of the plan (if exists)")

class PlanNameSchema(BaseModel):
    plan_name: str = Field(..., description="The name of the plan")

class PlanAnalysisSchema(BaseModel):
    plan_name: str = Field(..., description="The name of the plan to analyse")
    plan_analysis: str = Field(..., description="A note outlining the analysis of the plan")
    plan_adjustment: str = Field(..., description="A note denoting the adjustment needed for the plan (or the lack of it)")

class AllPlanNamesSchema(BaseModel):
    plan_names: List[str] = Field(..., description="All plan names")

class SuggestedNextWeekSessions(BaseModel):
    plan_name: str = Field(..., description="The name of the plan")
    next_week_sessions: List[PlanSession] = Field(..., description="The sessions to be added to the plan for the upcoming week")

class ExtractedPlanSessions(BaseModel):
    plan_id: str = Field(..., description="The ID of the plan these sessions belong to")
    sessions: List[PlanSession] = Field(..., description="The sessions to be added to the plan for the upcoming week")


first_message_flowchart = {
    "FirstTimeEver": {
        "text": "Based on the conversation history, is this the first time ever talking to the user?",
        "connections": {"Yes": "Introduce", "No": "FirstTimeToday"},
    },
    "Introduce": {
        "text": "Introduce yourself, say that you're Jarvis, you're happy to meet the user and you're here to help them prepare next week, which you'll do by analysing their plans and activity logs. Ask for his confirmation.",
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
    "Start": {
        "text": "Start the conversation.",
        "connections": {"default": "ExtractPlanNames"}
    },
    "ExtractPlanNames": {
        "text": "Extract all plan names from the users plan list.",
        "connections": {"default": "StartPlanLoop"},
        "schema": AllPlanNamesSchema,
    },
    "StartPlanLoop": {
        "type": "loop_start",
        "iterator": "current_plan",
        "collection": "plan_names",
        "connections": {"default": "CheckPlanDiscussed"}
    },
    "CheckPlanDiscussed": {
        "text": "Based exclusively on the very conversation, have you asked the user to specifically discuss '${current_plan}' and user accepted?",
        "connections": {
            "Yes": "CheckNextWeekPlans",
            "No": "AskToDiscussPlan"
        }
    },
    "AskToDiscussPlan": {
        "text": "Ask the user if they would like to discuss the plan '${current_plan}'.",
        "temperature": 1
    },
    "CheckNextWeekPlans": {
        "text": "Did the user explictly mention in the recent conversation history which upcoming week's sessions for plan ${current_plan}' he is intending on doing? Note that a mention that no adjustments are needed is also an explicit mention and should be answered with 'Yes'",
        "connections": {
            "Yes": "CheckSuggestedChanges",
            "No": "AskNextWeekPlans"
        }
    },
    "AskNextWeekPlans": {
        "text": "Remind the user of his upcoming week planned sessions for '${current_plan}' and ask what's his plans about it / if he plans on doing them all.",
        "temperature": 1
    },
    "CheckSuggestedChanges": {
        "text": "Based on recent conversation history, do you suggest any change to '${current_plan}' upcoming week's sessions? Note that the frequency of the sessions is much more important than the day of the week.",
        "connections": {
            "Yes": "SuggestedChanges",
            "No": "NextPlan"
        }
    },
    "SuggestedChanges": {
        "text": "Analyse and suggest changes for plan '${current_plan}'. You can only make changes to the plan sessions date & details.",
        "temperature": 1,
        "schema": SuggestedNextWeekSessions,
        "connections": {"default": "InformTheUsreAboutTheChanges"}
    },
    "InformTheUsreAboutTheChanges": {
        "text": "Inform the user that you've generated some upcoming week changes, which he needs to accept or reject."
    },
    "NextPlan": {
        "type": "loop_continue",
        "connections": {
            "HasMore": "StartPlanLoop",
            "Complete": "Conclude"
        }
    },
    "Conclude": {
        "text": "Wrap up the conversation with a summary of what was discussed and what actions were decided.",
        "temperature": 1
    }
}


class WeekAnalyserAssistant(object):
    def __init__(
        self,
        user: User,
        user_activities: List[Activity],
        user_plans: List[Plan],
        memory: Memory,
    ):
        self.name = "Jarvis"
        self.memory = memory
        self.user = user
        self.user_activities = user_activities
        self.user_plans = user_plans

    def get_response(
        self, user_input: str, message_id: str, emotions: List[Emotion] = []
    ) -> Tuple[str, ExtractedPlanSessions | None]:
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

        system_prompt = f"""You are {self.name}, an AI assistant helping the adapt their plans for the following week. 
        Respond to the user in the same language that he talks to you in.
        """

        if is_first_message_in_more_than_a_day:
            flowchart = first_message_flowchart
        else:
            flowchart = every_message_flowchart

        framework = FlowchartLLMFramework(
            flowchart,
            system_prompt,
        )

        result, extracted = framework.run(
            f"""
        Here's the user's plan list of {len(self.user_plans)} plans:
        {plan_controller.get_readable_plans_and_sessions(self.user.id, past_day_limit=max(6, datetime.now().isoweekday()))}

        Here's user's logged activities during last week:
        {activities_gateway.get_readable_recent_activity_entries(self.user.id, past_day_limit=max(6, datetime.now().isoweekday()))}
                               
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

        # Create a mapping of plan names to IDs TODO: this assumes that the plan present plan name is unique
        plan_name_to_id = {plan.goal: plan.id for plan in self.user_plans}

        return result, (
            ExtractedPlanSessions(
                plan_id=plan_name_to_id[extracted["SuggestedChanges"].plan_name],
                sessions=extracted["SuggestedChanges"].next_week_sessions
            )
            if "SuggestedChanges" in extracted
            else None
        )