import { TaskDetailPage } from "../../../../components/workspace/task-detail-page";

interface PageProps {
  params: Promise<{ taskId: string }>;
}

export default async function Page({ params }: PageProps) {
  const { taskId } = await params;
  return <TaskDetailPage taskId={taskId} />;
}
