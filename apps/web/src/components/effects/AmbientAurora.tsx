export default function AmbientAurora({ className = "" }: { className?: string }) {
  return (
    <div className={`xagent-ambient pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden="true">
      <span className="xagent-ambient__halo xagent-ambient__halo--gold" />
      <span className="xagent-ambient__halo xagent-ambient__halo--red" />
      <span className="xagent-ambient__ring" />
      <span className="xagent-ambient__grain" />
    </div>
  );
}
