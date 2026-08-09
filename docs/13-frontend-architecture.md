# 13 — Frontend Architecture (Next.js 14 App Router)

The web application for CyberSim AI: a **Next.js 14 App Router** app (TypeScript, Tailwind v4, Radix-based design system) that hosts the **marketing site**, the **SOC dashboard**, **Mission Mode theater**, account/org/billing, and the **knowledge browser**. The visual language lives in `02`; this doc covers the application structure, data fetching, state, the WebSocket data layer, routing, the component inventory mapped to design system sections, and concrete file paths the implementing agent must follow.

> **Normative dependencies:** App Router + RSC, TanStack Query (server cache), Zustand (UI state), `useSyncExternalStore` (WS), Tailwind v4 + CSS vars, Radix UI primitives, Lucide icons, Shiki code blocks, `reactflow`-lite custom SVG/Canvas graph renderer. **No raw fetch.** All HTTP via the typed client generated from `/v1/openapi.json`.

---

## 1. Repository layout (`apps/web`)

```
apps/web/
├─ next.config.mjs
├─ tailwind.config.ts
├─ tsconfig.json
├─ package.json
├─ src/
│  ├─ styles/
│  │  ├─ tokens.css         # design tokens (02 §3) — single source of truth
│  │  ├─ global.css         # resets, base layers, prose-like content styles
│  │  └─ animations.css     # streaming reveal, reduced-motion overrides
│  ├─ lib/
│  │  ├─ api/
│  │  │  ├─ schema.ts       # generated via openapi-typescript from /v1/openapi.json
│  │  │  ├─ client.ts       # typed fetcher (auth, base URL, error mapping)
│  │  │  └─ hooks/          # generated or hand-written TanStack hooks (queries/mutations)
│  │  ├─ ws/
│  │  │  ├─ SocketProvider.tsx
│  │  │  ├─ useChannel.ts
│  │  │  └─ frames.ts       # typed frame dispatch (08 §5.2) ↔ Zustand store events
│  │  ├─ auth/
│  │  │  ├─ AuthProvider.tsx
│  │  │  └─ tokens.ts       # refresh rotation, ws-ticket fetch
│  │  ├─ i18n/              # en; ship en at v0.1; scaff for keys
│  │  └─ utils/             # formatters (RelativeTime, SevBadge), cn() class merge
│  ├─ components/
│  │  ├─ ui/                # design-system primitives (Button, Modal, Drawer, Toast, CmdK, ...)
│  │  ├─ shell/              # AppShell, Sidebar, Topbar, DensityMenu, ThemeToggle
│  │  ├─ scenario/           # ScenarioCard, ScenarioFilters, ScenarioParamsForm
│  │  ├─ dashboard/          # SOC Console pieces (see §6)
│  │  ├─ graph/              # GraphView + drawers + minimap
│  │  ├─ mission/            # MissionStage theater (14)
│  │  ├─ account/            # org settings, members, billing
│  │  ├─ knowledge/          # KnowledgeBrowser
│  │  └─ marketing/         # hero, features, stat, code-hero
│  ├─ app/
│  │  ├─ (marketing)/        # public site; root route group; ISR/SSG
│  │  ├─ (auth)/             # /login /register /webauthn-flow step pages
│  │  ├─ (dashboard)/        # authenticated area; uses AppShell layout
│  │  │  ├─ layout.tsx
│  │  │  ├─ page.tsx         # home: scenario picker + active sims
│  │  │  ├─ scenarios/page.tsx + [scenario_id]/page.tsx
│  │  │  ├─ simulations/page.tsx + [sim_id]/page.tsx    # SOC dashboard route
│  │  │  ├─ missions/page.tsx + [mission_id]/page.tsx
│  │  │  ├─ knowledge/page.tsx + [entry_id]/page.tsx
│  │  │  ├─ org/ /billing/ /settings/
│  │  ├─ api/                # route handlers proxyauth bootstrap + Next route webhooks (optional)
│  │  └─ globals.css
│  └─ middleware.ts          # auth gate, theme default, locale, redirect
```

