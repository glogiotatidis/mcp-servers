# Sklavenitis MCP Servers

A collection of MCP (Model Context Protocol) servers for Greek e-commerce platforms.

## MCP Servers

### [E-Fresh](./efresh-mcp-server/)

MCP server for [e-fresh.gr](https://www.e-fresh.gr), a Greek online grocery store.

**Features:**
- Product search by name or EAN/barcode
- Shopping cart management
- Order viewing and history
- Multi-language support (Greek/English)
- Automatic session management

See the [E-Fresh MCP Server README](./efresh-mcp-server/README.md) for installation and usage instructions.

## Project Structure

```
sklavenitis/
├── efresh-mcp-server/    # E-Fresh MCP server
│   ├── efresh_server/    # Server implementation
│   ├── pyproject.toml    # Python package configuration
│   └── README.md         # Detailed documentation
└── README.md             # This file
```

## Future Servers

This repository is designed to host multiple MCP servers for Greek e-commerce platforms. Additional servers will be added as they are developed.

## License

MIT License - See individual server directories for details.
