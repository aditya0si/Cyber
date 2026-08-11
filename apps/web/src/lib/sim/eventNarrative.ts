/**
 * eventNarrative.ts
 * Converts raw CanonicalEvent data into human-readable attack narratives.
 * This is the bridge between internal tech jargon and what an observer sees.
 */

import type { CanonicalEvent, Detection } from "@/lib/api/types";

export type EventKind = "attack" | "benign" | "detection" | "system";

export interface EventNarrative {
  /** One-liner summary: what happened */
  headline: string;
  /** Expanded description: attacker perspective */
  what: string;
  /** The raw payload sent / received */
  payloadSummary: string;
  /** How the system classified this */
  classification: string;
  /** The MITRE tactic if known */
  mitreTactic: string | null;
  /** Color bucket for the row */
  kind: EventKind;
  /** Emoji glyph */
  icon: string;
}

/** Map internal subtype / event_type codes → plain English one-liners */
const SUBTYPE_HEADLINE: Record<string, string> = {
  // API subtypes
  idor_enumeration_indicator: "🔴 Attacker enumerated a protected order ID",
  api_rate_abuse_indicator: "🟠 Attacker hit rate limits — abuse detected",
  unsanitized_auth_failure_burst: "🔴 Brute-force burst on login endpoint",
  "api.request": "API request sent",
  "api.data_response": "API response with sensitive data returned",
  // Web / auth
  sql_injection_indicator: "🔴 SQL injection payload detected in login",
  exfil_candidate_query: "🔴 Database query flagged as exfiltration attempt",
  auth_success_after_burst:
    "🔴 Login succeeded after brute-force — credential compromise!",
  "auth.attempt": "Failed login attempt",
  "auth.success": "Login succeeded",
  "http.request": "HTTP request to application",
  "db.query": "Database query executed",
  // Network
  port_scan_indicator: "🟠 Port scan detected from attacker IP",
  service_discovery_indicator: "🟠 Attacker fingerprinted a running service",
  lateral_movement_indicator: "🔴 Attacker moved laterally to new host",
  data_exfil_indicator: "🔴 Bulk data exfiltration detected",
  "net.scan_probe": "Network scan probe",
  "net.service_discovered": "Service banner discovered",
  "net.lateral_hop": "Lateral movement hop",
  "evidence.data_exfil": "Data exfiltration evidence",
  // Supply chain
  package_lifecycle_hook_suspicious:
    "🔴 Malicious lifecycle hook ran at install time",
  env_exfil_pattern: "🔴 Environment variables exfiltrated by package",
  "package.lifecycle.hook": "Package lifecycle script executed",
  "process.env_exfil": "Process read environment secrets",
  "build.dependency.install": "Dependency installed during build",
};

const MITRE_LABEL: Record<string, string> = {
  TA0001: "Initial Access",
  TA0003: "Persistence",
  TA0004: "Privilege Escalation",
  TA0006: "Credential Access",
  TA0007: "Discovery",
  TA0008: "Lateral Movement",
  TA0009: "Collection",
  TA0010: "Exfiltration",
  TA0011: "Command & Control",
  TA0040: "Impact",
  T1110: "Brute Force",
  T1190: "Exploit Public-Facing Application",
  T1059: "Command Execution",
  T1078: "Valid Accounts",
  T1046: "Network Service Discovery",
  T1021: "Remote Services",
  T1105: "Ingress Tool Transfer",
  T1048: "Exfiltration Over Alternative Protocol",
  T1195: "Supply Chain Compromise",
  "A01:2021": "Broken Access Control",
  "A03:2021": "Injection",
  "A07:2021": "Auth Failures",
};

function mitreFriendly(refs: string[]): string | null {
  for (const ref of refs) {
    const label = MITRE_LABEL[ref];
    if (label) return `${ref}: ${label}`;
  }
  return refs.length > 0 ? (refs[0] ?? null) : null;
}

