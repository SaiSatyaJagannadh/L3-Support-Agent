import { useState } from "react";
import { Button, Input, Card, Text, Badge, Textarea } from "@fluentui/react-components";
import type { PublicClientApplication } from "@azure/msal-browser";

type Msg = { who: "user" | "bot"; text: string; cites?: { id: string; source: string; url: string }[] };
type Draft = { draft: { short: string; body: string }; similar: { number: string; state: string; text: string }[] };

export default function App({ msal }: { msal: PublicClientApplication | null }) {
  const [thread, setThread] = useState(""); const [msgs, setMsgs] = useState<Msg[]>([]); const [input, setInput] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null); const [extra, setExtra] = useState("");
  const add = (m: Msg) => setMsgs(x => [...x, m]);
  async function post(url: string, body: object) {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (msal) {
      let acc = msal.getAllAccounts()[0]; if (!acc) acc = (await msal.loginPopup({ scopes: ["openid"] })).account;
      const t = await msal.acquireTokenSilent({ scopes: [`api://${import.meta.env.VITE_AAD_CLIENT_ID}/.default`], account: acc });
      headers.Authorization = `Bearer ${t.accessToken}`;
    }
    const r = await (await fetch(url, { method: "POST", headers, body: JSON.stringify(body) })).json();
    setThread(r.thread);
    if (r.status === "needs_approval") setDraft(r); else { setDraft(null); add({ who: "bot", text: r.reply, cites: r.citations }); }
  }
  const send = () => { if (!input) return; add({ who: "user", text: input }); post("/chat", { thread, message: input }); setInput(""); };
  const confirm = (decision: string, inc = "") => post("/confirm", { thread, decision, inc });
  const showTickets = async () => add({ who: "bot", text: (await (await fetch("/tickets")).json()).map((t: any) => `${t.number} ${t.group}`).join(" | ") || "No tickets" });
  return (
    <div style={{ maxWidth: 680, margin: "24px auto", display: "grid", gap: 12 }}>
      <Text size={600} weight="semibold">L3 Support Agent</Text>
      {msgs.map((m, i) => <Card key={i}><Text>{m.who === "user" ? "🧑 " : "🤖 "}{m.text}</Text>{m.cites?.map(c => <Badge key={c.id} appearance="outline">{c.source}</Badge>)}</Card>)}
      {draft && <Card><Text weight="semibold">Draft ticket: {draft.draft.short}</Text>
        <Textarea value={draft.draft.body + (extra ? "\n" + extra : "")} readOnly />
        {draft.similar.map(t => <Button key={t.number} onClick={() => confirm("link", t.number)}>Same as {t.number} ({t.state})</Button>)}
        <div><Button appearance="primary" onClick={() => confirm("create")}>Submit</Button> <Button onClick={() => confirm("cancel")}>Cancel</Button></div></Card>}
      <Input value={input} onChange={(_, d) => setInput(d.value)} onKeyDown={e => e.key === "Enter" && send()} placeholder="Describe the issue" />
      <div><Button appearance="primary" onClick={send}>Send</Button> <Button onClick={() => post("/chat", { thread, action: "not_solved" })}>Still stuck? Raise a ticket</Button>
        <Button onClick={() => fetch("/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ thread, rating: 1 }) })}>👍</Button>
        <Button onClick={showTickets}>My tickets</Button></div>
    </div>);
}