> Path names are normative; `21` references them directly.

## 2. Rendering strategy per surface

| Surface | Strategy | Why |
|---------|----------|-----|
| Marketing (`(marketing)`) | **SSG + ISR (revalidate 600s)** | Marketing is fast, cacheable; no per-request data needed. Hero embeds OpenAI-parity CTAs. |
| Auth pages (`(auth)`) | **Edge runtime** static (no need for DB calls in the gate) | No DB hits on login UX; tokens issued by API. |
| Dashboard (`(dashboard)`) shell (layout) | **SSR + auth gate** (server component fetches `/v1/me` via cookies) | Cold-load shows the shell with the user's navigation pre-resolved; client islands hydrate. |
| SOC Dashboard (`simulations/[sim_id]`) | **RSC initial tail** fetch `/events?cursor=tail&limit=200` + `/graph` (server-side) sent as serialized initial state to the island; **client-side WebSocket** resumes from `next_seq` | First paint fast & SEO-debuggable; subsequent live updates via WS (`08` §5). |
| Knowledge | hybrid ISR (entries change nightly) with on-demand revalidate | Cheap to serve, refreshable. |
| Billing | purely client-side after SSR auth | Privacy + Stripe-hosted redirect. |

### 2.1 Why SSR + WS hybrid for the dashboard (and not pure client SPA)?
- SEO/debugging: SOC dashboard pages are linkable with the initial tail rendered; incidents can be deep-linked and reviewed by a teammate without an auth-required route handoff.
- Pre-resolved queries (`ScenarioCard`, `/graph` initial JSON) arrive with HTML, avoiding client-side waterfall.
- The live layer is WS; SSE considered but rejected for Uni-directional edge-terminated scenarios — see `04` cross-reference in `13` §7.

## 3. State management

| Kind | Tool | Examples |
|------|------|----------|
| Server data (REST) | **TanStack Query** with normalized cache keys `["sim", simId, "events", {cursor}]` | scenario lists, simulation details, detections, knowledge entries |
| Live (WebSocket) frames | **`useSyncExternalStore`** wrapping a small `WSStore` keyed by `(sim_id, channel)`; the store dispatches to TanStack cache + Zustand | new event appended → invalidate `["sim", simId, "events", cursor-leaf]`? No — we keep a separate live buffer and merge server-conn confirms via `cursor.resume` |
| UI state | **Zustand** stores (one per concern; small and typed) | `densityStore`, `themeStore`, `selectionStore` (selected events/detections), `drawerOpenStore`, `commandPaletteStore` |
| Form state | React Hook Form + Zod | scenario params, auth forms |
| Client markers | URLs (searchParams) where shareable | active filters (`?severity=high&o=graph`), sim tab (`?tab=analyst` or graph) |

> **Self-question:** Why dedicate-separate stores instead of one big Zustand store? **Answer:** Smaller diff surface, easier to test, no global re-render from a single setter. Per concern = per `useXStore` hook subscribing to slices.

## 4. Typed API client & codegen

- `pnpm run codegen:api` → fetch `http://localhost:8000/v1/openapi.json` (dev) → `openapi-typescript` writing `src/lib/api/schema.ts`. CI fails if schema changes break client (contract tests, `20`).
- `src/lib/api/client.ts` wraps `fetch` with: auth header injection, refresh-token rotation on 401, request-id propagation, retries on 429 with `Retry-After`, idempotency-key minting (uuidv7) for listed mutations.
- Custom hooks in `src/lib/api/hooks/*` use TanStack Query; mutations wrap our typed client.

## 5. WebSocket layer (`src/lib/ws`)

