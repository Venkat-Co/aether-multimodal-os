import { Canvas, useFrame } from "@react-three/fiber";
import { Float, OrbitControls, Sphere, Torus } from "@react-three/drei";
import { useEffect, useState } from "react";

type DashboardState = {
  generated_at: string;
  status: string;
  streams: Array<Record<string, unknown>>;
  fusion: Array<Record<string, unknown>>;
  alerts: Array<Record<string, unknown>>;
  reasoning: Array<Record<string, unknown>>;
  memory_updates: Array<Record<string, unknown>>;
  agents: Array<Record<string, unknown>>;
  agent_runs: Array<Record<string, unknown>>;
  latest_action?: Record<string, unknown>;
};

type Tone = "cyan" | "amber" | "red" | "mint" | "slate";

type MetricModel = {
  label: string;
  value: string;
  detail: string;
  progress: number;
  tone: Tone;
};

type InsightModel = {
  lane: string;
  title: string;
  summary: string;
  meta: string[];
  tone: Tone;
  timestamp: string;
  relativeTime: string;
};

type ActivityModel = {
  lane: string;
  title: string;
  detail: string;
  tone: Tone;
  timestamp: string;
  sortKey: number;
};

type StreamRowModel = {
  sourceId: string;
  modality: string;
  detail: string;
  timestamp: string;
  relativeTime: string;
  tone: Tone;
};

const initialState: DashboardState = {
  generated_at: new Date().toISOString(),
  status: "connecting",
  streams: [],
  fusion: [],
  alerts: [],
  reasoning: [],
  memory_updates: [],
  agents: [],
  agent_runs: [],
};

const orbitalNodes: Array<{ position: [number, number, number]; color: string; scale: number }> = [
  { position: [2.8, 0.18, 0.24], color: "#8ee9ff", scale: 0.18 },
  { position: [-2.6, -0.2, 0.18], color: "#f8c271", scale: 0.16 },
  { position: [0.9, 2.2, -0.22], color: "#8ce7bb", scale: 0.15 },
  { position: [-0.8, -2.2, 0.32], color: "#ff8e7a", scale: 0.14 },
];

