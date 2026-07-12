import { WhatsAppConnectionDetailPage } from "../../../../../components/settings/whatsapp-integration-pages";

interface PageProps {
  params: Promise<{ connectionId: string }>;
}

export default async function Page({ params }: PageProps) {
  const { connectionId } = await params;
  return <WhatsAppConnectionDetailPage connectionId={connectionId} />;
}