/** Whether this event represents an attacker action (not benign traffic) */
function isAttackEvent(ev: CanonicalEvent): boolean {
  const ctx = ev.raw_context as Record<string, unknown>;
  if (ctx?.benign) return false;
  const subtype = String(ctx?.subtype ?? ev.event_type ?? "");
  return (
    subtype.includes("indicator") ||
    subtype.includes("burst") ||
    subtype.includes("exfil") ||
    subtype.includes("injection") ||
    subtype.includes("lateral") ||
    subtype.includes("scan") ||
    subtype.includes("hook_suspicious") ||
    ev.severity === "HIGH" ||
    ev.severity === "CRITICAL" ||
    ev.severity === "MEDIUM"
  );
}

/** Build an attacker IP label */
function attackerLabel(ev: CanonicalEvent): string {
  const ctx = ev.raw_context as Record<string, unknown>;
  const ip = ev.source_ip ?? ctx?.source_ip ?? "";
  const benign = ctx?.benign ?? false;
  if (benign) return `User (${ip})`;
  if (ip === "203.0.113.42") return `Attacker (${ip})`;
  return ip ? `${ip}` : "Unknown";
}

/** Format payload fields as readable key: value lines */
function describePayload(ev: CanonicalEvent): string {
  const ctx = ev.raw_context as Record<string, unknown>;
  const payload = (ctx?.payload ?? {}) as Record<string, unknown>;

  const lines: string[] = [];

  if (payload.method && payload.route) {
    lines.push(`${payload.method} ${payload.route}`);
  }
  if (payload.route_params && typeof payload.route_params === "object") {
    const rp = payload.route_params as Record<string, unknown>;
    lines.push(`Object ID: #${rp.id ?? JSON.stringify(rp)}`);
  }
  if (payload.status !== undefined) {
    lines.push(`Response: HTTP ${payload.status}`);
  }
  if (payload.fields_returned) {
    const fields = payload.fields_returned as string[];
    lines.push(`Fields returned: ${fields.join(", ")}`);
    if (payload.scope_exceeded) lines.push(`⚠ Scope exceeded!`);
  }
  if (payload.username) lines.push(`Username: ${payload.username}`);
  if (payload.cmdline) lines.push(`Command: ${payload.cmdline}`);
  if (payload.statement) lines.push(`Query: ${payload.statement}`);
  if (payload.body && typeof payload.body === "object") {
    const body = payload.body as Record<string, unknown>;
    Object.entries(body).forEach(([k, v]) => {
      if (k !== "password") lines.push(`${k}: ${v}`);
    });
  }
  if (payload.ports) {
    const ports = payload.ports as number[];
    lines.push(`Ports scanned: ${ports.slice(0, 5).join(", ")}${ports.length > 5 ? "…" : ""}`);
  }

  return lines.length > 0 ? lines.join("\n") : "No payload details";
}

