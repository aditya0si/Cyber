/**
 * Public judge mode (docs/14 §5): /m/[token] — no signup, token-addressed.
 * Rendered outside (dashboard) so no auth gate applies.
 */

"use client";

import { useParams } from "next/navigation";

import { MissionStage } from "@/components/mission/MissionStage";
import { useMissionSession } from "@/components/mission/useMissionSession";
import { Spinner } from "@/components/ui/Spinner";

export default function PublicMissionPage() {
  const params = useParams<{ token: string }>();
  const session = useMissionSession(null, params.token);

  if (!session.mission) {
    return (
      <div className="bg-cs-neutral-0 text-cs-text-primary flex h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Spinner size={20} />
          <p className="text-cs-text-secondary text-sm">
            {session.notice ?? "Opening mission…"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-cs-neutral-0 text-cs-text-primary h-screen">
      <MissionStage
        mission={session.mission}
        simId={session.simId}
        status={session.status}
        events={session.events}
        detections={session.detections}
        score={session.score}
        lastAction={session.lastAction}
        shareUrl={null}
        judge
        starting={false}
        notice={session.notice}
        onStart={async () => undefined}
        onExecute={session.execute}
      />
    </div>
  );
}
