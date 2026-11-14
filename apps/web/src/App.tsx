import { useEffect, useRef, useState } from "react";
import { Button, Input, Card, Text, Badge, Textarea, Spinner, TabList, Tab, MessageBar, MessageBarBody } from "@fluentui/react-components";
import type { PublicClientApplication } from "@azure/msal-browser";

type Cite = { id: string; source: string; url: string };
type Msg = { id: number; who: "user" | "bot"; text: string; cites?: Cite[]; rated?: 1 | -1; ticket?: string };
type Draft = { draft: { short: string; body: string }; similar: { number: string; state: string; text: string }[] };
type Meta = { thread: string; status: string; citations?: Cite[]; ticket?: string } & Partial<Draft>;

const APPS = ["payflow", "wealthplan", "branchdesk"], ENVS = ["prod", "uat", "dev"];
let nextId = 1;

export default function App({ msal }: { msal: PublicClientApplication | null }) {
  const [thread, setThread] = useState(""); const [msgs, setMsgs] = useState<Msg[]>([]); const [input, setInput] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null); const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(""); const [tab, setTab] = useState("chat");
  const [tickets, setTickets] = useState<any[]>([]); const [admin, setAdmin] = useState<any>(null); const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, draft, busy]);

  async function headers() {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (msal) {
      let acc = msal.getAllAccounts()[0]; if (!acc) acc = (await msal.loginPopup({ scopes: ["openid"] })).account;
      const t = await msal.acquireTokenSilent({ scopes: [`api://${import.meta.env.VITE_AAD_CLIENT_ID}/.default`], account: acc });
      h.Authorization = `Bearer ${t.accessToken}`;
    }
    return h;
  }

  // Streams /chat/stream (SSE): "meta" event first, then "token" events appended word by word.
  async function stream(body: object) {
    setBusy(true); setErr(""); setDraft(null);
    const id = nextId++; let started = false;
    try {
      const res = await fetch("/chat/stream", { method: "POST", headers: await headers(), body: JSON.stringify(body) });
      if (!res.ok || !res.body) throw new Error(`API ${res.status}`);
      const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { done, value } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i; while ((i = buf.indexOf("\n\n")) >= 0) {
          const [ev, data] = buf.slice(0, i).split("\n").map(l => l.replace(/^(event|data): /, "")); buf = buf.slice(i + 2);
          if (ev === "meta") {
            const m: Meta = JSON.parse(data); setThread(m.thread); setStatus(m.status);
            if (m.status === "needs_approval") setDraft({ draft: m.draft!, similar: m.similar ?? [] });
            else { started = true; setMsgs(x => [...x, { id, who: "bot", text: "", cites: m.citations, ticket: m.ticket ?? undefined }]); }
          } else if (ev === "token" && started) {
            const w = JSON.parse(data) as string; setMsgs(x => x.map(m => m.id === id ? { ...m, text: m.text + w } : m));
          }
        }
        await new Promise(r => setTimeout(r, 15));   // let the typing effect show for short replies
      }
    } catch (e: any) { setErr(e.message ?? String(e)); } finally { setBusy(false); }
  }

  const say = (text: string) => { if (!text.trim() || busy) return; setMsgs(x => [...x, { id: nextId++, who: "user", text }]); setInput(""); stream({ thread, message: text }); };
  const stuck = () => stream({ thread, action: "not_solved" });

  async function confirm(decision: string, inc = "") {
    setBusy(true); setErr("");
    try {
      const r = await (await fetch("/confirm", { method: "POST", headers: await headers(), body: JSON.stringify({ thread, decision, inc }) })).json();
      setDraft(null); setStatus(r.status); setMsgs(x => [...x, { id: nextId++, who: "bot", text: r.reply, ticket: r.ticket ?? undefined }]);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  async function rate(id: number, rating: 1 | -1) {
    setMsgs(x => x.map(m => m.id === id ? { ...m, rated: rating } : m));
    await fetch("/feedback", { method: "POST", headers: await headers(), body: JSON.stringify({ thread, rating }) });
  }
  async function load(t: string) {
    setTab(t); setErr("");
    try {
      if (t === "tickets") setTickets(await (await fetch("/tickets")).json());
      if (t === "admin") { const r = await fetch("/admin/summary", { headers: { "X-User-Roles": "L3.Admin", ...(await headers()) } }); setAdmin(r.ok ? await r.json() : { error: `HTTP ${r.status}` }); }
    } catch (e: any) { setErr(e.message); }
  }
  const reset = () => { setThread(""); setMsgs([]); setDraft(null); setStatus(""); setErr(""); };
  const chips = status === "clarify" && !busy ? (/environment/i.test(msgs[msgs.length - 1]?.text ?? "") ? ENVS : APPS) : [];

  return (
    <div style={{ maxWidth: 720, margin: "16px auto", padding: "0 16px", display: "grid", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Text size={600} weight="semibold">L3 Support Agent</Text>
        <Button size="small" onClick={reset} data-testid="new-chat">New chat</Button>
      </div>
      <TabList selectedValue={tab} onTabSelect={(_, d) => load(d.value as string)}>
        <Tab value="chat">Chat</Tab><Tab value="tickets">My tickets</Tab><Tab value="admin">Admin</Tab>
      </TabList>
      {err && <MessageBar intent="error"><MessageBarBody>{err}</MessageBarBody></MessageBar>}

      {tab === "chat" && <>
        {msgs.length === 0 && <Card><Text>Describe your issue, or try an example:</Text>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {["PayFlow 504 timeout", "WealthPlan login loop after SSO", "BranchDesk attachment upload fails"].map(s => <Button key={s} size="small" onClick={() => say(s)}>{s}</Button>)}
          </div></Card>}
        {msgs.map(m => (
          <Card key={m.id} style={{ background: m.who === "user" ? "#eef4ff" : undefined }}>
            <Text>{m.who === "user" ? "🧑 " : "🤖 "}{m.text}</Text>
            {m.cites && m.cites.length > 0 && <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {m.cites.map(c => <a key={c.id} href={c.url} target="_blank" rel="noreferrer"><Badge appearance="outline">{c.source} · {c.id}</Badge></a>)}</div>}
            {m.ticket && <Badge color="success">{m.ticket}</Badge>}
            {m.who === "bot" && m.cites && m.cites.length > 0 && <div>
              <Button size="small" appearance={m.rated === 1 ? "primary" : "subtle"} onClick={() => rate(m.id, 1)} aria-label="helpful">👍</Button>
              <Button size="small" appearance={m.rated === -1 ? "primary" : "subtle"} onClick={() => rate(m.id, -1)} aria-label="not helpful">👎</Button></div>}
          </Card>))}
        {busy && !draft && <Spinner size="tiny" label="Thinking…" />}
        {chips.length > 0 && <div style={{ display: "flex", gap: 8 }}>{chips.map(c => <Button key={c} size="small" shape="circular" onClick={() => say(c)}>{c}</Button>)}</div>}
        {draft && <Card data-testid="draft">
          <Text weight="semibold">Draft ticket — review before submitting</Text>
          <Text>{draft.draft.short}</Text>
          <Textarea value={draft.draft.body} readOnly rows={6} />
          {draft.similar.length > 0 && <Text size={200}>Similar tickets (link instead of creating a duplicate):</Text>}
          {draft.similar.map(t => <Button key={t.number} onClick={() => confirm("link", t.number)}>Same as {t.number} ({t.state})</Button>)}
          <div style={{ display: "flex", gap: 8 }}>
            <Button appearance="primary" disabled={busy} onClick={() => confirm("create")}>Submit</Button>
            <Button disabled={busy} onClick={() => confirm("cancel")}>Cancel</Button></div></Card>}
        <div ref={end} />
        <div style={{ display: "flex", gap: 8 }}>
          <Input style={{ flex: 1 }} value={input} disabled={busy || !!draft} onChange={(_, d) => setInput(d.value)} onKeyDown={e => e.key === "Enter" && say(input)} placeholder="Describe the issue" />
          <Button appearance="primary" disabled={busy || !!draft} onClick={() => say(input)}>Send</Button>
        </div>
        <div><Button disabled={busy || !!draft || !thread} onClick={stuck}>Still stuck? Raise a ticket</Button></div>
      </>}

      {tab === "tickets" && (tickets.length === 0 ? <Card><Text>No tickets yet.</Text></Card> :
        tickets.map(t => <Card key={t.number}><Text weight="semibold">{t.number} <Badge>{t.state}</Badge></Text><Text>{t.short}</Text><Text size={200}>{t.group}</Text></Card>))}

      {tab === "admin" && <Card>{!admin ? <Spinner size="tiny" /> : admin.error ? <Text>{admin.error}</Text> : <>
        <Text weight="semibold">Eval gate: {admin.eval.passed ? "passed ✅" : "failed ❌"}</Text>
        <Text size={200}>recall@3 {admin.eval["recall@3"]} · citations {admin.eval.citation_accuracy} · routing {admin.eval.routing_accuracy} · adversarial {admin.eval.adversarial_pass}</Text>
        <Text>Tickets created: {admin.tickets}</Text>
        <Text>Feedback: {admin.feedback.map((f: number[]) => `${f[0] > 0 ? "👍" : "👎"} ${f[1]}`).join("  ") || "none"}</Text>
        <Text>Unanswered questions (KB gaps): {admin.unanswered.length ? admin.unanswered.join("; ") : "none"}</Text></>}</Card>}
    </div>);
}