function NeuralCore() {
  useFrame(({ clock, scene }) => {
    const node = scene.getObjectByName("neural-core");
    if (node) {
      node.rotation.y = clock.getElapsedTime() * 0.11;
      node.rotation.x = Math.sin(clock.getElapsedTime() * 0.18) * 0.08;
    }
  });

  return (
    <group name="neural-core">
      <Float speed={2.2} rotationIntensity={0.18} floatIntensity={0.38}>
        <Sphere args={[1.24, 72, 72]} position={[0, 0, 0]}>
          <meshStandardMaterial color="#a9ecff" emissive="#36bce5" emissiveIntensity={0.72} roughness={0.16} metalness={0.45} />
        </Sphere>
      </Float>

      <Float speed={1.9} rotationIntensity={0.28} floatIntensity={0.18}>
        <Torus args={[2.38, 0.06, 32, 180]} rotation={[Math.PI / 2, 0.24, 0]}>
          <meshStandardMaterial color="#f4ba67" emissive="#d8712f" emissiveIntensity={0.56} roughness={0.3} metalness={0.62} />
        </Torus>
      </Float>

      <Float speed={1.65} rotationIntensity={0.24} floatIntensity={0.16}>
        <Torus args={[3.12, 0.035, 32, 180]} rotation={[0.42, 0.9, 0.18]}>
          <meshStandardMaterial color="#8ce7bb" emissive="#4acf92" emissiveIntensity={0.34} roughness={0.3} metalness={0.5} />
        </Torus>
      </Float>

      {orbitalNodes.map((node, index) => (
        <Float
          key={index}
          speed={1.45 + index * 0.25}
          rotationIntensity={0.3 + index * 0.08}
          floatIntensity={0.35}
        >
          <Sphere args={[node.scale, 24, 24]} position={node.position}>
            <meshStandardMaterial color={node.color} emissive={node.color} emissiveIntensity={0.76} roughness={0.2} metalness={0.55} />
          </Sphere>
        </Float>
      ))}
    </group>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function textValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function listValue(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1).trim()}…`;
}

function humanizeToken(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function normalizeConfidence(value: number | undefined): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  return value > 1 ? value / 100 : value;
}

function clampProgress(value: number | undefined): number {
  if (value === undefined || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(value, 1));
}

function timestampMillis(value: unknown): number {
  if (typeof value !== "string") {
    return 0;
  }

  const millis = new Date(value).getTime();
  return Number.isNaN(millis) ? 0 : millis;
}

function formatClock(value: unknown): string {
  const millis = timestampMillis(value);
  if (millis === 0) {
    return "Live";
  }

  return new Date(millis).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatRelativeTime(value: unknown, nowMs: number): string {
  const millis = timestampMillis(value);
  if (millis === 0) {
    return "Live";
  }

  const deltaSeconds = Math.max(0, Math.floor((nowMs - millis) / 1000));
  if (deltaSeconds < 5) {
    return "Just now";
  }
  if (deltaSeconds < 60) {
    return `${deltaSeconds}s ago`;
  }

  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) {
    return `${deltaMinutes}m ago`;
  }

  const deltaHours = Math.floor(deltaMinutes / 60);
  return `${deltaHours}h ago`;
}

function toneForSocketStatus(socketStatus: string): Tone {
  if (socketStatus === "online") {
    return "mint";
  }
  if (socketStatus === "demo") {
    return "cyan";
  }
  if (socketStatus === "degraded" || socketStatus === "connecting") {
    return "amber";
  }
  return "red";
}

function toneForModality(modality: string): Tone {
  if (modality === "vision") {
    return "cyan";
  }
  if (modality === "sensor") {
    return "amber";
  }
  if (modality === "audio") {
    return "mint";
  }
  if (modality === "text") {
    return "slate";
  }
  return "red";
}

function toneForGovernanceAction(action: string | undefined): Tone {
  if (action === "BLOCK") {
    return "red";
  }
  if (action === "ESCALATE" || action === "MONITOR") {
    return "amber";
  }
  return "mint";
}

function describeStream(modality: string, rawData: Record<string, unknown>): string {
  if (modality === "vision") {
    const objects = listValue(rawData["objects"]);
    return objects.length > 0 ? `Objects ${objects.slice(0, 3).join(" / ")}` : "Vision frame active";
  }
  if (modality === "audio") {
    return truncateText(textValue(rawData["transcript"]) ?? "Live audio transcript unavailable.", 68);
  }
  if (modality === "sensor") {
    const temperature = numberValue(rawData["temperature_c"]);
    const vibration = numberValue(rawData["vibration_g"]);
    const pressure = numberValue(rawData["pressure_kpa"]);
    const parts = [
      temperature !== undefined ? `${temperature.toFixed(1)} C` : undefined,
      vibration !== undefined ? `${vibration.toFixed(2)}g` : undefined,
      pressure !== undefined ? `${pressure.toFixed(0)} kPa` : undefined,
    ].filter((part): part is string => Boolean(part));
    return parts.length > 0 ? parts.join(" • ") : "Sensor payload active";
  }
  if (modality === "text") {
    return truncateText(textValue(rawData["message"]) ?? "Operational text channel active.", 68);
  }
  return "Realtime source active";
}

function buildStreamDirectory(streams: Array<Record<string, unknown>>, nowMs: number): StreamRowModel[] {
  const latestBySource = new Map<string, StreamRowModel>();

  for (const stream of streams) {
    const sourceId = textValue(stream["source_id"]);
    if (!sourceId) {
      continue;
    }

    const modality = textValue(stream["modality"]) ?? "unknown";
    latestBySource.set(sourceId, {
      sourceId,
      modality,
      detail: describeStream(modality, asRecord(stream["raw_data"])),
      timestamp: formatClock(stream["timestamp"]),
      relativeTime: formatRelativeTime(stream["timestamp"], nowMs),
      tone: toneForModality(modality),
    });
  }

  return Array.from(latestBySource.values()).sort((left, right) => left.sourceId.localeCompare(right.sourceId));
}

function summarizeFusion(item: Record<string, unknown>, nowMs: number): InsightModel {
  const modalities = listValue(item["modalities"]);
  const confidence = normalizeConfidence(numberValue(item["confidence"]));

  return {
    lane: "Fusion",
    title: truncateText(
      textValue(item["semantic_summary"]) ?? "Fusion engine synchronized a new multimodal event window.",
      108,
    ),
    summary:
      modalities.length > 0
        ? `Grounded across ${modalities.map(humanizeToken).join(" • ")}.`
        : "Temporal alignment completed for the active multimodal window.",
    meta: [
      confidence !== undefined ? `${Math.round(confidence * 100)}% confidence` : "Confidence pending",
      textValue(item["event_id"]) ?? "event pending",
    ],
    tone: "amber",
    timestamp: formatClock(item["timestamp"]),
    relativeTime: formatRelativeTime(item["timestamp"], nowMs),
  };
}

function summarizeReasoning(item: Record<string, unknown>, nowMs: number): InsightModel {
  const mode = textValue(item["mode"]) ?? "reasoning";
  const confidence = normalizeConfidence(numberValue(item["confidence"]));
  const actionCount = Array.isArray(item["action_plan"]) ? item["action_plan"].length : 0;
  const predictionCount = Array.isArray(item["predictions"]) ? item["predictions"].length : 0;
  const tone: Tone = mode === "proactive" ? "amber" : mode === "predictive" ? "cyan" : "mint";

  return {
    lane: humanizeToken(mode),
    title: truncateText(textValue(item["summary"]) ?? "Reasoning result published.", 110),
    summary:
      actionCount > 0
        ? `Prepared ${actionCount} downstream ${actionCount === 1 ? "action" : "actions"} for operator follow-through.`
        : predictionCount > 0
          ? `Forecast lane seeded with ${predictionCount} future state projections.`
          : "Inference lane is observing without immediate intervention.",
    meta: [
      confidence !== undefined ? `${Math.round(confidence * 100)}% confidence` : "Confidence pending",
      predictionCount > 0 ? `${predictionCount} forecasts` : actionCount > 0 ? `${actionCount} actions` : "Monitoring",
    ],
    tone,
    timestamp: formatClock(item["timestamp"]),
    relativeTime: formatRelativeTime(item["timestamp"], nowMs),
  };
}

function summarizeAlert(item: Record<string, unknown>, nowMs: number): InsightModel {
  const action = (textValue(item["action_taken"]) ?? "ALLOW").toUpperCase();
  const risk = textValue(item["risk_level"]) ?? "LOW";
  const confidence = normalizeConfidence(numberValue(item["confidence"]));

  return {
    lane: action,
    title: textValue(item["rule_id"]) ?? "DEFAULT_ALLOW",
    summary: truncateText(
      textValue(item["reasoning"]) ?? "Governance decision completed without additional annotation.",
      120,
    ),
    meta: [
      `Risk ${risk}`,
      confidence !== undefined ? `${Math.round(confidence * 100)}% confidence` : "Confidence pending",
    ],
    tone: toneForGovernanceAction(action),
    timestamp: formatClock(item["timestamp"]),
    relativeTime: formatRelativeTime(item["timestamp"], nowMs),
  };
}

function summarizeMemory(item: Record<string, unknown>, nowMs: number): InsightModel {
  const content = asRecord(item["content"]);
  const reasoningState = asRecord(content["reasoning_state"]);
  const temperature = numberValue(reasoningState["temperature_c"]);
  const vibration = numberValue(reasoningState["vibration_g"]);
  const tone: Tone = (textValue(item["memory_type"]) ?? "").toLowerCase() === "working" ? "cyan" : "slate";

  return {
    lane: humanizeToken(textValue(item["memory_type"]) ?? "memory"),
    title: truncateText(
      textValue(content["description"]) ?? textValue(content["event_type"]) ?? "Operational memory persisted into the graph.",
      92,
    ),
    summary: truncateText(
      textValue(content["query"]) ?? "Available for causal traversal and future reasoning recall.",
      108,
    ),
    meta: [
      textValue(item["node_id"]) ?? "memory-node",
      temperature !== undefined ? `${temperature.toFixed(1)} C` : "Thermals nominal",
      vibration !== undefined ? `${vibration.toFixed(2)}g vibration` : "Vibration nominal",
    ],
    tone,
    timestamp: formatClock(item["timestamp"]),
    relativeTime: formatRelativeTime(item["timestamp"], nowMs),
  };
}

function summarizeAgentDefinition(item: Record<string, unknown>, nowMs: number): InsightModel {
  const tags = Array.isArray(item["tags"])
    ? item["tags"].filter((tag): tag is string => typeof tag === "string").slice(0, 3)
    : [];
  const tools = Array.isArray(item["tools"]) ? item["tools"].length : 0;

  return {
    lane: "Agent",
    title: textValue(item["name"]) ?? textValue(item["agent_id"]) ?? "Registered agent",
    summary: truncateText(
      textValue(item["goal"]) ?? textValue(item["description"]) ?? "Agent definition is ready for governed execution.",
      112,
    ),
    meta: [
      textValue(item["agent_id"]) ?? "agent",
      `${tools} ${tools === 1 ? "tool" : "tools"}`,
      tags.length > 0 ? tags.map(humanizeToken).join(" • ") : "Runtime ready",
    ],
    tone: "cyan",
    timestamp: formatClock(item["created_at"]),
    relativeTime: formatRelativeTime(item["created_at"], nowMs),
  };
}

function summarizeAgentRun(item: Record<string, unknown>, nowMs: number): InsightModel {
  const status = textValue(item["status"]) ?? "completed";
  const governanceAction = textValue(item["governance_action"]) ?? "ALLOW";
  const tone: Tone =
    status === "blocked" ? "red" : status === "escalated" || status === "monitored" ? "amber" : "mint";

  return {
    lane: humanizeToken(status),
    title: textValue(item["agent_name"]) ?? textValue(item["agent_id"]) ?? "Agent run completed",
    summary: truncateText(
      `Governance ${governanceAction}. ${textValue(item["agent_id"]) ?? "Agent"} completed its latest orchestrated run.`,
      112,
    ),
    meta: [
      textValue(item["run_id"]) ?? "agent-run",
      `Action ${governanceAction}`,
      textValue(item["agent_id"]) ?? "agent",
    ],
    tone,
    timestamp: formatClock(item["completed_at"] ?? item["started_at"]),
    relativeTime: formatRelativeTime(item["completed_at"] ?? item["started_at"], nowMs),
  };
}

function buildActivityTimeline(state: DashboardState, nowMs: number): ActivityModel[] {
  const items: ActivityModel[] = [];

  for (const item of state.fusion.slice(-3)) {
    const record = asRecord(item);
    items.push({
      lane: "Fusion",
      title: truncateText(textValue(record["semantic_summary"]) ?? "Fusion event published.", 78),
      detail: formatRelativeTime(record["timestamp"], nowMs),
      tone: "amber",
      timestamp: formatClock(record["timestamp"]),
      sortKey: timestampMillis(record["timestamp"]),
    });
  }

  for (const item of state.reasoning.slice(-3)) {
    const record = asRecord(item);
    items.push({
      lane: humanizeToken(textValue(record["mode"]) ?? "reasoning"),
      title: truncateText(textValue(record["summary"]) ?? "Reasoning output published.", 78),
      detail: formatRelativeTime(record["timestamp"], nowMs),
      tone: textValue(record["mode"]) === "proactive" ? "amber" : "mint",
      timestamp: formatClock(record["timestamp"]),
      sortKey: timestampMillis(record["timestamp"]),
    });
  }

  for (const item of state.alerts.slice(-3)) {
    const record = asRecord(item);
    items.push({
      lane: "Governance",
      title: truncateText(
        `${textValue(record["rule_id"]) ?? "DEFAULT_ALLOW"} · ${textValue(record["action_taken"]) ?? "ALLOW"}`,
        78,
      ),
      detail: formatRelativeTime(record["timestamp"], nowMs),
      tone: toneForGovernanceAction((textValue(record["action_taken"]) ?? "ALLOW").toUpperCase()),
      timestamp: formatClock(record["timestamp"]),
      sortKey: timestampMillis(record["timestamp"]),
    });
  }

  for (const item of state.memory_updates.slice(-3)) {
    const record = asRecord(item);
    const content = asRecord(record["content"]);
    items.push({
      lane: "Memory",
      title: truncateText(
        textValue(content["description"]) ?? textValue(content["event_type"]) ?? "Memory node stored.",
        78,
      ),
      detail: formatRelativeTime(record["timestamp"], nowMs),
      tone: "slate",
      timestamp: formatClock(record["timestamp"]),
      sortKey: timestampMillis(record["timestamp"]),
    });
  }

  for (const item of state.agent_runs.slice(-3)) {
    const record = asRecord(item);
    items.push({
      lane: "Agent Runtime",
      title: truncateText(
        `${textValue(record["agent_name"]) ?? "Agent"} · ${humanizeToken(textValue(record["status"]) ?? "completed")}`,
        78,
      ),
      detail: formatRelativeTime(record["completed_at"] ?? record["started_at"], nowMs),
      tone:
        textValue(record["status"]) === "blocked"
          ? "red"
          : textValue(record["status"]) === "escalated" || textValue(record["status"]) === "monitored"
            ? "amber"
            : "mint",
      timestamp: formatClock(record["completed_at"] ?? record["started_at"]),
      sortKey: timestampMillis(record["completed_at"] ?? record["started_at"]),
    });
  }

  return items.sort((left, right) => right.sortKey - left.sortKey).slice(0, 8);
}

function normalizeSocketBase(value: string): string {
  return value.replace(/\/+$/, "");
}

function resolveSocketBase(): string | undefined {
  const params = new URLSearchParams(window.location.search);
  const queryValue = params.get("ws");
  if (queryValue && queryValue.trim().length > 0) {
    return normalizeSocketBase(queryValue.trim());
  }

  const envValue = import.meta.env.VITE_WS_URL;
  if (typeof envValue === "string" && envValue.trim().length > 0) {
    return normalizeSocketBase(envValue.trim());
  }

  return undefined;
}

function prefersStaticDemo(): boolean {
  return window.location.hostname.endsWith("github.io");
}

function useDashboardState() {
  const [state, setState] = useState<DashboardState>(initialState);
  const [socketStatus, setSocketStatus] = useState("connecting");
  const [nowMs, setNowMs] = useState(Date.now());

  useEffect(() => {
    const wsBase = resolveSocketBase();
    const useStaticDemo = prefersStaticDemo() && !wsBase;
    let socket: WebSocket | undefined;
    let disposed = false;

    async function loadDemoState() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}demo-state.json`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error("demo-state-unavailable");
        }

        const payload = (await response.json()) as DashboardState;
        if (!disposed) {
          setState(payload);
          setSocketStatus("demo");
        }
      } catch {
        if (!disposed) {
          setSocketStatus("offline");
        }
      }
    }

    if (useStaticDemo) {
      void loadDemoState();
    } else if (wsBase) {
      socket = new WebSocket(`${wsBase}/ws/dashboard/state`);

      socket.addEventListener("open", () => setSocketStatus("online"));
      socket.addEventListener("close", () => {
        if (prefersStaticDemo()) {
          void loadDemoState();
          return;
        }
        setSocketStatus("offline");
      });
      socket.addEventListener("error", () => setSocketStatus(prefersStaticDemo() ? "demo" : "degraded"));
      socket.addEventListener("message", (event) => {
        try {
          const payload = JSON.parse(event.data) as DashboardState;
          setState(payload);
        } catch {
          setSocketStatus("degraded");
        }
      });
    } else {
      setSocketStatus("offline");
    }

    const heartbeat = window.setInterval(() => {
      setNowMs(Date.now());
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send("pulse");
      }
    }, 1000);

    return () => {
      disposed = true;
      window.clearInterval(heartbeat);
      socket?.close();
    };
  }, []);

  return { state, socketStatus, nowMs };
}