- `SocketProvider` connects once per user session to `wss://api/.../ws?ticket=...`; manages reconnect (exponential backoff + new ticket fresh after refresh flow).
- `useChannel(channel)` subscribes to a channel (e.g., `sim.{simId}`) and re-emits frames via `useSyncExternalStore`.
- Frame handlers update the WS store per channel; coalesced batches (`event.batch` ≤32) flush in one render pass; we also implement the client's coalescing cap ≤4 renders/sec.
- Cursor resume: client tracks `lastSeq` per channel; on reconnect, sends `subscribe` with `cursors.events=lastSeq`. Server replays from there (idempotent on write-side).
- Backpressure: unread buffer > 64 → send `subscribe?coalesce_ms=120` request; > 128 → disconnect/reconnect policy.

## 6. SOC Dashboard component tree (primary surface)

Map of `app/(dashboard)/simulations/[sim_id]/page.tsx` → `SocConsole`:

```
<AppShell>
  <SocConsole simId>
    <ConsoleLayout>
      <LeftPane>            // feed
        <FeedToolbar/>
        <EventFeed>
          for ev in liveTail + cursor-stream:
            <EventRow ev/> (02 §4.3)
        <FeedTailLoading/>
      </LeftPane>
      <CenterPane>            // analyst | graph (tabbed)
        <Tabs>
          <Tab id="analyst">
            <AnalystStream>     // detection cards + benign attestations
              for det in detections stream:
                <DetectionCard det/>   (02 §4.4)
                (collapsed evidence rows expand to EventRow references)
            </AnalystStream>
            <AskAnalyst simId/>
          </Tab>
          <Tab id="graph">
            <GraphView simId/>   (02 §4.5) — uses server-seeded layout + WS deltas
          </Tab>
        </Tabs>
      </CenterPane>
      <RightPane>            // inspector + response console
        <Inspector selectedEntity={event|detection|node}/>
        <ResponseConsole simId/>
      </RightPane>
    </ConsoleLayout>
    <StatusBar/>            // lag indicator, degraded banner (analyst offline → rules), pip counters
  </SocConsole>
</AppShell>
```

### 6.1 Sub-components (all in `components/dashboard/`)
`EventFeed`, `EventRow`, `FeedTailLoading`, `FeedToolbar`, `FilterChips`, `DetectionCard`, `EvidenceList`, `EvidenceItemRef`, `AttackPathPanel`, `RationaleBlock`, `CitationsList`, `RecommendedActionsList`, `ExecuteActionDialog`, `AskAnalyst`, `AnalystAnswerCard`, `GraphView`, `NodeDrawer`, `GraphScrubber`, `Inspector`, `ResponseConsole`, `StatusDot`, `SevGlyph`, `SeverityBadge`, `DensityToggle`, `ThemeToggle`, `LagIndicator`, `DegradedBanner`.

### 6.2 Selection model
- `selectionStore`: `{ type: "event"|"detection"|"node", id, source: "feed"|"graph"|"detection" }`.
- Selecting an EventRow sets selection → Inspector shows its raw payload + MITRE tags + graph node link; that node highlights on graph; all evidence items referencing it highlight across DetectionCards ("relationship glow").
- Cmd-click adds multi-select; `Shift-↑/↓` selects contiguous rows in feed.

### 6.3 "Evidence glow" interaction (the killer UX beat)
When the user clicks a Detection → all EventRow's referenced by its evidence highlight (left sev bar turns accent green); when user hovers evidence item in a card →🍰 feed scrolls to first referenced event with a 200ms outset highlight. This makes the **evidence-mandate** spatially visible — the literal embodiment of "every AI decision has evidence attached."

## 7. Tailwind v4 + tokens wiring
- `tailwind.config.ts` uses v4 `@theme` direct mapping to CSS vars from `tokens.css` (`02` §8).
- Component primitives use **utility classes only**: no CSS-in-JS.
- `prefers-color-scheme` flips `data-theme`; user override persisted in localStorage + synced via API (`/v1/me` PATCH).

## 8. Routing & auth gate (middleware.ts)

