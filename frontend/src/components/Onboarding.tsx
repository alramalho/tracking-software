"use client";

import React, { useState, useEffect } from "react";
import { useApiWithAuth } from "@/api";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { DatePicker } from "@/components/ui/date-picker";
import { Calendar } from "@/components/ui/calendar";
import toast from "react-hot-toast";
import { Loader2, ShieldEllipsisIcon } from "lucide-react";
import { format, parseISO } from "date-fns";
import HeatMap from "@uiw/react-heat-map";
import { addDays } from "date-fns";
import { Badge } from "./ui/badge";

interface Plan {
  goal: string;
  finishing_date?: Date;
  sessions: { date: Date; descriptive_guide: string; quantity: number }[];
  activities: { title: string, measure: string }[];
  intensity: string;
  overview: string;
}

interface ApiPlan extends Omit<Plan, 'finishing_date' | 'sessions'> {
  finishing_date?: string;
  sessions: { date: string; descriptive_guide: string; quantity: number }[];
}

const Onboarding: React.FC = () => {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [goal, setGoal] = useState("");
  const [finishingDate, setFinishingDate] = useState<Date | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [planDescription, setPlanDescription] = useState("");
  const [selectedPlanIndex, setSelectedPlanIndex] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);
  const [focusedDate, setFocusedDate] = useState<Date | null>(null);
  const [focusedActivity, setFocusedActivity] = useState<string | null>(null);

  const api = useApiWithAuth();
  const router = useRouter();

  useEffect(() => {
    // Load onboarding progress when component mounts
    const loadOnboardingProgress = async () => {
      try {
        const response = await api.get("/api/onboarding/step");
        const userData = response.data;
        if (userData.onboarding_progress) {
          setName(userData.onboarding_progress.name || "");
          setTimezone(userData.onboarding_progress.timezone || "");
          setGoal(userData.onboarding_progress.goal || "");
          setFinishingDate(userData.onboarding_progress.finishing_date ? parseISO(userData.onboarding_progress.finishing_date) : null);
          // Set the appropriate step based on progress
          // This is a simple example, you might want to implement more sophisticated logic
          if (userData.onboarding_progress.name) setStep(1);
          if (userData.onboarding_progress.timezone) setStep(2);
          if (userData.onboarding_progress.goal) setStep(3);
          if (userData.onboarding_progress.finishing_date) {
            await handleGeneratePlans();
            setStep(4);
          }
        }
      } catch (error) {
        console.error("Error loading onboarding progress:", error);
      }
    };
    loadOnboardingProgress();
  }, []);

  const saveStep = async (stepKey: string, stepValue: string) => {
    try {
      await api.post("/api/onboarding/step", { [stepKey]: stepValue });
    } catch (error) {
      console.error("Error saving onboarding step:", error);
    }
  };

  const handleGeneratePlans = async () => {
    setIsGenerating(true);
    try {
      const response = await api.post("/api/onboarding/generate-plans", {
        planDescription: planDescription.trim() || undefined
      });
      // Convert string dates to Date objects
      const plansWithDateObjects = response.data.plans.map((plan: ApiPlan) => ({
        ...plan,
        finishing_date: plan.finishing_date ? parseISO(plan.finishing_date) : undefined,
        sessions: plan.sessions.map(session => ({
          ...session,
          date: parseISO(session.date)
        }))
      }));
      setPlans(plansWithDateObjects);
      setStep(4);
    } catch (error) {
      console.error("Error generating plans:", error);
      toast.error("Failed to generate plans. Please try again.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handlePlanSelection = async (plan: Plan) => {
    try {
      await api.post("/api/onboarding/select-plan", plan);
      router.push("/dashboard");
    } catch (error) {
      console.error("Plan selection error:", error);
    }
  };

  const formatSessionsForHeatMap = (plan: Plan) => {
    const sessions = plan.sessions.map(session => ({
      date: session.date,
      count: session.quantity
    }));

    if (plan.finishing_date) {
      sessions.push({
        date: plan.finishing_date,
        count: -1
      });
    }

    return sessions;
  };

  const getActivityColor = (index: number) => {
    const colors = [
      "bg-red-200 text-red-800",
      "bg-blue-200 text-blue-800",
      "bg-green-200 text-green-800",
      "bg-yellow-200 text-yellow-800",
      "bg-purple-200 text-purple-800",
      "bg-pink-200 text-pink-800",
      "bg-indigo-200 text-indigo-800",
      "bg-gray-200 text-gray-800",
    ];
    return colors[index % colors.length];
  };

  const renderHeatMap = (plan: Plan) => {
    const today = new Date();
    const endDate = plan.finishing_date ? addDays(plan.finishing_date, 1) : undefined;
    const heatmapData = formatSessionsForHeatMap(plan);

    console.log("Plan: ", plan.intensity);
    console.log({ heatmapData });

    // Calculate min and max quantities
    const quantities = plan.sessions.map(session => session.quantity);
    const minQuantity = Math.min(...quantities);
    const maxQuantity = Math.max(...quantities);

    // Define intensity levels (excluding 0)
    const intensityLevels = 4;
    const intensityStep = (maxQuantity - minQuantity) / intensityLevels;

    // Define colors array (first color is for 0 quantity)
    const colors = ["#EBEDF0", "#9BE9A8", "#40C463", "#30A14E", "#216E39", "#E16A42"];

    return (
      <div className="mb-4">
        <HeatMap
          value={heatmapData}
          startDate={today}
          endDate={endDate}
          height={200}
          rectSize={14}
          legendCellSize={12}
          rectProps={{
            rx: 3,
          }}
          rectRender={(props, data) => {
            // Determine intensity level
            let intensityLevel;
            if (data.count === -1) {
              intensityLevel = 5; // Special case for finishing date
            } else if (data.count === undefined || data.count === null || data.count === 0) {
              intensityLevel = 0; // Special case for no data or 0 quantity
            } else {
              intensityLevel = Math.min(Math.floor((data.count - minQuantity) / intensityStep) + 1, intensityLevels);
            }
            
            // Ensure intensityLevel is within the valid range
            intensityLevel = Math.max(0, Math.min(intensityLevel, colors.length - 1));
            
            // Assign color based on intensity level
            props.fill = colors[intensityLevel];

            return (
              <rect
                key={data.index}
                {...props}
                onClick={() => {
                  // Parse the date string correctly
                  const clickedDate = new Date(data.date);
                  if (!isNaN(clickedDate.getTime())) {
                    setFocusedDate(clickedDate);
                    setFocusedActivity(null);
                  } else {
                    console.error("Invalid date:", data.date);
                  }
                }}
              />
            );
          }}
          legendRender={(props) => (
            // @ts-ignore
            <rect {...props} y={props.y + 10} rx={props.range} />
          )}
        />
        <div className="flex justify-center mt-4">
          {renderActivityViewer(plan)}
        </div>
      </div>
    );
  };

  const renderActivityViewer = (plan: Plan) => {
    if (!focusedDate) return null;


    const sessionsOnDate = plan.sessions.filter(
      session => format(session.date, 'yyyy-MM-dd') === format(focusedDate, 'yyyy-MM-dd')
    );

    console.log({sessionsOnDate});

    const isFinishingDate = plan.finishing_date && 
      format(plan.finishing_date, 'yyyy-MM-dd') === format(focusedDate, 'yyyy-MM-dd');

    console.log({isFinishingDate});

    return (
      <div className="mt-4 p-4 border rounded-lg bg-white w-full max-w-md w-96">
        <h3 className="text-lg font-semibold mb-2">
          {isFinishingDate ? (
            <span >🎉 Finishing Date: {format(focusedDate, 'MMMM d, yyyy')}</span>
          ) : (
            `Activities on ${format(focusedDate, 'MMMM d, yyyy')}`
          )}
        </h3>
        {isFinishingDate ? (
          <p>This is your goal completion date!</p>
        ) : sessionsOnDate.length === 0 ? (
          <p>No activities scheduled for this date.</p>
        ) : (
          <div>
            {sessionsOnDate.map((session, index) => (
              <div key={index} className="p-2 mb-2 rounded border border-gray-200">
                <div className="flex flex-wrap gap-2 mb-2">
                  {plan.activities.map((activity, actIndex) => (
                    <Badge key={actIndex} className={`${getActivityColor(actIndex)}`}>
                      {activity.title}
                    </Badge>
                  ))}
                </div>
                <p className="text-sm font-semibold">Intensity: {session.quantity} {plan.activities[0].measure}</p>
                <p className="text-sm">{session.descriptive_guide}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderStep = () => {
    switch (step) {
      case 0:
        return (
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>What is your name?</CardTitle>
            </CardHeader>
            <CardContent>
              <Input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter your name"
                className="mb-4"
              />
              <Button
                className="w-full"
                onClick={() => {
                  saveStep("name", name);
                  setStep(1);
                }}
                disabled={!name.trim()}
              >
                Next
              </Button>
            </CardContent>
          </Card>
        );
      case 1:
        return (
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>What is your location?</CardTitle>
            </CardHeader>
            <CardContent>
              <Button
                className="w-full"
                onClick={() => {
                  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                  setTimezone(timezone);
                  saveStep("timezone", timezone);
                  setStep(2);
                  toast.success("Timezone set successfully to " + timezone);
                }}
              >
                Get Location
              </Button>
            </CardContent>
          </Card>
        );
      case 2:
        return (
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>What goal do you want to accomplish?</CardTitle>
            </CardHeader>
            <CardContent>
              <Input
                type="text"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Enter your goal"
                className="mb-4"
              />
              <Button
                className="w-full"
                onClick={() => {
                  saveStep("goal", goal);
                  setStep(3);
                }}
                disabled={!goal.trim()}
              >
                Next
              </Button>
            </CardContent>
          </Card>
        );
      case 3:
        return (
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>Do you have a finishing date? (Optional)</CardTitle>
            </CardHeader>
            <CardContent>
              <DatePicker
                selected={finishingDate!}
                onSelect={(date: Date | undefined) => setFinishingDate(date!)}
                className="mb-4"
              />
              <Button
                className="w-full"
                onClick={() => {
                  saveStep("finishing_date", finishingDate ? finishingDate.toISOString().split('T')[0] : '');
                  handleGeneratePlans();
                }}
                disabled={isGenerating}
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating Plans...
                  </>
                ) : (
                  "Generate Plans"
                )}
              </Button>
            </CardContent>
          </Card>
        );
      case 4:
        return (
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle>Select a Plan</CardTitle>
            </CardHeader>
            <CardContent>
              <Textarea
                placeholder="Describe your ideal plan (optional)"
                value={planDescription}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setPlanDescription(e.target.value)}
                className="mb-4"
              />
              <Button
                className="w-full mb-4"
                onClick={() => handleGeneratePlans()}
                disabled={isGenerating}
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Regenerating Plans...
                  </>
                ) : (
                  "Regenerate Plans"
                )}
              </Button>
              <p>Goal: {goal}</p>
              {plans.map((plan, index) => (
                <Card key={index} className="mb-8">
                  <CardHeader>
                    <CardTitle>Plan {index + 1} - {plan.intensity} Intensity</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p>Finishing Date: {plan.finishing_date ? format(plan.finishing_date, 'yyyy-MM-dd') : "Not specified"}</p>
                    <p>Number of sessions: {plan.sessions.length}</p>
                    <div className="mt-4 mb-4">
                      <h3 className="text-lg font-semibold mb-2">Plan Overview:</h3>
                      <p className="text-sm text-gray-600">{plan.overview}</p>
                    </div>
                    {renderHeatMap(plan)}
                    <Button
                      className="w-full mt-2"
                      onClick={() => handlePlanSelection(plan)}
                    >
                      Select This Plan
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </CardContent>
          </Card>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col items-center justify-center p-4">
      <h1 className="text-2xl font-bold mb-8">Welcome to the Onboarding Process</h1>
      {renderStep()}
    </div>
  );
};

export default Onboarding;