function StatusBadge({ label, tone }: { label: string; tone: Tone }) {
  return <span className={`status-pill tone-${tone}`}>{label}</span>;
}

function MetricCard({ label, value, detail, progress, tone }: MetricModel) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <div className="metric-copy">
        <span className="metric-label">{label}</span>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
      <div className="metric-progress">
        <span className="metric-progress-fill" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
    </article>
  );
}

function InsightCard({ item, featured = false }: { item: InsightModel; featured?: boolean }) {
  return (
    <article className={`insight-card tone-${item.tone} ${featured ? "featured-card" : ""}`}>
      <div className="insight-head">
        <span className="insight-lane">{item.lane}</span>
        <div className="insight-time">
          <strong>{item.timestamp}</strong>
          <span>{item.relativeTime}</span>
        </div>
      </div>
      <h3>{item.title}</h3>
      <p>{item.summary}</p>
      <div className="insight-meta">
        {item.meta.map((meta, index) => (
          <span key={`${meta}-${index}`}>{meta}</span>
        ))}
      </div>
    </article>
  );
}

function TimelineItem({ item }: { item: ActivityModel }) {
  return (
    <article className={`timeline-item tone-${item.tone}`}>
      <div className="timeline-marker" />
      <div className="timeline-copy">
        <div className="timeline-head">
          <span>{item.lane}</span>
          <time>{item.timestamp}</time>
        </div>
        <strong>{item.title}</strong>
        <p>{item.detail}</p>
      </div>
    </article>
  );
}