```ts
// src/middleware.ts (excerpt)
export const config = {
  matcher: ["/((?!api|_next|favicon|ingest).*)"]
}
export function middleware(req) {
  const { pathname } = req.nextUrl;
  const auth = publicRoutes.has(pathname) || pathname.startsWith("/(marketing)") || isAuthSubtree(pathname);
  if (!auth && !req.cookies.get("cs_session")) {
    const url = req.nextUrl.clone(); url.pathname = "/login"; url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  // theme + density bootstrap via cookies for SSR-correct first paint
  const res = NextResponse.next();
  res.headers.set("x-cs-pathname", pathname);
  return res;
}
```
On the server side, `(dashboard)` layout's RSC fetches `/v1/me` (server-side with cookie forwarding) and renders nothing if 401 (redirect via middleware) — eliminates the "flash of unauthenticated content" anti-pattern.

## 9. Performance budgets (Lighthouse CI gate — `20`)

| Metric | Target | Approach |
|--------|--------|----------|
| LCP (dashboard) | ≤ 2.5s p75 | RSC pre-fetches initial tail + graph; small JS bundle |
| JS size (gzip routing `sim/[id]` ee) | ≤ 220 KB | tree-shake socket+graph vendors; dynamic-import `GraphView` (heavy) |
| CLS | ≤ 0.05 | reserve layout space for graphs/drawers; deferred highlight only after stabilize |
| INP | ≤ 200ms | virtualize `EventFeed` (windowing lib); WS batches ≤4 renders/sec; React 18 `startTransition` for selection cascade |
| Force | densities & theme persisted via cookie for SSR | avoids FOUC and reflow on hydration |

Lighthouse CI run on PRs (`20`); hard gate "perf score ≥ 90" on `/` (marketing) and `score ≥ 85` on `sim/[id]`.

## 10. Accessibility in app code (extends `02` §7)
- `EventRow` uses `<article aria-label=...>` and a `button[aria-expanded]` for expand.
- `DetectionCard` exposes `role="region" aria-label="Detection: ..."`.
- Streaming reveal hidden from AT (aria-hidden during entrance; polite region for batch summaries).
- Keyboard: `J/K` next/prev event (vim-style SOC convention; documented in `?`).
- Focus management on tab switching & drawer open returns to originating trigger.

## 11. Code blocks & terminal-style components
- `CodeBlock` (02 §4.7) wraps Shiki with `json/http/sql/bash/mermaid` grammars.
- `TerminalHero` marketing piece stylizes a "live-trace" sample JSON rotated by intersection-observer-driven CSS motion.

## 12. Self-questioning & decisions (frontend)

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Next.js App Router + RSC | Yes | Vite SPA | SSR-first marketing + live console hybrid; matches OpenAI-parity (`02`, `04` §2.12). |
| TanStack Query + Zustand | Yes | Redux | Less boilerplate; clear server-vs-UI boundary. |
| Custom graph renderer | Yes | react-flow default | We need overlay+foothold encoding; a tailored SVG/Canvas hybrid wins perf + design-language alignment (`02` §4.5). |
| WS via `useSyncExternalStore` | Yes | context+state batchers | Stable concurrent rendering; React-recommended pattern. |
| Typed client via OpenAPI codegen | Yes | manual fetch wrappers | Contract drift fails in CI; (`08`, `20`). |
| Token-themed CSS vars + Tailwind v4 | Yes | CSS-in-JS | Tooling/runtime + RSC compat (`02` §8). |
| Open-design-system ownership via Radix + custom (not shadcn snapshots) | Yes | shadcn/ui scaffolds | Full control over a11y decisions + visual identity (`04` §2.14). |
| Marketing SSR-stale + Dashboard SSR-tail + WS | Yes | SPA-only | First paint + shareable + decodeable dashboards |
| Heavy GraphView dynamic-import | Yes | eager | bundles; first paint p75. |

---

End of `13-frontend-architecture.md`. Next: `14-mission-mode.md`.
