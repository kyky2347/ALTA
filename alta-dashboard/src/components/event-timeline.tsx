import { useEffect, useMemo, useState } from "react";
import { Clock3, Pause, Play, Radio, Rewind } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { clockTime, titleCase } from "@/lib/display";
import type { AltaEvent, SelectedEntity } from "@/lib/types";

export function EventTimeline({
  events,
  onSelect,
}: {
  events: AltaEvent[];
  onSelect: (entity: SelectedEntity) => void;
}) {
  const items = useMemo(
    () => [...events].sort((a, b) => a.cursor - b.cursor),
    [events],
  );
  const [playCursor, setPlayCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const activeIndex =
    playCursor === null
      ? Math.max(0, items.length - 1)
      : Math.max(
          0,
          items.findIndex((event) => event.cursor === playCursor),
        );
  const active = items[activeIndex];

  useEffect(() => {
    if (!playing || !items.length) return;
    const timer = window.setInterval(() => {
      setPlayCursor((current) => {
        const currentIndex =
          current === null
            ? 0
            : Math.max(
                0,
                items.findIndex((event) => event.cursor === current),
              );
        if (currentIndex >= items.length - 1) {
          setPlaying(false);
          return null;
        }
        return items[currentIndex + 1].cursor;
      });
    }, 1100);
    return () => window.clearInterval(timer);
  }, [items, playing]);

  function selectAt(index: number) {
    const event = items[index];
    if (!event) return;
    setPlayCursor(event.cursor);
    onSelect({
      kind: "event",
      id: event.eventId,
      label: titleCase(event.eventType),
      summary: event as unknown as Record<string, unknown>,
    });
  }

  return (
    <section className="timeline" aria-label="Recent event replay">
      <div className="timeline-label">
        <Rewind />
        <span>Replay ribbon</span>
        <small>{items.length} loaded durable events</small>
      </div>
      <div className="timeline-player">
        <div className="timeline-readout">
          <strong>
            {active ? titleCase(active.eventType) : "Waiting for events"}
          </strong>
          <span>
            {active
              ? `${clockTime(active.knownAt)} · #${active.cursor}`
              : "No replay range"}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, items.length - 1)}
          value={activeIndex}
          disabled={!items.length}
          onChange={(event) => selectAt(Number(event.target.value))}
          aria-label="Replay loaded decision history"
        />
        <div className="timeline-scale">
          <span>{clockTime(items[0]?.knownAt)}</span>
          <span className="timeline-playhead">
            {playCursor === null ? "LIVE" : "REPLAY"}
          </span>
          <span>{clockTime(items.at(-1)?.knownAt)}</span>
        </div>
        {!items.length && (
          <div className="timeline-waiting">
            <Clock3 /> Waiting for the first event
          </div>
        )}
      </div>
      <div className="timeline-controls">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              disabled={!items.length}
              aria-label={playing ? "Pause replay" : "Play replay"}
              onClick={() => {
                if (!playing && playCursor === null)
                  setPlayCursor(items[0]?.cursor ?? null);
                setPlaying((current) => !current);
              }}
            >
              {playing ? <Pause /> : <Play />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {playing ? "Pause replay" : "Play loaded history"}
          </TooltipContent>
        </Tooltip>
        <Button
          variant="outline"
          size="sm"
          className="live-button"
          onClick={() => {
            setPlaying(false);
            setPlayCursor(null);
            const event = items.at(-1);
            if (event) selectAt(items.length - 1);
            setPlayCursor(null);
          }}
        >
          <Radio data-icon="inline-start" /> Live now
        </Button>
      </div>
    </section>
  );
}
