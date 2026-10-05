# OpenAI Secure MCP Tunnel Setup v0.1

## Current state

Tunnel and native ChatGPT MCP proof are operational; the Gateway MCP listener remains localhost-only and the tunnel remains outbound-only.

The Gateway MCP facade is now a persistent system service:

- Service: `context-gateway-mcp.service`
- Listener: `127.0.0.1:8766/mcp`
- Network exposure: localhost only
- MCP transport: Streamable HTTP
- Identity probe: `context_host_identity_probe`

OpenAI `tunnel-client` v0.0.15 is installed at:

`/home/hermes/.local/bin/tunnel-client`

The release ZIP was SHA-256 verified before installation.

## Secure path

```text
ChatGPT / supported OpenAI product
        |
        | OpenAI-hosted MCP tunnel endpoint
        v
OpenAI tunnel control plane
        ^
        | outbound HTTPS only
        |
tunnel-client on hermes-vm
        |
        | localhost
        v
Universal Context Gateway MCP
127.0.0.1:8766/mcp
```

No public inbound MCP port is required. OpenAI documents Secure MCP Tunnel specifically for private/on-premises/local MCP servers. The client polls the OpenAI control plane over outbound HTTPS and forwards MCP requests to the private server. citeturn434516search0

## Required user-owned platform values

The tunnel runtime values are configured in the local secret file. The restricted runtime key is used by the daemon; no admin key is stored there.

OpenAI documents that the tunnel ID comes from Platform Tunnels and the runtime key should have Tunnels Read + Use. An admin key is only needed for tunnel CRUD. citeturn312767search0turn312767search4

Do not put an admin key into the long-running daemon.

## Local secret file

Create:

`/home/hermes/.config/tunnel-client/context-gateway.env`

with mode `600`:

```text
CONTROL_PLANE_TUNNEL_ID=tunnel_<32 lowercase hex characters>
CONTROL_PLANE_API_KEY=<restricted runtime key>
MCP_SERVER_URL=http://127.0.0.1:8766/mcp
```

An example template is present beside this runbook as:

`/home/hermes/.config/tunnel-client/context-gateway.env.example`

The systemd unit is already installed and enabled:

`openai-context-tunnel.service`

The service is enabled and running. The local secret file remains mode 600 and is excluded from version control.

For the environment-variable path, the supported runtime requirements are the tunnel ID, runtime API key, and MCP server URL. citeturn312767search0

## ChatGPT availability constraint

OpenAI currently documents custom MCP connectivity for Pro in developer mode with read/fetch permissions, while full MCP is currently rolling out for Business and Enterprise/Edu. The documentation does not state that ChatGPT Go has this custom-MCP capability. Therefore the tunnel can be prepared independently, but native ChatGPT Level-1 identity proof is still conditional on the user's actual ChatGPT surface exposing custom MCP developer mode. citeturn434516search1turn434516search2

## Verified proof

The native ChatGPT custom MCP path has been exercised successfully: host metadata reached the Gateway, the host session was bound to a canonical conversation, exact snapshot retrieval was verified, and the hardened worker handoff completed a golden E2E. Raw host identity and handoff bearer values are not returned to the model.

## Lifecycle follow-up

A second independent thread fingerprint remains a characterization test rather than a prerequisite for the already-proven single-thread binding path. Cross-thread/session lifecycle behavior is tracked separately from the transport proof.