function StreamRow({ item }: { item: StreamRowModel }) {
  return (
    <article className={`stream-row tone-${item.tone}`}>
      <div className="stream-id">
        <span>{humanizeToken(item.modality)}</span>
        <strong>{item.sourceId}</strong>
      </div>
      <p>{item.detail}</p>
      <div className="stream-meta">
        <span>{item.timestamp}</span>
        <span>{item.relativeTime}</span>
      </div>
    </article>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <article className="empty-state">
      <strong>{title}</strong>
      <p>{body}</p>
    </article>
  );
}

export default function App() {
  const { state, socketStatus, nowMs } = useDashboardState();
  const streamDirectory = buildStreamDirectory(state.streams, nowMs);
  const reasoningCards = state.reasoning.slice(-4).map((item) => summarizeReasoning(item, nowMs));
  const alertCards = state.alerts.slice(-4).map((item) => summarizeAlert(item, nowMs));
  const memoryCards = state.memory_updates.slice(-6).map((item) => summarizeMemory(item, nowMs));
  const agentRunCards = state.agent_runs.slice(-4).map((item) => summarizeAgentRun(item, nowMs));
  const agentCards = state.agents.slice(-4).map((item) => summarizeAgentDefinition(item, nowMs));
  const fusionCards = state.fusion.slice(-4).map((item) => summarizeFusion(item, nowMs));
  const activityTimeline = buildActivityTimeline(state, nowMs);
  const latestReasoning = reasoningCards[reasoningCards.length - 1];
  const latestAlert = alertCards[alertCards.length - 1];
  const latestMemory = memoryCards[memoryCards.length - 1];
  const latestFusion = fusionCards[fusionCards.length - 1];
  const latestAgentRun = agentRunCards[agentRunCards.length - 1];
  const latestAction = asRecord(state.latest_action);
  const latestDecision = asRecord(latestAction["decision"]);
  const latestResult = asRecord(latestAction["result"]);
  const activeModalities = Array.from(new Set(streamDirectory.map((stream) => stream.modality)));
  const socketTone = toneForSocketStatus(socketStatus);
  const latestFusionConfidence = normalizeConfidence(numberValue(asRecord(state.fusion[state.fusion.length - 1])["confidence"]));
  const latestDecisionAction = textValue(latestDecision["action_taken"])?.toUpperCase() ?? "ALLOW";
  const metricCards: MetricModel[] = [
    {
      label: "Signal Fabric",
      value: String(streamDirectory.length),
      detail:
        streamDirectory.length > 0
          ? `${activeModalities.map(humanizeToken).join(" • ")} live`
          : "Waiting for registered stream sources",
      progress: clampProgress(streamDirectory.length / 4),
      tone: "cyan",
    },
    {
      label: "Fusion Integrity",
      value: latestFusionConfidence !== undefined ? `${Math.round(latestFusionConfidence * 100)}%` : "Idle",
      detail: latestFusion?.title ?? "No fused event has been published yet",
      progress: clampProgress(latestFusionConfidence),
      tone: "amber",
    },
    {
      label: "Governance",
      value: latestDecisionAction,
      detail: textValue(latestDecision["rule_id"]) ?? "Default allow posture",
      progress: latestDecisionAction === "BLOCK" ? 1 : latestDecisionAction === "ESCALATE" ? 0.72 : 0.38,
      tone: toneForGovernanceAction(latestDecisionAction),
    },
    {
      label: "Agent Runtime",
      value: String(state.agents.length),
      detail: latestAgentRun?.title ?? `${state.agent_runs.length} recent governed runs`,
      progress: clampProgress(state.agent_runs.length > 0 ? state.agent_runs.length / 6 : state.agents.length / 4),
      tone: "mint",
    },
  ];

  return (
    <div className="shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">
            <span className="brand-core" />
            <span className="brand-ring" />
          </div>
          <div className="brand-copy">
            <span>AETHER Kernel</span>
            <strong>Realtime Multimodal Command Center</strong>
          </div>
        </div>

        <div className="topbar-tray">
          <StatusBadge label={socketStatus} tone={socketTone} />
          <div className="micro-panel">
            <span>Realtime Sync</span>
            <strong>{formatRelativeTime(state.generated_at, nowMs)}</strong>
          </div>
          <div className="micro-panel">
            <span>Operator Clock</span>
            <strong>{new Date(nowMs).toLocaleTimeString()}</strong>
          </div>
        </div>
      </header>

      <main className="dashboard">
        <section className="hero-grid">
          <article className="hero-panel hero-copy-panel">
            <p className="eyebrow">Expert-level situational awareness for live systems</p>
            <h1 className="headline">AETHER is now structured like a real operations product, not a demo screen.</h1>
            <p className="lede">
              Clear live status, disciplined information hierarchy, and a better operator rhythm across perception,
              reasoning, governance, and memory. The UI updates every second so the cockpit feels continuously alive.
            </p>

            <div className="hero-ribbon">
              <span className="inline-pill">Kernel {humanizeToken(state.status)}</span>
              <span className="inline-pill">Modalities {activeModalities.length}</span>
              <span className="inline-pill">Agents {state.agents.length}</span>
              <span className="inline-pill">Events {activityTimeline.length}</span>
              <span className="inline-pill">Action Loop {textValue(latestResult["status"]) ?? "idle"}</span>
            </div>

            <div className="hero-summary-grid">
              {latestReasoning ? (
                <InsightCard item={latestReasoning} featured />
              ) : (
                <EmptyState title="Reasoning lane idle" body="Run the pipeline to populate predictive and proactive outputs." />
              )}

              <div className="hero-summary-stack">
                {latestAlert ? (
                  <InsightCard item={latestAlert} />
                ) : (
                  <EmptyState title="Governance quiet" body="No recent constitutional decision has been published." />
                )}

                <article className="dispatch-card">
                  <div className="dispatch-head">
                    <span>Latest Dispatch</span>
                    <strong>{textValue(latestResult["status"]) ?? "Idle"}</strong>
                  </div>
                  <h3>{textValue(latestResult["target"]) ?? textValue(latestDecision["rule_id"]) ?? "No active dispatch"}</h3>
                  <p>
                    {truncateText(
                      textValue(latestResult["detail"]) ??
                        textValue(latestDecision["reasoning"]) ??
                        "The action orchestration layer has not published a recent dispatch.",
                      130,
                    )}
                  </p>
                  <div className="dispatch-meta">
                    <span>{textValue(latestDecision["action_taken"]) ?? "ALLOW"}</span>
                    <span>{formatClock(latestResult["timestamp"] ?? latestDecision["timestamp"])}</span>
                  </div>
                </article>
              </div>
            </div>
          </article>

          <article className="hero-panel timeline-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Live Activity Rail</span>
                <h2>What changed most recently</h2>
              </div>
              <span className="panel-meta">{activityTimeline.length} surfaced events</span>
            </div>

            <div className="timeline-list">
              {activityTimeline.length > 0 ? (
                activityTimeline.map((item, index) => <TimelineItem key={`${item.lane}-${item.timestamp}-${index}`} item={item} />)
              ) : (
                <EmptyState title="No activity yet" body="Once the kernel emits events, they will appear here in time order." />
              )}
            </div>
          </article>
        </section>

        <section className="metric-strip">
          {metricCards.map((item) => (
            <MetricCard key={item.label} {...item} />
          ))}
        </section>

        <section className="operations-grid">
          <article className="panel scene-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Spatial Command Lattice</span>
                <h2>Live multimodal field</h2>
              </div>
              <span className="panel-meta">{streamDirectory.length} active sources</span>
            </div>

            <div className="scene-wrap">
              <Canvas camera={{ position: [0, 0, 7.2], fov: 46 }}>
                <ambientLight intensity={1.28} />
                <pointLight position={[5, 5, 4]} intensity={2.5} color="#96e9ff" />
                <pointLight position={[-4.5, -4, 2]} intensity={2.2} color="#ff9b5c" />
                <pointLight position={[0, 2, -3]} intensity={1.35} color="#87e7b6" />
                <NeuralCore />
                <OrbitControls enablePan={false} enableZoom={false} />
              </Canvas>

              <div className="scene-overlay">
                <div className="scene-overlay-card">
                  <span>Latest fused narrative</span>
                  <strong>{latestFusion?.title ?? "Waiting for fused event"}</strong>
                  <p>{latestFusion?.summary ?? "When multimodal alignment completes, the semantic summary appears here."}</p>
                </div>

                <div className="scene-overlay-grid">
                  <article>
                    <span>Signal Fabric</span>
                    <strong>{streamDirectory.length}</strong>
                    <small>{activeModalities.length} modalities</small>
                  </article>
                  <article>
                    <span>Realtime Sync</span>
                    <strong>{formatRelativeTime(state.generated_at, nowMs)}</strong>
                    <small>{formatClock(state.generated_at)}</small>
                  </article>
                  <article>
                    <span>Dispatch State</span>
                    <strong>{textValue(latestResult["status"]) ?? "idle"}</strong>
                    <small>{textValue(latestResult["action_type"]) ?? "No action type"}</small>
                  </article>
                </div>
              </div>
            </div>
          </article>

          <article className="panel stream-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Source Matrix</span>
                <h2>Active stream directory</h2>
              </div>
              <span className="panel-meta">{streamDirectory.length} tracked sources</span>
            </div>

            <div className="stream-list">
              {streamDirectory.length > 0 ? (
                streamDirectory.map((item) => <StreamRow key={item.sourceId} item={item} />)
              ) : (
                <EmptyState title="No streams online" body="Register and emit sources to bring the signal matrix online." />
              )}
            </div>
          </article>

          <article className="panel reasoning-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Reasoning Lane</span>
                <h2>Inference and prediction</h2>
              </div>
              <span className="panel-meta">{reasoningCards.length} recent outputs</span>
            </div>

            <div className="insight-stack">
              {reasoningCards.length > 0 ? (
                reasoningCards
                  .slice()
                  .reverse()
                  .map((item, index) => <InsightCard key={`${item.lane}-${item.timestamp}-${index}`} item={item} featured={index === 0} />)
              ) : (
                <EmptyState title="Reasoning not active" body="The reasoning service will publish analysis here as soon as the pipeline runs." />
              )}
            </div>
          </article>

          <article className="panel governance-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Governance Console</span>
                <h2>Constitutional decisions</h2>
              </div>
              <span className="panel-meta">{alertCards.length} recent decisions</span>
            </div>

            <div className="insight-stack">
              {alertCards.length > 0 ? (
                alertCards
                  .slice()
                  .reverse()
                  .map((item, index) => <InsightCard key={`${item.lane}-${item.timestamp}-${index}`} item={item} featured={index === 0} />)
              ) : (
                <EmptyState title="No governance alerts" body="Safety blocks, escalations, and allows will appear here with cleaner operator summaries." />
              )}
            </div>
          </article>

          <article className="panel memory-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Memory Ledger</span>
                <h2>Retained operational memory</h2>
              </div>
              <span className="panel-meta">{memoryCards.length} visible memory nodes</span>
            </div>

            <div className="memory-grid">
              {memoryCards.length > 0 ? (
                memoryCards
                  .slice()
                  .reverse()
                  .map((item, index) => <InsightCard key={`${item.lane}-${item.timestamp}-${index}`} item={item} />)
              ) : (
                <EmptyState title="Memory graph warming up" body="Persisted memory nodes will land here once the kernel stores fused events." />
              )}
            </div>
          </article>

          <article className="panel agent-panel">
            <div className="panel-topline">
              <div>
                <span className="section-kicker">Agent Runtime</span>
                <h2>Governed agents and recent runs</h2>
              </div>
              <span className="panel-meta">{state.agent_runs.length} recent runs</span>
            </div>

            <div className="insight-stack">
              {agentRunCards.length > 0
                ? agentRunCards
                    .slice()
                    .reverse()
                    .map((item, index) => <InsightCard key={`${item.lane}-${item.timestamp}-${index}`} item={item} featured={index === 0} />)
                : agentCards.length > 0
                  ? agentCards.map((item, index) => <InsightCard key={`${item.lane}-${item.timestamp}-${index}`} item={item} featured={index === 0} />)
                  : <EmptyState title="No agents registered" body="Register or run an agent to bring the orchestration runtime online." />}
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
