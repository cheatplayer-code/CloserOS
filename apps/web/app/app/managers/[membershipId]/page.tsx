import { ManagerScorecardPage } from "../../../../components/workspace/manager-scorecard-page";

interface PageProps {
  params: Promise<{ membershipId: string }>;
}

export default async function Page({ params }: PageProps) {
  const { membershipId } = await params;
  return <ManagerScorecardPage membershipId={membershipId} />;
}
