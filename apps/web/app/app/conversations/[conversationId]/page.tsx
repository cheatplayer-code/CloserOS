import { ConversationDetailPage } from "../../../../components/workspace/conversation-detail-page";

interface PageProps {
  params: Promise<{ conversationId: string }>;
}

export default async function Page({ params }: PageProps) {
  const { conversationId } = await params;
  return <ConversationDetailPage conversationId={conversationId} />;
}