export function buildNarrative(ev: CanonicalEvent): EventNarrative {
  const ctx = ev.raw_context as Record<string, unknown>;
  const subtype = String(ctx?.subtype ?? ev.event_type ?? "");
  const attack = isAttackEvent(ev);
  const benign = Boolean(ctx?.benign ?? false);

  const headlineTemplate =
    SUBTYPE_HEADLINE[subtype] ?? SUBTYPE_HEADLINE[ev.event_type] ?? subtype.replace(/_/g, " ");

  const from = attackerLabel(ev);
  const targetNodeIds = (ctx?.target_node_ids as unknown[]) ?? [];
  const firstTarget = targetNodeIds.length > 0 ? String(targetNodeIds[0] ?? "") : "";
  const target = ev.target_asset !== "unknown" ? ev.target_asset : firstTarget;
  const mitre = mitreFriendly([
    ...((ctx?.mitre_tactics as string[] | undefined) ?? []),
    ...((ctx?.mitre_techniques as string[] | undefined) ?? []),
    ...((ctx?.owasp_refs as string[] | undefined) ?? []),
  ]);

  let what = "";
  if (benign) {
    what = `Legitimate user traffic from ${from} to ${target || "API"}.`;
  } else if (subtype === "idor_enumeration_indicator") {
    const rp = ((ctx?.payload as Record<string, unknown>)?.route_params ?? {}) as Record<string, unknown>;
    what = `${from} walked object IDs sequentially (e.g. #${rp.id ?? "?"}), accessing data beyond their authorization. This is a classic IDOR (Insecure Direct Object Reference) attack — the attacker cycles through IDs to dump all records.`;
  } else if (subtype.includes("brute") || subtype === "unsanitized_auth_failure_burst") {
    what = `${from} sent rapid failed login attempts against ${target || "/api/auth"}. The burst pattern (≥5 failed attempts/min from same IP) triggered the brute-force detector.`;
  } else if (subtype === "sql_injection_indicator") {
    what = `${from} injected SQL into the login form. The payload contains characters like ' OR 1=1 or UNION SELECT that can bypass authentication or dump the database.`;
  } else if (subtype === "auth_success_after_burst") {
    what = `After a brute-force burst, ${from} successfully logged in. This indicates credential compromise — the attacker found valid credentials.`;
  } else if (subtype === "package_lifecycle_hook_suspicious") {
    what = `A newly installed package ran a lifecycle script (postinstall hook) that executed shell commands. This is how supply-chain attacks embed malicious code into the build pipeline.`;
  } else if (subtype === "env_exfil_pattern") {
    what = `The malicious package process read environment variables matching secret patterns (API keys, tokens). These were likely sent to an external server.`;
  } else if (subtype === "lateral_movement_indicator") {
    what = `${from} moved from the compromised host to another internal system. The attacker is expanding their foothold inside the network.`;
  } else if (subtype === "data_exfil_indicator") {
    what = `Large volume of data was sent to an external destination. This is the final exfiltration stage — the attacker is extracting stolen data.`;
  } else {
    what = `${from} sent a request to ${target || "the target system"}.`;
  }

  const classification =
    benign
      ? "Normal traffic — not suspicious"
      : attack
        ? `Attack event · ${subtype.replace(/_/g, " ")}`
        : `Informational · ${subtype.replace(/_/g, " ")}`;

  const icon = benign ? "○" : attack ? "⚠" : "·";
  const kind: EventKind = benign ? "benign" : attack ? "attack" : "system";

  return {
    headline: headlineTemplate,
    what,
    payloadSummary: describePayload(ev),
    classification,
    mitreTactic: mitre,
    kind,
    icon,
  };
}

/** Build a short human summary for a Detection */
export function detectionSummary(d: Detection): string {
  const pct = Math.round((d.confidence ?? 0) * 100);
  const tactics: Record<string, string> = {
    idor: "Insecure Direct Object Reference (IDOR) — attacker enumerated protected records by cycling object IDs.",
    credential_brute_force: "Brute-force credential attack — automated login attempts from the same IP.",
    sql_injection: "SQL Injection — attacker injected malicious SQL to bypass login or dump database.",
    malicious_package: "Supply-chain compromise — malicious package executed code during installation.",
    lateral_movement: "Lateral movement — attacker pivoted from one host to another inside the network.",
    data_exfiltration: "Data exfiltration — large volume of sensitive data sent to an external destination.",
    credential_compromise: "Credential compromise — valid credentials obtained after brute-force burst.",
    port_scan: "Port scan — attacker mapped open services on the target network.",
    service_discovery: "Service discovery — attacker fingerprinted running services and banners.",
    rate_abuse: "API rate abuse — attacker flooded endpoints, detected by rate-window anomaly.",
  };

  const tc = d.threat_class?.toLowerCase().replace(/ /g, "_") ?? "";
  const desc = tactics[tc] ?? d.rationale ?? "Suspicious activity detected.";

  return `${desc} (${pct}% confidence, ${d.confidence_band ?? "medium"})`;
}
