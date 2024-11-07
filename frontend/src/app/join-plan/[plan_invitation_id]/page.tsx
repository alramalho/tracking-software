import { Metadata, ResolvingMetadata } from "next";
import ClientPage from "./ClientPage";
import { ApiPlan, Plan, Activity, countAverageSessionsPerWeek } from "@/contexts/UserPlanContext";

type Props = {
  params: { plan_invitation_id: string }
}

export const dynamic = 'force-dynamic'

interface PlanData {
  plan: ApiPlan;
  plan_activities: Activity[];
  inviter: {
    id: string;
    name: string;
    username: string;
    picture: string;
  };
}

export async function generateMetadata(
  { params }: Props,
  parent: ResolvingMetadata
): Promise<Metadata> {
  try {
    const planData = await fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL}/get-plan-from-invitation-id/${params.plan_invitation_id}`
    ).then((res) => {
      if (!res.ok) throw new Error("Failed to fetch plan data");
      return res.json();
    });

    const title = `Join ${planData.inviter.name}'s on '${planData.plan.goal}' ${planData.plan.emoji}`;
    const description = `${planData.inviter.name} has invited you to join their plan '${planData.plan.goal}' ${planData.plan.emoji} on self.tracking.so`;

    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || "https://self.tracking.so";
    const ogImageUrl = new URL("/api/og", baseUrl);
    ogImageUrl.searchParams.append("planName", planData.plan.goal);
    ogImageUrl.searchParams.append("inviterName", planData.inviter.name);
    ogImageUrl.searchParams.append("emoji", planData.plan.emoji);
    const averageSessionsPerWeek = countAverageSessionsPerWeek(planData.plan);
    ogImageUrl.searchParams.append("sessionsPerWeekCount", averageSessionsPerWeek.toString());

    return {
      title,
      description,
      openGraph: {
        title,
        description,
        type: "website",
        url: `https://self.tracking.so/join-plan/${params.plan_invitation_id}`,
        images: [{
          url: ogImageUrl.toString(),
          width: 1200,
          height: 630,
          alt: title,
        }],
      },
      twitter: {
        card: "summary_large_image",
        title,
        description,
        images: [ogImageUrl.toString()],
      },
    };
  } catch (error) {
    console.error("Error generating metadata:", error);
    return {
      title: "Join Plan - self.tracking.so",
      description: "Join a plan on self.tracking.so",
    };
  }
}

export default function Page({ params }: Props) {
  return <ClientPage params={params} />;
}
