import {
  Bot,
  Compass,
  MessagesSquare,
  Scale,
  ShieldCheck,
  Waypoints,
} from "lucide-react";

/** Presentation only: role imagery never represents execution permission. */
export function AgentMark({ role }: { role: string }) {
  const Icon = /audit/i.test(role)
    ? ShieldCheck
    : /expression/i.test(role)
      ? Waypoints
      : /moderator|committee/i.test(role)
        ? MessagesSquare
        : /counter|skeptic|disconfirm|risk/i.test(role)
          ? Scale
          : /scout|flow|discovery|research/i.test(role)
            ? Compass
            : Bot;
  return <Icon aria-hidden="true" />;
}
