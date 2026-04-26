import { useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";
import {
  Activity,
  Copy,
  Edit3,
  Gauge,
  Globe,
  Heart,
  LayoutDashboard,
  Link as LinkIcon,
  LoaderCircle,
  Logs,
  Network,
  Power,
  QrCode,
  Radar,
  RefreshCw,
  Server,
  Settings,
  Shield,
  TerminalSquare,
  Wifi,
} from "lucide-react";
import QRCode from "qrcode";

import { ApiError, api } from "./api";
import type { LogsResponse, NodeItem, Overview, SettingsResponse, TrafficResponse } from "./types";

type RouteKey = "overview" | "nodes" | "traffic" | "control" | "diagnostics" | "settings";

const navItems: { key: RouteKey; to: string; label: string; icon: typeof LayoutDashboard }[] = [
  { key: "overview", to: "/", label: "总览", icon: LayoutDashboard },
  { key: "nodes", to: "/nodes", label: "节点", icon: Network },
  { key: "traffic", to: "/traffic", label: "流量", icon: Activity },
  { key: "control", to: "/control", label: "控制", icon: Power },
  { key: "diagnostics", to: "/diagnostics", label: "诊断", icon: Radar },
  { key: "settings", to: "/settings", label: "设置", icon: Settings },
];

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [checkingSession, setCheckingSession] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [busy, setBusy] = useState<string>("");
  const [notice, setNotice] = useState("");

  const [overview, setOverview] = useState<Overview | null>(null);
  const [nodes, setNodes] = useState<NodeItem[]>([]);
  const [traffic, setTraffic] = useState<TrafficResponse | null>(null);
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [diagResult, setDiagResult] = useState<Record<string, unknown> | null>(null);
  const [trafficRange, setTrafficRange] = useState("24h");
  const [trafficNodeId, setTrafficNodeId] = useState("");
  const [trafficService, setTrafficService] = useState("all");
  const [logSource, setLogSource] = useState("combined");
  const [logQuery, setLogQuery] = useState("");
  const [settingsForm, setSettingsForm] = useState({ ipWhitelist: "", password: "" });
  const [editingNodeId, setEditingNodeId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [latencyMap, setLatencyMap] = useState<Record<string, { ok: boolean; median_ms?: number; message?: string }>>({});
  const [siteLatency, setSiteLatency] = useState<
    Array<{ name: string; host: string; ip: string; dns_ms?: number | null; tcp_ms?: number | null; tls_ms?: number | null; total_ms?: number | null; ok: boolean; message?: string }>
  >([]);

  useEffect(() => {
    api
      .session()
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
      .finally(() => setCheckingSession(false));
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    void refreshAll();
  }, [authenticated]);

  useEffect(() => {
    if (!authenticated) return;
    void loadTraffic();
  }, [authenticated, trafficRange, trafficNodeId, trafficService]);

  useEffect(() => {
    if (!authenticated) return;
    void loadLogs();
  }, [authenticated, logSource]);

  useEffect(() => {
    if (!authenticated) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/overview`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { overview: Overview; latestAudit: LogsResponse };
      setOverview(payload.overview);
      setSettings((prev) => (prev ? { ...prev, auditLogs: payload.latestAudit.entries } : prev));
    };
    socket.onerror = () => setNotice("实时刷新连接中断，已回退到手动刷新");
    return () => socket.close();
  }, [authenticated]);

  useEffect(() => {
    if (settings) {
      setSettingsForm({ ipWhitelist: settings.ipWhitelist, password: "" });
    }
  }, [settings]);

  async function refreshAll() {
    try {
      const [overviewData, nodeData, trafficData, logData, settingsData, latencyData] = await Promise.all([
        api.overview(),
        api.nodes(),
        api.traffic(trafficRange, trafficNodeId || undefined, trafficService),
        api.logs(logSource, logQuery),
        api.settings(),
        api.latencyMap(),
      ]);
      setOverview(overviewData);
      setNodes(nodeData.items);
      setTraffic(trafficData);
      setLogs(logData);
      setSettings(settingsData);
      setLatencyMap(
        Object.fromEntries(
          latencyData.items.map((item) => [
            item.node_id,
            { ok: item.ok, median_ms: item.median_ms, message: item.message },
          ]),
        ),
      );
    } catch (error) {
      handleApiError(error);
    }
  }

  async function loadTraffic() {
    try {
      const data = await api.traffic(trafficRange, trafficNodeId || undefined, trafficService);
      setTraffic(data);
    } catch (error) {
      handleApiError(error);
    }
  }

  async function loadLogs(query = logQuery) {
    try {
      const data = await api.logs(logSource, query);
      setLogs(data);
    } catch (error) {
      handleApiError(error);
    }
  }

  function handleApiError(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      setAuthenticated(false);
      navigate("/");
      return;
    }
    setNotice(error instanceof Error ? error.message : "请求失败");
  }

  async function submitLogin(event: React.FormEvent) {
    event.preventDefault();
    setBusy("login");
    setAuthError("");
    try {
      await api.login(password);
      setAuthenticated(true);
      setPassword("");
    } catch (error) {
      if (error instanceof ApiError) {
        const remaining = error.details?.remainingAttempts;
        const retryAfter = error.details?.retryAfter;
        if (typeof remaining === "number" && remaining > 0) {
          setAuthError(`${error.message}`);
        } else if (typeof retryAfter === "number" && retryAfter > 0) {
          setAuthError(`${error.message}`);
        } else {
          setAuthError(error.message);
        }
      } else {
        setAuthError(error instanceof Error ? error.message : "登录失败");
      }
    } finally {
      setBusy("");
      setCheckingSession(false);
    }
  }

  async function logout() {
    await api.logout();
    setAuthenticated(false);
    setOverview(null);
    setNodes([]);
    setTraffic(null);
    setLogs(null);
    setSettings(null);
  }

  async function switchNode(nodeId: string) {
    setBusy(`node-${nodeId}`);
    try {
      await api.activateNode(nodeId);
      await refreshAll();
      setNotice("当前节点已切换");
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  async function toggleFavorite(nodeId: string, favorite: boolean) {
    try {
      await api.favoriteNode(nodeId, favorite);
      const data = await api.nodes();
      setNodes(data.items);
    } catch (error) {
      handleApiError(error);
    }
  }

  async function renameNode(nodeId: string) {
    const label = renameDraft.trim();
    if (!label) {
      setNotice("节点名称不能为空");
      return;
    }
    setBusy(`rename-${nodeId}`);
    try {
      await api.renameNode(nodeId, label);
      const data = await api.nodes();
      setNodes(data.items);
      setEditingNodeId("");
      setRenameDraft("");
      setNotice("节点名称已更新");
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  async function refreshLatencyMap() {
    setBusy("latency-map");
    try {
      const data = await api.latencyMap();
      setLatencyMap(
        Object.fromEntries(
          data.items.map((item) => [
            item.node_id,
            { ok: item.ok, median_ms: item.median_ms, message: item.message },
          ]),
        ),
      );
      setNotice("节点测速已刷新");
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  async function refreshSiteLatency() {
    setBusy("site-latency");
    try {
      const data = await api.siteLatency();
      setSiteLatency(data.items);
      setNotice("海外站点测速已刷新");
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  async function copyText(value: string, message: string) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        throw new Error("clipboard unavailable");
      }
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setNotice(message);
  }

  async function downloadQr(node: NodeItem) {
    const dataUrl = await QRCode.toDataURL(node.raw_link, {
      margin: 1,
      color: { dark: "#eef7f6", light: "#050608" },
      width: 640,
    });
    const anchor = document.createElement("a");
    anchor.href = dataUrl;
    anchor.download = `${node.label}.png`;
    anchor.click();
    setNotice("二维码已导出");
  }

  async function runAction(action: string, target: string, dangerous = false) {
    const label = `${action} ${target}`;
    if (dangerous) {
      const confirmText = window.prompt(`危险操作确认，请输入 ${label.toUpperCase()}`);
      if (confirmText !== label.toUpperCase()) return;
    }
    setBusy(`${action}-${target}`);
    try {
      const result = await api.action(action, target);
      setNotice(result.message);
      await refreshAll();
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  async function runDiagnostic(kind: "latency" | "dns" | "config") {
    setBusy(`diag-${kind}`);
    try {
      const nodeId = overview?.activeNode?.id;
      const result =
        kind === "latency"
          ? await api.latencyTest(nodeId)
          : kind === "dns"
            ? await api.dnsCheck(nodeId)
            : await api.configValidate();
      setDiagResult(result);
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    setBusy("settings");
    try {
      await api.updateSettings({
        ipWhitelist: settingsForm.ipWhitelist,
        password: settingsForm.password || undefined,
      });
      setNotice("设置已更新");
      const latest = await api.settings();
      setSettings(latest);
      setSettingsForm((prev) => ({ ...prev, password: "" }));
    } catch (error) {
      handleApiError(error);
    } finally {
      setBusy("");
    }
  }

  const trafficOption = useMemo(() => {
    const series = traffic?.series ?? [];
    return {
      backgroundColor: "transparent",
      textStyle: { color: "#dbe6e5" },
      grid: { left: 12, right: 12, top: 28, bottom: 18, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#050608",
        borderColor: "rgba(111,255,214,.2)",
        textStyle: { color: "#eaf5f4" },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        axisLabel: { color: "#718583", fontFamily: "JetBrains Mono, monospace" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,.14)" } },
        splitLine: { show: true, lineStyle: { color: "rgba(255,255,255,.04)" } },
        data: series.map((item) => new Date(item.ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })),
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#718583", formatter: (value: number) => `${value.toFixed(1)} B/s`, fontFamily: "JetBrains Mono, monospace" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
      },
      series: [
        {
          name: "下载",
          type: "line",
          smooth: false,
          showSymbol: false,
          lineStyle: { color: "#6fffd6", width: 2 },
          areaStyle: { color: "rgba(111,255,214,.08)" },
          data: series.map((item) => item.download_bps),
        },
        {
          name: "上传",
          type: "line",
          smooth: false,
          showSymbol: false,
          lineStyle: { color: "#79a7ff", width: 2 },
          areaStyle: { color: "rgba(121,167,255,.06)" },
          data: series.map((item) => item.upload_bps),
        },
      ],
    };
  }, [traffic]);

  const currentPageLabel = navItems.find((item) => item.to === location.pathname)?.label ?? "总览";
  const clashUrl = settings ? new URL(settings.clashSubscriptionUrl, window.location.origin).toString() : "";

  if (checkingSession) {
    return <FullScreenState icon={LoaderCircle} title="正在检查会话" spinning />;
  }

  if (!authenticated) {
    return (
      <div className="login-shell">
        <div className="login-card">
          <span className="login-eyebrow">Proxy Admin · Dark Tape</span>
          <h1>代理管理台</h1>
          <p>以近黑的行情板方式管理 Xray 与 Argosbx，先看状态，再下动作。</p>
          <form className="login-form" onSubmit={submitLogin}>
            <label>
              <span>管理员口令</span>
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="输入口令" />
            </label>
            <button type="submit" disabled={!password || busy === "login"}>
              {busy === "login" ? "登录中..." : "登录"}
            </button>
            {authError ? <div className="banner error">{authError}</div> : null}
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">PA</div>
          <div>
            <strong>Proxy Admin</strong>
            <span>ARGOSBX / XRAY</span>
          </div>
        </div>
        <nav className="nav">
          {navItems.map(({ icon: Icon, ...item }) => (
            <NavLink key={item.key} to={item.to} end={item.to === "/"} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon size={16} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <button type="button" className="ghost-button logout-button" onClick={logout}>
          退出登录
        </button>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="eyebrow">SERVER OPS PANEL</span>
            <h2>{currentPageLabel}</h2>
          </div>
          <div className="status-row">
            <StatusPill label="Xray" active={Boolean(overview?.serviceStatus.xray.active)} />
            <StatusPill label="Argo" active={Boolean(overview?.serviceStatus.argo.active)} />
            <button type="button" className="ghost-button" onClick={() => void refreshAll()}>
              <RefreshCw size={15} />
              刷新
            </button>
          </div>
        </header>

        <div className="market-strip">
          <TapeCard title="STACK" value={overview?.serviceStatus.stack.healthy ? "UP" : "DOWN"} tone={overview?.serviceStatus.stack.healthy ? "good" : "bad"} />
          <TapeCard title="NODE" value={overview?.activeNode?.label ?? "N/A"} tone="neutral" />
          <TapeCard title="DOWN" value={formatRate(overview?.traffic.download_bps ?? 0)} tone="good" />
          <TapeCard title="UP" value={formatRate(overview?.traffic.upload_bps ?? 0)} tone="info" />
          <TapeCard title="CLASH" value={clashUrl ? "READY" : "OFF"} tone={clashUrl ? "good" : "neutral"} />
        </div>

        {notice ? <div className="banner">{notice}</div> : null}

        <Routes>
          <Route path="/" element={<OverviewPage overview={overview} trafficOption={trafficOption} logs={logs} />} />
          <Route
            path="/nodes"
            element={
              <NodesPage
                nodes={nodes}
                busy={busy}
                latencyMap={latencyMap}
                editingNodeId={editingNodeId}
                renameDraft={renameDraft}
                setEditingNodeId={setEditingNodeId}
                setRenameDraft={setRenameDraft}
                onSwitch={switchNode}
                onFavorite={toggleFavorite}
                onRename={renameNode}
                onRefreshLatency={refreshLatencyMap}
                onCopy={copyText}
                onDownloadQr={downloadQr}
              />
            }
          />
          <Route
            path="/traffic"
            element={
              <TrafficPage
                nodes={nodes}
                traffic={traffic}
                trafficOption={trafficOption}
                trafficRange={trafficRange}
                trafficNodeId={trafficNodeId}
                trafficService={trafficService}
                setTrafficRange={setTrafficRange}
                setTrafficNodeId={setTrafficNodeId}
                setTrafficService={setTrafficService}
              />
            }
          />
          <Route path="/control" element={<ControlPage overview={overview} busy={busy} onAction={runAction} />} />
          <Route
            path="/diagnostics"
            element={
              <DiagnosticsPage
                overview={overview}
                logs={logs}
                busy={busy}
                logSource={logSource}
                setLogSource={setLogSource}
                logQuery={logQuery}
                setLogQuery={setLogQuery}
                onSearchLogs={() => void loadLogs(logQuery)}
                onDiagnostic={runDiagnostic}
                diagResult={diagResult}
                siteLatency={siteLatency}
                onRefreshSiteLatency={refreshSiteLatency}
              />
            }
          />
          <Route
            path="/settings"
            element={
              <SettingsPage
                settings={settings}
                form={settingsForm}
                setForm={setSettingsForm}
                busy={busy}
                onSave={saveSettings}
                onCopy={copyText}
                clashUrl={clashUrl}
                shadowrocketUrl={settings ? new URL(settings.shadowrocketSubscriptionUrl, window.location.origin).toString() : ""}
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function OverviewPage({ overview, trafficOption, logs }: { overview: Overview | null; trafficOption: Record<string, unknown>; logs: LogsResponse | null }) {
  if (!overview) return <FullScreenState icon={LoaderCircle} title="正在加载总览" spinning />;
  return (
    <div className="page-grid">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">CURRENT INSTRUMENT</span>
          <h1>{overview.activeNode?.label ?? "未检测到节点"}</h1>
          <p>
            {overview.activeNode?.address}:{overview.activeNode?.port} · {overview.activeNode?.scheme.toUpperCase()} · {overview.activeNode?.security.toUpperCase()}
          </p>
        </div>
        <div className="hero-board">
          <MetricCard title="下载" value={formatRate(overview.traffic.download_bps)} icon={Globe} />
          <MetricCard title="上传" value={formatRate(overview.traffic.upload_bps)} icon={Server} />
          <MetricCard title="错误数" value={String(overview.errorCount)} icon={TerminalSquare} />
        </div>
      </section>

      <section className="panel panel-sharp">
        <div className="panel-head">
          <h3>运行状态</h3>
        </div>
        <div className="stats-grid">
          <InfoRow label="Xray 状态" value={overview.serviceStatus.xray.status} />
          <InfoRow label="Argo 状态" value={overview.serviceStatus.argo.status} />
          <InfoRow label="Xray 自启" value={overview.autostart.xray ? "ON" : "OFF"} />
          <InfoRow label="Argo 自启" value={overview.autostart.argo ? "ON" : "OFF"} />
          <InfoRow label="节点数量" value={String(overview.nodeCount)} />
          <InfoRow label="收藏数量" value={String(overview.favoriteCount)} />
        </div>
      </section>

      <section className="panel panel-span-two panel-sharp">
        <div className="panel-head">
          <h3>流量走势</h3>
          <span className="subtle mono">24H / LIVE RATE</span>
        </div>
        <ReactECharts option={trafficOption} style={{ height: 330 }} />
      </section>

      <section className="panel panel-span-three panel-sharp">
        <div className="panel-head">
          <h3>最新日志</h3>
        </div>
        <div className="log-pane compact">
          {(logs?.entries ?? []).slice(0, 14).map((entry, index) => (
            <div key={`${entry.ts}-${index}`} className="log-line">
              <span className="log-source">{entry.source ?? entry.action ?? "LOG"}</span>
              <code>{entry.line ?? entry.message}</code>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function NodesPage({
  nodes,
  busy,
  latencyMap,
  editingNodeId,
  renameDraft,
  setEditingNodeId,
  setRenameDraft,
  onSwitch,
  onFavorite,
  onRename,
  onRefreshLatency,
  onCopy,
  onDownloadQr,
}: {
  nodes: NodeItem[];
  busy: string;
  latencyMap: Record<string, { ok: boolean; median_ms?: number; message?: string }>;
  editingNodeId: string;
  renameDraft: string;
  setEditingNodeId: (value: string) => void;
  setRenameDraft: (value: string) => void;
  onSwitch: (nodeId: string) => Promise<void>;
  onFavorite: (nodeId: string, favorite: boolean) => Promise<void>;
  onRename: (nodeId: string) => Promise<void>;
  onRefreshLatency: () => Promise<void>;
  onCopy: (value: string, message: string) => Promise<void>;
  onDownloadQr: (node: NodeItem) => Promise<void>;
}) {
  const sortedNodes = [...nodes].sort((a, b) => {
    if (a.active !== b.active) return a.active ? -1 : 1;
    if (a.favorite !== b.favorite) return a.favorite ? -1 : 1;
    const aLatency = latencyMap[a.id]?.median_ms;
    const bLatency = latencyMap[b.id]?.median_ms;
    if (typeof aLatency === "number" && typeof bLatency === "number") return aLatency - bLatency;
    if (typeof aLatency === "number") return -1;
    if (typeof bLatency === "number") return 1;
    return a.label.localeCompare(b.label, "zh-CN");
  });

  return (
    <div className="page-grid single-column">
      <section className="panel panel-sharp">
        <div className="panel-head">
          <h3>节点矩阵</h3>
          <div className="filters">
            <span className="subtle mono">SWITCH / RENAME / FAVORITE / SHARE</span>
            <button type="button" className="ghost-button" disabled={busy === "latency-map"} onClick={() => void onRefreshLatency()}>
              <Radar size={15} />
              {busy === "latency-map" ? "测速中..." : "全测速"}
            </button>
          </div>
        </div>
        <div className="node-list stock-list">
          {sortedNodes.map((node) => (
            <article key={node.id} className={`node-row ${node.active ? "active" : ""}`}>
              <div className="node-main">
                <div className="node-title">
                  {editingNodeId === node.id ? (
                    <div className="rename-box">
                      <input value={renameDraft} onChange={(event) => setRenameDraft(event.target.value)} maxLength={24} />
                      <button type="button" className="accent-button compact" disabled={busy === `rename-${node.id}`} onClick={() => void onRename(node.id)}>
                        {busy === `rename-${node.id}` ? "保存中..." : "保存"}
                      </button>
                      <button type="button" className="ghost-button compact" onClick={() => { setEditingNodeId(""); setRenameDraft(""); }}>
                        取消
                      </button>
                    </div>
                  ) : (
                    <strong>{node.label}</strong>
                  )}
                  {node.active ? <span className="tag active">当前</span> : null}
                  {node.favorite ? <span className="tag">收藏</span> : null}
                </div>
                <p>
                  {node.address}:{node.port} · {node.network} · {node.security} · {node.host || "直连"}
                </p>
                <div className="latency-inline">
                  {latencyMap[node.id]?.ok ? (
                    <span className={`latency-pill ${latencyTone(latencyMap[node.id].median_ms)}`}>{latencyMap[node.id].median_ms} ms</span>
                  ) : (
                    <span className="latency-pill muted">{latencyMap[node.id]?.message || "未测"}</span>
                  )}
                </div>
              </div>
              <div className="node-actions">
                <button type="button" className="ghost-button" onClick={() => void onFavorite(node.id, !node.favorite)}>
                  <Heart size={15} />
                  {node.favorite ? "取消收藏" : "收藏"}
                </button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setEditingNodeId(node.id);
                    setRenameDraft(node.label);
                  }}
                >
                  <Edit3 size={15} />改名
                </button>
                <button type="button" className="ghost-button" onClick={() => void onCopy(node.raw_link, "导入串已复制")}>
                  <Copy size={15} />复制
                </button>
                <button type="button" className="ghost-button" onClick={() => void onDownloadQr(node)}>
                  <QrCode size={15} />二维码
                </button>
                <button type="button" className="accent-button" disabled={busy === `node-${node.id}` || node.active} onClick={() => void onSwitch(node.id)}>
                  {busy === `node-${node.id}` ? "切换中..." : "切换"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function TrafficPage({ nodes, traffic, trafficOption, trafficRange, trafficNodeId, trafficService, setTrafficRange, setTrafficNodeId, setTrafficService }: { nodes: NodeItem[]; traffic: TrafficResponse | null; trafficOption: Record<string, unknown>; trafficRange: string; trafficNodeId: string; trafficService: string; setTrafficRange: (value: string) => void; setTrafficNodeId: (value: string) => void; setTrafficService: (value: string) => void; }) {
  return (
    <div className="page-grid single-column">
      <section className="panel panel-sharp">
        <div className="panel-head">
          <h3>流量看板</h3>
          <div className="filters">
            <select value={trafficRange} onChange={(event) => setTrafficRange(event.target.value)}>
              <option value="1h">近 1 小时</option>
              <option value="6h">近 6 小时</option>
              <option value="24h">近 24 小时</option>
              <option value="7d">近 7 天</option>
            </select>
            <select value={trafficNodeId} onChange={(event) => setTrafficNodeId(event.target.value)}>
              <option value="">全部节点</option>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>{node.label}</option>
              ))}
            </select>
            <select value={trafficService} onChange={(event) => setTrafficService(event.target.value)}>
              <option value="all">全部服务</option>
              {(traffic?.services ?? ["stack"]).map((service) => (
                <option key={service} value={service}>{service}</option>
              ))}
            </select>
          </div>
        </div>
        <ReactECharts option={trafficOption} style={{ height: 420 }} />
      </section>
    </div>
  );
}

function ControlPage({ overview, busy, onAction }: { overview: Overview | null; busy: string; onAction: (action: string, target: string, dangerous?: boolean) => Promise<void>; }) {
  return (
    <div className="page-grid">
      <section className="panel panel-sharp">
        <div className="panel-head"><h3>服务控制</h3></div>
        <ControlGroup title="Xray" description={overview?.serviceStatus.xray.uptime || "读取中"} busy={busy} target="xray" onAction={onAction} />
        <ControlGroup title="Argo" description={overview?.serviceStatus.argo.uptime || "读取中"} busy={busy} target="argo" onAction={onAction} />
      </section>

      <section className="panel panel-sharp">
        <div className="panel-head"><h3>栈级动作</h3></div>
        <div className="action-grid">
          <ActionButton busy={busy === "restart-stack"} label="重启整套栈" accent onClick={() => void onAction("restart", "stack", true)} />
          <ActionButton busy={busy === "refresh-nodes"} label="刷新节点列表" onClick={() => void onAction("refresh", "nodes")} />
          <ActionButton busy={busy === "enable_autostart-xray"} label="启用 Xray 自启" onClick={() => void onAction("enable_autostart", "xray", true)} />
          <ActionButton busy={busy === "disable_autostart-xray"} label="关闭 Xray 自启" onClick={() => void onAction("disable_autostart", "xray", true)} />
          <ActionButton busy={busy === "enable_autostart-argo"} label="启用 Argo 自启" onClick={() => void onAction("enable_autostart", "argo", true)} />
          <ActionButton busy={busy === "disable_autostart-argo"} label="关闭 Argo 自启" onClick={() => void onAction("disable_autostart", "argo", true)} />
        </div>
      </section>
    </div>
  );
}

function DiagnosticsPage({
  overview,
  logs,
  busy,
  logSource,
  setLogSource,
  logQuery,
  setLogQuery,
  onSearchLogs,
  onDiagnostic,
  diagResult,
  siteLatency,
  onRefreshSiteLatency,
}: {
  overview: Overview | null;
  logs: LogsResponse | null;
  busy: string;
  logSource: string;
  setLogSource: (value: string) => void;
  logQuery: string;
  setLogQuery: (value: string) => void;
  onSearchLogs: () => void;
  onDiagnostic: (kind: "latency" | "dns" | "config") => Promise<void>;
  diagResult: Record<string, unknown> | null;
  siteLatency: Array<{ name: string; host: string; ip: string; dns_ms?: number | null; tcp_ms?: number | null; tls_ms?: number | null; total_ms?: number | null; ok: boolean; message?: string }>;
  onRefreshSiteLatency: () => Promise<void>;
}) {
  const latencyMedian = typeof diagResult?.median_ms === "number" ? `${diagResult.median_ms} ms` : null;
  const latencySamples = Array.isArray(diagResult?.samples) ? (diagResult.samples as number[]) : [];
  const dnsRecords = Array.isArray(diagResult?.address_records) ? (diagResult.address_records as string[]) : [];
  const sniRecords = Array.isArray(diagResult?.sni_records) ? (diagResult.sni_records as string[]) : [];
  const validateOutput = typeof diagResult?.output === "string" ? diagResult.output : "";

  return (
    <div className="page-grid">
      <section className="panel panel-sharp">
        <div className="panel-head">
          <h3>诊断动作</h3>
          <span className="subtle mono">{overview?.activeNode?.label ?? "未选中节点"}</span>
        </div>
        <div className="action-grid">
          <ActionButton busy={busy === "diag-latency"} label="延迟测试" onClick={() => void onDiagnostic("latency")} />
          <ActionButton busy={busy === "diag-dns"} label="DNS 检查" onClick={() => void onDiagnostic("dns")} />
          <ActionButton busy={busy === "diag-config"} label="配置校验" onClick={() => void onDiagnostic("config")} />
        </div>
        <div className="diag-panel">
          {latencyMedian ? (
            <div className="diag-metric">
              <span>中位延迟</span>
              <strong>{latencyMedian}</strong>
              <div className="diag-chip-row">
                {latencySamples.map((item, index) => (
                  <span key={`${item}-${index}`} className="diag-chip">
                    #{index + 1} {item} ms
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {dnsRecords.length ? (
            <div className="diag-metric">
              <span>解析结果</span>
              <strong>{dnsRecords.length} 条 A 记录</strong>
              <div className="diag-list">
                {dnsRecords.map((record) => (
                  <code key={record}>{record}</code>
                ))}
                {sniRecords.map((record) => (
                  <code key={`sni-${record}`}>SNI {record}</code>
                ))}
              </div>
            </div>
          ) : null}
          {validateOutput ? <pre className="diag-output">{validateOutput}</pre> : null}
          {!diagResult ? <pre className="diag-output">这里会显示诊断结果</pre> : null}
        </div>
      </section>

      <section className="panel panel-span-two panel-sharp">
        <div className="panel-head">
          <h3>主流站点延迟</h3>
            <button type="button" className="ghost-button" disabled={busy === "site-latency"} onClick={() => void onRefreshSiteLatency()}>
            <Globe size={15} />
            {busy === "site-latency" ? "测速中..." : "站点测速"}
          </button>
        </div>
        <div className="site-grid">
          {siteLatency.map((item) => (
            <div key={item.host} className="site-card">
              <div className="site-card-head">
                <strong>{item.name}</strong>
                <span className={`site-status ${item.ok ? "ok" : "fail"}`}>{item.ok ? `${item.total_ms} ms` : "FAIL"}</span>
              </div>
              <p>{item.host}</p>
              <div className="site-meta">
                <span>DNS {item.dns_ms ?? "-"}</span>
                <span>TCP {item.tcp_ms ?? "-"}</span>
                <span>TLS {item.tls_ms ?? "-"}</span>
              </div>
              {!item.ok && item.message ? <code>{item.message}</code> : null}
            </div>
          ))}
          {!siteLatency.length ? <div className="site-card empty">点击“站点测速”后这里会显示 OpenAI、Claude、X、YouTube 等站点延迟</div> : null}
        </div>
      </section>

      <section className="panel panel-span-two panel-sharp">
        <div className="panel-head">
          <h3>日志搜索</h3>
          <div className="filters">
            <select value={logSource} onChange={(event) => setLogSource(event.target.value)}>
              <option value="combined">组合日志</option>
              <option value="xray">Xray</option>
              <option value="argo">Argo</option>
              <option value="audit">审计</option>
            </select>
            <input value={logQuery} onChange={(event) => setLogQuery(event.target.value)} placeholder="按关键字搜索" />
            <button type="button" className="ghost-button" onClick={onSearchLogs}><Logs size={15} />搜索</button>
          </div>
        </div>
        <div className="log-pane">
          {(logs?.entries ?? []).map((entry, index) => (
            <div key={`${entry.ts}-${index}`} className="log-line">
              <span className="log-source">{entry.source ?? entry.action ?? entry.level ?? "LOG"}</span>
              <code>{entry.line ?? entry.message}</code>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function SettingsPage({ settings, form, setForm, busy, onSave, onCopy, clashUrl, shadowrocketUrl }: { settings: SettingsResponse | null; form: { ipWhitelist: string; password: string }; setForm: (value: { ipWhitelist: string; password: string }) => void; busy: string; onSave: (event: React.FormEvent) => Promise<void>; onCopy: (value: string, message: string) => Promise<void>; clashUrl: string; shadowrocketUrl: string; }) {
  const [clashTab, setClashTab] = useState<"link" | "qr">("link");
  const [shadowrocketTab, setShadowrocketTab] = useState<"link" | "qr">("link");
  const [clashQr, setClashQr] = useState("");
  const [shadowrocketQr, setShadowrocketQr] = useState("");

  useEffect(() => {
    if (clashTab === "qr" && clashUrl) {
      void QRCode.toDataURL(clashUrl, {
        margin: 1,
        width: 360,
        color: { dark: "#ff584c", light: "#050608" },
      }).then(setClashQr);
    }
  }, [clashTab, clashUrl]);

  useEffect(() => {
    if (shadowrocketTab === "qr" && shadowrocketUrl) {
      void QRCode.toDataURL(shadowrocketUrl, {
        margin: 1,
        width: 360,
        color: { dark: "#ff584c", light: "#050608" },
      }).then(setShadowrocketQr);
    }
  }, [shadowrocketTab, shadowrocketUrl]);

  return (
    <div className="page-grid">
      <section className="panel panel-sharp">
        <div className="panel-head"><h3>访问控制</h3></div>
        <form className="settings-form" onSubmit={onSave}>
          <label>
            <span>IP 白名单</span>
            <textarea rows={5} value={form.ipWhitelist} onChange={(event) => setForm({ ...form, ipWhitelist: event.target.value })} placeholder="留空表示允许任意来源连接" />
          </label>
          <label>
            <span>更新管理员口令</span>
            <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="留空则不修改" />
          </label>
          <button className="accent-button" type="submit" disabled={busy === "settings"}>{busy === "settings" ? "保存中..." : "保存设置"}</button>
        </form>
      </section>

      <section className="panel panel-sharp">
        <div className="panel-head"><h3>Clash 订阅</h3></div>
        <div className="subscription-card">
          <p>支持 Mihomo / Clash Meta 直接拉取订阅。</p>
          <div className="tab-strip">
            <button type="button" className={clashTab === "link" ? "tab-button active" : "tab-button"} onClick={() => setClashTab("link")}>订阅链接</button>
            <button type="button" className={clashTab === "qr" ? "tab-button active" : "tab-button"} onClick={() => setClashTab("qr")}>订阅二维码</button>
          </div>
          {clashTab === "link" ? (
            <>
              <div className="subscription-url">{clashUrl || "暂未生成"}</div>
              <div className="action-grid single-line">
                <button type="button" className="accent-button" disabled={!clashUrl} onClick={() => void onCopy(clashUrl, "Clash 订阅地址已复制")}><LinkIcon size={15} />复制订阅链接</button>
              </div>
            </>
          ) : (
            <div className="subscription-qr-wrap">{clashQr ? <img className="subscription-qr" src={clashQr} alt="Clash 订阅二维码" /> : <div className="subscription-url">生成中...</div>}</div>
          )}
        </div>
      </section>

      <section className="panel panel-sharp">
        <div className="panel-head"><h3>Shadowrocket 订阅</h3></div>
        <div className="subscription-card">
          <p>输出 Base64 URI 列表，适合 Shadowrocket 直接导入，也能兼容部分通用订阅客户端。</p>
          <p>{settings?.shadowrocketHint || "Shadowrocket 专用兼容节点状态未知"}</p>
          <div className="tab-strip">
            <button type="button" className={shadowrocketTab === "link" ? "tab-button active" : "tab-button"} onClick={() => setShadowrocketTab("link")}>订阅链接</button>
            <button type="button" className={shadowrocketTab === "qr" ? "tab-button active" : "tab-button"} onClick={() => setShadowrocketTab("qr")}>订阅二维码</button>
          </div>
          {shadowrocketTab === "link" ? (
            <>
              <div className="subscription-url">{shadowrocketUrl || "暂未生成"}</div>
              <div className="action-grid single-line">
                <button type="button" className="accent-button" disabled={!shadowrocketUrl} onClick={() => void onCopy(shadowrocketUrl, "Shadowrocket 订阅地址已复制")}><LinkIcon size={15} />复制订阅链接</button>
              </div>
            </>
          ) : (
            <div className="subscription-qr-wrap">{shadowrocketQr ? <img className="subscription-qr" src={shadowrocketQr} alt="Shadowrocket 订阅二维码" /> : <div className="subscription-url">生成中...</div>}</div>
          )}
        </div>
      </section>

      <section className="panel panel-span-three panel-sharp">
        <div className="panel-head">
          <h3>审计日志</h3>
          <span className="subtle mono">{settings?.bindHost}:{settings?.bindPort}</span>
        </div>
        <div className="log-pane">
          {(settings?.auditLogs ?? []).map((entry, index) => (
            <div key={`${entry.ts}-${index}`} className="log-line">
              <span className="log-source">{entry.level ?? "info"}</span>
              <code>{entry.message ?? entry.line}</code>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function FullScreenState({ icon: Icon, title, spinning = false }: { icon: typeof LoaderCircle; title: string; spinning?: boolean; }) {
  return (
    <div className="login-shell">
      <div className="login-card centered">
        <Icon className={spinning ? "spin" : ""} />
        <h2>{title}</h2>
      </div>
    </div>
  );
}

function MetricCard({ title, value, icon: Icon }: { title: string; value: string; icon: typeof Globe }) {
  return (
    <div className="metric-card">
      <div className="metric-title"><Icon size={15} /><span>{title}</span></div>
      <strong>{value}</strong>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ label, active }: { label: string; active: boolean }) {
  return <span className={`status-pill ${active ? "online" : "offline"}`}><Wifi size={14} />{label}</span>;
}

function TapeCard({ title, value, tone }: { title: string; value: string; tone: "good" | "bad" | "info" | "neutral" }) {
  return (
    <div className={`tape-card ${tone}`}>
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ActionButton({ label, onClick, busy, accent = false }: { label: string; onClick: () => void; busy: boolean; accent?: boolean; }) {
  return <button type="button" className={accent ? "accent-button" : "ghost-button"} disabled={busy} onClick={onClick}>{busy ? "执行中..." : label}</button>;
}

function ControlGroup({ title, description, target, busy, onAction }: { title: string; description: string; target: string; busy: string; onAction: (action: string, target: string, dangerous?: boolean) => Promise<void>; }) {
  return (
    <div className="control-group">
      <div>
        <h4>{title}</h4>
        <p>{description || "暂无运行时间"}</p>
      </div>
      <div className="action-grid">
        <ActionButton busy={busy === `start-${target}`} label="启动" onClick={() => void onAction("start", target, true)} />
        <ActionButton busy={busy === `stop-${target}`} label="停止" onClick={() => void onAction("stop", target, true)} />
        <ActionButton busy={busy === `restart-${target}`} label="重启" accent onClick={() => void onAction("restart", target, true)} />
        {target === "xray" ? <ActionButton busy={busy === `reload-${target}`} label="重载配置" onClick={() => void onAction("reload", target)} /> : null}
      </div>
    </div>
  );
}

function formatRate(value: number) {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB/s`;
  if (value >= 1024) return `${(value / 1024).toFixed(2)} KB/s`;
  return `${value.toFixed(2)} B/s`;
}

function latencyTone(value?: number) {
  if (typeof value !== "number") return "muted";
  if (value <= 120) return "good";
  if (value <= 350) return "warn";
  return "fail";
}

export default App;
