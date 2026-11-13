import React from "react"; import { createRoot } from "react-dom/client";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { PublicClientApplication } from "@azure/msal-browser"; import { MsalProvider } from "@azure/msal-react";
import App from "./App";
// MSAL sign-in is enabled when VITE_AAD_CLIENT_ID + VITE_AAD_TENANT_ID are set; otherwise dev mode (no auth).
const cid = import.meta.env.VITE_AAD_CLIENT_ID as string | undefined;
const msal = cid ? new PublicClientApplication({ auth: { clientId: cid, authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AAD_TENANT_ID}`, redirectUri: location.origin } }) : null;
const app = <FluentProvider theme={webLightTheme}><App msal={msal} /></FluentProvider>;
createRoot(document.getElementById("root")!).render(msal ? <MsalProvider instance={msal}>{app}</MsalProvider> : app);
