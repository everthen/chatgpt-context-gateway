# OpenAI Secure MCP Tunnel Setup v0.1

## Current state

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

The machine currently has none of these values configured:

- `CONTROL_PLANE_TUNNEL_ID`
- `CONTROL_PLANE_API_KEY`

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

It remains inactive until the secret file exists. Once populated, run:

```bash
systemctl start openai-context-tunnel.service
tunnel-client doctor --profile <profile> --explain
```

For the environment-variable path, the supported runtime requirements are the tunnel ID, runtime API key, and MCP server URL. citeturn312767search0

## ChatGPT availability constraint

OpenAI currently documents custom MCP connectivity for Pro in developer mode with read/fetch permissions, while full MCP is currently rolling out for Business and Enterprise/Edu. The documentation does not state that ChatGPT Go has this custom-MCP capability. Therefore the tunnel can be prepared independently, but native ChatGPT Level-1 identity proof is still conditional on the user's actual ChatGPT surface exposing custom MCP developer mode. citeturn434516search1turn434516search2

## Next proof

After the tunnel is authenticated and healthy:

1. Attach the tunnel to a supported ChatGPT custom app.
2. Call `context_host_identity_probe` in one ChatGPT thread twice.
3. Reload the same thread and call again.
4. Create a second ChatGPT thread and call again.
5. Compare only the returned fingerprints; the raw host identity must never be exposed.

Do not create `openai/session -> conversation_uid` binding until this native behavior is observed.
