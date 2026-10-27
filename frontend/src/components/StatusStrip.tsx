import { Bot, Clock, Globe, Pause, RefreshCw } from "lucide-react";
import type { CSSProperties } from "react";
import type { ShellStatus } from "../api/placeholder";
import { rampPercent } from "../lib/ramp";
import { formatTime, timeZoneName } from "../lib/time";
import { Tip } from "./Tip";

/**
 * The status strip (UI-SHELL, 05 section 5): auto-apply, trust ramp, last sync, next snapshot, and the time zone
 * every time on screen is in. One line of text-sm. A tooltip carries the reason where there is one (13 section 6).
 */
export function StatusStrip({ status }: { status: ShellStatus }) {
  const { autoApply, trustRamp, lastSyncAt, nextSnapshot } = status;
  const zone = timeZoneName();
  const ramp = rampPercent(trustRamp.count, trustRamp.target);
  const rampStyle = { "--ramp": `${ramp}%` } as CSSProperties;

  return (
    <section className="status-strip" aria-label="Status">
      {autoApply.kind === "off_trust_ramp" && (
        <Tip content={`Auto-apply stays off until the trust ramp reaches ${trustRamp.target}.`}>
          <button type="button" className="status-strip__item">
            <Bot className="icon" />
            Auto-apply <strong>off</strong>
          </button>
        </Tip>
      )}
      {autoApply.kind === "paused_brake" && (
        <Tip content={autoApply.reason}>
          <button type="button" className="status-strip__item">
            <Pause className="icon" />
            Auto-apply <strong>paused</strong>
          </button>
        </Tip>
      )}
      {autoApply.kind === "on" && (
        <span className="status-strip__item">
          <Bot className="icon" />
          Auto-apply <strong>on</strong>
        </span>
      )}
      <span className="status-strip__item">
        Trust ramp{" "}
        <strong className="num">
          {trustRamp.count} / {trustRamp.target}
        </strong>
        <span className="ramp-meter" style={rampStyle} aria-hidden="true">
          <span />
        </span>
      </span>
      <span className="status-strip__item">
        <RefreshCw className="icon" />
        Last sync <strong className="num">{lastSyncAt === null ? "not yet" : formatTime(new Date(lastSyncAt))}</strong>
      </span>
      {nextSnapshot !== null && (
        <span className="status-strip__item">
          <Clock className="icon" />
          Next snapshot <strong className="num">{nextSnapshot}</strong>
        </span>
      )}
      {zone && (
        <Tip content={`Times in ${zone}`}>
          <button type="button" className="status-strip__item">
            <Globe className="icon" />
            {zone}
          </button>
        </Tip>
      )}
    </section>
  );
}
