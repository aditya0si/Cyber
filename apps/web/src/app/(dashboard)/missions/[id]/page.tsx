/**
 * Mission theater route (docs/14 §3) — authed mode.
 * Data orchestration lives in useMissionSession; the theater is MissionStage.
 */

"use client";

import { useParams } from "next/navigation";

import { MissionStage } from "@/components/mission/MissionStage";
import { useMissionSession } from "@/components/mission/useMissionSession";
import { Spinner } from "@/components/ui/Spinner";

export default function MissionTheaterPage() {
  const params = useParams<{ id: string }>();
  const session = useMissionSession(params.id);

  if (!session.mission) {
    return (
      <div className="flex justify-center p-16">
        <Spinner size={20} />
      </div>
    );
  }

  return (
    <MissionStage
      mission={session.mission}
      simId={session.simId}
      status={session.status}
      events={session.events}
      detections={session.detections}
      score={session.score}
      lastAction={session.lastAction}
      shareUrl={session.shareUrl}
      judge={false}
      starting={session.starting}
      notice={session.notice}
      onStart={session.start}
      onExecute={session.execute}
    />
  );
}
