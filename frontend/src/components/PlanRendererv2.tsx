import { useState, useEffect, useMemo, useCallback } from "react";
import {
  format,
  parseISO,
  isToday,
  isBefore,
  isFuture,
  startOfWeek,
  endOfWeek,
  addWeeks,
  subWeeks,
  isAfter,
} from "date-fns";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";
import {
  ApiPlan,
  Activity,
  useUserPlan,
  UserDataEntry,
  PlanGroupMember,
  convertApiPlanToPlan,
} from "@/contexts/UserPlanContext";
import { LineChart } from "@/components/charts/line";
import { Loader2, PlusSquare } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import {
  SmallActivityEntryCard,
  Entry,
} from "@/components/SmallActivityEntryCard";
import PlanActivityEntriesRenderer from "./PlanActivityEntriesRenderer";
import PlanSessionsRenderer from "./PlanSessionsRenderer";
import { Switch } from "./ui/switch";
import Link from "next/link";
import { Button } from "./ui/button";
import { WeeklyCompletionCard } from "./WeeklyCompletionCard";
import { WeeklySessionsChecklist } from "./WeeklySessionsChecklist";

interface PlanRendererv2Props {
  selectedPlan: ApiPlan;
}

export function PlanRendererv2({ selectedPlan }: PlanRendererv2Props) {
  const { useUserDataQuery, useMultipleUsersDataQuery, fetchUserData } =
    useUserPlan();
  const { data: userData } = useUserDataQuery("me");
  const [loading, setLoading] = useState(true);

  // Get usernames of all plan group members except current user
  const memberUsernames = useMemo(() => {
    if (!selectedPlan.plan_group_id || !userData?.user?.username) return [];

    const group = userData?.planGroups.find(
      (group) => group.id === selectedPlan.plan_group_id
    );

    return (group?.members || [])
      .map((member) => member.username)
      .filter((username) => username !== userData?.user?.username);
  }, [selectedPlan.plan_group_id, userData]);

  const { data: membersData } = useMultipleUsersDataQuery(memberUsernames);

  // Replace getUserData function with this helper
  const getMemberData = (username: string): UserDataEntry | undefined => {
    if (username === "me" || username === userData?.user?.username)
      return userData;
    return membersData?.[username];
  };

  const [sessionData, setSessionData] = useState<
    { week: string; [key: string]: number | string }[]
  >([]);
  const [selectedSession, setSelectedSession] = useState<
    ApiPlan["sessions"][0] | null
  >(null);
  const [displayFutureActivities, setDisplayFutureActivities] = useState(false);

  // Get current user's activities
  const activities = useMemo(() => {
    return userData?.activities || [];
  }, [userData]);

  const activityEntries = useMemo(() => {
    return userData?.activityEntries || [];
  }, [userData]);

  // Get plan group members and their associated plans
  const { planGroupMembers, memberPlans } = useMemo(() => {
    if (!selectedPlan.plan_group_id)
      return { planGroupMembers: [], memberPlans: new Map() };

    const group = userData?.planGroups.find(
      (group) => group.id === selectedPlan.plan_group_id
    );

    // Fetch data for all members except current user
    group?.members?.forEach((member) => {
      if (member.username !== userData?.user?.username) {
        fetchUserData({ username: member.username });
      }
    });

    // Get each member's plan from the plan group
    const memberPlans = new Map<string, ApiPlan>();
    group?.members?.forEach((member) => {
      const memberData = getMemberData(member.username);
      const memberPlan = memberData?.plans.find(
        (p) => p.plan_group_id === selectedPlan.plan_group_id
      );
      if (memberPlan) {
        memberPlans.set(member.username, memberPlan);
      }
    });

    return {
      planGroupMembers: group?.members || [],
      memberPlans,
    };
  }, [selectedPlan, userData?.planGroups, membersData]);

  // Add this helper function near the top of the component
  const getCompletedSessionsForPlan = useCallback(
    (plan: ApiPlan, startDate?: Date, endDate?: Date) => {
      const userId = plan.user_id;
      const username = planGroupMembers.find(
        (m) => m.user_id === userId
      )?.username;
      if (!username) return [];

      const memberData = getMemberData(username);
      if (!memberData) return [];

      // Get all completed entries that match plan activities
      const planActivityIds = new Set(plan.sessions.map((s) => s.activity_id));

      let completedEntries = memberData.activityEntries.filter((entry) =>
        planActivityIds.has(entry.activity_id)
      );

      // Filter by date range if provided
      if (startDate && endDate) {
        completedEntries = completedEntries.filter((entry) => {
          const entryDate = parseISO(entry.date);
          return entryDate >= startDate && entryDate <= endDate;
        });
      }

      return completedEntries;
    },
    [userData, planGroupMembers, membersData]
  );

  // Modify the useEffect for session data calculation
  useEffect(() => {
    const calculateSessionData = () => {
      setLoading(true);
      if (!selectedPlan || !selectedPlan.plan_group_id) {
        setLoading(false);
        return;
      }

      // Get all plans in the group
      const groupPlans = planGroupMembers
        .map((member) => {
          const memberData = getMemberData(member.username);
          return memberData?.plans.find(
            (p) => p.plan_group_id === selectedPlan.plan_group_id
          );
        })
        .filter((p): p is ApiPlan => p !== undefined);

      // Get all dates from plans and completed entries
      const allDates = [
        ...groupPlans.flatMap((plan) => {
          if (plan.outline_type === "times_per_week") {
            // For times_per_week plans, generate dates based on times_per_week
            const startDate = new Date();
            return Array.from({ length: 12 }).map((_, i) => {
              const date = new Date();
              date.setDate(date.getDate() - (7 * i));
              return date;
            });
          }
          return plan.sessions.map((s) => parseISO(s.date));
        }),
        ...groupPlans.flatMap((plan) =>
          getCompletedSessionsForPlan(plan).map((e) => parseISO(e.date))
        ),
      ].sort((a, b) => a.getTime() - b.getTime());

      if (allDates.length === 0) {
        setLoading(false);
        return;
      }

      // Calculate weekly data
      const startDate = subWeeks(startOfWeek(allDates[0]), 1);
      const endDate = addWeeks(endOfWeek(allDates[allDates.length - 1]), 1);
      const weeklyData: {
        [key: string]: { [username: string]: number; planned: number };
      } = {};

      let currentWeek = startDate;
      while (currentWeek <= endDate) {
        const weekKey = format(currentWeek, "yyyy-MM-dd");
        const weekEnd = endOfWeek(currentWeek);

        weeklyData[weekKey] = { planned: 0 };

        // Calculate planned sessions for this week
        if (selectedPlan.outline_type === "times_per_week") {
          weeklyData[weekKey].planned = selectedPlan.times_per_week || 0;
        } else {
          const plannedThisWeek = selectedPlan.sessions.filter((session) => {
            const sessionDate = parseISO(session.date);
            return sessionDate >= currentWeek && sessionDate <= weekEnd;
          }).length;
          weeklyData[weekKey].planned += plannedThisWeek;
        }

        // Calculate data for each user in the plan group
        groupPlans.forEach((plan) => {
          const member = planGroupMembers.find((m) => m.user_id === plan.user_id);
          if (!member) return;

          // Count completed sessions this week
          const completedThisWeek = getCompletedSessionsForPlan(
            plan,
            currentWeek,
            weekEnd
          ).length;
          weeklyData[weekKey][member.username] = completedThisWeek;
        });

        currentWeek = addWeeks(currentWeek, 1);
      }

      // Format data for chart
      const formattedData = Object.entries(weeklyData).map(([week, data]) => ({
        week: format(parseISO(week), "MMM d, yyyy"),
        planned: data.planned,
        ...Object.fromEntries(
          planGroupMembers.map((member) => [
            member.username,
            data[member.username] || 0,
          ])
        ),
      }));
      setSessionData(formattedData);
      setLoading(false);
    };

    calculateSessionData();
  }, [selectedPlan, userData, membersData]);

  const isSessionCompleted = (session: ApiPlan["sessions"][0]) => {
    const sessionDate = parseISO(session.date);
    const weekStart = startOfWeek(sessionDate);
    const weekEnd = endOfWeek(sessionDate);

    const plannedSessionsThisWeek = selectedPlan.sessions
      .filter((s) => {
        const sDate = parseISO(s.date);
        return (
          s.activity_id === session.activity_id &&
          sDate >= weekStart &&
          sDate <= weekEnd
        );
      })
      .sort((a, b) => parseISO(a.date).getTime() - parseISO(b.date).getTime());

    const completedSessionsThisWeek = activityEntries
      .filter(
        (entry) =>
          entry.activity_id === session.activity_id &&
          parseISO(entry.date) >= weekStart &&
          parseISO(entry.date) <= weekEnd
      )
      .sort((a, b) => parseISO(a.date).getTime() - parseISO(b.date).getTime());

    const sessionIndex = plannedSessionsThisWeek.findIndex(
      (s) => s.date === session.date
    );
    return completedSessionsThisWeek.length > sessionIndex;
  };

  const getCompletedOn = (session: ApiPlan["sessions"][0]) => {
    const sessionDate = parseISO(session.date);
    const weekStart = startOfWeek(sessionDate);
    const weekEnd = endOfWeek(sessionDate);

    const plannedSessionsThisWeek = selectedPlan.sessions
      .filter((s) => {
        const sDate = parseISO(s.date);
        return (
          s.activity_id === session.activity_id &&
          sDate >= weekStart &&
          sDate <= weekEnd
        );
      })
      .sort((a, b) => parseISO(a.date).getTime() - parseISO(b.date).getTime());

    const completedSessionsThisWeek = activityEntries
      .filter(
        (entry) =>
          entry.activity_id === session.activity_id &&
          parseISO(entry.date) >= weekStart &&
          parseISO(entry.date) <= weekEnd
      )
      .sort((a, b) => parseISO(a.date).getTime() - parseISO(b.date).getTime());

    const sessionIndex = plannedSessionsThisWeek.findIndex(
      (s) => s.date === session.date
    );

    return completedSessionsThisWeek[sessionIndex]?.date
      ? parseISO(completedSessionsThisWeek[sessionIndex]?.date)
      : undefined;
  };

  const prepareCalendarData = (plan: ApiPlan) => {
    const sessions = plan.sessions.map((session) => ({
      ...session,
      date: parseISO(session.date),
    }));
    const dates = sessions.map((session) => session.date);
    const sessionsMap = new Map(
      sessions.map((session) => [format(session.date, "yyyy-MM-dd"), session])
    );

    return { dates, sessionsMap };
  };

  const renderSessionDetails = (
    session: ApiPlan["sessions"][0],
    activity: Activity | undefined
  ) => {
    const sessionDate =
      typeof session.date === "string" ? parseISO(session.date) : session.date;

    return (
      <div className="mb-4 p-4 bg-gray-100 rounded-lg">
        <h3 className="text-lg font-semibold mb-2">
          📆 {format(sessionDate, "EEEE, MMMM d")}
        </h3>
        <ul className="list-disc list-inside mb-2">
          <li>
            {session.quantity} {activity?.measure} of {activity?.title}
          </li>
        </ul>
        <p className="text-sm text-gray-600">{session.descriptive_guide}</p>
      </div>
    );
  };

  function getMemberUsername(member: PlanGroupMember) {
    return member.username === userData?.user?.username
      ? "me"
      : member.username;
  }

  // Add this helper function near other helper functions
  const areAllWeeklyActivitiesCompleted = useCallback(() => {
    const currentWeekStart = startOfWeek(new Date());
    const currentWeekEnd = endOfWeek(new Date());

    const thisWeekSessions = selectedPlan.sessions.filter((session) => {
      const sessionDate = parseISO(session.date);
      return sessionDate >= currentWeekStart && sessionDate <= currentWeekEnd;
    });

    return (
      thisWeekSessions.length > 0 &&
      thisWeekSessions.every((session) => isSessionCompleted(session))
    );
  }, [selectedPlan.sessions, isSessionCompleted]);

  return (
    <div>
      {selectedPlan.outline_type === "specific" &&
        areAllWeeklyActivitiesCompleted() && <WeeklyCompletionCard />}
      {planGroupMembers && planGroupMembers.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-lg font-semibold mb-2">People in this plan</h2>
          <div className="flex flex-row flex-wrap gap-6">
            {planGroupMembers.map((member) => (
              <div
                key={member.user_id}
                className="flex flex-row flex-nowrap gap-2 items-center"
              >
                <Link href={`/profile/${member.username}`}>
                  <Avatar className="w-12 h-12 text-2xl">
                    <AvatarImage
                      src={member.picture || ""}
                      alt={member.name || member.username}
                    />
                    <AvatarFallback>{member.name?.[0] || "U"}</AvatarFallback>
                  </Avatar>
                </Link>
                <div className="text-lg text-gray-800">
                  {userData?.user?.username === member.username
                    ? "You"
                    : member.name}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {loading ? (
        <div className="flex items-center justify-center mt-8">
          <Loader2 className="h-8 w-8 animate-spin" />
          <span className="ml-2">Loading session data...</span>
        </div>
      ) : sessionData.length > 0 ? (
        <div className="mt-8 max-w-4xl">
          <LineChart
            data={sessionData}
            xAxisKey="week"
            lines={[
              {
                dataKey: "planned",
                name: "Planned Sessions",
                color: "hsl(var(--chart-1))",
              },
              ...planGroupMembers.map((member, index) => ({
                dataKey: member.username,
                name: `${member.name}'s Sessions`,
                color: `hsl(var(--chart-${index + 2}))`,
              })),
            ]}
            title={`Sessions Overview 📈`}
            description={`${sessionData[0].week} - ${
              sessionData[sessionData.length - 1].week
            }`}
            currentDate={new Date()}
          />
        </div>
      ) : null}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mt-8">
        <h2 className="text-2xl font-bold mb-4">
          Activities Overview {selectedPlan.emoji}
        </h2>
        {/* <div className="flex flex-row flex-wrap gap-4">
          {recentActivityEntries.length === 0 && (
            <div className="text-sm text-gray-500">
              No activity history yet.
            </div>
          )}
          {recentActivityEntries.map((entry) => {
            const activity = activities.find((a) => a.id === entry.activity_id);
            if (!activity) return null;

            return (
              <ActivityEntryCard
                key={`${entry.date}-${entry.activity_id}`}
                entry={entry}
                activity={activity}
                completed={true}
              />
            );
          })}
        </div> */}
        {selectedPlan.outline_type === "specific" && (
          <div className="flex flex-row flex-nowrap items-center gap-2 mb-4">
            <span className="text-xs text-gray-500">Completed</span>
            <Switch
              checked={displayFutureActivities}
              onCheckedChange={setDisplayFutureActivities}
            />
            <span className="text-xs text-gray-500">Planned</span>
          </div>
        )}
        {displayFutureActivities ? (
          <PlanSessionsRenderer
            plan={convertApiPlanToPlan(
              selectedPlan,
              activities.filter((a) =>
                selectedPlan.sessions.some((s) => s.activity_id === a.id)
              )
            )}
            activities={activities.filter((a) =>
              selectedPlan.sessions.some((s) => s.activity_id === a.id)
            )}
          />
        ) : (
          <PlanActivityEntriesRenderer
            plan={convertApiPlanToPlan(selectedPlan, activities)}
            activities={activities}
            activityEntries={activityEntries}
          />
        )}
        <div className="mt-8">
          {selectedPlan.outline_type === "specific" && (
            <>
              <div className="mb-4">
                <h2 className="text-lg font-semibold text-gray-800">
                  This week
                </h2>

                <span className="text-sm text-gray-500 ">
                  Completed activities are calculated on a per week count basis.
                </span>
              </div>
              <div className="flex flex-row flex-wrap gap-4">
                {selectedPlan.sessions
                  .filter((session) => {
                    const sessionDate = parseISO(session.date);
                    const endOfCurrentWeek = endOfWeek(new Date());
                    const beginningOfCurrentWeek = startOfWeek(new Date());
                    return (
                      isAfter(sessionDate, beginningOfCurrentWeek) &&
                      isBefore(sessionDate, endOfCurrentWeek)
                    );
                  })
                  .map((session) => {
                    const activity = activities.find(
                      (a) => a.id === session.activity_id
                    );
                    const completed = isSessionCompleted(session);
                    const completedOn = getCompletedOn(session);
                    if (!activity) return null;

                    return (
                      <SmallActivityEntryCard
                        key={`${session.date}-${session.activity_id}`}
                        entry={session as Entry}
                        activity={activity}
                        onClick={() => setSelectedSession(session)}
                        completed={completed}
                        completedOn={completedOn}
                      />
                    );
                  })}
              </div>
            </>
          )}

          {selectedPlan.outline_type === "times_per_week" && (
            <WeeklySessionsChecklist
              plan={selectedPlan}
              activityEntries={activityEntries}
            />
          )}
        </div>
      </div>
      {/* 
      <div className="mt-8 border border-gray-200 rounded-lg p-4 mb-8">
        <h2 className="text-2xl font-bold mb-4">Calendar</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            {selectedSession && (
              <>
                {renderSessionDetails(
                  selectedSession,
                  activities.find((a) => a.id === selectedSession.activity_id)
                )}
              </>
            )}
          </div>
          <Calendar
            mode="multiple"
            selected={prepareCalendarData(selectedPlan).dates}
            className="rounded-md border"
            components={{
              Day: ({ date, ...props }) => {
                const { sessionsMap } = prepareCalendarData(selectedPlan);
                const sessionDate = format(date, "yyyy-MM-dd");
                const session = sessionsMap.get(sessionDate);

                return (
                  <div
                    className={cn(
                      "h-9 w-9 p-0 font-normal aria-selected:opacity-100",
                      "relative flex items-center justify-center",
                      session &&
                        "bg-blue-50 h-9 w-9 rounded-full cursor-pointer",
                      session && isFuture(date) && "bg-blue-100",
                      isToday(date) && "font-extrabold",
                      isBefore(date, new Date()) &&
                        !isToday(date) &&
                        "text-gray-400"
                    )}
                    {...props}
                    onClick={() => {
                      if (session && (isFuture(date) || isToday(date))) {
                        setSelectedSession({
                          ...session,
                          date: format(
                            typeof session.date === "string"
                              ? parseISO(session.date)
                              : session.date,
                            "yyyy-MM-dd"
                          ),
                        });
                      }
                    }}
                  >
                    <span>{date.getDate()}</span>
                  </div>
                );
              },
            }}
          />
        </div>
      </div> */}

      <Link href="/add" passHref>
        <Button
          variant="outline"
          className="bg-gray-50 mt-2 w-full h-[100px] flex flex-col items-center justify-center border-2 border-dashed border-gray-300 text-gray-500"
        >
          <PlusSquare className="h-8 w-8 mb-2 text-gray-400" />
          <span>Log Activity</span>
        </Button>
      </Link>
    </div>
  );
}
